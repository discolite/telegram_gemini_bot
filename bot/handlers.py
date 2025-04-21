# --- START OF FILE bot/handlers.py ---

import asyncio
import os
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, FSInputFile, InputFile, User
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from loguru import logger
from typing import Optional, Dict
from pathlib import Path

# Импортируем настройки и сервисы
from config import settings
from services import (
    gemini,
    weather,
    speech,
    image_analyzer, # Используется для анализа фото
    file_handler,   # Используется для анализа документов
    database,
    tts,
    translator,
)
# Импортируем хелперы
from utils.helpers import (
    get_temp_filepath,
    cleanup_temp_file,
    escape_markdown_v2,
    is_ocr_potentially_useful # Функция остается, т.к. OCR используется для логов/истории
)
# Импортируем клавиатуры
from .keyboards import get_mood_keyboard

router = Router()

# --- Вспомогательная функция для получения user_id ---
def get_user_id(message: Optional[Message] = None, callback_query: Optional[CallbackQuery] = None) -> Optional[int]:
    """Safely extracts user_id from Message or CallbackQuery."""
    user: Optional[User] = None
    if message and message.from_user: user = message.from_user
    elif callback_query and callback_query.from_user: user = callback_query.from_user
    if user: return user.id
    logger.warning("Could not extract user_id from event.")
    return None

# --- Command Handlers ---

@router.message(Command("start", "help"))
async def handle_start(message: Message):
    """Handles /start and /help commands."""
    user_id = get_user_id(message=message)
    if not user_id: return
    user_name = message.from_user.full_name if message.from_user else "Пользователь"
    await database.get_user_settings(user_id) # Инициализируем или получаем настройки
    help_text = (
        f"Привет, {escape_markdown_v2(user_name)}\!\n\n"
        "Я многофункциональный AI\-бот\. Вот что я умею:\n\n"
        "🧠 **Общение:** Просто напиши мне, и я отвечу с помощью Google Gemini\. Можешь спросить погоду, написав `погода <город>`\.\n" # Обновил текст
        "🗣️ **Голосовые сообщения:** Отправь мне голосовое, я его распознаю и отвечу\.\n"
        "🖼️ **Анализ изображений:** Отправь картинку, я опишу её с помощью Gemini Vision \(текст с картинки не выводится\)\.\n"
        "📄 **Обработка файлов:** Отправь \.txt, \.pdf, \.csv, \.xlsx или \.docx, и я проанализирую содержимое\.\n"
        "☀️ **Погода (команда):** `/weather <город>` \(по умолчанию Москва\)\.\n"
        "🎭 **Стиль общения:** `/mood` \- выбери мой стиль \(дружелюбный, проф\., саркастичный\)\.\n"
        "🔊 **Озвучка:** \n"
        "   \- `/speak <текст>` \- озвучу твой текст\.\n"
        "   \- `/toggle_speak` \- вкл/выкл озвучку моих ответов\.\n"
        "🌐 **Перевод:** `/translate <текст> [язык]` \(напр\., `/translate hello ru`\)\. Я также могу переводить через Gemini \(попроси меня\)\.\n\n"
        f"Твой ID: `{user_id}`\n"
        "Настройки хранятся для каждого пользователя\."
    )
    await message.answer(help_text, parse_mode="MarkdownV2")

@router.message(Command("weather"))
async def handle_weather(message: Message, command: CommandObject, bot: Bot):
    """Handles /weather command."""
    user_id = get_user_id(message=message)
    if not user_id: return
    city_input = command.args if command.args else "Moscow"
    logger.info(f"User {user_id} requested weather for '{city_input}' using /weather command")
    processing_msg = await message.answer(f"Узнаю погоду для '{escape_markdown_v2(city_input)}'...", parse_mode=None)
    weather_report = await weather.get_weather(city_input)
    if weather_report:
        final_parse_mode: Optional[str] = "MarkdownV2"
        error_keywords = ["не найден", "ошибка", "сервис погоды недоступен", "таймаут", "invalid", "not found"]
        if any(keyword.lower() in weather_report.lower() for keyword in error_keywords):
            final_parse_mode = None

        try:
            await bot.edit_message_text(weather_report, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=final_parse_mode, disable_web_page_preview=True)
        except TelegramBadRequest as e:
             if "message is not modified" in str(e): logger.debug(f"Weather report for {city_input} was not modified.")
             else:
                 logger.error(f"Error editing weather message (parse_mode={final_parse_mode}): {e}. Report: '{weather_report[:200]}...'")
                 try:
                     await bot.edit_message_text(weather_report, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None, disable_web_page_preview=True)
                 except Exception as fallback_edit_err:
                      logger.error(f"Failed to edit weather message even without parse_mode: {fallback_edit_err}")
                      await message.answer(weather_report, parse_mode=None, disable_web_page_preview=True)
        except Exception as e:
             logger.error(f"Unexpected error editing weather message: {e}")
             await message.answer(weather_report, parse_mode=final_parse_mode, disable_web_page_preview=True)
             try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
             except Exception: pass
    else:
        await bot.edit_message_text("Не удалось получить информацию о погоде.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)

@router.message(Command("mood"))
async def handle_mood(message: Message):
    """Handles /mood command, shows mood selection keyboard."""
    user_id = get_user_id(message=message)
    if not user_id: return
    settings_data = await database.get_user_settings(user_id)
    current_mood = settings_data.get('mood', settings.DEFAULT_MOOD)
    await message.answer(f"Выбери мой стиль общения\. Текущий: `{escape_markdown_v2(current_mood)}`", reply_markup=get_mood_keyboard(), parse_mode="MarkdownV2")

@router.message(Command("speak"))
async def handle_speak(message: Message, command: CommandObject, bot: Bot):
    """Handles /speak command for TTS."""
    user_id = get_user_id(message=message)
    if not user_id: return
    text_to_speak = command.args
    if not text_to_speak:
        await message.answer("Пожалуйста, укажи текст для озвучивания после команды `/speak`\.", parse_mode="MarkdownV2")
        return

    logger.info(f"User {user_id} requested to speak: '{text_to_speak[:50]}...'")
    processing_msg = await message.answer("Генерирую аудио...", parse_mode=None)
    audio_path: Optional[Path] = None
    try:
        audio_path = await tts.generate_speech(text_to_speak)
        if audio_path:
            audio_input = FSInputFile(audio_path)
            await message.reply_voice(voice=audio_input)
            try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
            except TelegramBadRequest as del_e: logger.warning(f"Could not delete 'generating audio' message: {del_e}")
            logger.info(f"Sent generated voice message for /speak to {user_id}")
        else:
            logger.error(f"Failed to generate speech for /speak for user {user_id}")
            await bot.edit_message_text("Не удалось сгенерировать аудио.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)
    except Exception as send_err:
        logger.error(f"Error handling /speak for user {user_id}: {send_err}")
        await bot.edit_message_text("Ошибка при отправке аудио.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)
    finally:
        if audio_path:
            await cleanup_temp_file(audio_path)

@router.message(Command("toggle_speak"))
async def handle_toggle_speak(message: Message):
    """Handles /toggle_speak command."""
    user_id = get_user_id(message=message)
    if not user_id: return
    new_state = await database.toggle_speak_mode(user_id)
    state_text = "ВКЛЮЧЕНА" if new_state else "ВЫКЛЮЧЕНА"
    logger.info(f"User {user_id} toggled speak mode to {state_text}")
    await message.answer(f"🔊 Озвучка моих ответов теперь **{state_text}**\.", parse_mode="MarkdownV2")

@router.message(Command("translate"))
async def handle_translate(message: Message, command: CommandObject, bot: Bot):
    """Handles /translate command."""
    user_id = get_user_id(message=message)
    if not user_id: return
    if not command.args:
        await message.answer("Использование: `/translate <текст> [код\_языка]`\nПример: `/translate Привет мир en`", parse_mode="MarkdownV2")
        return

    args_list = command.args.split()
    target_lang = 'ru' # По умолчанию русский
    text_to_translate = ""
    notification_message = None

    if len(args_list) >= 2:
        potential_lang = args_list[-1].lower()
        lang_code = translator.get_lang_code(potential_lang)
        if lang_code and (len(potential_lang) <= 3 or lang_code != potential_lang):
            target_lang = lang_code
            text_to_translate = " ".join(args_list[:-1])
            logger.info(f"User {user_id} requested translation to '{target_lang}'. Original lang input: '{potential_lang}'. Text: '{text_to_translate[:50]}...'")
        else:
            text_to_translate = command.args
            notification_message = f"Код языка не указан или не распознан, перевожу на русский ('ru')"
            logger.info(f"User {user_id} requested translation (defaulting to 'ru'). Text: '{text_to_translate[:50]}...'")
    else:
         text_to_translate = command.args
         notification_message = f"Код языка не указан, перевожу на русский ('ru')"
         logger.info(f"User {user_id} requested translation (defaulting to 'ru'). Text: '{text_to_translate[:50]}...'")

    if not text_to_translate:
         await message.answer("Не указан текст для перевода.", parse_mode=None)
         return

    if notification_message:
        await message.answer(notification_message, parse_mode=None)

    processing_msg = await message.answer(f"Перевожу на язык '{target_lang}'...", parse_mode=None)
    translated_text = await translator.translate_text_googletrans(text_to_translate, target_lang)

    if translated_text and "ошибка" not in translated_text.lower() and "error" not in translated_text.lower():
        response_text = (f"**Оригинал:**\n{escape_markdown_v2(text_to_translate)}\n\n"
                         f"**Перевод ({target_lang}):**\n{escape_markdown_v2(translated_text)}")
        try:
            await bot.edit_message_text(response_text, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode="MarkdownV2")
        except TelegramBadRequest as e:
             if "message is not modified" not in str(e):
                 logger.error(f"Error editing translation message (MarkdownV2): {e}")
                 try:
                     fallback_text = f"Оригинал:\n{text_to_translate}\n\nПеревод ({target_lang}):\n{translated_text}"
                     await bot.edit_message_text(fallback_text, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)
                 except Exception as fallback_edit_err:
                     logger.error(f"Failed to edit translation fallback: {fallback_edit_err}")
                     await message.answer(response_text, parse_mode="MarkdownV2")
        except Exception as e:
             logger.error(f"Unexpected error editing translation message: {e}")
             await message.answer(response_text, parse_mode="MarkdownV2")
             try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
             except Exception: pass
    else:
        logger.error(f"Translation failed for user {user_id}. Fallback response: {translated_text}")
        fail_message = translated_text if translated_text else "Не удалось выполнить перевод."
        await bot.edit_message_text(fail_message, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)

# --- Callback Query Handlers ---

@router.callback_query(F.data.startswith("set_mood:"))
async def process_mood_callback(callback_query: CallbackQuery, bot: Bot):
    """Handles mood selection callbacks."""
    user_id = get_user_id(callback_query=callback_query)
    if not user_id:
        await callback_query.answer("Ошибка: не удалось определить пользователя.", show_alert=True)
        return

    mood = callback_query.data.split(":")[1]
    await database.update_user_mood(user_id, mood)
    logger.info(f"User {user_id} set mood to {mood}")
    await callback_query.answer(f"Стиль общения изменен на: {mood}")
    try:
        await bot.edit_message_text(f"✅ Стиль общения изменен на: `{escape_markdown_v2(mood)}`",
                                    chat_id=callback_query.message.chat.id,
                                    message_id=callback_query.message.message_id,
                                    reply_markup=None,
                                    parse_mode="MarkdownV2")
    except TelegramBadRequest as e: logger.warning(f"Failed to edit mood message (might be old or unchanged): {e}")
    except Exception as e: logger.error(f"Unexpected error editing mood message: {e}")

# --- Message Handlers ---

@router.message(F.voice)
async def handle_voice_message(message: Message, bot: Bot):
    """Handles voice messages."""
    user_id = get_user_id(message=message)
    if not user_id: return
    logger.debug(f"Entered handle_voice_message for user {user_id}")
    logger.info(f"Received voice message from user {user_id} (duration: {message.voice.duration}s)")
    processing_msg = await message.reply("Обрабатываю голосовое сообщение...", parse_mode=None)

    ogg_filepath = get_temp_filepath("ogg")
    try:
        await bot.download(message.voice, destination=str(ogg_filepath))
        logger.debug(f"Voice message saved to {ogg_filepath}")
    except Exception as e:
        logger.error(f"Failed to download voice message from {user_id}: {e}")
        await bot.edit_message_text("Ошибка при скачивании голосового сообщения.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)
        await cleanup_temp_file(ogg_filepath)
        return

    try:
        await bot.edit_message_text("Распознаю речь...", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)
    except TelegramBadRequest: pass

    recognized_text = await speech.recognize_speech(ogg_filepath) # recognize_speech handles cleanup

    if recognized_text is not None:
        logger.info(f"User {user_id} voice recognized as: '{recognized_text}'")
        try:
            await bot.edit_message_text(f"Распознанный текст: \"{escape_markdown_v2(recognized_text)}\"\n\nГенерирую ответ\.\.\.",
                                        chat_id=processing_msg.chat.id,
                                        message_id=processing_msg.message_id,
                                        parse_mode="MarkdownV2")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e): logger.error(f"Error editing recognized text message: {e}")

        await database.add_message(user_id, 'user', recognized_text)
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        response_text = await gemini.generate_text_response(user_id, recognized_text)

        if response_text:
            await database.add_message(user_id, 'model', response_text)
            await send_response(bot, message.chat.id, user_id, response_text)
            try:
                await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
            except TelegramBadRequest as del_e: logger.warning(f"Could not delete processing message after voice reply: {del_e}")
            except Exception as del_e: logger.error(f"Unexpected error deleting processing message: {del_e}")
        else:
            logger.error(f"Failed to generate Gemini response for recognized voice from user {user_id}")
            try:
                await bot.edit_message_text(f"Распознанный текст: \"{escape_markdown_v2(recognized_text)}\"\n\nНе удалось сгенерировать ответ от AI\.",
                                            chat_id=processing_msg.chat.id,
                                            message_id=processing_msg.message_id,
                                            parse_mode="MarkdownV2")
            except TelegramBadRequest: pass
    else:
        logger.warning(f"Could not recognize speech from user {user_id} (recognize_speech returned None)")
        await bot.edit_message_text("Не удалось распознать речь в вашем сообщении.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)

# --- Обработчик Фото ---
@router.message(F.photo)
async def handle_photo_message(message: Message, bot: Bot):
    """Handles photo messages, sending only Vision analysis to the user."""
    user_id = get_user_id(message=message)
    if not user_id: return
    photo_id = message.photo[-1].file_unique_id
    logger.info(f"Received photo '{photo_id}' from user {user_id}")
    processing_msg = await message.reply("Анализирую изображение...", parse_mode=None)

    photo = message.photo[-1]
    temp_filename = f"{user_id}_{photo.file_unique_id}.jpg"
    jpg_filepath = settings.TEMP_DIR / temp_filename

    try:
        await bot.download(photo, destination=str(jpg_filepath))
        logger.debug(f"Photo '{photo_id}' saved to {jpg_filepath}")
    except Exception as e:
        logger.error(f"Failed to download photo '{photo_id}' from {user_id}: {e}")
        await bot.edit_message_text("Ошибка при скачивании изображения.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)
        await cleanup_temp_file(jpg_filepath)
        return

    analysis_result = await image_analyzer.analyze_image(jpg_filepath, user_id) # jpg_filepath удаляется внутри
    ocr_text = analysis_result.get("ocr_text")
    vision_analysis = analysis_result.get("vision_analysis")

    response_parts = []
    analysis_summary_for_history = f"[Анализ изображения '{photo_id}'] "

    if vision_analysis:
        escaped_vision_analysis = escape_markdown_v2(vision_analysis)
        response_parts.append(escaped_vision_analysis) # Добавляем ТОЛЬКО Vision
        analysis_summary_for_history += f"Vision: '{vision_analysis[:100]}...'. "
        logger.info(f"Gemini Vision analysis received for photo '{photo_id}' user {user_id}.")
    else:
        response_parts.append("_Не удалось получить описание изображения \(Gemini Vision\)\._")
        analysis_summary_for_history += "Vision: Ошибка/Нет. "
        logger.warning(f"Gemini Vision analysis failed or returned empty for photo '{photo_id}' user {user_id}.")

    # Логируем OCR, но не добавляем в response_parts
    if ocr_text is not None and ocr_text != "":
        analysis_summary_for_history += f"OCR: '{ocr_text[:100]}...'. "
        logger.info(f"OCR text found (but not shown to user {user_id}) for photo '{photo_id}': length {len(ocr_text)}")
    elif ocr_text == "":
        analysis_summary_for_history += "OCR: Текст не найден. "
        logger.debug(f"No text found (OCR) for photo '{photo_id}' user {user_id}.")
    else:
        analysis_summary_for_history += "OCR: Ошибка. "
        logger.warning(f"OCR returned None (error) for photo '{photo_id}' user {user_id}.")

    # Запись в БД
    await database.add_message(user_id, 'user', f"[Отправлено изображение '{photo_id}']")
    await database.add_message(user_id, 'model', analysis_summary_for_history.strip())

    # Формирование и отправка ответа
    final_response = "\n\n".join(response_parts).strip()
    parse_mode_final: Optional[str] = "MarkdownV2" # Всегда используем Markdown, т.к. есть или Vision или сообщение об ошибке в курсиве

    try:
        await message.reply(final_response, parse_mode=parse_mode_final, disable_web_page_preview=True)
        logger.info(f"Successfully sent formatted image analysis response (Vision only) to user {user_id}")
        try:
            await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        except Exception as del_err:
            logger.warning(f"Could not delete processing message after image reply: {del_err}")

    except TelegramBadRequest as e:
        logger.error(f"Telegram API error sending formatted analysis (parse_mode={parse_mode_final}): {e}. Response: {final_response[:200]}...")
        try:
            fallback_text = vision_analysis if vision_analysis else "Не удалось получить описание изображения."
            await message.reply(fallback_text, parse_mode=None, disable_web_page_preview=True)
            logger.info(f"Successfully sent fallback unformatted analysis (Vision only) to user {user_id}")
            try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
            except Exception: pass
        except Exception as fallback_err:
             logger.error(f"Failed to send fallback unformatted analysis: {fallback_err}")
             try: await message.reply("Произошла ошибка при отправке результата анализа изображения.", parse_mode=None)
             except Exception: pass
             try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
             except Exception: pass
    except Exception as e:
        logger.error(f"General error sending final image analysis response: {e}")
        logger.exception(e)
        try: await message.reply("Произошла очень неожиданная ошибка при отправке результата анализа изображения.", parse_mode=None)
        except Exception: pass
        try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        except Exception: pass

# --- Обработчик Документов ---
@router.message(F.document)
async def handle_document_message(message: Message, bot: Bot):
    """Handles document messages (txt, pdf, csv, xlsx, docx)."""
    user_id = get_user_id(message=message)
    if not user_id: return
    doc = message.document
    filename = doc.file_name if doc.file_name else f"file_{doc.file_unique_id}"
    mime_type = doc.mime_type
    file_size = doc.file_size if doc.file_size else 0
    file_id = doc.file_id

    logger.info(f"Received document '{filename}' from user {user_id} (Type: {mime_type}, Size: {file_size})")
    processing_msg = await message.reply(f"Получил файл '{escape_markdown_v2(filename)}'. Обрабатываю...", parse_mode=None)

    safe_filename_part = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in filename)
    temp_filename = f"{user_id}_{file_id}_{safe_filename_part}"; max_len = 150
    if len(temp_filename) > max_len:
         name_part, ext_part = os.path.splitext(temp_filename)
         ext_len = len(ext_part)
         name_part = name_part[:max_len - ext_len - 1]
         temp_filename = name_part + ext_part
    doc_filepath = settings.TEMP_DIR / temp_filename

    try:
        await bot.download(doc, destination=str(doc_filepath))
        logger.debug(f"Document '{filename}' saved to {doc_filepath}")
    except Exception as e:
        logger.error(f"Failed to download document '{filename}' from {user_id}: {e}")
        await bot.edit_message_text(f"Ошибка при скачивании файла '{escape_markdown_v2(filename)}'.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)
        await cleanup_temp_file(doc_filepath)
        return

    try:
        await bot.edit_message_text(f"Анализирую содержимое файла '{escape_markdown_v2(filename)}'...", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)
    except TelegramBadRequest: pass

    process_result = await file_handler.process_file(doc_filepath, filename, mime_type, file_size) # Удаление файла внутри

    if process_result:
        status_message, analysis_result = process_result
        logger.info(f"File processing result for '{filename}': Status='{status_message}', Analysis received={analysis_result is not None}")

        response_parts = [
            f"**Файл:** `{escape_markdown_v2(filename)}`",
            f"**Статус:** {escape_markdown_v2(status_message)}"
        ]
        user_history_message = f"[Отправлен файл для анализа: {filename}]"
        model_history_message = f"[Статус обработки: {status_message}]"

        if analysis_result:
            response_parts.append(f"**Анализ содержимого \(Gemini\):**\n{escape_markdown_v2(analysis_result)}")
            model_history_message += f" [Анализ Gemini: {analysis_result[:150]}...]"
        # Не добавляем доп. сообщение, если анализ не удался, т.к. статус уже это отражает
        # (например, "Не удалось получить анализ содержимого от AI.")

        final_response = "\n\n".join(response_parts).strip()
        await database.add_message(user_id, 'user', user_history_message)
        await database.add_message(user_id, 'model', model_history_message)

        await send_response(bot, message.chat.id, user_id, final_response, parse_mode="MarkdownV2")

        try:
            await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        except TelegramBadRequest as del_e: logger.warning(f"Could not delete processing message after file reply: {del_e}")
        except Exception as del_e: logger.error(f"Unexpected error deleting processing message: {del_e}")

    else:
        logger.error(f"File processing failed unexpectedly for '{filename}' user {user_id} (process_file returned None)")
        fail_msg = f"Критическая ошибка при обработке файла '{escape_markdown_v2(filename)}'."
        await bot.edit_message_text(fail_msg, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)
        await database.add_message(user_id, 'user', f"[Отправлен файл для анализа: {filename}]")
        await database.add_message(user_id, 'model', "[Критическая ошибка обработки файла]")

# --- Обработчик Текстовых Сообщений ---
# <<< ИЗМЕНЕНИЕ: Добавлена проверка на "погода <город>" >>>
@router.message(F.text)
async def handle_text_message(message: Message, bot: Bot):
    """
    Handles regular text messages.
    Checks if the message is a weather request (starts with 'погода ').
    If not, processes it using Gemini.
    """
    user_id = get_user_id(message=message)
    if not user_id: return
    user_text = message.text
    if not user_text or user_text.isspace():
        logger.debug(f"Ignoring empty/whitespace message from user {user_id}")
        return

    lower_text = user_text.lower()
    weather_keyword = "погода "

    # --- Проверка на запрос погоды ---
    if lower_text.startswith(weather_keyword):
        city_input = user_text[len(weather_keyword):].strip()
        if not city_input:
            city_input = "Moscow" # Город по умолчанию
            logger.info(f"User {user_id} requested weather via text, defaulting to Moscow")
        else:
            logger.info(f"User {user_id} requested weather for '{city_input}' via text")

        processing_msg = await message.reply(f"Узнаю погоду для '{escape_markdown_v2(city_input)}'...", parse_mode=None)
        weather_report = await weather.get_weather(city_input)

        if weather_report:
            final_parse_mode: Optional[str] = "MarkdownV2"
            error_keywords = ["не найден", "ошибка", "сервис погоды недоступен", "таймаут", "invalid", "not found"]
            if any(keyword.lower() in weather_report.lower() for keyword in error_keywords):
                final_parse_mode = None

            try:
                await bot.edit_message_text(weather_report,
                                            chat_id=processing_msg.chat.id,
                                            message_id=processing_msg.message_id,
                                            parse_mode=final_parse_mode,
                                            disable_web_page_preview=True)
            except TelegramBadRequest as e:
                 if "message is not modified" in str(e): logger.debug(f"Weather report for {city_input} was not modified.")
                 else:
                     logger.error(f"Error editing weather message (parse_mode={final_parse_mode}): {e}. Report: '{weather_report[:200]}...'")
                     try:
                         await bot.edit_message_text(weather_report, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None, disable_web_page_preview=True)
                     except Exception as fallback_edit_err:
                          logger.error(f"Failed to edit weather message even without parse_mode: {fallback_edit_err}")
                          await message.reply(weather_report, parse_mode=None, disable_web_page_preview=True)
                          try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
                          except Exception: pass
            except Exception as e:
                 logger.error(f"Unexpected error sending weather message: {e}")
                 await message.reply(weather_report, parse_mode=final_parse_mode, disable_web_page_preview=True)
                 try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
                 except Exception: pass
        else:
            await bot.edit_message_text("Не удалось получить информацию о погоде.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None)

        return # <-- ВАЖНО: Прекращаем обработку здесь

    # --- Если это НЕ запрос погоды, обрабатываем через Gemini ---
    else:
        logger.info(f"Received non-weather text message from user {user_id}: '{user_text[:100]}...'")
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        await database.add_message(user_id, 'user', user_text)
        response_text = await gemini.generate_text_response(user_id, user_text)

        if response_text:
            await database.add_message(user_id, 'model', response_text)
            await send_response(bot, message.chat.id, user_id, response_text)
        else:
            logger.error(f"Failed to generate Gemini response for user {user_id}")
            error_response = "Извините, не могу сейчас ответить. Попробуйте позже."
            await message.reply(error_response, parse_mode=None)
            await database.add_message(user_id, 'model', "[Ошибка генерации ответа AI]")


# --- Вспомогательная функция для отправки ответа ---
async def send_response(bot: Bot, chat_id: int, user_id: int, text: str, parse_mode: Optional[str] = None):
    """Sends response as text or voice based on user settings, handling long messages and errors."""
    text_to_send = text
    speak_enabled = False

    try:
        speak_enabled = await database.get_speak_enabled(user_id)

        if speak_enabled:
            logger.info(f"Sending voice response to user {user_id}")
            await tts.speak_and_cleanup(bot, chat_id, text)
        else:
            logger.info(f"Sending text response to user {user_id} with parse_mode={parse_mode}")
            max_len = 4096
            if len(text_to_send) <= max_len:
                 await bot.send_message(chat_id, text_to_send, parse_mode=parse_mode, disable_web_page_preview=True)
            else:
                 logger.warning(f"Response for user {user_id} is too long ({len(text_to_send)} chars). Sending in parts.")
                 parts = []
                 current_part = ""
                 lines = text_to_send.split('\n')
                 for i, line in enumerate(lines):
                     if len(current_part) + len(line) + 1 <= max_len:
                         current_part += line + "\n"
                     else:
                         if current_part:
                             parts.append(current_part.strip())
                         if len(line) > max_len:
                             for j in range(0, len(line), max_len):
                                 chunk = line[j:j+max_len]
                                 if chunk: parts.append(chunk)
                             current_part = ""
                         else:
                             current_part = line + "\n"
                 if current_part.strip():
                     parts.append(current_part.strip())

                 for i, part in enumerate(parts):
                     if not part: continue
                     logger.debug(f"Sending part {i+1}/{len(parts)} ({len(part)} chars) to chat {chat_id}")
                     await bot.send_message(chat_id, part, parse_mode=parse_mode, disable_web_page_preview=True)
                     if i < len(parts) - 1:
                         await asyncio.sleep(0.8)

    except TelegramBadRequest as e:
         logger.error(f"Telegram API error sending response to user {user_id} (chat {chat_id}) with parse_mode={parse_mode}: {e}")
         if parse_mode:
             logger.warning(f"Retrying to send message to {user_id} without parse_mode.")
             try:
                 await send_response(bot, chat_id, user_id, text, parse_mode=None)
                 logger.info("Successfully sent response without formatting as fallback.")
             except Exception as fallback_e:
                  logger.error(f"Failed to send fallback unformatted message to chat {chat_id}: {fallback_e}")
         else:
             logger.error(f"Failed to send message/voice to chat {chat_id}. Error: {e}")
             if not speak_enabled:
                try: await bot.send_message(chat_id, "Произошла ошибка при отправке ответа.", parse_mode=None)
                except Exception: pass

    except Exception as e:
        logger.error(f"General error sending response to user {user_id} (chat {chat_id}): {e}")
        logger.exception(e)
        if not speak_enabled:
            try: await bot.send_message(chat_id, "Произошла непредвиденная ошибка при отправке ответа.", parse_mode=None)
            except Exception: pass

# --- END OF FILE bot/handlers.py ---