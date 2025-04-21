import os
import uuid
import asyncio
from pathlib import Path
from loguru import logger

from config import settings

async def cleanup_temp_file(file_path: Path):
    """Safely removes a temporary file."""
    try:
        if file_path and await asyncio.to_thread(file_path.exists):
            await asyncio.to_thread(os.remove, file_path)
            logger.info(f"Successfully cleaned up temporary file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up temporary file {file_path}: {e}")

def get_temp_filepath(extension: str) -> Path:
    """Generates a unique temporary file path."""
    filename = f"{uuid.uuid4()}.{extension}"
    return settings.TEMP_DIR / filename

def escape_markdown_v2(text: str) -> str:
    """Escapes characters for Telegram MarkdownV2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(f'\\{char}' if char in escape_chars else char for char in text)

def get_current_datetime_str() -> str:
    """Returns the current date and time as a formatted string."""
    from datetime import datetime
    now = datetime.now()
    # Пример формата: "15 мая 2024 года, 14:30"
    # Можно настроить локализацию, но для простоты оставим так
    # Для русской локали:
    # import locale
    # try:
    #     locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    # except locale.Error:
    #     logger.warning("Russian locale 'ru_RU.UTF-8' not available. Using default format.")
    # return now.strftime("Сегодня %d %B %Y года, %H:%M")

    # Простой формат без локали
    return now.strftime("%d %B %Y, %H:%M") # Requires babel potentially for full month names
    # Fallback format
    # return now.strftime("%Y-%m-%d %H:%M")