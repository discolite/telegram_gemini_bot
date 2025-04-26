from loguru import logger
import sys

logger.remove()  # Удаляем стандартный обработчик
logger.add(
    "/home/telegram_gemini_bot/logs/bot.log",
    rotation="10 MB",  # Ротация при достижении 10 МБ
    retention="7 days",  # Храним логи 7 дней
    level="DEBUG",  # Минимальный уровень логов
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
)