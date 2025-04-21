import pandas as pd
import PyPDF2
import asyncio
from pathlib import Path
from loguru import logger
from typing import Optional, Tuple

from utils.helpers import cleanup_temp_file
from config import settings
from services.gemini import analyze_file_content

# Максимальный размер файла для обработки (в байтах) - например, 50 МБ
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

async def process_file(file_path: Path, filename: str, mime_type: Optional[str], file_size: int) -> Optional[Tuple[str, str]]:
    """
    Processes uploaded files (txt, pdf, csv, xlsx), extracts content,
    analyzes it with Gemini, and cleans up the temp file.
    Returns a tuple: (status_message, analysis_result) or None if unsupported/error.
    """
    extracted_content = None
    analysis_result = None
    status_message = f"Обрабатываю файл: {filename}"

    if file_size > MAX_FILE_SIZE_BYTES:
         logger.warning(f"File '{filename}' exceeds max size ({file_size} > {MAX_FILE_SIZE_BYTES}). Skipping.")
         await cleanup_temp_file(file_path)
         return f"Файл '{filename}' слишком большой (>{MAX_FILE_SIZE_BYTES // 1024 // 1024} МБ).", None


    file_ext = filename.split('.')[-1].lower() if '.' in filename else None
    logger.info(f"Processing file: {filename}, size: {file_size}, type: {mime_type}, ext: {file_ext}")

    try:
        # --- Определение типа файла и извлечение контента ---
        if file_ext == 'txt' or mime_type == 'text/plain':
            logger.debug(f"Reading text file: {filename}")
            def read_txt():
                 with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            extracted_content = await asyncio.to_thread(read_txt)
            status_message = f"Извлек текст из {filename}."

        elif file_ext == 'pdf' or mime_type == 'application/pdf':
            logger.debug(f"Reading PDF file: {filename}")
            def read_pdf():
                text = ""
                try:
                    with open(file_path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        num_pages = len(reader.pages)
                        logger.debug(f"PDF has {num_pages} pages.")
                        for i, page in enumerate(reader.pages):
                            try:
                                page_text = page.extract_text()
                                if page_text:
                                     text += page_text + "\n"
                            except Exception as page_err:
                                 logger.warning(f"Could not extract text from page {i+1} of {filename}: {page_err}")
                except PyPDF2.errors.PdfReadError as pdf_err:
                     logger.error(f"Error reading PDF {filename}: {pdf_err}")
                     return f"Ошибка: Не удалось прочитать PDF файл '{filename}'. Возможно, он поврежден или зашифрован."
                except Exception as e:
                    logger.error(f"Unexpected error reading PDF {filename}: {e}")
                    return f"Ошибка при чтении PDF {filename}."
                return text

            extracted_content = await asyncio.to_thread(read_pdf)
            if extracted_content and not extracted_content.startswith("Ошибка:"):
                 status_message = f"Извлек текст из PDF {filename} ({len(extracted_content)} символов)."
            elif extracted_content and extracted_content.startswith("Ошибка:"):
                 status_message = extracted_content # Сообщение об ошибке от read_pdf
                 extracted_content = None # Сбрасываем контент, т.к. была ошибка

        elif file_ext in ['csv', 'xlsx'] or mime_type in ['text/csv', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel']:
            logger.debug(f"Reading table file: {filename}")
            def read_table():
                try:
                    if file_ext == 'csv' or mime_type == 'text/csv':
                        # Пытаемся определить разделитель
                        try:
                             df = pd.read_csv(file_path, sep=None, engine='python', on_bad_lines='skip', nrows=5) # Пробуем автоопределение на первых 5 строках
                             delimiter = df.columns[0] if len(df.columns) == 1 else ',' # Эвристика
                             if delimiter not in [',', ';', '\t', '|']: delimiter = ',' # Default
                             df = pd.read_csv(file_path, sep=delimiter, on_bad_lines='skip')
                        except Exception:
                             df = pd.read_csv(file_path, on_bad_lines='skip') # Fallback
                    else: # xlsx
                        df = pd.read_excel(file_path, engine='openpyxl')

                    # Для анализа Gemini передаем информацию о структуре и несколько строк
                    num_rows, num_cols = df.shape
                    header = ", ".join(df.columns)
                    head_data = df.head().to_string(index=False)
                    return f"Таблица содержит {num_rows} строк и {num_cols} колонок.\nЗаголовки: {header}\n\nПервые несколько строк:\n{head_data}"
                except Exception as e:
                    logger.error(f"Error reading table file {filename}: {e}")
                    return f"Ошибка при чтении файла таблицы '{filename}': {e}"

            extracted_content = await asyncio.to_thread(read_table)
            if extracted_content and not extracted_content.startswith("Ошибка:"):
                status_message = f"Прочитал данные из таблицы {filename}."
            elif extracted_content and extracted_content.startswith("Ошибка:"):
                status_message = extracted_content
                extracted_content = None

        else:
            logger.warning(f"Unsupported file type: {filename} (ext: {file_ext}, mime: {mime_type})")
            status_message = f"Файл '{filename}' имеет неподдерживаемый тип ({file_ext or mime_type}). Поддерживаются: .txt, .pdf, .csv, .xlsx."
            await cleanup_temp_file(file_path)
            return status_message, None # Возвращаем только сообщение об ошибке

        # --- Анализ извлеченного контента с помощью Gemini ---
        if extracted_content:
            logger.info(f"Content extracted from {filename}. Length/Info: {len(extracted_content) if isinstance(extracted_content, str) else 'Table Info'}. Requesting analysis.")
            analysis_result = await analyze_file_content(extracted_content, filename)
        else:
             logger.warning(f"No content could be extracted from {filename} for analysis.")
             # Статус уже содержит сообщение об ошибке или причину отсутствия контента

        return status_message, analysis_result # Возвращаем и статус, и результат анализа (может быть None)

    except Exception as e:
        logger.error(f"Unexpected error processing file {filename}: {e}")
        logger.exception(e)
        status_message = f"Непредвиденная ошибка при обработке файла {filename}."
        return status_message, None
    finally:
        # Очистка временного файла в любом случае (кроме случая неподдерживаемого типа, где он уже удален)
        if file_ext in ['txt', 'pdf', 'csv', 'xlsx'] or mime_type in ['text/plain', 'application/pdf', 'text/csv', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel']:
             await cleanup_temp_file(file_path)