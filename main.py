import asyncio
import sys
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties # Для установки parse_mode по умолчанию
from aiogram.enums import ParseMode
from loguru import logger

from config import settings
from utils.logger import log # Импортируем настроенный логгер
from services.database import init_db
from bot.handlers import router as main_router # Импортируем роутер из handlers
from bot.middleware import AuthMiddleware # Импортируем middleware

async def main():
    # --- Initialization ---
    log.info("Initializing bot...")

    # Initialize database
    await init_db()

    # Initialize Bot
    # Устанавливаем MarkdownV2 как режим парсинга по умолчанию для удобства
    default_props = DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2)
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=default_props)

    # Initialize Dispatcher
    dp = Dispatcher()

    # --- Middleware ---
    # Регистрируем middleware авторизации ПЕРЕД хэндлерами
    # Он будет применяться ко всем апдейтам (сообщения, колбэки и т.д.)
    dp.update.outer_middleware(AuthMiddleware())
    log.info("Authorization middleware registered.")

    # --- Routers ---
    dp.include_router(main_router)
    log.info("Main router included.")

    # --- Start Polling ---
    log.info("Starting polling...")
    # Перед запуском удалим вебхук, если он был установлен
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        await dp.start_polling(bot)
    except Exception as e:
        log.critical(f"Critical error during polling: {e}")
        log.exception(e)
    finally:
        log.warning("Bot stopped.")
        await bot.session.close()


if __name__ == "__main__":
    # Проверка версии Python (опционально, но полезно)
    if sys.version_info < (3, 10): # aiogram 3 требует Python 3.8+, но мы указали 3.11
        log.error("Bot requires Python 3.10 or higher.")
        sys.exit(1)

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped manually.")
    except Exception as e:
         log.critical(f"Unhandled exception at top level: {e}")
         log.exception(e)