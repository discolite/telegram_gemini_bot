# --- START OF FILE settings.py ---

import os
from dotenv import load_dotenv
from pathlib import Path
from loguru import logger

# Определяем базовую директорию проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Загружаем переменные окружения из файла .env
dotenv_path = BASE_DIR / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path)
    logger.info(f"Loaded environment variables from {dotenv_path}")
else:
    logger.warning(f".env file not found at {dotenv_path}. Relying on system environment variables.")

# --- Telegram Bot ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not found in .env or environment variables.")
    raise ValueError("Необходимо указать TELEGRAM_BOT_TOKEN")

# --- APIs ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    # Эта проверка теперь находится в правильном месте и с правильным отступом
    logger.error("GEMINI_API_KEY not found in .env or environment variables.")
    raise ValueError("Необходимо указать GEMINI_API_KEY")

OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
if not OPENWEATHERMAP_API_KEY:
    logger.warning("OPENWEATHERMAP_API_KEY not found. Weather functionality will be disabled.")

# --- Security ---
authorized_users_str = os.getenv("AUTHORIZED_USERS", "")
try:
    # Убираем лишние пробелы и пустые строки после split
    AUTHORIZED_USERS = [int(user_id.strip()) for user_id in authorized_users_str.split(',') if user_id.strip()]
    if not AUTHORIZED_USERS:
        logger.warning("AUTHORIZED_USERS list is empty in .env. Bot will respond to everyone (NOT RECOMMENDED).")
    else:
         logger.info(f"Authorized users: {AUTHORIZED_USERS}")
except ValueError:
    logger.error("Invalid format for AUTHORIZED_USERS in .env. Should be comma-separated integers. Bot access will be blocked.")
    AUTHORIZED_USERS = [] # Блокируем всех, если формат неверный

# --- Bot Behavior ---
DEFAULT_MOOD = os.getenv("DEFAULT_MOOD", "friendly").lower()
if DEFAULT_MOOD not in ["friendly", "professional", "sarcastic"]:
    logger.warning(f"Invalid DEFAULT_MOOD '{DEFAULT_MOOD}'. Falling back to 'friendly'.")
    DEFAULT_MOOD = "friendly"

# --- File Paths ---
LOG_FILE = BASE_DIR / os.getenv("LOG_FILE", "logs/bot.log")
DATABASE_FILE = BASE_DIR / os.getenv("DATABASE_FILE", "bot.db")
TEMP_DIR = BASE_DIR / os.getenv("TEMP_DIR", "temp")

# --- Log Rotation ---
LOG_ROTATION = os.getenv("LOG_ROTATION", "1 MB")

# --- Ensure directories exist ---
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)

# --- Models ---
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.0-flash")
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.0-flash")

# --- Other ---
MAX_CONTEXT_MESSAGES = 5 # Количество сообщений в контексте (пар пользователь-модель)

# Максимальная длина контента файла (в символах) для отправки в Gemini
# Gemini имеет лимиты на входные токены. Установка лимита на символы предотвращает ошибки.
MAX_FILE_CONTENT_LENGTH_FOR_GEMINI = int(os.getenv("MAX_FILE_CONTENT_LENGTH_FOR_GEMINI", 30000))
logger.debug(f"Max file content length for Gemini analysis: {MAX_FILE_CONTENT_LENGTH_FOR_GEMINI} characters")

# --- Configure Loguru Logger ---
# Удаляем стандартный обработчик, чтобы избежать дублирования вывода в консоль, если запускается не через systemd
try:
    logger.remove(0) # Удаляем обработчик по умолчанию (ID=0)
except ValueError:
    pass # Игнорируем ошибку, если обработчик уже удален или не существует

# Добавляем вывод в stderr (который systemd перенаправит в bot_stderr.log для ошибок, а stdout в bot_stdout.log)
# Loguru по умолчанию пишет в stderr, так что стандартный add должен работать для логов ошибок
# Настроим вывод INFO+ в stdout, а DEBUG+ в файл
logger.add(
    lambda msg: print(msg, end=''), # INFO и выше пойдут в stdout -> bot_stdout.log
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)
logger.add(
    LOG_FILE, # DEBUG и выше пойдут в файл
    rotation=LOG_ROTATION,
    compression="zip",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}" # Детальный формат для файла
)

logger.info("Configuration loaded successfully.")
logger.debug(f"Base directory: {BASE_DIR}")
logger.debug(f"Temp directory: {TEMP_DIR}")
logger.debug(f"Database file: {DATABASE_FILE}")
logger.debug(f"Log file: {LOG_FILE}")
logger.debug(f"Text Model: {GEMINI_TEXT_MODEL}, Vision Model: {GEMINI_VISION_MODEL}")
logger.debug(f"Max file content length for Gemini: {MAX_FILE_CONTENT_LENGTH_FOR_GEMINI}")

# --- END OF FILE settings.py ---