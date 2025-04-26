# /home/telegram_gemini_bot/bot/handlers.py

import asyncio
import os
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
# --- ИЗМЕНЕНИЕ: Импортируем ParseMode ---
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, FSInputFile, InputFile, User, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from loguru import logger
from typing import Optional, Dict, Tuple, Union
from pathlib import Path
import re # Добавлен импорт re для fallback в help

# Импортируем настройки и сервисы
from config import settings
from services import (
    gemini,
    weather,
    speech,
    image_analyzer,
    file_handler,
    database,
    tts,
    translator, # Оставляем на случай, если Gemini попросит перевести
)
# Импортируем хелперы
from utils.helpers import (
    get_temp_filepath,
    cleanup_temp_file,
    escape_markdown_v2,
    is_ocr_potentially_useful,
    format_response_html, # <<< ДОБАВЛЕН ИМПОРТ ФОРМАТТЕРА >>>
    escape_html # <<< ДОБАВЛЕН ИМПОРТ HTML ЭСКЕЙПЕРА >>>
)
# Импортируем клавиатуры
from .keyboards import get_mood_keyboard

router = Router()

# --- Вспомогательные функции (без изменений) ---
def get_user_id(message: Optional[Message] = None, callback_query: Optional[CallbackQuery] = None) -> Optional[int]:
    user: Optional[User] = None
    if message and message.from_user: user = message.from_user
    elif callback_query and callback_query.from_user: user = callback_query.from_user
    if user: return user.id
    logger.warning("Could not extract user_id from event.")
    return None

def is_admin(user_id: int) -> bool:
    auth_list = getattr(settings, 'AUTHORIZED_USERS', [])
    if not isinstance(auth_list, (list, tuple)): return False
    return user_id in auth_list

# --- Command Handlers ---

@router.message(Command("start", "help"))
async def handle_start(message: Message):
    user_id = get_user_id(message=message)
    if not user_id: return
    user_name = message.from_user.full_name if message.from_user else "Пользователь"
    await database.get_user_settings(user_id)

    # Используем HTML для большей гибкости и избежания проблем с MarkdownV2
    help_text = (
        f"Привет, <b>{escape_html(user_name)}</b>!\n\n"
        "Я многофункциональный AI-бот. Вот что я умею:\n\n"
        "🧠 <b>Общение:</b> Просто напиши мне, и я отвечу с помощью Google Gemini. Можешь спросить погоду, написав <code>погода <город></code>.\n"
        "🗣️ <b>Голосовые сообщения:</b> Отправь мне голосовое, я его распознаю и отвечу.\n"
        "🖼️ <b>Анализ изображений:</b> Отправь картинку, я опишу её с помощью Gemini Vision. Если хочешь получить и текст с картинки (OCR), спроси об этом после анализа.\n"
        "📄 <b>Обработка файлов:</b> Отправь .txt, .pdf, .csv, .xlsx или .docx, и я проанализирую содержимое. Задавай вопросы по тексту после анализа.\n"
        "☀️ <b>Погода (команда):</b> <code>/weather <город></code> (по умолчанию Москва).\n"
        "🎭 <b>Стиль общения:</b> /mood - выбери мой стиль (дружелюбный, проф., саркастичный).\n"
        "🌐 <b>Перевод и Озвучка:</b>\n"
        "   - Попроси меня <b>перевести</b> текст (напр., <code>переведи 'hello' на немецкий</code>).\n"
        "   - Попроси меня <b>озвучить</b> текст (напр., <code>озвучь 'привет мир'</code> или <code>скажи 'я бот'</code>).\n"
        "   - <code>/toggle_speak</code> - вкл/выкл автоматическую озвучку моих ответов.\n\n"
        f"Твой ID: <code>{user_id}</code>\n"
        "<i>Настройки хранятся для каждого пользователя.</i>"
    )
    if is_admin(user_id):
        help_text += "\n\n<b>Админ-команды:</b>\n<code>/admin</code> <code>/status</code> <code>/restart</code>"

    try:
        await message.answer(help_text, parse_mode=ParseMode.HTML)
    except TelegramBadRequest as e:
        logger.error(f"Failed to send help message with HTML: {e}")
        help_text_plain = re.sub('<[^<]+?>', '', help_text) # Убираем HTML теги для fallback
        try:
            await message.answer(help_text_plain, parse_mode=None)
            logger.info("Sent help message without HTML as fallback.")
        except Exception as fallback_e:
            logger.error(f"Failed to send plain help message: {fallback_e}")

@router.message(Command("weather"))
async def handle_weather(message: Message, command: CommandObject, bot: Bot):
    user_id = get_user_id(message=message)
    if not user_id: return
    city_input = command.args if command.args else "Moscow"
    logger.info(f"User {user_id} requested weather for '{city_input}' using /weather command")
    processing_msg = await message.reply(f"<i>Узнаю погоду для '{escape_html(city_input)}'...</i>", parse_mode=ParseMode.HTML)

    # Предполагаем, что weather.get_weather возвращает форматированный MarkdownV2 или текст ошибки
    weather_report_markdown = await weather.get_weather(city_input)

    if weather_report_markdown:
        is_error_report = any(keyword.lower() in weather_report_markdown.lower() for keyword in ["не найден", "ошибка", "сервис погоды недоступен", "таймаут", "invalid", "not found"])
        final_parse_mode = ParseMode.MARKDOWN_V2 if not is_error_report else None

        try:
            await bot.edit_message_text(weather_report_markdown, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=final_parse_mode, disable_web_page_preview=True)
        except TelegramBadRequest as e:
             if "message is not modified" in str(e): logger.debug(f"Weather report for {city_input} was not modified.")
             elif "can't parse entities" in str(e).lower() and final_parse_mode == ParseMode.MARKDOWN_V2:
                 logger.error(f"Error editing weather message with MarkdownV2: {e}. Retrying without parse mode.")
                 plain_text_report = re.sub(r'[\\`*_\[\]()~>#+\-=|{}.!]', '', weather_report_markdown)
                 await bot.edit_message_text(plain_text_report, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None, disable_web_page_preview=True)
             else:
                 logger.error(f"Unhandled TelegramBadRequest editing weather message: {e}")
                 await message.reply(weather_report_markdown, parse_mode=None, disable_web_page_preview=True) # Отправляем новым сообщением
                 try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
                 except Exception: pass
        except Exception as e:
             logger.error(f"Unexpected error sending/editing weather message: {e}")
             await message.reply(weather_report_markdown, parse_mode=None, disable_web_page_preview=True)
             try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
             except Exception: pass
    else:
        await bot.edit_message_text("❌ Не удалось получить информацию о погоде.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)


@router.message(Command("mood"))
async def handle_mood(message: Message):
    user_id = get_user_id(message=message)
    if not user_id: return
    settings_data = await database.get_user_settings(user_id)
    current_mood = settings_data.get('mood', settings.DEFAULT_MOOD)
    await message.answer(f"Выбери мой стиль общения. Текущий: <code>{escape_html(current_mood)}</code>",
                         reply_markup=get_mood_keyboard(),
                         parse_mode=ParseMode.HTML)

@router.message(Command("toggle_speak"))
async def handle_toggle_speak(message: Message):
    user_id = get_user_id(message=message)
    if not user_id: return
    new_state = await database.toggle_speak_mode(user_id)
    state_text = "ВКЛЮЧЕНА" if new_state else "ВЫКЛЮЧЕНА"
    logger.info(f"User {user_id} toggled speak mode to {state_text}")
    await message.answer(f"🔊 Озвучка моих ответов теперь <b>{state_text}</b>.", parse_mode=ParseMode.HTML)


# --- Admin Commands (без изменений) ---
@router.message(Command("admin"))
async def handle_admin(message: Message):
    user_id = get_user_id(message=message)
    if not user_id or not is_admin(user_id): return
    logger.info(f"Admin command executed by user {user_id}")
    admin_info = f"🛠️ <b>Админ-панель</b>\n\n"
    auth_users_list = getattr(settings, 'AUTHORIZED_USERS', [])
    auth_users_str = ', '.join(map(str, auth_users_list)) if isinstance(auth_users_list, (list, tuple)) and auth_users_list else '<i>Список пуст или не задан</i>'
    admin_info += f"🔑 <b>Авторизованные пользователи:</b>\n<code>{escape_html(auth_users_str)}</code>\n\n"
    admin_info += "✅ Сервис бота активен. Для деталей используйте /status."
    try:
        await message.reply(admin_info, parse_mode=ParseMode.HTML)
    except Exception as e:
         logger.error(f"Failed to send admin info: {e}")
         await message.reply("Ошибка при отображении информации админа.")

async def run_shell_command(command: str) -> Tuple[str, str, int]:
    logger.debug(f"Running shell command: {command}")
    proc = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    exit_code = proc.returncode
    logger.debug(f"Command '{command}' finished with exit code {exit_code}")
    return stdout.decode(errors='ignore'), stderr.decode(errors='ignore'), exit_code

@router.message(Command("status"))
async def handle_status(message: Message, bot: Bot):
    user_id = get_user_id(message=message)
    if not user_id or not is_admin(user_id): return
    logger.info(f"Status command executed by user {user_id}")
    service_name = "telegram_gemini_bot.service"
    processing_msg = await message.reply(f"<i>Получаю статус сервиса <code>{escape_html(service_name)}</code>...</i>", parse_mode=ParseMode.HTML)
    command = f"systemctl status {service_name}"
    output_parts = [f"<code>{escape_html(command)}</code>"]
    try:
        stdout, stderr, exit_code = await run_shell_command(command)
        output_parts.append(f"Код выхода: <code>{exit_code}</code>")
        max_lines = 15
        if stdout:
             stdout_lines = stdout.strip().splitlines(); stdout_limited = "\n".join(stdout_lines[-max_lines:])
             if len(stdout_lines) > max_lines: stdout_limited = "... (начало урезано)\n" + stdout_limited
             output_parts.append(f"<b>Stdout:</b>\n<pre><code>{escape_html(stdout_limited)}</code></pre>")
        if stderr:
             stderr_lines = stderr.strip().splitlines(); stderr_limited = "\n".join(stderr_lines[-max_lines:])
             if len(stderr_lines) > max_lines: stderr_limited = "... (начало урезано)\n" + stderr_limited
             output_parts.append(f"<b>Stderr:</b>\n<pre><code>{escape_html(stderr_limited)}</code></pre>")
        if not stdout and not stderr: output_parts.append("<i>(Команда не вернула вывод)</i>")
    except FileNotFoundError: output_parts.append("\n❌ Ошибка: команда <code>systemctl</code> не найдена.")
    except Exception as e: output_parts.append(f"\n❌ Ошибка при выполнении команды: {escape_html(str(e))}")
    final_output = "\n\n".join(output_parts); max_telegram_len = 4090
    if len(final_output) > max_telegram_len: final_output = final_output[:max_telegram_len] + "\n\n<i>✂️ Вывод был урезан</i>"
    try:
        await bot.edit_message_text(final_output, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Error editing status message: {e}. Sending as plain text.")
        plain_output = re.sub('<[^<]+?>', '', final_output)
        if len(plain_output) > max_telegram_len: plain_output = plain_output[:max_telegram_len] + "\n\n...Вывод был урезан"
        try: await bot.edit_message_text(plain_output, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None, disable_web_page_preview=True)
        except Exception as fallback_e: logger.error(f"Failed to send plain status info: {fallback_e}")

@router.message(Command("restart"))
async def handle_restart(message: Message):
    user_id = get_user_id(message=message)
    if not user_id or not is_admin(user_id): return
    logger.info(f"Restart command executed by user {user_id}")
    service_name = "telegram_gemini_bot.service"
    try: await message.reply(f"⚠️ Отправляю команду перезапуска сервиса <code>{escape_html(service_name)}</code>...\nБот будет перезапущен.", parse_mode=ParseMode.HTML)
    except Exception as reply_e: logger.error(f"Failed to send restart confirmation message: {reply_e}")
    command = f"systemctl restart {service_name}"
    try:
        proc = await asyncio.create_subprocess_shell(command)
        logger.info(f"Launched command '{command}' (PID: {proc.pid}). Service should restart shortly.")
        await asyncio.sleep(1)
    except FileNotFoundError:
         logger.error("Command 'systemctl' not found. Cannot restart service.")
         try: await message.answer("❌ Ошибка: команда <code>systemctl</code> не найдена.", parse_mode=ParseMode.HTML)
         except Exception: pass
    except Exception as e:
        logger.error(f"Error launching restart command '{command}': {e}")
        try: await message.answer("❌ Ошибка при запуске команды перезапуска.")
        except Exception: pass

# --- Callback Query Handlers ---

@router.callback_query(F.data.startswith("set_mood:"))
async def process_mood_callback(callback_query: CallbackQuery, bot: Bot):
    user_id = get_user_id(callback_query=callback_query)
    if not user_id:
        await callback_query.answer("Ошибка: не удалось определить пользователя.", show_alert=True)
        return
    mood = callback_query.data.split(":")[1]
    await database.update_user_mood(user_id, mood)
    logger.info(f"User {user_id} set mood to {mood}")
    await callback_query.answer(f"Стиль общения изменен на: {mood}")
    try:
        await bot.edit_message_text(f"✅ Стиль общения изменен на: <code>{escape_html(mood)}</code>",
                                    chat_id=callback_query.message.chat.id,
                                    message_id=callback_query.message.message_id,
                                    reply_markup=None,
                                    parse_mode=ParseMode.HTML)
    except TelegramBadRequest as e: logger.warning(f"Failed to edit mood message (might be old or unchanged): {e}")
    except Exception as e: logger.error(f"Unexpected error editing mood message: {e}")


# --- Message Handlers ---

@router.message(F.voice)
async def handle_voice_message(message: Message, bot: Bot):
    user_id = get_user_id(message=message)
    if not user_id: return
    logger.debug(f"Entered handle_voice_message for user {user_id}")
    logger.info(f"Received voice message from user {user_id} (duration: {message.voice.duration}s)")
    processing_msg = await message.reply("<i>Обрабатываю голосовое...</i>", parse_mode=ParseMode.HTML)

    ogg_filepath = get_temp_filepath("ogg")
    try:
        await bot.download(message.voice, destination=str(ogg_filepath))
        logger.debug(f"Voice message saved to {ogg_filepath}")
    except Exception as e:
        logger.error(f"Failed to download voice message from {user_id}: {e}")
        await bot.edit_message_text("❌ Ошибка при скачивании голосового.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        await cleanup_temp_file(ogg_filepath)
        return

    try: await bot.edit_message_text("<i>Распознаю речь...</i>", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=ParseMode.HTML)
    except TelegramBadRequest: pass

    recognized_text = await speech.recognize_speech(ogg_filepath)

    if recognized_text is not None:
        logger.info(f"User {user_id} voice recognized as: '{recognized_text}'")
        try:
            await bot.edit_message_text(f"Вы сказали: \"<i>{escape_html(recognized_text)}</i>\"\n\n<i>Генерирую ответ...</i>",
                                        chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=ParseMode.HTML)
        except TelegramBadRequest: pass

        await database.add_message(user_id, 'user', recognized_text)
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        response_text = await gemini.generate_text_response(user_id, recognized_text)

        if response_text:
            tts_marker_start = "[TTS:"
            tts_marker_end = "]"
            if response_text.startswith(tts_marker_start) and response_text.endswith(tts_marker_end):
                text_to_speak = response_text[len(tts_marker_start):-len(tts_marker_end)].strip()
                if text_to_speak:
                    logger.info(f"Detected explicit TTS request from Gemini (voice input) for user {user_id}.")
                    await database.add_message(user_id, 'model', f"[Запрошена озвучка текста: '{text_to_speak[:100]}...']")
                    await tts.speak_and_cleanup(bot, message.chat.id, text_to_speak)
                else:
                    logger.warning(f"Gemini returned TTS marker but text was empty (voice input) for user {user_id}")
                    await message.reply("Не могу озвучить пустой текст.", parse_mode=None)
                    await database.add_message(user_id, 'model', "[Ошибка: Gemini вернул пустой текст для озвучки]")
            else:
                # --- ИЗМЕНЕНИЕ: Форматируем ответ перед отправкой ---
                formatted_response = format_response_html(response_text)
                await database.add_message(user_id, 'model', response_text) # В историю кладем оригинал
                await send_response(bot, message.chat.id, user_id, formatted_response, parse_mode=ParseMode.HTML) # Отправляем форматированный HTML

            try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
            except Exception as del_e: logger.warning(f"Could not delete processing message after voice reply: {del_e}")

        else:
            logger.error(f"Failed to generate Gemini response for recognized voice from user {user_id}")
            try:
                await bot.edit_message_text(f"Вы сказали: \"<i>{escape_html(recognized_text)}</i>\"\n\n❌ Не удалось сгенерировать ответ от AI.",
                                            chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=ParseMode.HTML)
            except TelegramBadRequest: pass
            await database.add_message(user_id, 'model', "[Ошибка генерации ответа AI]")
    else:
        logger.warning(f"Could not recognize speech from user {user_id} (recognize_speech returned None)")
        await bot.edit_message_text("❌ Не удалось распознать речь.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)


# --- Обработчик Фото ---
@router.message(F.photo)
async def handle_photo_message(message: Message, bot: Bot):
    user_id = get_user_id(message=message)
    if not user_id: return
    photo_id = message.photo[-1].file_unique_id
    logger.info(f"Received photo '{photo_id}' from user {user_id}")
    processing_msg = await message.reply("<i>Анализирую изображение...</i>", parse_mode=ParseMode.HTML)

    photo = message.photo[-1]
    temp_filename = f"{user_id}_{photo.file_unique_id}.jpg"
    jpg_filepath = settings.TEMP_DIR / temp_filename

    try:
        await bot.download(photo, destination=str(jpg_filepath))
        logger.debug(f"Photo '{photo_id}' saved to {jpg_filepath}")
    except Exception as e:
        logger.error(f"Failed to download photo '{photo_id}' from {user_id}: {e}")
        await bot.edit_message_text("❌ Ошибка при скачивании изображения.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        await cleanup_temp_file(jpg_filepath)
        return

    analysis_result = await image_analyzer.analyze_image(jpg_filepath, user_id)
    ocr_text = analysis_result.get("ocr_text")
    vision_analysis = analysis_result.get("vision_analysis")
    ocr_useful = is_ocr_potentially_useful(ocr_text)

    analysis_summary_for_history = f"[Анализ изображения '{photo_id}'] "
    final_response = ""

    if vision_analysis:
        # --- ИЗМЕНЕНИЕ: Форматируем ответ Vision ---
        formatted_vision_analysis = format_response_html(vision_analysis)
        final_response += formatted_vision_analysis
        analysis_summary_for_history += f"Vision: '{vision_analysis[:100]}...'. "
        logger.info(f"Gemini Vision analysis received for photo '{photo_id}' user {user_id}.")
    else:
        final_response += "<i>Не удалось получить описание изображения (Gemini Vision).</i>"
        analysis_summary_for_history += "Vision: Ошибка/Нет. "
        logger.warning(f"Gemini Vision analysis failed or returned empty for photo '{photo_id}' user {user_id}.")

    # Добавляем OCR в историю, если он полезен
    if ocr_text:
        analysis_summary_for_history += f"OCR: '{ocr_text[:100]}...'. "
        if ocr_useful: logger.info(f"OCR text found (useful, not shown) for photo '{photo_id}': length {len(ocr_text)}")
        else: logger.info(f"OCR text found (not useful) for photo '{photo_id}': length {len(ocr_text)}")
    elif ocr_text == "": analysis_summary_for_history += "OCR: Текст не найден. "
    else: analysis_summary_for_history += "OCR: Ошибка. "

    # Запись в БД
    await database.add_message(user_id, 'user', f"[Отправлено изображение '{photo_id}']")
    await database.add_message(user_id, 'model', analysis_summary_for_history.strip())

    # --- ИЗМЕНЕНИЕ: Отправка форматированного ответа ---
    await send_response(bot, message.chat.id, user_id, final_response.strip(), parse_mode=ParseMode.HTML)

    try:
        await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
    except Exception as del_err: logger.warning(f"Could not delete processing message after image reply: {del_err}")


# --- Обработчик Документов ---
@router.message(F.document)
async def handle_document_message(message: Message, bot: Bot):
    user_id = get_user_id(message=message)
    if not user_id: return
    doc = message.document
    filename = doc.file_name if doc.file_name else f"file_{doc.file_unique_id}"
    mime_type = doc.mime_type
    file_size = doc.file_size if doc.file_size else 0
    file_id = doc.file_id

    logger.info(f"Received document '{filename}' from user {user_id} (Type: {mime_type}, Size: {file_size})")
    processing_msg = await message.reply(f"<i>Получил файл '{escape_html(filename)}'. Обрабатываю...</i>", parse_mode=ParseMode.HTML)

    safe_filename_part = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in filename)
    temp_filename = f"{user_id}_{file_id}_{safe_filename_part}"; max_len = 150
    if len(temp_filename) > max_len:
         name_part, ext_part = os.path.splitext(temp_filename); ext_len = len(ext_part)
         name_part = name_part[:max_len - ext_len - 1]; temp_filename = name_part + ext_part
    doc_filepath = settings.TEMP_DIR / temp_filename

    try:
        await bot.download(doc, destination=str(doc_filepath))
        logger.debug(f"Document '{filename}' saved to {doc_filepath}")
    except Exception as e:
        logger.error(f"Failed to download document '{filename}' from {user_id}: {e}")
        await bot.edit_message_text(f"❌ Ошибка при скачивании файла '{escape_html(filename)}'.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        await cleanup_temp_file(doc_filepath)
        return

    try:
        await bot.edit_message_text(f"<i>Анализирую содержимое файла '{escape_html(filename)}'...</i>", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=ParseMode.HTML)
    except TelegramBadRequest: pass

    process_result = await file_handler.process_file(doc_filepath, filename, mime_type, file_size)

    if process_result:
        status_message, analysis_result, extracted_content = process_result
        logger.info(f"File processing result for '{filename}': Status='{status_message}', Analysis received={analysis_result is not None}")

        # --- ИЗМЕНЕНИЕ: Формируем HTML ответ ---
        response_parts_html = [
            f"<b>Файл:</b> <code>{escape_html(filename)}</code>",
            f"<b>Статус:</b> {escape_html(status_message)}"
        ]

        max_history_len = settings.MAX_HISTORY_FILE_CONTENT_LENGTH
        history_content_info = ""
        if extracted_content and not status_message.startswith("Файл") and not status_message.startswith("Не удалось"):
             truncated_content = extracted_content[:max_history_len]
             history_content_info = f" [Содержимое{' (урезанное)' if len(extracted_content) > max_history_len else ''}: {truncated_content}...]"
        elif not extracted_content and status_message.startswith("Извлек"):
             history_content_info = " [Содержимое: (пусто)]"

        user_history_message = f"[Отправлен файл для анализа: {filename}]"
        model_history_message = f"[Статус обработки: {status_message}]{history_content_info}"

        if analysis_result:
            # --- ИЗМЕНЕНИЕ: Форматируем анализ ---
            formatted_analysis = format_response_html(analysis_result)
            response_parts_html.append(f"\n<b>Анализ содержимого (Gemini):</b>\n{formatted_analysis}") # Добавляем уже форматированный HTML
            model_history_message += f" [Анализ Gemini: {analysis_result[:150]}...]"

        final_response_html = "\n\n".join(response_parts_html).strip()
        await database.add_message(user_id, 'user', user_history_message)
        await database.add_message(user_id, 'model', model_history_message)

        # --- ИЗМЕНЕНИЕ: Отправляем с HTML ---
        await send_response(bot, message.chat.id, user_id, final_response_html, parse_mode=ParseMode.HTML)

        try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        except Exception as del_e: logger.warning(f"Could not delete processing message after file reply: {del_e}")

    else:
        logger.error(f"File processing failed unexpectedly for '{filename}' user {user_id} (process_file returned None)")
        fail_msg = f"❌ Критическая ошибка при обработке файла '{escape_html(filename)}'."
        await bot.edit_message_text(fail_msg, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        await database.add_message(user_id, 'user', f"[Отправлен файл для анализа: {filename}]")
        await database.add_message(user_id, 'model', "[Критическая ошибка обработки файла]")


# --- Обработчик Текстовых Сообщений ---
@router.message(F.text)
async def handle_text_message(message: Message, bot: Bot):
    user_id = get_user_id(message=message)
    if not user_id: return
    user_text = message.text
    if not user_text or user_text.isspace(): return

    lower_text = user_text.lower()
    weather_keyword = "погода "

    # --- Проверка на погоду ---
    if lower_text.startswith(weather_keyword):
        city_input = user_text[len(weather_keyword):].strip() or "Moscow"
        logger.info(f"User {user_id} requested weather for '{city_input}' via text")
        processing_msg = await message.reply(f"<i>Узнаю погоду для '{escape_html(city_input)}'...</i>", parse_mode=ParseMode.HTML)
        weather_report_markdown = await weather.get_weather(city_input)

        if weather_report_markdown:
            is_error_report = any(keyword.lower() in weather_report_markdown.lower() for keyword in ["не найден", "ошибка", "сервис погоды недоступен", "таймаут", "invalid", "not found"])
            final_parse_mode = ParseMode.MARKDOWN_V2 if not is_error_report else None
            try:
                await bot.edit_message_text(weather_report_markdown, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=final_parse_mode, disable_web_page_preview=True)
            except TelegramBadRequest as e:
                 if "message is not modified" in str(e): logger.debug(f"Weather report for {city_input} was not modified.")
                 elif "can't parse entities" in str(e).lower() and final_parse_mode == ParseMode.MARKDOWN_V2:
                     logger.error(f"Error editing weather message with MarkdownV2: {e}. Retrying without parse mode.")
                     plain_text_report = re.sub(r'[\\`*_\[\]()~>#+\-=|{}.!]', '', weather_report_markdown)
                     await bot.edit_message_text(plain_text_report, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode=None, disable_web_page_preview=True)
                 else:
                     logger.error(f"Unhandled TelegramBadRequest editing weather message: {e}")
                     await message.reply(weather_report_markdown, parse_mode=None, disable_web_page_preview=True)
                     try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
                     except Exception: pass
            except Exception as e:
                 logger.error(f"Unexpected error sending/editing weather message: {e}")
                 await message.reply(weather_report_markdown, parse_mode=None, disable_web_page_preview=True)
                 try: await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
                 except Exception: pass
        else:
            await bot.edit_message_text("❌ Не удалось получить информацию о погоде.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        return # Погода обработана

    # --- Если не погода, то Gemini ---
    else:
        logger.info(f"Received text message from user {user_id} for Gemini: '{user_text[:100]}...'")
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        await database.add_message(user_id, 'user', user_text)
        response_text = await gemini.generate_text_response(user_id, user_text)

        if response_text:
            tts_marker_start = "[TTS:"
            tts_marker_end = "]"
            if response_text.startswith(tts_marker_start) and response_text.endswith(tts_marker_end):
                text_to_speak = response_text[len(tts_marker_start):-len(tts_marker_end)].strip()
                if text_to_speak:
                    logger.info(f"Detected explicit TTS request from Gemini for user {user_id}. Text: '{text_to_speak[:50]}...'")
                    await database.add_message(user_id, 'model', f"[Запрошена озвучка текста: '{text_to_speak[:100]}...']")
                    await tts.speak_and_cleanup(bot, message.chat.id, text_to_speak)
                else:
                    logger.warning(f"Gemini returned TTS marker but text was empty for user {user_id}")
                    await message.reply("Не могу озвучить пустой текст.", parse_mode=None)
                    await database.add_message(user_id, 'model', "[Ошибка: Gemini вернул пустой текст для озвучки]")
            else:
                # --- ИЗМЕНЕНИЕ: Форматируем обычный ответ ---
                formatted_response = format_response_html(response_text)
                await database.add_message(user_id, 'model', response_text) # В историю кладем оригинал
                await send_response(bot, message.chat.id, user_id, formatted_response, parse_mode=ParseMode.HTML) # Отправляем форматированный HTML
        else:
            logger.error(f"Failed to generate Gemini response for user {user_id}")
            error_response = "Извините, не могу сейчас ответить. Попробуйте позже."
            await message.reply(error_response, parse_mode=None)
            await database.add_message(user_id, 'model', "[Ошибка генерации ответа AI]")


# --- Вспомогательная функция для отправки ответа (с улучшенной обработкой ошибок) ---
async def send_response(bot: Bot, chat_id: int, user_id: int, text: str, parse_mode: Optional[str] = None, keyboard: Optional[InlineKeyboardMarkup] = None):
    """Sends response as text or voice based on user settings, handling long messages and errors."""
    speak_enabled = False
    try:
        speak_enabled = await database.get_speak_enabled(user_id)
    except Exception as e:
        logger.error(f"Failed to get speak mode for user {user_id}: {e}")
        # Продолжаем с speak_enabled = False

    text_to_send = text # Передаем текст (возможно, форматированный)

    try:
        if speak_enabled:
            logger.info(f"Sending voice response to user {user_id}")
            # Очищаем HTML/Markdown перед озвучкой
            plain_text_for_tts = re.sub('<[^<]+?>', '', text) # Удаляем HTML теги
            # Можно добавить удаление Markdown V2 символов, если нужно
            # plain_text_for_tts = re.sub(r'[\\`*_\[\]()~>#+\-=|{}.!]', '', plain_text_for_tts)
            await tts.speak_and_cleanup(bot, chat_id, plain_text_for_tts, keyboard=keyboard) # Передаем клавиатуру
        else:
            logger.info(f"Sending text response to user {user_id} with parse_mode={parse_mode}")
            max_len = 4096
            if len(text_to_send) <= max_len:
                 try:
                     await bot.send_message(chat_id, text_to_send, parse_mode=parse_mode, disable_web_page_preview=True, reply_markup=keyboard)
                 except TelegramBadRequest as e:
                     if "can't parse entities" in str(e).lower() and parse_mode:
                         logger.error(f"Failed to send message with parse_mode={parse_mode}: {e}. Retrying without parse_mode.")
                         await bot.send_message(chat_id, text, parse_mode=None, disable_web_page_preview=True, reply_markup=keyboard)
                     else:
                         logger.error(f"Unhandled TelegramBadRequest sending message to {chat_id}: {e}")
                         raise # Перевыбрасываем
            else:
                 logger.warning(f"Response for user {user_id} is too long ({len(text_to_send)} chars). Sending in parts.")
                 # Упрощенное разделение, может ломать HTML/Markdown на стыках
                 parts = []
                 for i in range(0, len(text_to_send), max_len):
                      parts.append(text_to_send[i:i + max_len])

                 for i, part in enumerate(parts):
                     if not part.strip(): continue
                     logger.debug(f"Sending part {i+1}/{len(parts)} ({len(part)} chars) to chat {chat_id}")
                     current_keyboard = keyboard if i == len(parts) - 1 else None
                     try:
                         await bot.send_message(chat_id, part, parse_mode=parse_mode, disable_web_page_preview=True, reply_markup=current_keyboard)
                     except TelegramBadRequest as e:
                         if "can't parse entities" in str(e).lower() and parse_mode:
                             logger.error(f"Failed to send part {i+1} with parse_mode={parse_mode}: {e}. Retrying without parse_mode.")
                             await bot.send_message(chat_id, part, parse_mode=None, disable_web_page_preview=True, reply_markup=current_keyboard)
                         else:
                             logger.error(f"Unhandled TelegramBadRequest sending part {i+1} to {chat_id}: {e}")
                             # Если даже без parse_mode не ушло, можно просто пропустить часть
                     except Exception as part_e:
                          logger.error(f"Failed to send part {i+1} to {chat_id}: {part_e}")

                     if i < len(parts) - 1:
                         await asyncio.sleep(0.8) # Задержка между частями

    except Exception as e:
        logger.error(f"General error in send_response for user {user_id} (chat {chat_id}): {e}")
        logger.exception(e)
        # Попытка отправить сообщение об ошибке пользователю, если это был не голосовой ответ
        if not speak_enabled:
            try:
                await bot.send_message(chat_id, "Произошла непредвиденная ошибка при обработке вашего запроса.", parse_mode=None)
            except Exception:
                logger.error(f"Failed even to send the error notification to chat {chat_id}")