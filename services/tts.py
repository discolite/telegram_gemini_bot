from gtts import gTTS
import asyncio
from pathlib import Path
from loguru import logger

from utils.helpers import get_temp_filepath, cleanup_temp_file

async def generate_speech(text: str, lang: str = 'ru') -> Path | None:
    """Generates an MP3 audio file from text using gTTS."""
    filepath = None # Определяем переменную заранее
    try:
        # Ограничиваем логгируемый текст
        log_text_preview = text[:80].replace('\n', ' ') + ('...' if len(text) > 80 else '')
        logger.info(f"Generating speech (gTTS, lang={lang}) for text (length: {len(text)}): '{log_text_preview}'")
        tts = gTTS(text=text, lang=lang, slow=False)
        filepath = get_temp_filepath("mp3")

        # <--- ИЗМЕНЕНИЕ: Добавляем логи до и после вызова --->
        logger.debug(f"Starting gTTS save to {filepath} in thread...")
        # Запускаем сохранение файла в отдельном потоке
        await asyncio.to_thread(tts.save, str(filepath))
        logger.debug(f"Finished gTTS save to {filepath} in thread.")

        logger.info(f"Speech generated successfully: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Error generating speech with gTTS: {e}")
        logger.exception(e)
        # Попытка удалить временный файл, если он был создан, но произошла ошибка
        if filepath:
            await cleanup_temp_file(filepath)
        return None

async def speak_and_cleanup(bot, chat_id, text: str, lang: str = 'ru'):
    """Generates speech, sends it as a voice message, and cleans up the file."""
    audio_path = await generate_speech(text, lang)
    if audio_path:
        try:
            from aiogram.types import FSInputFile # Локальный импорт для избежания цикличности
            audio_input = FSInputFile(audio_path)
            logger.debug(f"Sending generated voice message {audio_path} to {chat_id}")
            await bot.send_voice(chat_id=chat_id, voice=audio_input)
            logger.info(f"Sent generated voice message to {chat_id}")
        except Exception as send_err:
            logger.error(f"Error sending voice message to {chat_id}: {send_err}")
        finally:
            # Очистка файла происходит здесь в любом случае
            await cleanup_temp_file(audio_path)
    else:
        logger.error(f"Failed to generate speech for chat {chat_id}")
        # Можно отправить сообщение об ошибке пользователю
        try:
            await bot.send_message(chat_id, "Не удалось сгенерировать голосовое сообщение", parse_mode=None)
        except Exception as e:
             logger.error(f"Failed to send TTS generation error message to {chat_id}: {e}")