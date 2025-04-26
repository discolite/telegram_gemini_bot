# /home/telegram_gemini_bot/utils/helpers.py

import os
import uuid
import asyncio
from pathlib import Path
from loguru import logger
import re
import html # Добавлен импорт html

# Импортируем typing для Optional
from typing import Optional

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
    clean_extension = extension.lstrip('.')
    filename = f"{uuid.uuid4()}.{clean_extension}"
    return settings.TEMP_DIR / filename

def escape_markdown_v2(text: str) -> str:
    """Escapes characters for Telegram MarkdownV2."""
    if not isinstance(text, str):
        logger.warning(f"escape_markdown_v2 received non-string type: {type(text)}. Returning empty string.")
        return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    translation_table = str.maketrans({char: f'\\{char}' for char in escape_chars})
    return text.translate(translation_table)

def get_current_datetime_str() -> str:
    """Returns the current date and time as a formatted string."""
    from datetime import datetime
    now = datetime.now()
    return now.strftime("%d %B %Y, %H:%M")

def is_ocr_potentially_useful(text: Optional[str], min_chars: int = 5, min_alnum_ratio: float = 0.4) -> bool:
    """Checks if OCR text is potentially useful."""
    if not text or not isinstance(text, str): return False
    text_stripped = ''.join(text.split())
    if not text_stripped: return False
    alnum_chars = re.findall(r'[\w]', text_stripped, re.UNICODE)
    num_alnum = len(alnum_chars)
    total_len = len(text_stripped)
    if num_alnum < min_chars:
        logger.debug(f"OCR filter: Not enough alphanumeric chars ({num_alnum} < {min_chars}).")
        return False
    if total_len == 0: return False
    ratio = num_alnum / total_len
    if ratio < min_alnum_ratio:
        logger.debug(f"OCR filter: Low alphanumeric ratio ({ratio:.2f} < {min_alnum_ratio}).")
        return False
    logger.debug(f"OCR filter: Passed. Alphanum chars: {num_alnum}, Ratio: {ratio:.2f}.")
    return True

# --- НОВАЯ ФУНКЦИЯ ДЛЯ ФОРМАТИРОВАНИЯ HTML ---
def escape_html(text: str) -> str:
    """Экранирует основные HTML символы."""
    if not isinstance(text, str):
        return ""
    # Экранируем только <, >, & т.к. кавычки не конфликтуют с тегами
    return html.escape(text, quote=False)

def format_response_html(text: str) -> str:
    """
    Применяет базовое HTML-форматирование к тексту ответа.
    Пытается конвертировать Markdown в HTML и улучшить читаемость.
    """
    if not isinstance(text, str):
        logger.debug("format_response_html received non-string, returning empty.")
        return ""

    text = text.strip()
    if not text:
        logger.debug("format_response_html received empty string, returning.")
        return ""

    logger.debug(f"Formatting HTML, original length: {len(text)}")

    # 1. Обработка блоков кода ```...``` -> <pre><code>...</code></pre>
    code_blocks = {}
    placeholder_template = "___CODE_BLOCK_{}___"
    block_index = 0

    def replace_code_block(match):
        nonlocal block_index
        lang = match.group(1) or ''
        code = match.group(2)
        placeholder = placeholder_template.format(block_index)
        escaped_code = escape_html(code.strip())
        lang_class = f' class="language-{escape_html(lang.lower())}"' if lang else ''
        code_blocks[placeholder] = f'<pre><code{lang_class}>{escaped_code}</code></pre>'
        block_index += 1
        return placeholder

    text = re.sub(r'```(\w+)?\s*\n(.*?)\n```', replace_code_block, text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'```\s*\n(.*?)\n```', lambda m: replace_code_block(type('',(object,),{'group':lambda i: '' if i==1 else m.group(1)})()), text, flags=re.DOTALL)

    # 2. Экранируем оставшийся текст
    text = escape_html(text)

    # 3. Преобразование Markdown в HTML (после экранирования и извлечения кода)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text) # Жирный **text**
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)     # Курсив *text*
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text) # Моноширинный `text`

    # 4. Улучшение читаемости и добавление эмодзи
    lines = text.split('\n')
    formatted_lines = []
    in_list = False

    for i, line in enumerate(lines):
        stripped_line = line.strip()
        is_processed = False

        # Пропускаем пустые строки для простоты
        # if not stripped_line:
        #     formatted_lines.append("")
        #     in_list = False
        #     continue

        # Заголовки
        is_header = False
        if stripped_line.endswith(':') and len(stripped_line) < 100:
            is_header = True
        elif stripped_line.isupper() and len(stripped_line) > 3 and len(stripped_line) < 50 and i > 0 and lines[i-1].strip() == "":
            is_header = True

        if is_header:
            if i > 0 and formatted_lines and formatted_lines[-1].strip() != "": formatted_lines.append("")
            formatted_lines.append(f"<b>{line}</b>") # line уже экранирован
            in_list = False
            is_processed = True
            continue # Не применяем другое форматирование к заголовкам

        # Списки
        list_match = re.match(r'^(\s*)(\*|-|\d+\.)\s+(.*)', line)
        if list_match:
            indent, marker, item_text = list_match.groups()
            if not in_list and i > 0 and formatted_lines and formatted_lines[-1].strip() != "": formatted_lines.append("")
            in_list = True
            emoji_marker = "🔹" if marker in ['*', '-'] else f"<code>{escape_html(marker)}</code>"
            # item_text уже экранирован, так как весь line был экранирован
            formatted_lines.append(f"{indent}{emoji_marker} {item_text}")
            is_processed = True
            continue # Не применяем другое форматирование к элементам списка

        # Если строка не обработана как заголовок или список
        if not is_processed:
            in_list = False # Сбрасываем флаг списка
            # Добавление эмодзи (можно расширить)
            new_line = line # line уже экранирован
            if "ошибка" in line.lower() or "error" in line.lower(): new_line = f"❌ {line}"
            elif "важно" in line.lower() or "important" in line.lower(): new_line = f"⚠️ {line}"
            elif "совет" in line.lower() or "tip" in line.lower() or "рекомендация" in line.lower(): new_line = f"💡 {line}"
            elif "успешно" in line.lower() or "success" in line.lower() or "готово" in line.lower(): new_line = f"✅ {line}"
            elif "вопрос" in line.lower() or "question" in line.lower(): new_line = f"❓ {line}"
            elif stripped_line.lower().startswith("новост") and len(stripped_line) < 50: new_line = f"📰 {line}"
            formatted_lines.append(new_line)

    # Собираем обратно
    formatted_text = '\n'.join(formatted_lines)
    formatted_text = re.sub(r'\n{3,}', '\n\n', formatted_text) # Убираем лишние пустые строки

    # 5. Возвращаем блоки кода на место
    for placeholder, block in code_blocks.items():
        # Плейсхолдер НЕ экранирован, т.к. мы его сами создали
        formatted_text = formatted_text.replace(placeholder, block)

    logger.debug(f"Formatted HTML length: {len(formatted_text)}")
    return formatted_text.strip()