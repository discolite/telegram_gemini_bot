from gtts import gTTS
import asyncio
from pathlib import Path
from loguru import logger

from utils.helpers import get_temp_filepath, cleanup_temp_file

async def generate_speech(text: str, lang: str = 'ru') -> Path | None:
    """Generates an MP3 audio file from text using gTTS."""
    try:
        logger.info(f"Generating speech for text (lang={lang}): '{text[:50]}...'")
        tts = gTTS(text=text, lang=lang, slow=False)
        filepath = get_temp_filepath("mp3")

        # Запускаем сохранение файла в отдельном потоке
        await asyncio.to_thread(tts.save, str(filepath))

        logger.info(f"Speech generated successfully: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Error generating speech with gTTS: {e}")
        logger.exception(e)
        return None

async def speak_and_cleanup(bot, chat_id, text: str, lang: str = 'ru'):
    """Generates speech, sends it as a voice message, and cleans up the file."""
    audio_path = await generate_speech(text, lang)
    if audio_path:
        try:
            from aiogram.types import FSInputFile # Локальный импорт для избежания цикличности
            audio_input = FSInputFile(audio_path)
            await bot.send_voice(chat_id=chat_id, voice=audio_input)
            logger.info(f"Sent generated voice message to {chat_id}")
        except Exception as send_err:
            logger.error(f"Error sending voice message to {chat_id}: {send_err}")
        finally:
            await cleanup_temp_file(audio_path)
    else:
        logger.error(f"Failed to generate speech for chat {chat_id}")
        # Можно отправить сообщение об ошибке пользователю
        # await bot.send_message(chat_id, "Не удалось сгенерировать голосовое сообщение.")