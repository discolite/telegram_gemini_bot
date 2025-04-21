import asyncio
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, FSInputFile, InputFile
from aiogram.fsm.context import FSMContext # Если потребуется FSM
from loguru import logger

from config import settings
from services import (
    gemini,
    weather,
    speech,
    image_analyzer,
    file_handler,
    database,
    tts,
    translator,
)
from utils.helpers import get_temp_filepath, cleanup_temp_file, escape_markdown_v2
from .keyboards import get_mood_keyboard

# Создаем Router
router = Router()

# --- Command Handlers ---

@router.message(Command("start", "help"))
async def handle_start(message: Message):
    """Handles /start and /help commands."""
    user_name = message.from_user.full_name
    # Инициализация пользователя в БД (на случай, если он еще не писал)
    await database.get_user_settings(message.from_user.id)
    help_text = (
        f"Привет, {user_name}!\n\n"
        "Я многофункциональный AI-бот. Вот что я умею:\n\n"
        "🧠 **Общение:** Просто напиши мне, и я отвечу с помощью Google Gemini, учитывая контекст.\n"
        "🗣️ **Голосовые сообщения:** Отправь мне голосовое, я его распознаю и отвечу.\n"
        "🖼️ **Анализ изображений:** Отправь картинку, я извлеку текст (OCR) и опишу её (Gemini Vision).\n"
        "📄 **Обработка файлов:** Отправь .txt, .pdf, .csv или .xlsx, и я проанализирую содержимое.\n"
        "☀️ **Погода:** `/weather <город>` (по умолчанию Москва).\n"
        "🎭 **Стиль общения:** `/mood` - выбери мой стиль (дружелюбный, проф., саркастичный).\n"
        "🔊 **Озвучка:** \n"
        "   - `/speak <текст>` - озвучу твой текст.\n"
        "   - `/toggle_speak` - вкл/выкл озвучку моих ответов.\n"
        "🌐 **Перевод:** `/translate <текст> [язык]` (напр., `/translate hello ru`). Я также могу переводить через Gemini (попроси меня).\n\n"
        f"Твой ID: `{message.from_user.id}`\n"
        "Настройки хранятся для каждого пользователя."
    )
    await message.answer(help_text, parse_mode="MarkdownV2")

@router.message(Command("weather"))
async def handle_weather(message: Message, command: CommandObject, bot: Bot):
    """Handles /weather command."""
    city = command.args if command.args else "Moscow"
    logger.info(f"User {message.from_user.id} requested weather for '{city}'")
    processing_msg = await message.answer(f"Узнаю погоду для '{city}'...")

    weather_report = await weather.get_weather(city)

    # Используем MarkdownV2 для форматирования ответа погоды
    # Убедимся, что сам отчет не содержит конфликтующих Markdown символов
    # Но для погоды обычно это безопасно. Можно добавить escape_markdown_v2() если нужно.
    # formatted_report = escape_markdown_v2(weather_report) # Раскомментировать при необходимости
    formatted_report = weather_report # Используем как есть, т.к. форматирование уже в get_weather

    await bot.edit_message_text(formatted_report, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode="MarkdownV2") # Или HTML если используется он

@router.message(Command("mood"))
async def handle_mood(message: Message):
    """Handles /mood command, shows mood selection keyboard."""
    user_id = message.from_user.id
    settings_data = await database.get_user_settings(user_id)
    current_mood = settings_data.get('mood', settings.DEFAULT_MOOD)
    await message.answer(
        f"Выбери мой стиль общения. Текущий: `{current_mood}`",
        reply_markup=get_mood_keyboard(),
        parse_mode="MarkdownV2"
    )

@router.message(Command("speak"))
async def handle_speak(message: Message, command: CommandObject, bot: Bot):
    """Handles /speak command for TTS."""
    text_to_speak = command.args
    if not text_to_speak:
        await message.answer("Пожалуйста, укажи текст для озвучивания после команды /speak.")
        return

    user_id = message.from_user.id
    logger.info(f"User {user_id} requested to speak: '{text_to_speak[:50]}...'")
    processing_msg = await message.answer("Генерирую аудио...")

    audio_path = await tts.generate_speech(text_to_speak)

    if audio_path:
        try:
            audio_input = FSInputFile(audio_path)
            await message.reply_voice(voice=audio_input)
            await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
            logger.info(f"Sent generated voice message for /speak to {user_id}")
        except Exception as send_err:
            logger.error(f"Error sending voice message for /speak to {user_id}: {send_err}")
            await bot.edit_message_text("Ошибка при отправке аудио.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        finally:
            await cleanup_temp_file(audio_path)
    else:
        logger.error(f"Failed to generate speech for /speak for user {user_id}")
        await bot.edit_message_text("Не удалось сгенерировать аудио.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)

@router.message(Command("toggle_speak"))
async def handle_toggle_speak(message: Message):
    """Handles /toggle_speak command."""
    user_id = message.from_user.id
    new_state = await database.toggle_speak_mode(user_id)
    state_text = "ВКЛЮЧЕНА" if new_state else "ВЫКЛЮЧЕНА"
    logger.info(f"User {user_id} toggled speak mode to {state_text}")
    await message.answer(f"🔊 Озвучка моих ответов теперь **{state_text}**.", parse_mode="MarkdownV2")

@router.message(Command("translate"))
async def handle_translate(message: Message, command: CommandObject, bot: Bot):
    """Handles /translate command."""
    if not command.args:
        await message.answer("Использование: `/translate <текст> [код_языка]`\nПример: `/translate Привет мир en`", parse_mode="MarkdownV2")
        return

    args_list = command.args.split()
    if len(args_list) < 2:
        # Если язык не указан, предполагаем английский по умолчанию,
        # или просим указать явно
        # await message.answer("Пожалуйста, укажите текст и код языка (например, en, fr, de).")
        # return
        text_to_translate = command.args
        target_lang = 'en' # По умолчанию английский
        await message.answer(f"Язык не указан, перевожу на английский (`en`).")

    else:
        target_lang_input = args_list[-1]
        text_to_translate = " ".join(args_list[:-1])
        # Попытка получить код языка (ru, en, fr...)
        target_lang = translator.get_lang_code(target_lang_input)
        logger.info(f"User {message.from_user.id} requested translation to '{target_lang}'. Original lang input: '{target_lang_input}'")

    processing_msg = await message.answer(f"Перевожу на язык '{target_lang}'...")

    # Используем googletrans с fallback на Gemini
    translated_text = await translator.translate_text_googletrans(text_to_translate, target_lang)

    if translated_text:
        response_text = f"**Оригинал:**\n{escape_markdown_v2(text_to_translate)}\n\n" \
                        f"**Перевод ({target_lang}):**\n{escape_markdown_v2(translated_text)}"
        await bot.edit_message_text(response_text, chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode="MarkdownV2")
    else:
        logger.error(f"Translation failed for user {message.from_user.id}")
        await bot.edit_message_text("Не удалось выполнить перевод.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)


# --- Callback Query Handlers ---

@router.callback_query(F.data.startswith("set_mood:"))
async def process_mood_callback(callback_query: CallbackQuery, bot: Bot):
    """Handles mood selection callbacks."""
    mood = callback_query.data.split(":")[1]
    user_id = callback_query.from_user.id

    await database.update_user_mood(user_id, mood)
    logger.info(f"User {user_id} set mood to {mood}")

    await callback_query.answer(f"Стиль общения изменен на: {mood}")
    try:
        # Редактируем исходное сообщение, убирая клавиатуру
        await bot.edit_message_text(
            f"✅ Стиль общения изменен на: `{mood}`",
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            reply_markup=None, # Убираем клавиатуру
            parse_mode="MarkdownV2"
        )
    except Exception as e:
         logger.error(f"Failed to edit mood message: {e}") # Ошибка может быть, если сообщение старое


# --- Message Handlers (Order Matters!) ---

# 1. Voice messages
@router.message(F.voice)
async def handle_voice_message(message: Message, bot: Bot):
    """Handles voice messages."""
    user_id = message.from_user.id
    logger.info(f"Received voice message from user {user_id}")
    processing_msg = await message.reply("Обрабатываю голосовое сообщение...")

    # 1. Скачиваем OGG файл
    ogg_filepath = get_temp_filepath("ogg")
    try:
        await bot.download(message.voice, destination=ogg_filepath)
        logger.debug(f"Voice message saved to {ogg_filepath}")
    except Exception as e:
        logger.error(f"Failed to download voice message from {user_id}: {e}")
        await bot.edit_message_text("Ошибка при скачивании голосового сообщения.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        await cleanup_temp_file(ogg_filepath) # Очистка на случай частичного скачивания
        return

    # 2. Распознавание речи (конвертация и очистка внутри)
    await bot.edit_message_text("Распознаю речь...", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
    recognized_text = await speech.recognize_speech(ogg_filepath) # Путь к ogg, очистка внутри recognize_speech

    if recognized_text:
        logger.info(f"User {user_id} voice recognized as: '{recognized_text}'")
        await bot.edit_message_text(f"Распознанный текст: \"{escape_markdown_v2(recognized_text)}\"\n\nГенерирую ответ...", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode="MarkdownV2")

        # 3. Обработка как текстового сообщения
        await database.add_message(user_id, 'user', recognized_text)
        response_text = await gemini.generate_text_response(user_id, recognized_text)

        if response_text:
            await database.add_message(user_id, 'model', response_text)
            # Отправка ответа (текст или голос)
            await send_response(bot, message.chat.id, user_id, response_text)
            # Удаляем сообщение "Генерирую ответ..."
            await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        else:
            await bot.edit_message_text(f"Распознанный текст: \"{escape_markdown_v2(recognized_text)}\"\n\nНе удалось сгенерировать ответ от AI.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id, parse_mode="MarkdownV2")

    else:
        logger.warning(f"Could not recognize speech from user {user_id}")
        await bot.edit_message_text("Не удалось распознать речь в вашем сообщении.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)


# 2. Photo messages
@router.message(F.photo)
async def handle_photo_message(message: Message, bot: Bot):
    """Handles photo messages."""
    user_id = message.from_user.id
    logger.info(f"Received photo from user {user_id}")
    processing_msg = await message.reply("Анализирую изображение...")

    # 1. Скачиваем фото (лучшее качество)
    photo = message.photo[-1] # Берем последний элемент - самое высокое разрешение
    jpg_filepath = get_temp_filepath("jpg")
    try:
        await bot.download(photo, destination=jpg_filepath)
        logger.debug(f"Photo saved to {jpg_filepath}")
    except Exception as e:
        logger.error(f"Failed to download photo from {user_id}: {e}")
        await bot.edit_message_text("Ошибка при скачивании изображения.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        await cleanup_temp_file(jpg_filepath)
        return

    # 2. Анализ изображения (OCR + Vision) и очистка файла внутри
    analysis_result = await image_analyzer.analyze_image(jpg_filepath, user_id)
    ocr_text = analysis_result.get("ocr_text")
    vision_analysis = analysis_result.get("vision_analysis")

    await bot.edit_message_text("Генерирую ответ на основе анализа изображения...", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)

    # 3. Формируем промпт для Gemini на основе анализа
    combined_info = ""
    response_prefix = "" # Начало ответа бота

    if ocr_text is not None: # OCR мог вернуть пустую строку или None при ошибке
        if ocr_text:
            response_prefix += f"**Распознанный текст (OCR):**\n```\n{escape_markdown_v2(ocr_text)}\n```\n\n"
            combined_info += f"На изображении распознан текст: '{ocr_text}'. "
        else: # Пустая строка - текст не найден
             response_prefix += "*Текст на изображении не найден (OCR).*\n\n"
             combined_info += "Текст на изображении не найден. "
    else: # None - была ошибка OCR
        response_prefix += "*Ошибка при распознавании текста (OCR).*\n\n"
        # combined_info += "Ошибка OCR. " # Можно не добавлять в combined_info

    if vision_analysis:
        response_prefix += f"**Анализ изображения (Gemini Vision):**\n{escape_markdown_v2(vision_analysis)}\n\n"
        combined_info += f"Описание изображения: '{vision_analysis}'"
    else:
         response_prefix += "*Не удалось получить анализ изображения (Gemini Vision).*\n\n"
         # combined_info += "Ошибка Vision." # Можно не добавлять

    # Если не удалось получить ни OCR, ни Vision
    if not ocr_text and not vision_analysis:
         await bot.edit_message_text("Не удалось проанализировать изображение.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
         return

    # Сохраняем в историю информацию об анализе как сообщение "пользователя"
    # Это не идеальный вариант, но позволяет Gemini "знать", что мы обсуждаем картинку
    analysis_summary_for_history = f"[Анализ изображения] OCR: {ocr_text if ocr_text else 'Нет/Ошибка'}. Vision: {vision_analysis if vision_analysis else 'Нет/Ошибка'}."
    await database.add_message(user_id, 'user', analysis_summary_for_history)

    # 4. Генерируем финальный ответ Gemini (например, с просьбой прокомментировать анализ)
    # user_followup_prompt = "Что ты думаешь об этом изображении и тексте на нем?" # Или просто используем combined_info как промпт
    # response_text = await gemini.generate_text_response(user_id, user_followup_prompt)

    # Пока просто отправляем результат анализа
    response_text = response_prefix.strip() # Используем собранный текст ответа
    await database.add_message(user_id, 'model', response_text) # Сохраняем сам анализ как ответ модели

    # 5. Отправка ответа (текст или голос)
    await send_response(bot, message.chat.id, user_id, response_text, parse_mode="MarkdownV2") # Используем Markdown
    # Удаляем сообщение "Генерирую ответ..."
    await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)


# 3. Document messages
@router.message(F.document)
async def handle_document_message(message: Message, bot: Bot):
    """Handles document messages."""
    user_id = message.from_user.id
    doc = message.document
    filename = doc.file_name or "unknown_file"
    mime_type = doc.mime_type
    file_size = doc.file_size or 0

    logger.info(f"Received document '{filename}' from user {user_id} (Type: {mime_type}, Size: {file_size})")
    processing_msg = await message.reply(f"Получил файл '{filename}'. Обрабатываю...")

    # 1. Скачиваем файл
    doc_filepath = settings.TEMP_DIR / f"{doc.file_id}_{filename}" # Используем file_id для уникальности
    try:
        await bot.download(doc, destination=doc_filepath)
        logger.debug(f"Document saved to {doc_filepath}")
    except Exception as e:
        logger.error(f"Failed to download document '{filename}' from {user_id}: {e}")
        await bot.edit_message_text(f"Ошибка при скачивании файла '{filename}'.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
        await cleanup_temp_file(doc_filepath)
        return

    # 2. Обработка файла, анализ и очистка (все внутри file_handler.process_file)
    await bot.edit_message_text(f"Анализирую содержимое файла '{filename}'...", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)
    process_result = await file_handler.process_file(doc_filepath, filename, mime_type, file_size)

    # process_result это tuple: (status_message, analysis_result) или None

    if process_result:
        status_message, analysis_result = process_result

        # Формируем ответ
        response_text = f"**Файл:** `{escape_markdown_v2(filename)}`\n"
        response_text += f"**Статус:** {escape_markdown_v2(status_message)}\n\n"

        if analysis_result:
            response_text += f"**Анализ содержимого (Gemini):**\n{escape_markdown_v2(analysis_result)}"
            # Сохраняем анализ как ответ модели в историю
            await database.add_message(user_id, 'model', f"[Анализ файла {filename}]: {analysis_result}")
        else:
             # Если анализ не удался, но файл был обработан (например, неподдерживаемый тип или ошибка Gemini)
             # status_message уже содержит информацию об этом
             # Можно добавить уточнение
             if "Не удалось получить анализ" in status_message or "Ошибка при анализе" in status_message:
                  response_text += "_Не удалось получить детальный анализ от AI._"
             # Если тип не поддерживается, status_message уже это скажет

        # Отправка ответа (текст или голос)
        await send_response(bot, message.chat.id, user_id, response_text, parse_mode="MarkdownV2")
        await bot.delete_message(chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)

    else:
        # Сюда попадаем, если process_file вернул None (например, критическая ошибка)
        logger.error(f"File processing failed unexpectedly for '{filename}' user {user_id}")
        await bot.edit_message_text(f"Не удалось обработать файл '{filename}'.", chat_id=processing_msg.chat.id, message_id=processing_msg.message_id)


# 4. Text messages (should be last message handler)
@router.message(F.text)
async def handle_text_message(message: Message, bot: Bot):
    """Handles regular text messages."""
    user_id = message.from_user.id
    user_text = message.text
    logger.info(f"Received text message from user {user_id}: '{user_text[:100]}...'")

    # Показываем "печатает..."
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # 1. Сохраняем сообщение пользователя в историю
    await database.add_message(user_id, 'user', user_text)

    # 2. Генерируем ответ с помощью Gemini
    response_text = await gemini.generate_text_response(user_id, user_text)

    if response_text:
        # 3. Сохраняем ответ бота в историю
        await database.add_message(user_id, 'model', response_text)
        # 4. Отправляем ответ (текст или голос)
        await send_response(bot, message.chat.id, user_id, response_text)
    else:
        logger.error(f"Failed to generate Gemini response for user {user_id}")
        await message.reply("Извините, не могу сейчас ответить. Попробуйте позже.")

# --- Helper Function for Sending Responses ---

async def send_response(bot: Bot, chat_id: int, user_id: int, text: str, parse_mode: Optional[str] = None):
    """Sends response as text or voice based on user settings."""
    try:
        speak_enabled = await database.get_speak_enabled(user_id)
        if speak_enabled:
            logger.info(f"Sending voice response to user {user_id}")
            await tts.speak_and_cleanup(bot, chat_id, text) # Генерирует, отправляет, удаляет mp3
        else:
            logger.info(f"Sending text response to user {user_id}")
            # Ограничение длины сообщения Telegram
            max_len = 4096
            if len(text) <= max_len:
                 await bot.send_message(chat_id, text, parse_mode=parse_mode, disable_web_page_preview=True)
            else:
                 logger.warning(f"Response for user {user_id} is too long ({len(text)} chars). Sending in parts.")
                 # Разбиваем на части
                 for i in range(0, len(text), max_len):
                     part = text[i:i + max_len]
                     await bot.send_message(chat_id, part, parse_mode=parse_mode, disable_web_page_preview=True)
                     await asyncio.sleep(0.5) # Небольшая задержка между частями

    except Exception as e:
        logger.error(f"Error sending response to user {user_id} (chat {chat_id}): {e}")
        logger.exception(e)
        # Попытка отправить простое текстовое сообщение об ошибке
        try:
            await bot.send_message(chat_id, "Произошла ошибка при отправке ответа.")
        except Exception as fallback_e:
            logger.error(f"Failed to send fallback error message to {chat_id}: {fallback_e}")