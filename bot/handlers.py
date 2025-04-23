# --- START OF FILE bot/handlers.py ---

import asyncio
import os
# import subprocess # <<< УДАЛЕН НЕНУЖНЫЙ ИМПОРТ >>>
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, FSInputFile, InputFile, User
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from loguru import logger
from typing import Optional, Dict, Tuple # <<< Добавил Tuple для аннотации run_shell_command >>>
from pathlib import Path

# Импортируем настройки и сервисы
from config import settings
from services import (
    gemini,
    weather,
    speech,
    image_analyzer,
    file_handler,
    database,
    tts,  # <-- Убеждаемся, что tts импортирован
    translator,
)
# Импортируем хелперы
from utils.helpers import (
    get_temp_filepath,
    cleanup_temp_file,
    escape_markdown_v2,
    is_ocr_potentially_useful
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

# --- Вспомогательная функция для проверки прав админа ---
def is_admin(user_id: int) -> bool:
    """Checks if the user ID is in the authorized list."""
    # Убедимся, что AUTHORIZED_USERS существует и является списком/кортежем
    auth_list = getattr(settings, 'AUTHORIZED_USERS', [])
    if not isinstance(auth_list, (list, tuple)):
        logger.error("settings.AUTHORIZED_USERS is not a list or tuple.")
        return False
    return user_id in auth_list

# --- Command Handlers ---

@router.message(Command("start", "help"))
async def handle_start(message: Message):
    """Handles /start and /help commands."""
    user_id = get_user_id(message=message)
    if not user_id: return
    user_name = message.from_user.full_name if message.from_user else "Пользователь"
    await database.get_user_settings(user_id)

    # Экранируем скобки () для MarkdownV2
    help_text = (
        f"Привет, {escape_markdown_v2(user_name)}\!\n\n"
        "Я многофункциональный AI\-бот\. Вот что я умею:\n\n"
        "🧠 **Общение:** Просто напиши мне, и я отвечу с помощью Google Gemini\. Можешь спросить погоду, написав `погода <город>`\.\n"
        "🗣️ **Голосовые сообщения:** Отправь мне голосовое, я его распознаю и отвечу\.\n"
        "🖼️ **Анализ изображений:** Отправь картинку, я опишу её с помощью Gemini Vision \\(текст с картинки не выводится\\)\.\n"
        "📄 **Обработка файлов:** Отправь \.txt, \.pdf, \.csv, \.xlsx или \.docx, и я проанализирую содержимое\.\n"
        "☀️ **Погода \\(команда\\):** `/weather <город>` \\(по умолчанию Москва\\)\.\n"
        "🎭 **Стиль общения:** `/mood` \- выбери мой стиль \\(дружелюбный, проф\., саркастичный\\)\.\n"
        # --- ИЗМЕНЕНИЯ В СПРАВКЕ ---
        "🌐 **Перевод и Озвучка:**\n"
        "   \- Попроси меня **перевести** текст \\(напр\., `переведи 'hello' на немецкий`\\)\.\n"
        "   \- Попроси меня **озвучить** текст \\(напр\., `озвучь 'привет мир'` или `скажи 'я бот'`\\)\.\n"
        "   \- `/toggle_speak` \- вкл/выкл автоматическую озвучку моих ответов\.\n\n"
        # --- КОНЕЦ ИЗМЕНЕНИЙ В СПРАВКЕ ---
        f"Твой ID: `{user_id}`\n"
        "Настройки хранятся для каждого пользователя\."
    )
    if is_admin(user_id):
        help_text += "\n\n**Админ\-команды:**\n`/admin` `/status` `/restart`"

    try:
        await message.answer(help_text, parse_mode="MarkdownV2")
    except TelegramBadRequest as e:
        logger.error(f"Failed to send help message with MarkdownV2: {e}")
        help_text_plain = ( # Версия без MarkdownV2
            f"Привет, {user_name}!\n\n"
            "Я многофункциональный AI-бот. Вот что я умею:\n\n"
            "Общение: Просто напиши мне, и я отвечу с помощью Google Gemini. Можешь спросить погоду, написав 'погода <город>'.\n"
            "Голосовые сообщения: Отправь мне голосовое, я его распознаю и отвечу.\n"
            "Анализ изображений: Отправь картинку, я опишу её с помощью Gemini Vision (текст с картинки не выводится).\n"
            "Обработка файлов: Отправь .txt, .pdf, .csv, .xlsx или .docx, и я проанализирую содержимое.\n"
            "Погода (команда): /weather <город> (по умолчанию Москва).\n"
            "Стиль общения: /mood - выбери мой стиль (дружелюбный, проф., саркастичный).\n"
            # --- ИЗМЕНЕНИЯ В СПРАВКЕ (Plain Text) ---
            "Перевод и Озвучка:\n"
            "   - Попроси меня перевести текст (напр., `переведи 'hello' на немецкий`).\n"
            "   - Попроси меня озвучить текст (напр., `озвучь 'привет мир'` или `скажи 'я бот'`).\n"
            "   - /toggle_speak - вкл/выкл автоматическую озвучку моих ответов.\n\n"
            # --- КОНЕЦ ИЗМЕНЕНИЙ В СПРАВКЕ (Plain Text) ---
            f"Твой ID: {user_id}\n"
            "Настройки хранятся для каждого пользователя."
        )
        if is_admin(user_id):
             help_text_plain += "\n\nАдмин-команды:\n/admin /status /restart"
        try:
            await message.answer(help_text_plain, parse_mode=None)
            logger.info("Sent help message without Markdown as fallback.")
        except Exception as fallback_e:
            logger.error(f"Failed to send plain help message: {fallback_e}")


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

# <<< ФУНКЦИЯ handle_speak УДАЛЕНА >>>

@router.message(Command("toggle_speak"))
async def handle_toggle_speak(message: Message):
    """Handles /toggle_speak command."""
    user_id = get_user_id(message=message)
    if not user_id: return
    new_state = await database.toggle_speak_mode(user_id)
    state_text = "ВКЛЮЧЕНА" if new_state else "ВЫКЛЮЧЕНА"
    logger.info(f"User {user_id} toggled speak mode to {state_text}")
    await message.answer(f"🔊 Озвучка моих ответов теперь **{state_text}**\.", parse_mode="MarkdownV2")

# <<< ФУНКЦИЯ handle_translate УДАЛЕНА >>>


# ===========================================
# === НОВЫЕ АДМИНСКИЕ КОМАНДЫ НАЧИНАЮТСЯ ===
# ===========================================

@router.message(Command("admin"))
async def handle_admin(message: Message):
    """Handles /admin command (admins only)."""
    user_id = get_user_id(message=message)
    # Проверка прав администратора
    if not user_id or not is_admin(user_id):
        logger.warning(f"Unauthorized attempt to use /admin by user {user_id or 'unknown'}")
        # Обычно middleware уже блокирует, но можно и явно ничего не отвечать
        return

    logger.info(f"Admin command executed by user {user_id}")
    admin_info = f"🛠️ *Админ\-панель*\n\n"

    # Список авторизованных пользователей
    auth_users_list = getattr(settings, 'AUTHORIZED_USERS', [])
    if isinstance(auth_users_list, (list, tuple)) and auth_users_list:
        auth_users_str = ', '.join(map(str, auth_users_list))
    else:
        auth_users_str = '_Список пуст или не задан_'
    admin_info += f"🔑 **Авторизованные пользователи:**\n`{escape_markdown_v2(auth_users_str)}`\n\n"

    # Дополнительная информация (можно расширить)
    admin_info += "✅ Сервис бота активен \(проверено запуском этой команды\)\. Для деталей используйте `/status`\."

    try:
        await message.reply(admin_info, parse_mode="MarkdownV2")
    except TelegramBadRequest as e:
         logger.error(f"Failed to send admin info with MarkdownV2: {e}")
         # Fallback без разметки
         admin_info_plain = f"Админ-панель\n\n"
         admin_info_plain += f"Авторизованные пользователи:\n{auth_users_str}\n\n"
         admin_info_plain += "Сервис бота активен. Для деталей используйте /status."
         try:
             await message.reply(admin_info_plain, parse_mode=None)
         except Exception as plain_e:
              logger.error(f"Failed to send plain admin info: {plain_e}")


async def run_shell_command(command: str) -> Tuple[str, str, int]:
    """Executes a shell command asynchronously and returns output."""
    logger.debug(f"Running shell command: {command}")
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    exit_code = proc.returncode
    logger.debug(f"Command '{command}' finished with exit code {exit_code}")
    return stdout.decode(errors='ignore'), stderr.decode(errors='ignore'), exit_code


@router.message(Command("status"))
async def handle_status(message: Message, bot: Bot): # Добавил bot, т.к. используется bot.edit_message_text
    """Handles /status command (admins only). Gets systemd service status."""
    user_id = get_user_id(message=message)
    if not user_id or not is_admin(user_id):
        logger.warning(f"Unauthorized attempt to use /status by user {user_id or 'unknown'}")
        return

    logger.info(f"Status command executed by user {user_id}")
    # Имя сервиса systemd (должно совпадать с именем файла .service)
    service_name = "telegram_gemini_bot.service"
    processing_msg = await message.reply(f"Получаю статус сервиса `{escape_markdown_v2(service_name)}`...", parse_mode="MarkdownV2")

    command = f"systemctl status {service_name}"
    output_parts = [f"`{command}`"]
    try:
        stdout, stderr, exit_code = await run_shell_command(command)

        output_parts.append(f"Код выхода: `{exit_code}`")

        max_lines = 15 # Ограничиваем вывод для Telegram
        if stdout:
             stdout_lines = stdout.strip().splitlines()
             stdout_limited = "\n".join(stdout_lines[-max_lines:])
             if len(stdout_lines) > max_lines:
                 stdout_limited = "... (начало урезано)\n" + stdout_limited
             # Экранируем содержимое для блока кода MarkdownV2
             escaped_stdout = escape_markdown_v2(stdout_limited)
             output_parts.append(f"**Stdout:**\n```\n{escaped_stdout}\n```")
        if stderr:
             stderr_lines = stderr.strip().splitlines()
             stderr_limited = "\n".join(stderr_lines[-max_lines:])
             if len(stderr_lines) > max_lines:
                 stderr_limited = "... (начало урезано)\n" + stderr_limited
             escaped_stderr = escape_markdown_v2(stderr_limited)
             output_parts.append(f"**Stderr:**\n```\n{escaped_stderr}\n```")

        if not stdout and not stderr and exit_code == 0: # Уточняем случай пустого вывода
             output_parts.append("_(Команда выполнена успешно, но не вернула вывод)_")
        elif not stdout and not stderr and exit_code != 0:
             output_parts.append("_(Команда не вернула вывод, код выхода не 0)_")


    except FileNotFoundError:
         logger.error(f"Command 'systemctl' not found.")
         output_parts.append("\n❌ Ошибка: команда `systemctl` не найдена на сервере.")
    except Exception as e:
        logger.error(f"Error executing status command '{command}': {e}")
        output_parts.append(f"\n❌ Ошибка при выполнении команды: {escape_markdown_v2(str(e))}")

    final_output = "\n\n".join(output_parts)
    max_telegram_len = 4090
    if len(final_output) > max_telegram_len:
        final_output = final_output[:max_telegram_len] + "\n\n✂️ _Вывод был урезан_"

    try:
        await bot.edit_message_text(final_output,
                                    chat_id=processing_msg.chat.id,
                                    message_id=processing_msg.message_id,
                                    parse_mode="MarkdownV2",
                                    disable_web_page_preview=True)
    except TelegramBadRequest as e:
         logger.error(f"Error editing status message with MarkdownV2: {e}. Falling back to plain text.")
         try:
             # Формируем простой текст без Markdown
             plain_output_parts = [f"Команда: {command}"]
             if 'exit_code' in locals(): plain_output_parts.append(f"Код выхода: {exit_code}")
             if 'stdout_limited' in locals() and stdout_limited: plain_output_parts.append(f"Stdout:\n{stdout_limited}")
             if 'stderr_limited' in locals() and stderr_limited: plain_output_parts.append(f"Stderr:\n{stderr_limited}")
             if 'stdout' in locals() and 'stderr' in locals() and not stdout and not stderr:
                 if 'exit_code' in locals() and exit_code == 0: plain_output_parts.append("(Команда выполнена успешно, но не вернула вывод)")
                 else: plain_output_parts.append("(Команда не вернула вывод)")
             plain_output = "\n\n".join(plain_output_parts)

             if len(plain_output) > max_telegram_len:
                 plain_output = plain_output[:max_telegram_len] + "\n\n...Вывод был урезан"
             await bot.edit_message_text(plain_output,
                                         chat_id=processing_msg.chat.id,
                                         message_id=processing_msg.message_id,
                                         parse_mode=None,
                                         disable_web_page_preview=True)
         except Exception as fallback_e:
              logger.error(f"Failed to send plain status info: {fallback_e}")


@router.message(Command("restart"))
async def handle_restart(message: Message):
    """Handles /restart command (admins only). Restarts systemd service."""
    user_id = get_user_id(message=message)
    if not user_id or not is_admin(user_id):
        logger.warning(f"Unauthorized attempt to use /restart by user {user_id or 'unknown'}")
        return

    logger.info(f"Restart command executed by user {user_id}")
    service_name = "telegram_gemini_bot.service"
    # Отправляем сообщение ДО выполнения команды
    try:
        await message.reply(f"⚠️ Отправляю команду перезапуска сервиса `{escape_markdown_v2(service_name)}`\.\.\.\n"
                            "Бот будет перезапущен\. Ответ от `systemctl` может не прийти\.", parse_mode="MarkdownV2")
    except Exception as reply_e:
         logger.error(f"Failed to send restart confirmation message: {reply_e}")
         # Все равно пробуем перезапустить

    command = f"systemctl restart {service_name}"
    try:
        proc = await asyncio.create_subprocess_shell(command)
        # Не ждем завершения, просто логируем запуск
        logger.info(f"Launched command '{command}' (PID: {proc.pid}). Service should restart shortly.")
        # Даем systemd немного времени
        await asyncio.sleep(1)
    except FileNotFoundError:
         logger.error(f"Command 'systemctl' not found. Cannot restart service.")
         # Попытка отправить сообщение об ошибке, но может не успеть
         try: await message.answer("❌ Ошибка: команда `systemctl` не найдена.", parse_mode="MarkdownV2")
         except Exception: pass
    except Exception as e:
        logger.error(f"Error launching restart command '{command}': {e}")
        try: await message.answer("❌ Ошибка при запуске команды перезапуска.", parse_mode=None)
        except Exception: pass

# =========================================
# === НОВЫЕ АДМИНСКИЕ КОМАНДЫ КОНЧАЮТСЯ ===
# =========================================


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

        # --- ИЗМЕНЕНИЯ: Проверка на TTS маркер в ответе на ГОЛОСОВОЕ сообщение ---
        if response_text:
            tts_marker_start = "[TTS:"
            tts_marker_end = "]"
            if response_text.startswith(tts_marker_start) and response_text.endswith(tts_marker_end):
                text_to_speak = response_text[len(tts_marker_start):-len(tts_marker_end)]
                if text_to_speak:
                    logger.info(f"Detected explicit TTS request from Gemini (voice input) for user {user_id}.")
                    await database.add_message(user_id, 'model', f"[Запрошена озвучка текста: '{text_to_speak[:100]}...']")
                    await tts.speak_and_cleanup(bot, message.chat.id, text_to_speak)
                else:
                    logger.warning(f"Gemini returned TTS marker but text was empty (voice input) for user {user_id}")
                    await message.reply("Не могу озвучить пустой текст.", parse_mode=None)
                    await database.add_message(user_id, 'model', "[Ошибка: Gemini вернул пустой текст для озвучки]")
            else:
                # Обычный ответ (текстом или голосом в зависимости от /toggle_speak)
                await database.add_message(user_id, 'model', response_text)
                await send_response(bot, message.chat.id, user_id, response_text)

            try:
                await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
            except TelegramBadRequest as del_e: logger.warning(f"Could not delete processing message after voice reply: {del_e}")
            except Exception as del_e: logger.error(f"Unexpected error deleting processing message: {del_e}")
        # --- КОНЕЦ ИЗМЕНЕНИЙ В ОТВЕТЕ НА ГОЛОС ---
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
    parse_mode_final: Optional[str] = "MarkdownV2"

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
    file_ext = filename.split('.')[-1].lower() if '.' in filename else None

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
        status_message, analysis_result, extracted_content = process_result # Распаковываем 3 значения
        logger.info(f"File processing result for '{filename}': Status='{status_message}', Analysis received={analysis_result is not None}")

        response_parts = [
            f"**Файл:** `{escape_markdown_v2(filename)}`",
            f"**Статус:** {escape_markdown_v2(status_message)}"
        ]

        # --- ИЗМЕНЕНИЕ: Формируем историю с урезанным контентом ---
        max_history_len = settings.MAX_HISTORY_FILE_CONTENT_LENGTH
        history_content_info = ""
        if extracted_content and not status_message.startswith("Файл") and not status_message.startswith("Не удалось"):
             if len(extracted_content) > max_history_len:
                 history_content_info = f" [Содержимое (урезанное): {extracted_content[:max_history_len]}...]"
             else:
                 history_content_info = f" [Содержимое: {extracted_content[:max_history_len]}]" # Показываем все, если короткое
        # --- КОНЕЦ ИЗМЕНЕНИЯ ИСТОРИИ ---

        user_history_message = f"[Отправлен файл для анализа: {filename}]"
        model_history_message = f"[Статус обработки: {status_message}]{history_content_info}" # Добавляем инфо о контенте

        if analysis_result:
            response_parts.append(f"**Анализ содержимого \(Gemini\):**\n{escape_markdown_v2(analysis_result)}")
            model_history_message += f" [Анализ Gemini: {analysis_result[:150]}...]" # Добавляем инфо об анализе

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
@router.message(F.text)
async def handle_text_message(message: Message, bot: Bot):
    """
    Handles regular text messages.
    Checks for weather request.
    If not weather, processes using Gemini, detecting translation and TTS requests.
    """
    user_id = get_user_id(message=message)
    if not user_id: return
    user_text = message.text
    if not user_text or user_text.isspace():
        logger.debug(f"Ignoring empty/whitespace message from user {user_id}")
        return

    lower_text = user_text.lower()
    weather_keyword = "погода "

    # --- Проверка на запрос погоды (остается без изменений) ---
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
        logger.info(f"Received text message from user {user_id} for Gemini: '{user_text[:100]}...'")
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        await database.add_message(user_id, 'user', user_text)
        response_text = await gemini.generate_text_response(user_id, user_text)

        if response_text:
            # --- НОВАЯ ЛОГИКА: Проверка на маркер TTS ---
            tts_marker_start = "[TTS:"
            tts_marker_end = "]"
            if response_text.startswith(tts_marker_start) and response_text.endswith(tts_marker_end):
                # Извлекаем текст для озвучки
                text_to_speak = response_text[len(tts_marker_start):-len(tts_marker_end)]
                if text_to_speak:
                    logger.info(f"Detected explicit TTS request from Gemini for user {user_id}. Text: '{text_to_speak[:50]}...'")
                    # Логируем действие в БД (не сам маркер)
                    await database.add_message(user_id, 'model', f"[Запрошена озвучка текста: '{text_to_speak[:100]}...']")
                    # Выполняем озвучку напрямую
                    await tts.speak_and_cleanup(bot, message.chat.id, text_to_speak)
                else:
                    logger.warning(f"Gemini returned TTS marker but text was empty for user {user_id}")
                    # Отправляем сообщение об ошибке, если текст пуст
                    await message.reply("Не могу озвучить пустой текст.", parse_mode=None)
                    await database.add_message(user_id, 'model', "[Ошибка: Gemini вернул пустой текст для озвучки]")

            # --- СТАРАЯ ЛОГИКА: Если это не TTS маркер ---
            else:
                # Это обычный ответ или ответ с переводом от Gemini
                await database.add_message(user_id, 'model', response_text)
                # Отправляем ответ (текстом или голосом в зависимости от /toggle_speak)
                await send_response(bot, message.chat.id, user_id, response_text)
            # --- КОНЕЦ ИЗМЕНЕНИЙ ---

        else:
            # Обработка ошибки генерации Gemini (остается без изменений)
            logger.error(f"Failed to generate Gemini response for user {user_id}")
            error_response = "Извините, не могу сейчас ответить. Попробуйте позже."
            await message.reply(error_response, parse_mode=None)
            await database.add_message(user_id, 'model', "[Ошибка генерации ответа AI]")


# --- Вспомогательная функция для отправки ответа (без изменений) ---
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