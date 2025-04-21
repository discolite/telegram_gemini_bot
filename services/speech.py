import speech_recognition as sr
from pydub import AudioSegment
import asyncio
from pathlib import Path
from loguru import logger

from utils.helpers import cleanup_temp_file, get_temp_filepath

# Убедитесь, что ffmpeg установлен в системе (sudo apt install ffmpeg)
# pydub может потребовать явно указать путь к ffmpeg/ffprobe, если он не в PATH
# from pydub.utils import which
# AudioSegment.converter = which("ffmpeg")
# AudioSegment.ffprobe = which("ffprobe")

# Инициализация распознавателя
recognizer = sr.Recognizer()

async def recognize_speech(ogg_filepath: Path) -> str | None:
    """
    Recognizes speech from an OGG audio file using Google Speech Recognition.
    Returns the recognized text or None if recognition fails.
    """
    wav_filepath = None
    try:
        # 1. Конвертация OGG в WAV (pydub требует ffmpeg)
        logger.info(f"Converting OGG to WAV: {ogg_filepath}")
        wav_filepath = get_temp_filepath("wav")

        # Запускаем конвертацию в отдельном потоке
        def convert_audio():
            audio = AudioSegment.from_ogg(ogg_filepath)
            audio.export(wav_filepath, format="wav")
        await asyncio.to_thread(convert_audio)
        logger.info(f"Successfully converted to WAV: {wav_filepath}")

        # 2. Распознавание речи из WAV файла
        logger.info(f"Recognizing speech from WAV: {wav_filepath}")
        with sr.AudioFile(str(wav_filepath)) as source:
            audio_data = await asyncio.to_thread(recognizer.record, source) # Запускаем в потоке

        # 3. Используем Google Speech Recognition (бесплатный API, требует интернет)
        # Запускаем распознавание в отдельном потоке
        def recognize_google_thread():
             try:
                 # Указываем русский язык
                 text = recognizer.recognize_google(audio_data, language="ru-RU")
                 logger.info(f"Speech recognized successfully: '{text}'")
                 return text
             except sr.UnknownValueError:
                 logger.warning("Google Speech Recognition could not understand audio")
                 return None
             except sr.RequestError as e:
                 logger.error(f"Could not request results from Google Speech Recognition service; {e}")
                 return None
             except Exception as e_rec:
                 logger.error(f"Unexpected error during speech recognition: {e_rec}")
                 return None

        recognized_text = await asyncio.to_thread(recognize_google_thread)
        return recognized_text

    except FileNotFoundError:
        logger.error(f"Audio file not found for conversion/recognition: {ogg_filepath} or {wav_filepath}")
        return None
    except Exception as e:
        logger.error(f"Error during speech recognition process: {e}")
        logger.exception(e)
        return None
    finally:
        # 4. Очистка временных файлов
        await cleanup_temp_file(ogg_filepath)
        if wav_filepath:
            await cleanup_temp_file(wav_filepath)