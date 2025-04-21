import pytesseract
from PIL import Image
import asyncio
from pathlib import Path
from loguru import logger
from typing import Optional

from services.gemini import analyze_image_content as analyze_with_gemini # Gemini Vision
from utils.helpers import cleanup_temp_file

# Убедитесь, что Tesseract установлен и настроен:
# sudo apt update
# sudo apt install tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng
# Проверить языки: tesseract --list-langs

# Можно указать путь к tesseract, если он не в PATH
# pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

async def extract_text_from_image(image_path: Path) -> Optional[str]:
    """Extracts text from an image using Tesseract OCR (Russian + English)."""
    try:
        logger.info(f"Extracting text from image (OCR): {image_path}")

        # Запускаем Tesseract в отдельном потоке
        def run_ocr():
            try:
                # Используем русский и английский языки
                return pytesseract.image_to_string(Image.open(image_path), lang='rus+eng')
            except pytesseract.TesseractNotFoundError:
                 logger.error("Tesseract is not installed or not in PATH.")
                 return "Ошибка: Tesseract OCR не найден на сервере."
            except Exception as ocr_err:
                 logger.error(f"Error during Tesseract OCR processing: {ocr_err}")
                 return f"Ошибка при извлечении текста: {ocr_err}"

        text = await asyncio.to_thread(run_ocr)

        if text and "Ошибка:" not in text:
            logger.info(f"Text extracted successfully from {image_path}")
            return text.strip()
        elif "Ошибка:" in text:
             logger.error(f"OCR failed for {image_path}: {text}")
             return None # Возвращаем None если была ошибка Tesseract
        else:
            logger.info(f"No text found in image {image_path}")
            return "" # Возвращаем пустую строку, если текст не найден

    except FileNotFoundError:
        logger.error(f"Image file not found for OCR: {image_path}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during OCR text extraction ({image_path}): {e}")
        logger.exception(e)
        return None

async def analyze_image(image_path: Path, user_id: int) -> Dict[str, Optional[str]]:
    """
    Analyzes an image using both Tesseract OCR and Gemini Vision.
    Cleans up the temporary image file afterwards.
    Returns a dictionary with 'ocr_text' and 'vision_analysis'.
    """
    ocr_text = None
    vision_analysis = None

    try:
        # 1. Извлечение текста с помощью OCR
        ocr_text = await extract_text_from_image(image_path)

        # 2. Анализ содержимого с помощью Gemini Vision
        # Можно добавить специфичный промпт, если нужно
        vision_prompt = "Опиши это изображение."
        if ocr_text:
             vision_prompt += f" На изображении также есть текст: '{ocr_text[:100]}...'" # Добавляем начало OCR текста в промпт Vision

        vision_analysis = await analyze_with_gemini(str(image_path), prompt=vision_prompt)

    except Exception as e:
        logger.error(f"Error during combined image analysis for {image_path}: {e}")
        # Ошибки уже залогированы в вызываемых функциях
    finally:
        # 3. Очистка временного файла изображения
        await cleanup_temp_file(image_path)

    return {"ocr_text": ocr_text, "vision_analysis": vision_analysis}