# --- START OF FILE services/file_handler.py ---

import pandas as pd
import PyPDF2
import asyncio
from pathlib import Path
from loguru import logger
from typing import Optional, Tuple
# Импорт для DOCX
try:
    import docx
except ImportError:
    docx = None # Обработаем отсутствие библиотеки ниже

from utils.helpers import cleanup_temp_file
from config import settings
from services.gemini import analyze_file_content

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

async def process_file(file_path: Path, filename: str, mime_type: Optional[str], file_size: int) -> Optional[Tuple[str, Optional[str]]]:
    """
    Обрабатывает файл: извлекает содержимое (текст, данные таблицы) и отправляет на анализ Gemini.

    Args:
        file_path: Путь к временному файлу.
        filename: Оригинальное имя файла.
        mime_type: MIME-тип файла (может быть None).
        file_size: Размер файла в байтах.

    Returns:
        Кортеж (status_message, analysis_result) или None в случае критической ошибки.
        status_message: Строка со статусом обработки (успех, ошибка, причина).
        analysis_result: Результат анализа от Gemini (строка) или None, если анализ не проводился или не удался.
    """
    extracted_content = None
    analysis_result = None
    status_message = f"Обрабатываю файл: {filename}"

    if file_size > MAX_FILE_SIZE_BYTES:
         logger.warning(f"File '{filename}' exceeds max size ({file_size} > {MAX_FILE_SIZE_BYTES}). Skipping.")
         # Файл будет удален в finally
         return f"Файл '{filename}' слишком большой (>{MAX_FILE_SIZE_BYTES // 1024 // 1024} МБ)", None

    file_ext = filename.split('.')[-1].lower() if '.' in filename else None
    logger.info(f"Processing file: {filename}, size: {file_size}, type: {mime_type}, ext: {file_ext}")

    try:
        # --- Обработка TXT ---
        if file_ext == 'txt' or mime_type == 'text/plain':
            logger.debug(f"Reading text file: {filename}")
            def read_txt():
                 try:
                     with open(file_path, 'r', errors='ignore') as f: return f.read()
                 except Exception as read_e:
                     logger.error(f"Error reading text file {filename}: {read_e}")
                     return f"Ошибка чтения текстового файла {filename}"
            logger.debug(f"Starting read_txt in thread for {filename}...")
            extracted_content = await asyncio.to_thread(read_txt)
            logger.debug(f"Finished read_txt in thread for {filename}.")
            if not isinstance(extracted_content, str) or extracted_content.startswith("Ошибка"):
                 status_message = extracted_content if isinstance(extracted_content, str) else "Ошибка чтения TXT"
                 extracted_content = None
            else:
                 status_message = f"Извлек текст из {filename}"
                 if not extracted_content.strip():
                     logger.info(f"Text file {filename} is empty or contains only whitespace.")
                     status_message = f"Файл {filename} пустой"
                     extracted_content = None # Не анализируем пустой файл

        # --- Обработка PDF ---
        elif file_ext == 'pdf' or mime_type == 'application/pdf':
            logger.debug(f"Reading PDF file: {filename}")
            def read_pdf():
                text = ""
                try:
                    with open(file_path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f, strict=False)
                        if reader.is_encrypted:
                             logger.warning(f"PDF file '{filename}' is encrypted.")
                             try:
                                 if reader.decrypt('') == PyPDF2.PasswordType.NOT_DECRYPTED:
                                      logger.warning(f"Could not decrypt PDF {filename} with empty password.")
                                      return f"Ошибка: PDF файл '{filename}' зашифрован и не может быть открыт"
                             except Exception as decrypt_err:
                                  logger.error(f"Error trying to decrypt PDF {filename}: {decrypt_err}")
                                  return f"Ошибка при попытке расшифровать PDF '{filename}'"
                        num_pages = len(reader.pages)
                        logger.debug(f"PDF '{filename}' has {num_pages} pages.")
                        extracted_texts = []
                        for i, page in enumerate(reader.pages):
                            try:
                                page_text = page.extract_text()
                                if page_text: extracted_texts.append(page_text)
                            except Exception as page_err:
                                logger.warning(f"Could not extract text from page {i+1} of {filename}: {page_err}")
                        text = "\n\n".join(extracted_texts) # Разделяем страницы двойным переносом строки
                except PyPDF2.errors.PdfReadError as pdf_err:
                     logger.error(f"Error reading PDF {filename}: {pdf_err}")
                     return f"Ошибка: Не удалось прочитать PDF файл '{filename}'. Возможно, он поврежден или имеет несовместимый формат."
                except FileNotFoundError:
                    logger.error(f"PDF file not found during read: {file_path}")
                    return f"Ошибка: Файл {filename} не найден во время чтения."
                except Exception as e:
                    logger.error(f"Unexpected error reading PDF {filename}: {e}")
                    logger.exception(e)
                    return f"Непредвиденная ошибка при чтении PDF {filename}"
                return text
            logger.debug(f"Starting read_pdf in thread for {filename}...")
            extracted_content = await asyncio.to_thread(read_pdf)
            logger.debug(f"Finished read_pdf in thread for {filename}.")
            if not isinstance(extracted_content, str) or extracted_content.startswith("Ошибка"):
                status_message = extracted_content if isinstance(extracted_content, str) else "Ошибка чтения PDF"
                extracted_content = None
            elif extracted_content.strip():
                 status_message = f"Извлек текст из PDF {filename} ({len(extracted_content)} символов)"
            else:
                 status_message = f"Не удалось извлечь текст из PDF {filename} (возможно, содержит только изображения или текст не извлекается)"
                 extracted_content = None

        # --- Обработка Таблиц (CSV, XLSX, XLS) ---
        elif file_ext in ['csv', 'xlsx', 'xls'] or mime_type in ['text/csv', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel']:
            logger.debug(f"Reading table file: {filename}")
            def read_table():
                df = None
                try:
                    if file_ext == 'csv' or mime_type == 'text/csv':
                        logger.debug(f"Attempting to read CSV file: {filename}")
                        try:
                             import csv
                             with open(file_path, 'r', encoding='utf-8', errors='ignore') as csvfile:
                                 sample = csvfile.read(1024*10)
                                 if not sample: logger.warning(f"CSV file {filename} is empty."); return "Таблица пуста."
                                 csvfile.seek(0)
                                 sniffer = csv.Sniffer(); dialect = sniffer.sniff(sample); sep = dialect.delimiter
                                 logger.info(f"Detected CSV delimiter for {filename}: '{sep}'")
                             df = pd.read_csv(file_path, sep=sep, on_bad_lines='warn', engine='python', encoding_errors='ignore', low_memory=False)
                             logger.info(f"Successfully read CSV {filename} with detected separator '{sep}'.")
                        except (csv.Error, pd.errors.ParserError, Exception) as sniff_err:
                             logger.warning(f"CSV sniffing/reading failed for {filename}: {sniff_err}. Trying common separators.")
                             df = None; common_separators = [',', ';', '\t', '|']
                             for sep_try in common_separators:
                                 logger.debug(f"Trying separator '{sep_try}' for {filename}")
                                 try:
                                     df_try = pd.read_csv(file_path, sep=sep_try, on_bad_lines='skip', nrows=10, encoding_errors='ignore', low_memory=False)
                                     if len(df_try.columns) > 1 or (len(df_try.columns) == 1 and not str(df_try.columns[0]).isdigit()):
                                         df = pd.read_csv(file_path, sep=sep_try, on_bad_lines='warn', encoding_errors='ignore', low_memory=False); logger.info(f"Successfully read CSV {filename} using separator '{sep_try}'."); break
                                 except Exception as read_try_err: logger.debug(f"Reading CSV {filename} with separator '{sep_try}' failed: {read_try_err}"); continue
                             if df is None: logger.error(f"Could not read CSV file {filename} with any common separator."); return f"Ошибка: Не удалось определить разделитель или прочитать CSV файл '{filename}'."
                    elif file_ext in ['xlsx', 'xls'] or mime_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel']:
                        engine_to_try = 'openpyxl' if file_ext == 'xlsx' else None; logger.debug(f"Attempting to read Excel file {filename} (extension: {file_ext})")
                        if engine_to_try == 'openpyxl':
                            logger.debug(f"Trying engine 'openpyxl' for {filename}")
                            try: df = pd.read_excel(file_path, engine=engine_to_try); logger.info(f"Successfully read Excel file {filename} using openpyxl.")
                            except ImportError: logger.critical("`openpyxl` library is not installed..."); return "Критическая ошибка: Не установлена библиотека 'openpyxl' для чтения современных Excel файлов (.xlsx)"
                            except Exception as excel_read_err: logger.warning(f"Failed to read Excel file {filename} with openpyxl: {excel_read_err}. Trying other engines if applicable."); df = None; engine_to_try = None
                        if df is None and (file_ext == 'xls' or engine_to_try is None):
                            logger.debug(f"Trying engine 'xlrd' for {filename}")
                            try:
                                df = pd.read_excel(file_path, engine='xlrd')
                                logger.info(f"Successfully read Excel file {filename} using xlrd.")
                            # =======================================
                            # ===== ИСПРАВЛЕННЫЙ БЛОК НАЧИНАЕТСЯ =====
                            # =======================================
                            except ImportError:
                                logger.error("`xlrd` library is not installed. Cannot read old .xls files. Run `pip install xlrd`")
                                # Переносим if на новую строку с отступом
                                if file_ext == 'xls':
                                    return "Ошибка: Не установлена библиотека 'xlrd' для чтения старых Excel файлов (.xls)"
                                # Если это был xlsx, просто логируем ошибку xlrd, так как openpyxl должен был сработать
                            # =====================================
                            # ===== ИСПРАВЛЕННЫЙ БЛОК КОНЧАЕТСЯ =====
                            # =====================================
                            except Exception as xlrd_err:
                                logger.error(f"Failed to read Excel file {filename} with xlrd: {xlrd_err}")
                                df = None # Сбрасываем df
                        if df is None: logger.error(f"Could not read Excel file {filename} with available engines."); return f"Ошибка при чтении файла Excel '{filename}'. Файл может быть поврежден, зашифрован или иметь несовместимый формат."
                    else: logger.error(f"Unexpected file extension/MIME type for table processing: {filename}"); return f"Внутренняя ошибка: Неожиданный тип файла для таблицы: {filename}"
                    if df is None: logger.error(f"DataFrame is None after attempting to read table {filename}"); return f"Ошибка: Не удалось получить данные из файла таблицы '{filename}'"
                    if df.empty: logger.info(f"Table file {filename} is empty."); return "Таблица пуста."
                    num_rows, num_cols = df.shape; header = ", ".join(map(str, df.columns)); head_df_safe = df.iloc[:5, :10]; head_data = head_df_safe.to_string(index=False, max_rows=5, max_cols=10)
                    if len(df.columns) > 10: head_data += "\n... (колонки урезаны)"
                    if len(df) > 5: head_data += "\n... (строки урезаны)"
                    max_len = 4000; content_str = (f"Таблица содержит {num_rows} строк и {num_cols} колонок.\n" f"Заголовки: {header}\n\n" f"Первые несколько строк (до 5 строк, до 10 колонок):\n{head_data}"); return content_str[:max_len]
                except FileNotFoundError: logger.error(f"Table file not found during read: {file_path}"); return f"Ошибка: Файл {filename} не найден во время чтения."
                except Exception as e: logger.error(f"General error reading table file {filename}: {e}"); logger.exception(e); return f"Непредвденная ошибка при чтении файла таблицы '{filename}'"

            logger.debug(f"Starting read_table in thread for {filename}...")
            extracted_content = await asyncio.to_thread(read_table)
            logger.debug(f"Finished read_table in thread for {filename}.")
            if not isinstance(extracted_content, str): logger.error(f"read_table returned unexpected type: {type(extracted_content)}"); status_message = f"Внутренняя ошибка при обработке таблицы {filename}"; extracted_content = None
            elif extracted_content.startswith("Ошибка") or extracted_content.startswith("Критическая ошибка"): status_message = extracted_content; extracted_content = None
            elif extracted_content == "Таблица пуста.": status_message = f"Файл таблицы '{filename}' пуст."; extracted_content = None
            else: status_message = f"Прочитал данные из таблицы {filename}"

        # --- Обработка DOCX ---
        elif file_ext == 'docx' or mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            logger.debug(f"Reading DOCX file: {filename}")
            def read_docx():
                if docx is None:
                     logger.critical("`python-docx` library is not installed. Cannot read .docx files. Run `pip install python-docx`")
                     return "Критическая ошибка: Не установлена библиотека 'python-docx' для чтения .docx файлов."
                try:
                    document = docx.Document(file_path)
                    full_text = [para.text for para in document.paragraphs]
                    return "\n".join(full_text)
                except docx.opc.exceptions.PackageNotFoundError:
                     logger.error(f"Error reading DOCX file {filename}: File not found or corrupted.")
                     return f"Ошибка: Не удалось открыть DOCX файл '{filename}'. Возможно, он поврежден или не является DOCX файлом."
                except Exception as docx_err:
                    logger.error(f"Error reading DOCX file {filename}: {docx_err}")
                    logger.exception(docx_err)
                    if "encrypted" in str(docx_err).lower():
                         return f"Ошибка: Файл DOCX '{filename}' защищен паролем."
                    return f"Ошибка при чтении файла DOCX '{filename}'."

            logger.debug(f"Starting read_docx in thread for {filename}...")
            extracted_content = await asyncio.to_thread(read_docx)
            logger.debug(f"Finished read_docx in thread for {filename}.")

            if not isinstance(extracted_content, str) or extracted_content.startswith("Ошибка") or extracted_content.startswith("Критическая ошибка"):
                status_message = extracted_content if isinstance(extracted_content, str) else "Ошибка чтения DOCX"
                extracted_content = None
            elif extracted_content.strip():
                status_message = f"Извлек текст из DOCX {filename} ({len(extracted_content)} символов)"
            else:
                status_message = f"Не удалось извлечь текст из DOCX {filename} (файл пустой?)"
                extracted_content = None

        # --- Обработка DOC (Не поддерживается) ---
        elif file_ext == 'doc' or mime_type == 'application/msword':
            logger.warning(f"Received legacy .doc file: {filename}. Reading is not supported.")
            status_message = (f"Файл '{filename}' старого формата .doc.\n"
                              f"Чтение таких файлов напрямую не поддерживается из-за сложности формата.\n"
                              f"Пожалуйста, **конвертируйте его в формат .docx или .txt** и отправьте снова.")
            extracted_content = None
            # Файл будет удален в finally
            return status_message, None

        # --- Неподдерживаемый тип файла ---
        else:
            logger.warning(f"Unsupported file type: {filename} (ext: {file_ext}, mime: {mime_type})")
            status_message = f"Файл '{filename}' имеет неподдерживаемый тип ({file_ext or mime_type or 'неизвестный'})"
            extracted_content = None
            # Файл будет удален в finally
            return status_message, None

        # --- Анализ извлеченного содержимого (если оно есть) ---
        if extracted_content:
            logger.info(f"Content extracted from {filename}. Length/Info: {len(extracted_content)}. Requesting analysis.")
            # Формируем промпт для Gemini
            if status_message.startswith("Прочитал данные из таблицы"):
                 analysis_prompt = f"Проанализируй следующую информацию о таблице из файла '{filename}':\n{extracted_content}\n\nСделай краткое резюме о данных в таблице, их возможном назначении или ключевых особенностях."
            else: # Обычный текст из TXT, PDF, DOCX
                 content_to_analyze = extracted_content[:settings.MAX_FILE_CONTENT_LENGTH_FOR_GEMINI]
                 analysis_prompt = f"Проанализируй следующее содержимое файла '{filename}':\n{content_to_analyze}"
                 if len(extracted_content) > settings.MAX_FILE_CONTENT_LENGTH_FOR_GEMINI:
                     logger.warning(f"Content from {filename} was truncated for Gemini analysis (sent {len(content_to_analyze)} chars).")
                     analysis_prompt += "\n\n[Примечание: Содержимое файла было урезано для анализа из-за ограничений по длине]"

            analysis_result = await analyze_file_content(analysis_prompt, filename)
            if not analysis_result:
                 logger.warning(f"Gemini analysis for {filename} returned empty or failed.")
                 if "Ошибка" not in status_message:
                    status_message += ". Не удалось получить анализ содержимого от AI."
        elif status_message and "Ошибка" not in status_message and file_ext not in ['doc']:
             logger.info(f"No content extracted from {filename} for analysis (Status: {status_message}). Skipping analysis.")

        # Возвращаем актуальный статус и результат анализа (может быть None)
        return status_message, analysis_result

    except Exception as e:
        # Непредвиденная ошибка на верхнем уровне обработки файла
        logger.error(f"Unexpected top-level error processing file {filename}: {e}")
        logger.exception(e)
        status_message = f"Непредвиденная критическая ошибка при обработке файла {filename}"
        return status_message, None
    finally:
        # Гарантированное удаление временного файла
        await cleanup_temp_file(file_path)
        logger.debug(f"Cleaned up temporary file {file_path} for {filename}")

# --- END OF FILE services/file_handler.py ---