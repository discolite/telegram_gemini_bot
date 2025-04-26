# /home/telegram_gemini_bot/main.py

import asyncio
import signal
import sys
import google.generativeai as genai
from loguru import logger
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramForbiddenError,
    TelegramUnauthorizedError, # Добавлен импорт
)

# --- Configuration Loading and Logging Setup ---
try:
    from config import settings
    # Пытаемся настроить логгер из utils, если не получится - используем базовый
    if not getattr(settings, 'LOGURU_CONFIGURED', False):
        try:
            from utils.logger import setup_logging
            setup_logging()
            settings.LOGURU_CONFIGURED = True
            logger.info("Logger configured from utils.logger.")
        except ImportError:
            logger.warning("utils.logger not found, using basic loguru config.")
            logger.remove() # Удаляем стандартный обработчик, чтобы избежать дублирования
            logger.add(sys.stderr, level="INFO")
            log_file = getattr(settings, 'LOG_FILE', 'logs/bot.log') # Берем путь из настроек, если есть
            logger.add(log_file, rotation="10 MB", retention="7 days", level="DEBUG", encoding="utf-8")
            settings.LOGURU_CONFIGURED = True
        except Exception as log_e:
            logger.error(f"Failed to setup logger from utils.logger: {log_e}")
            logger.add(sys.stderr, level="INFO") # Fallback
            settings.LOGURU_CONFIGURED = True

except ImportError as e:
    logger.critical(f"Failed to import settings or logger: {e}. Ensure config/settings.py and utils/logger.py exist and are correct.")
    sys.exit(1)
except Exception as e:
    logger.critical(f"Unexpected error during initial import/setup: {e}")
    sys.exit(1)


# Импортируем остальные компоненты после настройки логгера
try:
    from services import database, gemini # Импортируем сервисы
    from bot.handlers import router as main_router
    from bot.middleware import AuthMiddleware
except ImportError as e:
    logger.critical(f"Failed to import core components (services, handlers, middleware): {e}")
    sys.exit(1)


# --- Function to Set Bot Commands ---
async def set_bot_commands(bot: Bot):
    """Устанавливает команды меню для бота."""
    commands_for_users = [
        BotCommand(command="start", description="🚀 Старт / Помощь"),
        BotCommand(command="weather", description="🌦️ Погода (напр. /weather Минск)"),
        BotCommand(command="mood", description="🎭 Сменить стиль общения"),
        BotCommand(command="toggle_speak", description="🔊 Вкл/Выкл озвучку"),
    ]
    admin_commands = commands_for_users + [
        BotCommand(command="admin", description="🛠️ Админ-панель"),
        BotCommand(command="status", description="📊 Статус сервиса"),
        BotCommand(command="restart", description="🔄 Перезапустить бота"),
    ]

    try:
        await bot.set_my_commands(commands=commands_for_users, scope=BotCommandScopeDefault())
        logger.info("Default bot commands set successfully.")

        admin_ids = getattr(settings, 'AUTHORIZED_USERS', [])
        if admin_ids and isinstance(admin_ids, (list, tuple)):
            successful_admins = 0
            for admin_id in admin_ids:
                try:
                    # Проверяем, что ID является числом
                    admin_id_int = int(admin_id)
                    await bot.set_my_commands(commands=admin_commands, scope=BotCommandScopeChat(chat_id=admin_id_int))
                    successful_admins += 1
                except ValueError:
                    logger.error(f"Invalid admin ID found in AUTHORIZED_USERS: {admin_id}. Skipping.")
                except TelegramForbiddenError:
                    logger.warning(f"Bot might be blocked by admin {admin_id}, cannot set commands for them.")
                except TelegramBadRequest as e:
                    # Может возникнуть, если чат с админом не был начат
                    logger.warning(f"Could not set commands for admin {admin_id} (maybe chat not started?): {e}")
                except Exception as admin_cmd_err:
                    logger.error(f"Failed to set admin commands for user {admin_id}: {admin_cmd_err}")
            if successful_admins > 0:
                logger.info(f"Admin commands set successfully for {successful_admins} admin(s).")
            if successful_admins < len(admin_ids):
                logger.warning(f"Could not set admin commands for {len(admin_ids) - successful_admins} admin(s). See previous logs.")
        elif not admin_ids:
             logger.info("No admin IDs found in settings.AUTHORIZED_USERS. Skipping admin-specific commands.")
        else:
             logger.error("settings.AUTHORIZED_USERS is defined but is not a list or tuple. Cannot set admin commands.")

    except TelegramNetworkError as e:
        logger.error(f"Network error setting bot commands: {e}. Continuing without setting commands.")
    except TelegramUnauthorizedError:
        logger.error("Invalid token when trying to set bot commands.") # Эта ошибка может быть критичной
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")

# --- Main Application Logic ---
async def main():
    logger.info("Starting bot application...")

    # --- Configuration Loading ---
    logger.info("Using loaded configuration from settings.")
    # Проверим наличие критичных переменных
    if not settings.TELEGRAM_BOT_TOKEN:
         logger.critical("TELEGRAM_BOT_TOKEN not found in settings. Exiting.")
         sys.exit(1)
    # GEMINI_API_KEY необязателен для запуска, но его отсутствие будет залогировано ниже

    # --- Google Generative AI Configuration ---
    try:
        # Используем правильное имя переменной из .env/settings.py
        if api_key := getattr(settings, 'GOOGLE_API_KEY', None): # Используем правильное имя из предыдущего лога
            genai.configure(api_key=api_key)
            logger.info("Google Generative AI configured successfully.")
            # Можно добавить тестовый вызов, если нужно убедиться в работоспособности ключа
            # list(genai.list_models()) # Например
        else:
            logger.warning("GOOGLE_API_KEY not found in settings. Google AI features may not work.")
    except Exception as e:
        logger.error(f"Failed to configure or verify Google Generative AI: {e}")
        # Не выходим, бот может работать и без Gemini (если логика это позволяет)

    # --- Database Initialization ---
    logger.info("Initializing database...")
    try:
        await database.init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        logger.exception(e)
        sys.exit(1) # База данных критична

    # --- Bot and Dispatcher Initialization ---
    logger.info("Initializing bot...")
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        user = await bot.get_me()
        logger.info(f"Bot instance created and token verified for bot ID {user.id} (@{user.username})")
    except TelegramUnauthorizedError:
        logger.critical("Invalid Telegram Bot Token. Please check your .env file.")
        sys.exit(1)
    except TelegramNetworkError as e:
        logger.error(f"Network error during bot initialization (get_me): {e}. Check connection.")
        # Если не удалось проверить токен из-за сети, можно продолжить, но с риском
    except Exception as e:
        logger.critical(f"Failed to initialize bot: {e}")
        logger.exception(e)
        sys.exit(1)

    # --- Set Bot Commands ---
    await set_bot_commands(bot) # Вызываем установку команд

    # --- Dispatcher Setup ---
    dp = Dispatcher()
    logger.info("Dispatcher instance created.")

    # --- Middleware ---
    # Проверяем, определены ли пользователи, прежде чем включать middleware
    if hasattr(settings, 'AUTHORIZED_USERS') and settings.AUTHORIZED_USERS:
         dp.update.outer_middleware(AuthMiddleware())
         logger.info("Authorization middleware registered.")
    else:
         logger.warning("AUTHORIZED_USERS not defined or empty in settings. AuthMiddleware is disabled.")

    # --- Routers ---
    dp.include_router(main_router)
    logger.info("Main router included.")

    # --- Start Polling ---
    logger.info("Starting polling...")
    session_closed_cleanly = False # Флаг для finally
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted (if existed).")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    except (KeyboardInterrupt, SystemExit):
        logger.warning("Bot stopped by user (Ctrl+C or SystemExit).")
    except TelegramUnauthorizedError:
         logger.critical("Bot token became invalid during polling.")
    except TelegramNetworkError as e:
        logger.critical(f"Critical network error during polling: {e}")
    except Exception as e:
        logger.critical(f"Critical error during polling: {e}")
        logger.exception(e)
    finally:
        logger.warning("Bot polling stopped.")
        # Корректное закрытие сессии бота
        try:
             # Проверяем, есть ли сессия и не закрыта ли она уже
             if bot.session and hasattr(bot.session, 'closed') and not await bot.session.closed():
                 await bot.session.close()
                 logger.info("Bot session closed.")
                 session_closed_cleanly = True
             elif bot.session and not hasattr(bot.session, 'closed'): # Для старых версий aiogram/aiohttp
                  await bot.session.close()
                  logger.info("Bot session closed (assumed mechanism).")
                  session_closed_cleanly = True
             elif not bot.session:
                  logger.warning("Bot session object does not exist.")
             else:
                  logger.info("Bot session was already closed.")
                  session_closed_cleanly = True # Считаем, что закрыта
        except Exception as close_err:
             logger.error(f"Error closing bot session: {close_err}")

        logger.info(f"Bot shutdown {'complete' if session_closed_cleanly else 'finished with potential issues'}.")

# --- Graceful Shutdown Handling ---
async def shutdown(sig: signal.Signals, loop: asyncio.AbstractEventLoop, bot: Bot):
    """Gracefully shutdown the bot on signal."""
    logger.warning(f"Received exit signal {sig.name}... Shutting down.")
    # Завершаем опрос (если он еще работает)
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    logger.info(f"Cancelling {len(tasks)} outstanding tasks...")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Tasks cancelled.")

    # Закрываем сессию бота
    if bot.session and hasattr(bot.session, 'closed') and not await bot.session.closed():
        await bot.session.close()
        logger.info("Bot session closed during shutdown.")
    elif bot.session and not hasattr(bot.session, 'closed'):
         await bot.session.close()
         logger.info("Bot session closed during shutdown (assumed mechanism).")

    loop.stop() # Останавливаем цикл событий

# --- Entry Point ---
if __name__ == "__main__":
    if sys.version_info < (3, 10):
        print("ERROR: Bot requires Python 3.10 or higher.", file=sys.stderr)
        sys.exit(1)

    # --- Настройка цикла событий и обработчиков сигналов ---
    # Используем try..except для совместимости с Windows, где add_signal_handler нет
    try:
        loop = asyncio.get_event_loop()

        # Создаем временный объект бота ТОЛЬКО для передачи в shutdown
        temp_bot_for_shutdown = Bot(token=settings.TELEGRAM_BOT_TOKEN)

        signals_to_handle = (signal.SIGINT, signal.SIGTERM) # SIGINT (Ctrl+C), SIGTERM
        for s in signals_to_handle:
            loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(shutdown(s, loop, temp_bot_for_shutdown))
            )
        logger.info(f"Registered signal handlers for {', '.join(s.name for s in signals_to_handle)}")
    except NotImplementedError: # Для Windows
        logger.warning("Signal handlers are not fully supported on this platform (Windows).")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except Exception as e:
        logger.error(f"Error setting up event loop or signal handlers: {e}")
        sys.exit(1)

    # --- Запуск основного цикла ---
    try:
        logger.info("Starting event loop...")
        loop.run_until_complete(main())
    except asyncio.CancelledError:
        logger.warning("Main task cancelled during shutdown.")
    except Exception as e:
         # Логируем критические ошибки, которые могли произойти до старта polling или после его остановки
         logger.critical(f"Unhandled exception in event loop: {e}")
         logger.exception(e)
    finally:
        logger.info("Closing event loop.")
        # Убедимся, что все задачи завершены перед закрытием цикла
        # loop.run_until_complete(loop.shutdown_asyncgens()) # Для более новых Python
        loop.close()
        logger.info("Event loop closed. Exiting application.")
        sys.exit(0) # Явный выход с кодом 0