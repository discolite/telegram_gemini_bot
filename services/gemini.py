# --- START OF FILE services/gemini.py ---

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

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

generation_config = genai.types.GenerationConfig(
    # temperature=0.7,
    # max_output_tokens=2048
)

async def generate_text_response(user_id: int, user_prompt: str) -> Optional[str]:
    """Generates a text response using Gemini, considering context and mood."""
    if not text_model:
        logger.error("Gemini text model is not initialized.")
        return "Извините, произошла ошибка конфигурации AI"

    try:
        user_settings = await get_user_settings(user_id)
        mood = user_settings.get('mood', settings.DEFAULT_MOOD)
        history = await get_message_history(user_id)

        current_time_str = get_current_datetime_str()
        # --- ИЗМЕНЕНИЯ В ИНСТРУКЦИИ ---
        system_instruction = (
            f"Ты - ИИ-ассистент в Telegram. Отвечай на русском языке, если не указано иное. "
            f"Учитывай предыдущие сообщения. Сегодня {current_time_str}. "
            f"ВАЖНО: Если пользователь явно просит тебя 'озвучить', 'сказать', 'произнести' какой-то текст "
            f"(например: 'озвучь Привет мир', 'скажи Как дела?'), твой единственный ответ ДОЛЖЕН быть в формате "
            f"`[TTS:Текст для озвучки]`, где 'Текст для озвучки' - это именно тот текст, который нужно озвучить. "
            f"Не добавляй к этому маркеру НИКАКИХ других слов, пояснений или приветствий. "
            f"Если пользователь просит перевести текст (например: 'переведи hello на русский'), выполни перевод. "
            f"В остальных случаях отвечай на запрос как обычно."
        )
        # --- КОНЕЦ ИЗМЕНЕНИЙ В ИНСТРУКЦИИ ---

        if mood == "friendly": system_instruction += " Общайся дружелюбно и неформально."
        elif mood == "professional": system_instruction += " Общайся строго профессионально и формально."
        elif mood == "sarcastic": system_instruction += " Общайся с сарказмом и иронией, но оставайся полезным."

        gemini_history: List[Dict[str, List[str]]] = []
        if system_instruction:
             gemini_history.append({'role': 'user', 'parts': [system_instruction]})
             gemini_history.append({'role': 'model', 'parts': ["Понял. Я готов отвечать."]})

        for msg in history:
             if msg.get('content'):
                 gemini_history.append({'role': msg['role'], 'parts': [str(msg['content'])]})

        current_user_message = {'role': 'user', 'parts': [user_prompt]}
        request_payload = gemini_history + [current_user_message]

        logger.debug(f"Sending request to Gemini text model ({settings.GEMINI_TEXT_MODEL}) for user {user_id}. History length: {len(gemini_history)}. Payload size approx: {len(str(request_payload))} chars.")
        # logger.debug(f"Gemini History: {gemini_history}")
        # logger.debug(f"Current prompt: {current_user_message}")

        logger.debug(f"Starting Gemini text generation in thread for user {user_id}...")
        response = await asyncio.to_thread(
            text_model.generate_content,
            contents=request_payload,
            generation_config=generation_config,
            safety_settings=safety_settings,
        )
        logger.debug(f"Finished Gemini text generation in thread for user {user_id}.")

        if response and response.candidates and response.candidates[0].content.parts:
            generated_text = response.candidates[0].content.parts[0].text
            logger.info(f"Received text response from Gemini for user {user_id} (length: {len(generated_text)}).")
            return generated_text.strip()
        else:
            block_reason = response.prompt_feedback.block_reason if response.prompt_feedback else 'Unknown'
            finish_reason = response.candidates[0].finish_reason if response.candidates else 'Unknown'
            logger.warning(f"Gemini text response was empty or blocked for user {user_id}. Block reason: {block_reason}, Finish reason: {finish_reason}")
            try: fallback_text = response.text; logger.warning(f"Trying fallback text: {fallback_text[:100]}...");
            except Exception: fallback_text = None
            if finish_reason == 'SAFETY': return "Извините, ваш запрос или контекст не соответствуют правилам безопасности. Попробуйте переформулировать"
            elif block_reason != 'Unknown' and block_reason != 'OTHER': return f"Извините, не могу сгенерировать ответ. Причина: {block_reason}"
            elif fallback_text: return fallback_text.strip()
            else: return "Извините, не удалось получить ответ от AI. Попробуйте позже"

    except Exception as e:
        logger.error(f"Error generating text response from Gemini for user {user_id}: {e}")
        logger.exception(e)
        return "Произошла ошибка при обращении к AI. Попробуйте позже"

async def analyze_image_content(image_path: str, prompt: str = "Опиши, что изображено на этой картинке.") -> Optional[str]:
    """Analyzes image content using Gemini Vision."""
    if not vision_model:
        logger.error("Gemini vision model is not initialized.")
        return "Извините, произошла ошибка конфигурации AI Vision"

    try:
        logger.info(f"Analyzing image using {settings.GEMINI_VISION_MODEL}: {image_path}")
        img = await asyncio.to_thread(PIL.Image.open, image_path)

        logger.debug(f"Starting Gemini vision analysis in thread for image {image_path}...")
        response = await asyncio.to_thread(
            vision_model.generate_content,
            contents=[prompt, img],
            generation_config=generation_config,
            safety_settings=safety_settings,
        )
        logger.debug(f"Finished Gemini vision analysis in thread for image {image_path}.")

        if response and response.candidates and response.candidates[0].content.parts:
            analysis = response.candidates[0].content.parts[0].text
            logger.info(f"Received image analysis from Gemini Vision (length: {len(analysis)}).")
            return analysis.strip()
        else:
            block_reason = response.prompt_feedback.block_reason if response.prompt_feedback else 'Unknown'
            finish_reason = response.candidates[0].finish_reason if response.candidates else 'Unknown'
            logger.warning(f"Gemini Vision response was empty or blocked for {image_path}. Block reason: {block_reason}, Finish reason: {finish_reason}")
            try: fallback_text = response.text
            except Exception: fallback_text = None
            if finish_reason == 'SAFETY': return "Извините, изображение или запрос не соответствуют правилам безопасности"
            elif block_reason != 'Unknown' and block_reason != 'OTHER': return f"Извините, не могу проанализировать изображение. Причина: {block_reason}"
            elif fallback_text: return fallback_text.strip()
            else: return "Извините, не удалось получить анализ изображения от AI"

    except Exception as e:
        logger.error(f"Error analyzing image with Gemini Vision ({image_path}): {e}")
        logger.exception(e)
        return "Произошла ошибка при анализе изображения"

async def analyze_file_content(text_content: str, filename: str) -> Optional[str]:
    """Analyzes extracted text content from a file using Gemini."""
    if not text_model:
        logger.error("Gemini text model is not initialized.")
        return "Извините, произошла ошибка конфигурации AI"

    max_chars_for_prompt = 8000
    truncated_content = text_content[:max_chars_for_prompt]
    truncation_note = "\n\n(Содержимое файла было урезано для анализа)" if len(text_content) > max_chars_for_prompt else ""
    prompt = f"Проанализируй содержимое файла '{filename}'. Основные моменты:\n\n{truncated_content}{truncation_note}"

    try:
        logger.debug(f"Sending file content analysis request ({settings.GEMINI_TEXT_MODEL}) for file: {filename}. Prompt size approx: {len(prompt)} chars.")

        logger.debug(f"Starting Gemini file analysis in thread for {filename}...")
        response = await asyncio.to_thread(
            text_model.generate_content,
            contents=[prompt],
            generation_config=generation_config,
            safety_settings=safety_settings,
        )
        logger.debug(f"Finished Gemini file analysis in thread for {filename}.")

        if response and response.candidates and response.candidates[0].content.parts:
            analysis = response.candidates[0].content.parts[0].text
            logger.info(f"Received file content analysis from Gemini for file {filename} (length: {len(analysis)}).")
            return analysis.strip()
        else:
            block_reason = response.prompt_feedback.block_reason if response.prompt_feedback else 'Unknown'
            finish_reason = response.candidates[0].finish_reason if response.candidates else 'Unknown'
            logger.warning(f"Gemini file analysis response was empty/blocked for {filename}. Block reason: {block_reason}, Finish reason: {finish_reason}")
            try: fallback_text = response.text
            except Exception: fallback_text = None
            if finish_reason == 'SAFETY': return "Извините, содержимое файла не соответствует правилам безопасности"
            elif block_reason != 'Unknown' and block_reason != 'OTHER': return f"Извините, не могу проанализировать файл. Причина: {block_reason}"
            elif fallback_text: return fallback_text.strip()
            else: return "Извините, не удалось получить анализ файла от AI"

    except Exception as e:
        logger.error(f"Error analyzing file content with Gemini ({filename}): {e}")
        logger.exception(e)
        return "Произошла ошибка при анализе файла"

async def translate_via_gemini(text: str, target_language: str) -> Optional[str]:
    """Translates text using Gemini."""
    if not text_model:
        logger.error("Gemini text model is not initialized.")
        return "Извините, произошла ошибка конфигурации AI"

    prompt = f"Переведи следующий текст на язык '{target_language}':\n\n{text}"

    try:
        logger.info(f"Requesting translation via Gemini ({settings.GEMINI_TEXT_MODEL}) to '{target_language}'. Text length: {len(text)}")

        logger.debug(f"Starting Gemini translation in thread to {target_language}...")
        response = await asyncio.to_thread(
            text_model.generate_content,
            contents=[prompt],
            generation_config=generation_config,
            safety_settings=safety_settings,
        )
        logger.debug(f"Finished Gemini translation in thread to {target_language}.")

        if response and response.candidates and response.candidates[0].content.parts:
            translated_text = response.candidates[0].content.parts[0].text
            logger.info(f"Received translation from Gemini (length: {len(translated_text)}).")
            return translated_text.strip()
        else:
            block_reason = response.prompt_feedback.block_reason if response.prompt_feedback else 'Unknown'
            finish_reason = response.candidates[0].finish_reason if response.candidates else 'Unknown'
            logger.warning(f"Gemini translation response was empty/blocked. Block reason: {block_reason}, Finish reason: {finish_reason}")
            try: fallback_text = response.text
            except Exception: fallback_text = None
            if finish_reason == 'SAFETY': return "Извините, текст для перевода не соответствует правилам безопасности"
            else: return "Извините, не удалось получить перевод от AI"

    except Exception as e:
        logger.error(f"Error translating text via Gemini: {e}")
        logger.exception(e)
        return "Произошла ошибка при переводе через AI"

# --- END OF FILE services/gemini.py ---