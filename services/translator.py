from googletrans import Translator, LANGUAGES
import asyncio
from loguru import logger
from typing import Optional

from services.gemini import translate_via_gemini # Резервный метод через Gemini

translator = Translator()

async def translate_text_googletrans(text: str, dest_lang: str = 'en') -> Optional[str]:
    """Translates text using the googletrans library."""
    translated_text = None # Инициализируем
    try:
        if dest_lang not in LANGUAGES and dest_lang not in LANGUAGES.values():
             logger.warning(f"Unsupported language code for googletrans: {dest_lang}. Passing to API.")
        logger.info(f"Translating using googletrans to '{dest_lang}': '{text[:50]}...'")
        def run_translate():
            try:
                translation = translator.translate(text, dest=dest_lang)
                return translation.text
            except Exception as e:
                 logger.error(f"Error during googletrans translation execution: {e}")
                 return None
        # <--- ИЗМЕНЕНИЕ: Логи --->
        logger.debug(f"Starting googletrans translation in thread to {dest_lang}...")
        translated_text = await asyncio.to_thread(run_translate)
        logger.debug(f"Finished googletrans translation in thread to {dest_lang}.")

        if translated_text:
            logger.info("Translation successful (googletrans).")
            return translated_text
        else:
             logger.warning("googletrans failed or returned None, trying Gemini as fallback.")
             return await translate_via_gemini(text, dest_lang)

    except Exception as e:
        logger.error(f"Unexpected error in translate_text_googletrans wrapper: {e}")
        logger.exception(e)
        logger.warning("Trying Gemini translation as fallback due to unexpected error.")
        return await translate_via_gemini(text, dest_lang)

def get_lang_code(lang_name_or_code: str) -> str:
    lang_name_or_code = lang_name_or_code.strip().lower()
    if lang_name_or_code in LANGUAGES: return lang_name_or_code
    for code, name in LANGUAGES.items():
        if lang_name_or_code == name.lower(): return code
    logger.warning(f"Could not map '{lang_name_or_code}' to a known language code. Using as is.")
    return lang_name_or_code