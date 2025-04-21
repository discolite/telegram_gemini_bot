# /home/telegram_gemini_bot/utils/helpers.py

import os
import uuid
import asyncio
from pathlib import Path
from loguru import logger
import re # Убедитесь, что этот импорт есть

# Импортируем typing для Optional, если он еще не импортирован где-то выше в файле
from typing import Optional

from config import settings

async def cleanup_temp_file(file_path: Path):
    """Safely removes a temporary file."""
    try:
        # Проверяем существование асинхронно перед удалением
        if file_path and await asyncio.to_thread(file_path.exists):
            await asyncio.to_thread(os.remove, file_path)
            logger.info(f"Successfully cleaned up temporary file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up temporary file {file_path}: {e}")

def get_temp_filepath(extension: str) -> Path:
    """Generates a unique temporary file path."""
    # Убираем ведущую точку из расширения, если она есть
    clean_extension = extension.lstrip('.')
    filename = f"{uuid.uuid4()}.{clean_extension}"
    return settings.TEMP_DIR / filename

def escape_markdown_v2(text: str) -> str:
    """Escapes characters for Telegram MarkdownV2."""
    # Проверка, что на вход пришла строка
    if not isinstance(text, str):
        logger.warning(f"escape_markdown_v2 received non-string type: {type(text)}. Returning empty string.")
        return ""
    # Символы, которые нужно экранировать в MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    # Заменяем каждый спецсимвол на его экранированную версию (символ с \)
    # Используем str.translate для эффективности
    # Создаем таблицу для перевода
    translation_table = str.maketrans({char: f'\\{char}' for char in escape_chars})
    return text.translate(translation_table)

def get_current_datetime_str() -> str:
    """Returns the current date and time as a formatted string."""
    from datetime import datetime
    now = datetime.now()
    # Простой формат без локали, безопасный для Markdown
    return now.strftime("%d %B %Y, %H:%M")
    # Fallback format: return now.strftime("%Y-%m-%d %H:%M")

# --- Новая функция для проверки OCR ---
def is_ocr_potentially_useful(text: Optional[str], min_chars: int = 5, min_alnum_ratio: float = 0.4) -> bool:
    """
    Проверяет, является ли текст OCR потенциально полезным.
    - text: Текст для проверки.
    - min_chars: Минимальное количество буквенно-цифровых символов.
    - min_alnum_ratio: Минимальная доля буквенно-цифровых символов от общей длины (без пробелов/переносов).
    """
    if not text or not isinstance(text, str):
        return False

    # Удаляем пробелы и переносы строк для подсчета реальных символов
    text_stripped = ''.join(text.split())
    if not text_stripped:
        return False # Пустая строка после удаления пробелов

    # Ищем буквенно-цифровые символы (буквы любых алфавитов + цифры) с помощью re.UNICODE
    # \w включает буквы, цифры и знак подчеркивания (_)
    alnum_chars = re.findall(r'[\w]', text_stripped, re.UNICODE)

    num_alnum = len(alnum_chars)
    total_len = len(text_stripped)

    # Проверка 1: Достаточно ли буквенно-цифровых символов в абсолютном выражении?
    if num_alnum < min_chars:
        logger.debug(f"OCR filter: Not enough alphanumeric chars ({num_alnum} < {min_chars}). Text: '{text[:80]}...'")
        return False

    # Проверка 2: Не слишком ли мала доля буквенно-цифровых символов?
    # Избегаем деления на ноль, если total_len вдруг оказался 0 (хотя не должен после проверки text_stripped)
    if total_len == 0:
         return False

    ratio = num_alnum / total_len
    if ratio < min_alnum_ratio:
        logger.debug(f"OCR filter: Low alphanumeric ratio ({ratio:.2f} < {min_alnum_ratio}). Text: '{text[:80]}...'")
        return False

    # Если обе проверки пройдены
    logger.debug(f"OCR filter: Passed. Alphanum chars: {num_alnum}, Ratio: {ratio:.2f}. Text: '{text[:80]}...'")
    return True