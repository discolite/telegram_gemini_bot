# /home/telegram_gemini_bot/services/image_analyzer.py

import pytesseract
from PIL import Image
import asyncio
from pathlib import Path
from loguru import logger
from typing import Optional, Dict

# Предполагается, что эта функция импортируется и работает корректно
from services.gemini import analyze_image_content as analyze_with_gemini # Gemini Vision
from utils.helpers import cleanup_temp_file

async def extract_text_from_image(image_path: Path) -> Optional[str]:
    """Extracts text from an image using Tesseract OCR (Russian + English)."""
    # Проверяем существование файла асинхронно
    if not await asyncio.to_thread(image_path.exists):
        logger.error(f"Image file not found for OCR: {image_path}")
        return None
    try:
        logger.info(f"Extracting text from image (OCR): {image_path}")
        # Синхронная функция для выполнения OCR
        def run_ocr():
            try:
                # Указываем русский и английский языки, PSM 6 - предполагаем единый блок текста
                custom_config = r'-l rus+eng --psm 6'
                # Открываем изображение и распознаем текст
                return pytesseract.image_to_string(Image.open(image_path), config=custom_config)
            except pytesseract.TesseractNotFoundError:
                 # Критическая ошибка, если Tesseract не установлен
                 logger.critical("Tesseract is not installed or not in PATH. OCR will not work.")
                 return None
            except FileNotFoundError:
                 # На случай, если файл удалился между проверкой и открытием
                 logger.error(f"Image file disappeared before Tesseract could open it: {image_path}")
                 return None
            except Exception as ocr_err:
                 # Ловим другие ошибки Tesseract
                 logger.error(f"Error during Tesseract OCR processing for {image_path}: {ocr_err}")
                 return None

        # Запускаем синхронную функцию OCR в отдельном потоке
        logger.debug(f"Starting Tesseract OCR in thread for {image_path}...")
        text = await asyncio.to_thread(run_ocr)
        logger.debug(f"Finished Tesseract OCR in thread for {image_path}.")

        # Обрабатываем результат
        if text is not None:
            extracted_text = text.strip() # Убираем лишние пробелы/переносы
            if extracted_text:
                logger.info(f"Text extracted (OCR) from {image_path} (length: {len(extracted_text)})")
                return extracted_text
            else:
                # Текст не найден, но OCR отработал без ошибок
                logger.info(f"No text found (OCR) in image {image_path}")
                return "" # Возвращаем пустую строку
        else:
            # OCR завершился с ошибкой (None)
            logger.error(f"OCR processing failed for {image_path}")
            return None
    except FileNotFoundError:
        # Файл не найден на самой первой проверке
        logger.error(f"Image file disappeared before OCR could start: {image_path}")
        return None
    except Exception as e:
        # Ловим неожиданные ошибки на уровне обертки
        logger.error(f"Unexpected error during OCR text extraction wrapper ({image_path}): {e}")
        logger.exception(e) # Логируем traceback
        return None

async def analyze_image(image_path: Path, user_id: int) -> Dict[str, Optional[str]]:
    """
    Analyzes an image using Tesseract OCR and Gemini Vision.
    OCR result is obtained but NOT passed to Gemini Vision prompt.
    """
    ocr_text: Optional[str] = None
    vision_analysis: Optional[str] = None

    # Проверяем существование файла перед началом
    file_exists = await asyncio.to_thread(image_path.exists)
    if not file_exists:
        logger.error(f"Image file does not exist for analysis: {image_path}")
        return {"ocr_text": None, "vision_analysis": None}

    try:
        logger.debug(f"Starting combined image analysis for {image_path}, user {user_id}.")

        # 1. Выполняем OCR (результат нужен для возврата и логов)
        ocr_text = await extract_text_from_image(image_path)

        # 2. Формируем промпт для Gemini Vision БЕЗ OCR
        # +++ ИЗМЕНЕНИЕ ЗДЕСЬ +++
        vision_prompt = "Опиши это изображение подробно."
        # Строки ниже закомментированы/удалены:
        # if ocr_text: vision_prompt += f" На изображении также есть текст (результат OCR): '{ocr_text[:200]}...'"
        # elif ocr_text == "": vision_prompt += " Текст на изображении не был обнаружен с помощью OCR."
        # +++++++++++++++++++++++

        # 3. Вызываем Gemini Vision
        logger.debug(f"Starting Gemini Vision analysis for {image_path}...")
        # Передаем путь как строку
        vision_analysis = await analyze_with_gemini(str(image_path), prompt=vision_prompt)
        logger.debug(f"Finished Gemini Vision analysis for {image_path}.")

        # Логируем результат
        ocr_status = "Error" if ocr_text is None else ("Found" if ocr_text else "Not Found")
        vision_status = "Success" if vision_analysis else "Failed/None"
        logger.debug(f"Combined analysis result for {image_path}: OCR={ocr_status}, Vision={vision_status}")

    except Exception as e:
        logger.error(f"Error during combined image analysis for {image_path}: {e}")
        logger.exception(e)
        # В случае ошибки обнуляем результаты
        ocr_text = None
        vision_analysis = None
    finally:
        # Очистка временного файла в любом случае (успех или ошибка)
        await cleanup_temp_file(image_path)

    # Возвращаем словарь с результатами (OCR все еще возвращается, но не используется в промпте)
    return {"ocr_text": ocr_text, "vision_analysis": vision_analysis}