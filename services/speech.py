import speech_recognition as sr
from pydub import AudioSegment
import asyncio
from pathlib import Path
from loguru import logger

from utils.helpers import cleanup_temp_file, get_temp_filepath

recognizer = sr.Recognizer()

async def recognize_speech(ogg_filepath: Path) -> str | None:
    """Recognizes speech from an OGG audio file using Google Speech Recognition."""
    wav_filepath = None
    try:
        logger.info(f"Starting speech recognition process for: {ogg_filepath}")
        wav_filepath = get_temp_filepath("wav")
        def convert_audio():
            audio = AudioSegment.from_ogg(ogg_filepath)
            audio.export(wav_filepath, format="wav")
        # <--- ИЗМЕНЕНИЕ: Логи --->
        logger.debug(f"Starting OGG to WAV conversion in thread: {ogg_filepath} -> {wav_filepath}...")
        await asyncio.to_thread(convert_audio)
        logger.debug(f"Finished OGG to WAV conversion in thread: {wav_filepath}.")
        logger.info(f"Recognizing speech from WAV: {wav_filepath}")
        with sr.AudioFile(str(wav_filepath)) as source:
             # <--- ИЗМЕНЕНИЕ: Логи --->
             logger.debug("Starting recognizer.record in thread...")
             audio_data = await asyncio.to_thread(recognizer.record, source)
             logger.debug("Finished recognizer.record in thread.")
        def recognize_google_thread():
             try:
                 text = recognizer.recognize_google(audio_data, language="ru-RU")
                 logger.info(f"Speech recognized successfully: '{text}'")
                 return text
             except sr.UnknownValueError: logger.warning("Google Speech Recognition could not understand audio"); return None
             except sr.RequestError as e: logger.error(f"Google Speech Recognition request error; {e}"); return None
             except Exception as e_rec: logger.error(f"Unexpected error during speech recognition thread: {e_rec}"); return None
        # <--- ИЗМЕНЕНИЕ: Логи --->
        logger.debug("Starting recognize_google in thread...")
        recognized_text = await asyncio.to_thread(recognize_google_thread)
        logger.debug("Finished recognize_google in thread.")
        return recognized_text
    except FileNotFoundError: logger.error(f"Audio file not found: {ogg_filepath} or {wav_filepath}"); return None
    except Exception as e: logger.error(f"Error during speech recognition process: {e}"); logger.exception(e); return None
    finally:
        await cleanup_temp_file(ogg_filepath)
        if wav_filepath: await cleanup_temp_file(wav_filepath)
        logger.debug(f"Cleaned up temporary audio files for {ogg_filepath.name}")