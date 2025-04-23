# --- START OF FILE services/tts.py ---

import asyncio
from pathlib import Path
from loguru import logger
from aiogram import Bot
from aiogram.types import FSInputFile
from typing import Optional

# <<< Импортируем gTTS и его ошибку >>>
from gtts import gTTS, gTTSError

# Импортируем настройки и хелперы
from config import settings # Нужен для TEMP_DIR
from utils.helpers import get_temp_filepath, cleanup_temp_file

async def generate_speech_gtts(text: str) -> Optional[Path]:
    """
    Generates speech using the gTTS library (Google Text-to-Speech).

    Args:
        text: The text to synthesize.

    Returns:
        Path to the generated MP3 file, or None if generation failed.
    """
    if not text:
        logger.warning("gTTS: Получен пустой текст для генерации речи.")
        return None

    output_mp3_path: Optional[Path] = None # Инициализируем путь
    try:
        # Генерируем уникальный путь для временного MP3 файла
        output_mp3_path = get_temp_filepath("mp3")
        # Логируем начало генерации
        log_text_preview = text[:80].replace('\n', ' ') + ('...' if len(text) > 80 else '')
        logger.info(f"Генерация речи (gTTS) для текста (длина: {len(text)}): '{log_text_preview}'")
        logger.debug(f"Вывод gTTS в файл: {output_mp3_path}")

        # Создаем объект gTTS (язык 'ru' для русского)
        gtts_obj = gTTS(text=text, lang='ru', slow=False)

        # Функция для сохранения файла (блокирующая операция)
        def save_gtts_sync():
            try:
                gtts_obj.save(str(output_mp3_path))
                return True # Успех
            except gTTSError as e:
                # Обрабатываем специфичные ошибки gTTS
                logger.error(f"Ошибка gTTS API: {e}")
                return False
            except Exception as e:
                # Обрабатываем другие ошибки при сохранении
                logger.error(f"Ошибка сохранения файла gTTS {output_mp3_path}: {e}")
                return False

        # Запускаем сохранение в отдельном потоке, чтобы не блокировать asyncio
        logger.debug("Запуск сохранения gTTS в отдельном потоке...")
        success = await asyncio.to_thread(save_gtts_sync)
        logger.debug(f"Завершение сохранения gTTS в потоке. Успех: {success}")

        # Проверяем результат сохранения
        if not success:
            await cleanup_temp_file(output_mp3_path) # Удаляем файл, если сохранение не удалось
            return None

        # Дополнительная проверка: файл существует и не пустой?
        if not output_mp3_path.exists() or output_mp3_path.stat().st_size == 0:
           logger.error(f"Сохранение gTTS сообщило об успехе, но выходной файл отсутствует или пуст: {output_mp3_path}")
           await cleanup_temp_file(output_mp3_path) # Удаляем некорректный файл
           return None

        # Если все успешно
        logger.info(f"Речь успешно сгенерирована в {output_mp3_path}")
        return output_mp3_path

    except Exception as e:
        # Ловим любые другие неожиданные ошибки на уровне обертки
        logger.error(f"Неожиданная ошибка во время генерации gTTS: {e}")
        logger.exception(e)
        # Пытаемся удалить временный файл, если он был создан
        if output_mp3_path:
             await cleanup_temp_file(output_mp3_path)
        return None

async def speak_and_cleanup(bot: Bot, chat_id: int, text: str):
    """Generates speech using gTTS, sends it as a voice message, and cleans up the temp file."""
    audio_path: Optional[Path] = None # Указываем тип явно
    try:
        # <<< ИЗМЕНЕНИЕ: Вызываем функцию генерации gTTS >>>
        audio_path = await generate_speech_gtts(text)

        if audio_path:
            try:
                # Отправляем .mp3 как голосовое сообщение
                # Telegram обычно справляется с MP3 в send_voice
                audio_input = FSInputFile(audio_path, filename=f"{audio_path.stem}.mp3")
                logger.debug(f"Отправка сгенерированного gTTS голосового сообщения {audio_path} в {chat_id}")
                await bot.send_voice(chat_id=chat_id, voice=audio_input)
                logger.info(f"Отправлено сгенерированное gTTS голосовое сообщение в {chat_id}")
            except Exception as send_err:
                logger.error(f"Ошибка отправки сгенерированного голосового сообщения gTTS в чат {chat_id}: {send_err}")
                # Можно уведомить пользователя об ошибке отправки
                # try: await bot.send_message(chat_id, "Ошибка при отправке аудио.", parse_mode=None)
                # except Exception: pass
        else:
            # Если генерация gTTS не удалась
            logger.error(f"Генерация речи gTTS не удалась для чата {chat_id}")
            try:
                # Уведомляем пользователя
                await bot.send_message(chat_id, "Не удалось сгенерировать аудиоответ.", parse_mode=None)
            except Exception as notify_err:
                logger.error(f"Не удалось уведомить пользователя об ошибке генерации gTTS: {notify_err}")

    except Exception as e:
        # Общая ошибка в процессе озвучки
        logger.error(f"Ошибка в speak_and_cleanup (gTTS) для чата {chat_id}: {e}")
        try:
            # Уведомляем пользователя об общей ошибке
            await bot.send_message(chat_id, "Произошла ошибка при обработке озвучки.", parse_mode=None)
        except Exception as notify_err:
            logger.error(f"Не удалось уведомить пользователя об общей ошибке TTS: {notify_err}")
    finally:
        # Гарантированная очистка временного файла .mp3
        if audio_path:
            await cleanup_temp_file(audio_path)

# --- END OF FILE services/tts.py ---