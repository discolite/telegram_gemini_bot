import google.generativeai as genai
import PIL.Image
import asyncio
from loguru import logger
from typing import List, Dict, Optional

from config import settings
from services.database import get_message_history, get_user_settings
from utils.helpers import get_current_datetime_str

try:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    text_model = genai.GenerativeModel(settings.GEMINI_TEXT_MODEL)
    vision_model = genai.GenerativeModel(settings.GEMINI_VISION_MODEL)
    logger.info("Google Generative AI configured successfully.")
except Exception as e:
    logger.error(f"Failed to configure Google Generative AI: {e}")
    text_model = None
    vision_model = None

# Настройки безопасности (можно настроить по необходимости)
# https://ai.google.dev/docs/safety_setting_gemini
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

generation_config = genai.types.GenerationConfig(
    # temperature=0.7, # Раскомментируйте для настройки "креативности"
    # max_output_tokens=2048 # Ограничение длины ответа
)

async def generate_text_response(user_id: int, user_prompt: str) -> Optional[str]:
    """Generates a text response using Gemini, considering context and mood."""
    if not text_model:
        logger.error("Gemini text model is not initialized.")
        return "Извините, произошла ошибка конфигурации AI."

    try:
        user_settings = await get_user_settings(user_id)
        mood = user_settings.get('mood', settings.DEFAULT_MOOD)
        history = await get_message_history(user_id) # Получаем последние сообщения

        # Формируем системное сообщение (инструкцию для модели)
        current_time_str = get_current_datetime_str()
        system_instruction = f"Ты - ИИ-ассистент в Telegram. Отвечай на русском языке, если не указано иное. Учитывай предыдущие сообщения. Сегодня {current_time_str}."

        if mood == "friendly":
            system_instruction += " Общайся дружелюбно и неформально."
        elif mood == "professional":
            system_instruction += " Общайся строго профессионально и формально."
        elif mood == "sarcastic":
            system_instruction += " Общайся с сарказмом и иронией, но оставайся полезным."

        # Формируем историю для API Gemini
        # Gemini API ожидает список словарей: {'role': 'user'/'model', 'parts': [text]}
        gemini_history = []
        if system_instruction:
             # Начинаем с системной инструкции как первое сообщение 'user', затем 'model' с подтверждением
             gemini_history.append({'role': 'user', 'parts': [system_instruction]})
             gemini_history.append({'role': 'model', 'parts': ["Понял. Я готов отвечать."] }) # Или другой ответ

        # Добавляем реальную историю сообщений
        for msg in history:
             # Убедимся, что контент не пустой
             if msg.get('content'):
                 gemini_history.append({'role': msg['role'], 'parts': [msg['content']]})


        # Добавляем текущий промпт пользователя
        # Закомментировано ниже, так как generate_content принимает промпт отдельно от истории
        # gemini_history.append({'role': 'user', 'parts': [user_prompt]})

        logger.debug(f"Sending request to Gemini text model for user {user_id}. History length: {len(gemini_history)}")
        # logger.debug(f"Gemini History: {gemini_history}") # Раскомментировать для отладки

        # Запускаем генерацию в отдельном потоке, чтобы не блокировать основной цикл asyncio
        response = await asyncio.to_thread(
            text_model.generate_content,
            contents=gemini_history + [{'role': 'user', 'parts': [user_prompt]}], # Передаем историю и новый промпт
            generation_config=generation_config,
            safety_settings=safety_settings,
            # stream=False # Пока не используем стриминг
        )

        # Обработка ответа
        if response and response.candidates and response.candidates[0].content.parts:
            generated_text = response.candidates[0].content.parts[0].text
            logger.info(f"Received text response from Gemini for user {user_id}.")
            return generated_text.strip()
        else:
            # Проверка причины блокировки (если есть)
            block_reason = response.prompt_feedback.block_reason if response.prompt_feedback else 'Unknown'
            logger.warning(f"Gemini response was empty or blocked for user {user_id}. Block reason: {block_reason}")
            # Попытка получить текст из response.text напрямую (если API изменится)
            try:
                fallback_text = response.text
                logger.warning(f"Trying fallback text: {fallback_text[:100]}...")
                if fallback_text: return fallback_text.strip()
            except Exception:
                 pass # Ignore if .text doesn't exist or fails

            if block_reason != 'Unknown' and block_reason != 'SAFETY':
                 return f"Извините, не могу сгенерировать ответ. Причина: {block_reason}"
            elif block_reason == 'SAFETY':
                 return "Извините, ваш запрос или контекст не соответствуют правилам безопасности. Попробуйте переформулировать."
            else:
                return "Извините, не удалось получить ответ от AI. Попробуйте позже."

    except Exception as e:
        logger.error(f"Error generating text response from Gemini for user {user_id}: {e}")
        logger.exception(e) # Log full traceback
        return "Произошла ошибка при обращении к AI. Попробуйте позже."

async def analyze_image_content(image_path: str, prompt: str = "Опиши, что изображено на этой картинке.") -> Optional[str]:
    """Analyzes image content using Gemini Vision."""
    if not vision_model:
        logger.error("Gemini vision model is not initialized.")
        return "Извините, произошла ошибка конфигурации AI Vision."

    try:
        logger.info(f"Analyzing image: {image_path}")
        img = await asyncio.to_thread(PIL.Image.open, image_path)

        # Запускаем анализ в отдельном потоке
        response = await asyncio.to_thread(
            vision_model.generate_content,
            contents=[prompt, img], # Передаем текстовый промпт и изображение
            generation_config=generation_config,
            safety_settings=safety_settings,
            # stream=False
        )

        if response and response.candidates and response.candidates[0].content.parts:
            analysis = response.candidates[0].content.parts[0].text
            logger.info("Received image analysis from Gemini Vision.")
            return analysis.strip()
        else:
            block_reason = response.prompt_feedback.block_reason if response.prompt_feedback else 'Unknown'
            logger.warning(f"Gemini Vision response was empty or blocked. Block reason: {block_reason}")
            try:
                fallback_text = response.text
                if fallback_text: return fallback_text.strip()
            except Exception:
                 pass
            if block_reason != 'Unknown' and block_reason != 'SAFETY':
                 return f"Извините, не могу проанализировать изображение. Причина: {block_reason}"
            elif block_reason == 'SAFETY':
                 return "Извините, изображение или запрос не соответствуют правилам безопасности."
            else:
                return "Извините, не удалось получить анализ изображения от AI."

    except Exception as e:
        logger.error(f"Error analyzing image with Gemini Vision ({image_path}): {e}")
        logger.exception(e)
        return "Произошла ошибка при анализе изображения."

async def analyze_file_content(text_content: str, filename: str) -> Optional[str]:
    """Analyzes extracted text content from a file using Gemini."""
    if not text_model:
        logger.error("Gemini text model is not initialized.")
        return "Извините, произошла ошибка конфигурации AI."

    prompt = f"Проанализируй содержимое файла '{filename}'. Основные моменты:\n\n{text_content[:4000]}..." # Ограничиваем объем для промпта
    if len(text_content) > 4000:
        prompt += "\n\n(Содержимое файла было урезано для анализа)"

    # Для анализа файлов не будем передавать историю чата, чтобы фокус был на файле
    try:
        logger.debug(f"Sending file content analysis request to Gemini for file: {filename}")

        response = await asyncio.to_thread(
            text_model.generate_content,
            contents=[prompt], # Только промпт с контентом файла
            generation_config=generation_config,
            safety_settings=safety_settings,
            # stream=False
        )

        if response and response.candidates and response.candidates[0].content.parts:
            analysis = response.candidates[0].content.parts[0].text
            logger.info(f"Received file content analysis from Gemini for file: {filename}.")
            return analysis.strip()
        else:
            block_reason = response.prompt_feedback.block_reason if response.prompt_feedback else 'Unknown'
            logger.warning(f"Gemini file analysis response was empty or blocked for {filename}. Block reason: {block_reason}")
            try:
                fallback_text = response.text
                if fallback_text: return fallback_text.strip()
            except Exception:
                 pass
            if block_reason != 'Unknown' and block_reason != 'SAFETY':
                 return f"Извините, не могу проанализировать файл. Причина: {block_reason}"
            elif block_reason == 'SAFETY':
                 return "Извините, содержимое файла не соответствует правилам безопасности."
            else:
                return "Извините, не удалось получить анализ файла от AI."

    except Exception as e:
        logger.error(f"Error analyzing file content with Gemini ({filename}): {e}")
        logger.exception(e)
        return "Произошла ошибка при анализе файла."

async def translate_via_gemini(text: str, target_language: str) -> Optional[str]:
    """Translates text using Gemini."""
    if not text_model:
        logger.error("Gemini text model is not initialized.")
        return "Извините, произошла ошибка конфигурации AI."

    prompt = f"Переведи следующий текст на язык '{target_language}':\n\n{text}"

    try:
        logger.info(f"Requesting translation via Gemini to '{target_language}'")
        response = await asyncio.to_thread(
            text_model.generate_content,
            contents=[prompt],
            generation_config=generation_config,
            safety_settings=safety_settings,
        )

        if response and response.candidates and response.candidates[0].content.parts:
            translated_text = response.candidates[0].content.parts[0].text
            logger.info(f"Received translation from Gemini.")
            return translated_text.strip()
        else:
            block_reason = response.prompt_feedback.block_reason if response.prompt_feedback else 'Unknown'
            logger.warning(f"Gemini translation response was empty or blocked. Block reason: {block_reason}")
            try:
                fallback_text = response.text
                if fallback_text: return fallback_text.strip()
            except Exception:
                 pass
            return "Извините, не удалось получить перевод от AI."

    except Exception as e:
        logger.error(f"Error translating text via Gemini: {e}")
        logger.exception(e)
        return "Произошла ошибка при переводе через AI."