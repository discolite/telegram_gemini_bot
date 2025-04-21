from googletrans import Translator, LANGUAGES
# from googletrans.constants import DEFAULT_USER_AGENT # На случай проблем с User-Agent
import asyncio
from loguru import logger
from typing import Optional

from services.gemini import translate_via_gemini # Резервный метод через Gemini

# Инициализация переводчика
# user_agent = DEFAULT_USER_AGENT # Можно попробовать изменить User-Agent при проблемах
# translator = Translator(user_agent=user_agent)
translator = Translator()


async def translate_text_googletrans(text: str, dest_lang: str = 'en') -> Optional[str]:
    """Translates text using the googletrans library."""
    try:
        # Проверка, поддерживается ли язык
        if dest_lang not in LANGUAGES and dest_lang not in LANGUAGES.values():
             logger.warning(f"Unsupported language code for googletrans: {dest_lang}")
             # Попробуем передать как есть, вдруг сработает
             # return f"Ошибка: Язык '{dest_lang}' не поддерживается библиотекой googletrans."
             pass # Попробуем все равно

        logger.info(f"Translating using googletrans to '{dest_lang}': '{text[:50]}...'")

        # Запускаем перевод в отдельном потоке
        def run_translate():
            try:
                translation = translator.translate(text, dest=dest_lang)
                return translation.text
            except Exception as e:
                 logger.error(f"Error during googletrans translation: {e}")
                 return None

        translated_text = await asyncio.to_thread(run_translate)

        if translated_text:
            logger.info("Translation successful (googletrans).")
            return translated_text
        else:
             logger.warning("googletrans failed, trying Gemini as fallback.")
             # Попытка резервного перевода через Gemini
             return await translate_via_gemini(text, dest_lang)

    except Exception as e:
        logger.error(f"Unexpected error in translate_text_googletrans: {e}")
        logger.exception(e)
        logger.warning("Trying Gemini translation as fallback due to unexpected error.")
        # Попытка резервного перевода через Gemini при любой ошибке
        return await translate_via_gemini(text, dest_lang)

# Функция для получения кода языка (например, из 'английский' в 'en')
def get_lang_code(lang_name_or_code: str) -> str:
    lang_name_or_code = lang_name_or_code.strip().lower()
    if lang_name_or_code in LANGUAGES:
        return lang_name_or_code # Это уже код
    for code, name in LANGUAGES.items():
        if lang_name_or_code == name.lower():
            return code
    # Если не нашли, возвращаем как есть, Gemini может понять
    logger.warning(f"Could not map '{lang_name_or_code}' to a known language code. Using as is.")
    return lang_name_or_code