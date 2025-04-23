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
# Импорт для CSV Sniffer и Pandas ошибок
try:
    import csv
    from pandas.errors import ParserError
except ImportError:
    csv = None
    ParserError = None # Define as None if pandas not fully available or csv fails

from utils.helpers import cleanup_temp_file
from config import settings
from services.gemini import analyze_file_content

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024 # 50 MB limit

# <<< ИЗМЕНЕНИЕ: Возвращаем (status_message, analysis_result, extracted_content) >>>
async def process_file(file_path: Path, filename: str, mime_type: Optional[str], file_size: int) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    """
    Обрабатывает файл: извлекает содержимое, отправляет на анализ Gemini.

    Возвращает:
        Кортеж (status_message, analysis_result, extracted_content) или None.
        extracted_content: Извлеченный текст/данные (может быть None).
    """
    extracted_content: Optional[str] = None # Инициализируем здесь
    analysis_result: Optional[str] = None
    status_message: str = f"Обрабатываю файл: {filename}"

    if file_size > MAX_FILE_SIZE_BYTES:
         max_mb = MAX_FILE_SIZE_BYTES // 1024 // 1024
         logger.warning(f"Файл '{filename}' превышает макс. размер ({file_size} > {MAX_FILE_SIZE_BYTES} байт). Пропуск.")
         # <<< Возвращаем 3 значения >>>
         return f"Файл '{filename}' слишком большой (>{max_mb} МБ)", None, None

    file_ext = filename.split('.')[-1].lower() if '.' in filename else None
    logger.info(f"Обработка файла: {filename}, размер: {file_size}, тип: {mime_type}, расширение: {file_ext}")

    try:
        # --- Обработка TXT ---
        if file_ext == 'txt' or mime_type == 'text/plain':
            logger.debug(f"Чтение текстового файла: {filename}")
            def read_txt():
                 try:
                     # Используем errors='ignore' для чтения файлов с проблемами кодировки
                     with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                         return f.read()
                 except FileNotFoundError:
                     logger.error(f"Файл не найден во время чтения TXT: {file_path}")
                     return f"Ошибка: Файл {filename} не найден во время чтения."
                 except Exception as read_e:
                     logger.error(f"Ошибка чтения текстового файла {filename}: {read_e}")
                     return f"Ошибка чтения текстового файла {filename}" # Возвращаем строку с ошибкой

            extracted_content = await asyncio.to_thread(read_txt) # Сохраняем результат
            # Обработка ошибок read_txt
            if not isinstance(extracted_content, str) or extracted_content.startswith("Ошибка"):
                # Если read_txt вернул ошибку или не строку, записываем это в статус
                status_message = extracted_content if isinstance(extracted_content, str) else "Ошибка чтения TXT"
                extracted_content = None # Обнуляем если ошибка
            else:
                 status_message = f"Извлек текст из {filename}"
                 if not extracted_content.strip(): # Проверка на пустой файл или только пробелы
                     status_message = f"Файл {filename} пустой или содержит только пробелы"
                     extracted_content = None # Пустой контент не анализируем

        # --- Обработка PDF ---
        elif file_ext == 'pdf' or mime_type == 'application/pdf':
            logger.debug(f"Чтение PDF файла: {filename}")
            def read_pdf():
                text = ""
                try:
                    with open(file_path, 'rb') as f:
                        # strict=False для большей устойчивости к поврежденным PDF
                        reader = PyPDF2.PdfReader(f, strict=False)
                        if reader.is_encrypted:
                             logger.warning(f"PDF файл '{filename}' зашифрован.")
                             # Попытка расшифровать с пустым паролем
                             try:
                                 if reader.decrypt('') == PyPDF2.PasswordType.NOT_DECRYPTED:
                                      logger.warning(f"Не удалось расшифровать PDF {filename} пустым паролем.")
                                      return f"Ошибка: PDF файл '{filename}' зашифрован и не может быть открыт"
                             except Exception as decrypt_err:
                                  logger.error(f"Ошибка при попытке расшифровать PDF {filename}: {decrypt_err}")
                                  return f"Ошибка при попытке расшифровать PDF '{filename}'"

                        num_pages = len(reader.pages)
                        logger.debug(f"PDF '{filename}' содержит {num_pages} страниц.")
                        extracted_texts = []
                        # Обрабатываем каждую страницу
                        for i, page in enumerate(reader.pages):
                            try:
                                page_text = page.extract_text()
                                if page_text:
                                    extracted_texts.append(page_text.strip()) # Добавляем текст страницы
                            except Exception as page_err:
                                logger.warning(f"Не удалось извлечь текст со страницы {i+1} файла {filename}: {page_err}")
                        # Объединяем текст со всех страниц
                        text = "\n\n".join(extracted_texts) # Разделяем страницы двойным переносом строки
                except PyPDF2.errors.PdfReadError as pdf_err:
                     logger.error(f"Ошибка чтения PDF {filename} (PyPDF2): {pdf_err}")
                     return f"Ошибка: Не удалось прочитать PDF файл '{filename}'. Возможно, он поврежден или имеет несовместимый формат."
                except FileNotFoundError:
                    logger.error(f"PDF файл не найден во время чтения: {file_path}")
                    return f"Ошибка: Файл {filename} не найден во время чтения."
                except Exception as e:
                    logger.error(f"Неожиданная ошибка при чтении PDF {filename}: {e}")
                    logger.exception(e)
                    return f"Непредвиденная ошибка при чтении PDF {filename}"
                return text

            extracted_content = await asyncio.to_thread(read_pdf) # Сохраняем результат
            # Обработка ошибок read_pdf
            if not isinstance(extracted_content, str) or extracted_content.startswith("Ошибка"):
                status_message = extracted_content if isinstance(extracted_content, str) else "Ошибка чтения PDF"
                extracted_content = None
            elif extracted_content.strip(): # Если текст извлечен
                 status_message = f"Извлек текст из PDF {filename} ({len(extracted_content)} символов)"
            else:
                 # Текст не извлечен, но ошибки не было (например, PDF из картинок)
                 status_message = f"Не удалось извлечь текст из PDF {filename} (возможно, содержит только изображения или текст не извлекается)"
                 extracted_content = None

        # --- Обработка Таблиц (CSV, XLSX, XLS) ---
        elif file_ext in ['csv', 'xlsx', 'xls'] or mime_type in ['text/csv', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel']:
            logger.debug(f"Чтение файла таблицы: {filename}")
            def read_table():
                df = None
                try:
                    # --- CSV ---
                    if file_ext == 'csv' or mime_type == 'text/csv':
                        if not csv or not ParserError: # Проверяем импорты
                           logger.error("Библиотеки 'csv' или 'pandas' не доступны для обработки CSV.")
                           return "Ошибка: Необходимые библиотеки для CSV не установлены."
                        logger.debug(f"Попытка чтения CSV: {filename}")
                        detected_sep = None
                        try:
                             # Пробуем определить разделитель
                             with open(file_path, 'r', encoding='utf-8', errors='ignore') as csvfile:
                                 # Читаем небольшой кусок для определения диалекта
                                 sample = csvfile.read(1024 * 10) # 10 KB sample
                                 if not sample:
                                     logger.warning(f"CSV файл {filename} пуст.")
                                     return "Таблица пуста."
                                 csvfile.seek(0) # Возвращаемся в начало файла
                                 sniffer = csv.Sniffer()
                                 dialect = sniffer.sniff(sample, delimiters=',;\t|') # Явно указываем возможные разделители
                                 detected_sep = dialect.delimiter
                                 logger.info(f"Определен разделитель CSV для {filename}: '{detected_sep}'")
                             # Читаем с определенным разделителем
                             df = pd.read_csv(file_path, sep=detected_sep, on_bad_lines='warn', engine='python', encoding_errors='ignore', low_memory=False)
                             logger.info(f"Успешно прочитан CSV {filename} с разделителем '{detected_sep}'.")
                        except (csv.Error, ParserError, Exception) as sniff_read_err:
                             logger.warning(f"Определение разделителя/чтение CSV не удалось для {filename}: {sniff_read_err}. Пробуем стандартные разделители.")
                             df = None # Сбрасываем df
                             common_separators = [',', ';', '\t', '|']
                             for sep_try in common_separators:
                                 if sep_try == detected_sep: continue # Пропускаем уже опробованный
                                 logger.debug(f"Пробуем разделитель '{sep_try}' для {filename}")
                                 try:
                                     # Пробуем прочитать хотя бы несколько строк
                                     df_try = pd.read_csv(file_path, sep=sep_try, on_bad_lines='skip', nrows=10, encoding_errors='ignore', low_memory=False)
                                     # Считаем успешным, если есть колонки или не пустой DataFrame
                                     if not df_try.empty and len(df_try.columns) > 0:
                                         # Читаем весь файл с этим разделителем
                                         df = pd.read_csv(file_path, sep=sep_try, on_bad_lines='warn', encoding_errors='ignore', low_memory=False)
                                         logger.info(f"Успешно прочитан CSV {filename} с разделителем '{sep_try}'.")
                                         break # Выходим из цикла, если успешно
                                 except Exception as read_try_err:
                                     logger.debug(f"Чтение CSV {filename} с разделителем '{sep_try}' не удалось: {read_try_err}")
                                     continue
                             if df is None:
                                 logger.error(f"Не удалось прочитать CSV файл {filename} ни с одним из стандартных разделителей.")
                                 return f"Ошибка: Не удалось определить разделитель или прочитать CSV файл '{filename}'."
                    # --- Excel ---
                    elif file_ext in ['xlsx', 'xls'] or mime_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel']:
                        logger.debug(f"Попытка чтения Excel файла: {filename} (расширение: {file_ext})")
                        engine_to_try = 'openpyxl' if file_ext == 'xlsx' else None
                        # Сначала пробуем openpyxl для .xlsx
                        if engine_to_try == 'openpyxl':
                            logger.debug(f"Пробуем движок 'openpyxl' для {filename}")
                            try:
                                df = pd.read_excel(file_path, engine=engine_to_try)
                                logger.info(f"Успешно прочитан Excel файл {filename} с помощью openpyxl.")
                            except ImportError:
                                logger.critical("Библиотека `openpyxl` не установлена. Не могу читать .xlsx файлы. Выполните `pip install openpyxl`")
                                return "Критическая ошибка: Не установлена библиотека 'openpyxl' для чтения современных Excel файлов (.xlsx)"
                            except Exception as excel_read_err:
                                logger.warning(f"Не удалось прочитать Excel файл {filename} с помощью openpyxl: {excel_read_err}. Пробуем другие движки, если применимо.")
                                df = None # Сбрасываем df
                                engine_to_try = None # Попробуем другой движок ниже
                        # Если это .xls или openpyxl не сработал, пробуем xlrd
                        if df is None:
                            logger.debug(f"Пробуем движок 'xlrd' для {filename}")
                            try:
                                df = pd.read_excel(file_path, engine='xlrd')
                                logger.info(f"Успешно прочитан Excel файл {filename} с помощью xlrd.")
                            except ImportError:
                                logger.error("Библиотека `xlrd` не установлена. Не могу читать старые .xls файлы. Выполните `pip install xlrd`")
                                # Если это был .xls, то это критично
                                if file_ext == 'xls':
                                    return "Ошибка: Не установлена библиотека 'xlrd' для чтения старых Excel файлов (.xls)"
                                # Если это был .xlsx, просто логируем, т.к. openpyxl должен был сработать
                            except Exception as xlrd_err:
                                logger.error(f"Не удалось прочитать Excel файл {filename} с помощью xlrd: {xlrd_err}")
                                df = None # Сбрасываем df на всякий случай

                        if df is None: # Если ни один движок не сработал
                             logger.error(f"Не удалось прочитать файл Excel {filename} доступными движками.")
                             return f"Ошибка при чтении файла Excel '{filename}'. Файл может быть поврежден, зашифрован или иметь несовместимый формат."
                    # --- Неизвестный тип таблицы ---
                    else:
                         logger.error(f"Неожиданное расширение/MIME тип для обработки таблицы: {filename}")
                         return f"Внутренняя ошибка: Неожиданный тип файла для таблицы: {filename}"

                    # --- Обработка DataFrame ---
                    if df is None: # Дополнительная проверка
                        logger.error(f"DataFrame равен None после попытки чтения таблицы {filename}")
                        return f"Ошибка: Не удалось получить данные из файла таблицы '{filename}'"
                    if df.empty:
                        logger.info(f"Файл таблицы {filename} пуст.")
                        return "Таблица пуста."

                    # Формируем описание таблицы для Gemini
                    num_rows, num_cols = df.shape
                    header = ", ".join(map(str, df.columns))
                    # Берем небольшой срез данных для примера
                    # Ограничиваем и строки и колонки, чтобы не перегружать промпт
                    head_df_safe = df.iloc[:5, :10] # Первые 5 строк, первые 10 колонок
                    head_data = head_df_safe.to_string(index=False, max_rows=5, max_cols=10, header=True)

                    # Добавляем примечания, если данные были урезаны для примера
                    cols_truncated = " (...колонки урезаны)" if num_cols > 10 else ""
                    rows_truncated = "\n... (...строки урезаны)" if num_rows > 5 else ""

                    # Собираем финальное описание
                    max_len_table_desc = 5000 # Ограничиваем длину описания таблицы
                    content_str = (
                        f"Таблица содержит {num_rows} строк и {num_cols} колонок.\n"
                        f"Заголовки: {header}\n\n"
                        f"Пример данных (до 5 строк, до 10 колонок{cols_truncated}):\n{head_data}{rows_truncated}"
                    )
                    return content_str[:max_len_table_desc] # Возвращаем описание (может быть урезано)

                except FileNotFoundError:
                    logger.error(f"Файл таблицы не найден во время чтения: {file_path}")
                    return f"Ошибка: Файл {filename} не найден во время чтения."
                except Exception as e:
                    logger.error(f"Общая ошибка при чтении файла таблицы {filename}: {e}")
                    logger.exception(e)
                    return f"Непредвиденная ошибка при чтении файла таблицы '{filename}'"

            extracted_content = await asyncio.to_thread(read_table) # Сохраняем результат (описание таблицы)
            # Обработка ошибок read_table
            if not isinstance(extracted_content, str):
                logger.error(f"read_table вернул неожиданный тип: {type(extracted_content)}")
                status_message = f"Внутренняя ошибка при обработке таблицы {filename}"
                extracted_content = None
            elif extracted_content.startswith("Ошибка") or extracted_content.startswith("Критическая ошибка"):
                status_message = extracted_content # Сообщение об ошибке из read_table
                extracted_content = None
            elif extracted_content == "Таблица пуста.": # Специальный случай для пустых таблиц
                status_message = f"Файл таблицы '{filename}' пуст."
                extracted_content = None # Анализ не нужен
            else:
                # Успешно прочитали таблицу, extracted_content содержит ее описание
                status_message = f"Прочитал данные из таблицы {filename}"

        # --- Обработка DOCX ---
        elif file_ext == 'docx' or mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            logger.debug(f"Чтение DOCX файла: {filename}")
            def read_docx():
                if docx is None:
                     logger.critical("Библиотека `python-docx` не установлена. Не могу читать .docx файлы. Выполните `pip install python-docx`")
                     return "Критическая ошибка: Не установлена библиотека 'python-docx' для чтения .docx файлов."
                try:
                    document = docx.Document(file_path)
                    full_text = [para.text for para in document.paragraphs if para.text] # Собираем непустые параграфы
                    return "\n".join(full_text) # Объединяем параграфы через один перенос строки
                except docx.opc.exceptions.PackageNotFoundError:
                     logger.error(f"Ошибка чтения DOCX {filename}: Файл не найден или поврежден.")
                     return f"Ошибка: Не удалось открыть DOCX файл '{filename}'. Возможно, он поврежден или не является DOCX файлом."
                except Exception as docx_err:
                    logger.error(f"Ошибка чтения DOCX файла {filename}: {docx_err}")
                    logger.exception(docx_err)
                    # Проверяем на ошибку шифрования
                    if "encrypted" in str(docx_err).lower() or "password" in str(docx_err).lower():
                         return f"Ошибка: Файл DOCX '{filename}' защищен паролем или зашифрован."
                    return f"Ошибка при чтении файла DOCX '{filename}'."

            extracted_content = await asyncio.to_thread(read_docx) # Сохраняем результат
            # Обработка ошибок read_docx
            if not isinstance(extracted_content, str) or extracted_content.startswith("Ошибка") or extracted_content.startswith("Критическая ошибка"):
                status_message = extracted_content if isinstance(extracted_content, str) else "Ошибка чтения DOCX"
                extracted_content = None
            elif extracted_content.strip(): # Если текст извлечен
                status_message = f"Извлек текст из DOCX {filename} ({len(extracted_content)} символов)"
            else: # Если текст пустой после извлечения
                status_message = f"Не удалось извлечь текст из DOCX {filename} (файл пустой или содержит только нетекстовые элементы?)"
                extracted_content = None

        # --- Обработка DOC (Не поддерживается) ---
        elif file_ext == 'doc' or mime_type == 'application/msword':
            logger.warning(f"Получен устаревший файл .doc: {filename}. Чтение не поддерживается.")
            status_message = (f"Файл '{filename}' старого формата .doc.\n"
                              f"Чтение таких файлов напрямую не поддерживается.\n"
                              f"Пожалуйста, **конвертируйте его в .docx или .txt** и отправьте снова.")
            extracted_content = None
            # <<< Возвращаем 3 значения >>>
            return status_message, None, None

        # --- Неподдерживаемый тип файла ---
        else:
            logger.warning(f"Неподдерживаемый тип файла: {filename} (расширение: {file_ext}, mime: {mime_type})")
            status_message = f"Файл '{filename}' имеет неподдерживаемый тип ({file_ext or mime_type or 'неизвестный'})"
            extracted_content = None
            # <<< Возвращаем 3 значения >>>
            return status_message, None, None

        # --- Анализ извлеченного содержимого (если оно есть и не было ошибки извлечения) ---
        # Анализируем, только если есть контент и статус не содержит явную ошибку
        if extracted_content and "Ошибка" not in status_message and "Критическая" not in status_message:
            logger.info(f"Контент извлечен из {filename}. Длина/Инфо: {len(extracted_content)}. Запрос анализа.")
            # Формируем промпт для Gemini
            analysis_prompt = "" # Инициализируем
            if status_message.startswith("Прочитал данные из таблицы"):
                 # Промпт для анализа описания таблицы
                 analysis_prompt = f"Проанализируй следующую информацию о таблице из файла '{filename}':\n{extracted_content}\n\nСделай краткое резюме о данных в таблице, их возможном назначении или ключевых особенностях."
            else: # Обычный текст из TXT, PDF, DOCX
                 # Урезаем контент для промпта Gemini, если он слишком длинный
                 content_to_analyze = extracted_content[:settings.MAX_FILE_CONTENT_LENGTH_FOR_GEMINI]
                 analysis_prompt = f"Проанализируй следующее содержимое файла '{filename}':\n{content_to_analyze}"
                 if len(extracted_content) > settings.MAX_FILE_CONTENT_LENGTH_FOR_GEMINI:
                     logger.warning(f"Контент из {filename} был урезан для анализа Gemini (отправлено {len(content_to_analyze)} символов).")
                     analysis_prompt += "\n\n[Примечание: Содержимое файла было урезано для анализа из-за ограничений по длине]"

            # Вызываем Gemini для анализа
            analysis_result = await analyze_file_content(analysis_prompt, filename)
            if not analysis_result:
                 logger.warning(f"Анализ Gemini для {filename} вернул пустой результат или не удался.")
                 # Не добавляем ошибку анализа к status_message здесь, сделаем это в хендлере

        # Если контент не был извлечен, но статус не ошибка (пустой файл, PDF-картинка и т.п.), пропускаем анализ
        elif not extracted_content and "Ошибка" not in status_message and file_ext not in ['doc']:
             logger.info(f"Контент из {filename} не извлечен для анализа (Статус: {status_message}). Пропуск анализа.")

        # <<< ИЗМЕНЕНИЕ: Возвращаем все три значения >>>
        return status_message, analysis_result, extracted_content

    except Exception as e:
        # Непредвиденная ошибка на верхнем уровне обработки файла
        logger.error(f"Неожиданная ошибка верхнего уровня при обработке файла {filename}: {e}")
        logger.exception(e)
        status_message = f"Непредвиденная критическая ошибка при обработке файла {filename}"
        # <<< Возвращаем 3 значения >>>
        return status_message, None, None
    finally:
        # Гарантированное удаление временного файла
        await cleanup_temp_file(file_path)
        logger.debug(f"Очищен временный файл {file_path} для {filename}")

# --- КОНЕЦ ФАЙЛА services/file_handler.py ---