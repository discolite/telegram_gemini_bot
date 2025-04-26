# --- START OF FILE config/settings.py ---

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
    logger.error("GEMINI_API_KEY not found in .env or environment variables.")
    raise ValueError("Необходимо указать GEMINI_API_KEY")

OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
if not OPENWEATHERMAP_API_KEY:
    logger.warning("OPENWEATHERMAP_API_KEY not found. Weather functionality will be disabled.")

# --- Security ---
authorized_users_str = os.getenv("AUTHORIZED_USERS", "")
try:
    # Фильтруем пустые строки после split и проверяем на isdigit перед int()
    AUTHORIZED_USERS = [int(user_id.strip()) for user_id in authorized_users_str.split(',') if user_id.strip().isdigit()]
    if not authorized_users_str or not AUTHORIZED_USERS: # Проверяем исходную строку и результат
        logger.warning("AUTHORIZED_USERS list is empty or invalid in .env. Bot will respond to everyone (NOT RECOMMENDED).")
        AUTHORIZED_USERS = [] # Убеждаемся, что это пустой список, если были ошибки
    else:
         logger.info(f"Authorized users: {AUTHORIZED_USERS}")
except Exception as e: # Ловим более общие ошибки на всякий случай
    logger.error(f"Error parsing AUTHORIZED_USERS in .env: {e}. Should be comma-separated integers. Bot access will be blocked.")
    AUTHORIZED_USERS = []

# --- Bot Behavior ---
DEFAULT_MOOD = os.getenv("DEFAULT_MOOD", "friendly").lower()
allowed_moods = ["friendly", "professional", "sarcastic", "romantic", "funny"]
if DEFAULT_MOOD not in allowed_moods:
    logger.warning(f"Invalid DEFAULT_MOOD '{DEFAULT_MOOD}'. Allowed: {allowed_moods}. Falling back to 'friendly'.")
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
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-1.5-flash")
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-1.5-flash")

# --- TTS Settings (gTTS - Google Text-to-Speech library) ---
# Настройки для gTTS обычно не требуются в .env,
# так как язык задается в коде.

# <<< НАЧАЛО УДАЛЕНИЯ/КОММЕНТИРОВАНИЯ Piper >>>
# PIPER_EXECUTABLE_PATH = os.getenv("PIPER_EXECUTABLE_PATH")
# PIPER_VOICE_MODEL_PATH = os.getenv("PIPER_VOICE_MODEL_PATH")
# PIPER_VOICE_CONFIG_PATH = os.getenv("PIPER_VOICE_CONFIG_PATH") # Может быть None
#
# if not PIPER_EXECUTABLE_PATH:
#     logger.warning("PIPER_EXECUTABLE_PATH not set. Piper TTS will be disabled (using gTTS).")
# if not PIPER_VOICE_MODEL_PATH:
#      logger.warning("PIPER_VOICE_MODEL_PATH not set. Piper TTS will be disabled (using gTTS).")
# <<< КОНЕЦ УДАЛЕНИЯ/КОММЕНТИРОВАНИЯ Piper >>>

# --- Other ---
MAX_CONTEXT_MESSAGES = int(os.getenv("MAX_CONTEXT_MESSAGES", 20))
MAX_FILE_CONTENT_LENGTH_FOR_GEMINI = int(os.getenv("MAX_FILE_CONTENT_LENGTH_FOR_GEMINI", 30000))
WEATHER_FORECAST_DEFAULT_DAYS = int(os.getenv("WEATHER_FORECAST_DEFAULT_DAYS", 5))
# <<< НОВОЕ: Лимит символов файла для истории >>>
# Половина от лимита Gemini - хорошее начало. Можно настроить.
MAX_HISTORY_FILE_CONTENT_LENGTH = MAX_FILE_CONTENT_LENGTH_FOR_GEMINI // 2


# --- Configure Loguru Logger ---
# (Логика настройки логгера остается без изменений)
try:
    logger.remove(0)
except ValueError: pass
logger.add(lambda msg: print(msg, end=''), level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}")
logger.add(LOG_FILE, rotation=LOG_ROTATION, compression="zip", level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}", encoding="utf-8")

logger.info("Logger configured.")
logger.info("Configuration loaded successfully.")
logger.debug(f"Base directory: {BASE_DIR}")
logger.debug(f"Temp directory: {TEMP_DIR}")
logger.debug(f"Database file: {DATABASE_FILE}")
logger.debug(f"Log file: {LOG_FILE}")
logger.debug(f"Text Model: {GEMINI_TEXT_MODEL}, Vision Model: {GEMINI_VISION_MODEL}")
logger.debug(f"Max context message pairs: {MAX_CONTEXT_MESSAGES}")
logger.debug(f"Default mood: {DEFAULT_MOOD}")
logger.debug(f"Max file content length for Gemini: {MAX_FILE_CONTENT_LENGTH_FOR_GEMINI}")
logger.debug(f"Max file content length for history: {MAX_HISTORY_FILE_CONTENT_LENGTH}")
logger.debug(f"Default forecast days: {WEATHER_FORECAST_DEFAULT_DAYS}")
logger.info("Using gTTS for Text-to-Speech.") # Указываем, что используется gTTS

# --- END OF FILE config/settings.py ---