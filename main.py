# /home/telegram_gemini_bot/main.py

import asyncio
import sys
from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramUnauthorizedError, TelegramNetworkError # Добавим импорты ошибок
import google.generativeai as genai # <--- Добавим импорт genai
from loguru import logger

from config import settings
# Убедимся, что log настроен и импортируется правильно
if not hasattr(settings, 'LOGURU_CONFIGURED') or not settings.LOGURU_CONFIGURED:
    try:
        from utils.logger import setup_logging
        setup_logging()
        settings.LOGURU_CONFIGURED = True # Отмечаем, что настроили
    except ImportError:
         logger.warning("utils.logger not found, using basic loguru config.")
         logger.add(sys.stderr, level="INFO") # Базовый вывод в stderr
         settings.LOGURU_CONFIGURED = True


# Импортируем остальные компоненты
from services.database import init_db
from bot.handlers import router as main_router
from bot.middleware import AuthMiddleware


async def main():
    # --- Configuration Loading ---
    logger.info("Configuration loaded successfully.")

    # --- Google Generative AI Configuration ---
    try:
        if settings.GOOGLE_API_KEY:
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            logger.info("Google Generative AI configured successfully.")
        else:
            logger.warning("GOOGLE_API_KEY not found in settings. Google AI features may not work.")
    except Exception as e:
        logger.critical(f"Failed to configure Google Generative AI: {e}")
        logger.exception(e)
        # sys.exit(1) # Раскомментируйте, если Google AI критичен для запуска

    # --- Database Initialization ---
    logger.info("Initializing database...")
    try:
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        logger.exception(e)
        sys.exit(1) # База данных критична, выходим

    # --- Bot and Dispatcher Initialization ---
    logger.info("Initializing bot...")
    try:
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        await bot.get_me()
        logger.info("Bot instance created and token verified.")
    except TelegramUnauthorizedError:
        logger.critical("Invalid Telegram Bot Token. Please check your .env file.")
        sys.exit(1)
    except TelegramNetworkError as e:
        logger.error(f"Network error during bot initialization (get_me): {e}. Check connection.")
    except Exception as e:
        logger.critical(f"Failed to initialize bot: {e}")
        logger.exception(e)
        sys.exit(1)

    dp = Dispatcher()
    logger.info("Dispatcher instance created.")

    # --- Middleware ---
    dp.update.outer_middleware(AuthMiddleware())
    logger.info("Authorization middleware registered.")

    # --- Routers ---
    dp.include_router(main_router)
    logger.info("Main router included.")

    # --- Start Polling ---
    logger.info("Starting polling...")
    try:
        # Попытка удалить вебхук перед запуском
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted (if existed).")
        except TelegramUnauthorizedError:
             logger.error("Failed to delete webhook: Invalid Token.")
             sys.exit(1)
        except TelegramNetworkError as e:
             logger.warning(f"Network error deleting webhook: {e}. Continuing polling...")
        except Exception as e:
            logger.warning(f"Could not delete webhook: {e}. Continuing polling...")

        # Запуск поллинга
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    except TelegramUnauthorizedError:
         logger.critical("Bot token became invalid during polling.")
    except Exception as e:
        logger.critical(f"Critical error during polling: {e}")
        logger.exception(e)
    finally:
        logger.warning("Bot stopped polling.")
        # Корректное закрытие сессии бота
        try:
             if bot.session and not bot.session.closed:
                 await bot.session.close()
                 logger.info("Bot session closed.")
        except Exception as close_err:
             logger.error(f"Error closing bot session: {close_err}")


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        print("ERROR: Bot requires Python 3.10 or higher.", file=sys.stderr)
        sys.exit(1)

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
    except Exception as e:
         logger.critical(f"Unhandled exception at top level: {e}")
         logger.exception(e)
         sys.exit(1)