import os
from dotenv import load_dotenv
from pathlib import Path
from loguru import logger

# Определяем базовую директорию проекта
# Это позволяет корректно находить .env и другие файлы, даже если скрипт запускается из другого места
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
    logger.error("GEMINI_API_KEY not found in .env or environment variables.")
    raise ValueError("Необходимо указать GEMINI_API_KEY")

OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
if not OPENWEATHERMAP_API_KEY:
    logger.warning("OPENWEATHERMAP_API_KEY not found. Weather functionality will be disabled.")
    # Не делаем raise, так как погода - не критичная функция

# --- Security ---
authorized_users_str = os.getenv("AUTHORIZED_USERS", "")
try:
    AUTHORIZED_USERS = [int(user_id.strip()) for user_id in authorized_users_str.split(',') if user_id.strip()]
    if not AUTHORIZED_USERS:
        logger.warning("AUTHORIZED_USERS list is empty. Bot will respond to everyone (NOT RECOMMENDED).")
    else:
         logger.info(f"Authorized users: {AUTHORIZED_USERS}")
except ValueError:
    logger.error("Invalid format for AUTHORIZED_USERS in .env. Should be comma-separated integers.")
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
DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True) # Убедимся, что директория для БД существует

# --- Models ---
GEMINI_TEXT_MODEL = "gemini-1.5-pro-latest" # Или "gemini-1.5-pro"
GEMINI_VISION_MODEL = "gemini-pro-vision" # Gemini Vision model

# --- Other ---
MAX_CONTEXT_MESSAGES = 5 # Количество сообщений в контексте

# --- Проверка наличия ключей API ---
# (Уже сделано выше при загрузке)

logger.add(
    LOG_FILE,
    rotation=LOG_ROTATION,
    compression="zip",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)

logger.info("Configuration loaded successfully.")
logger.debug(f"Base directory: {BASE_DIR}")
logger.debug(f"Temp directory: {TEMP_DIR}")
logger.debug(f"Database file: {DATABASE_FILE}")
logger.debug(f"Log file: {LOG_FILE}")