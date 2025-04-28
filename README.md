# Telegram AI Bot (Gemini + Multimedia)

Многофункциональный Telegram-бот на Python с использованием `aiogram`, Google Gemini, SQLite и других сервисов.

## Возможности

*   **🤖 Интеллектуальные ответы:** Генерация ответов на текстовые сообщения с помощью Google Gemini (`gemini-1.5-pro`), учёт контекста последних 5 сообщений.
*   **🗣️ Обработка голоса:** Распознавание речи (русский язык) из голосовых сообщений (`speech_recognition` + Google Speech API) и ответ через Gemini.
*   **🖼️ Анализ изображений:** Извлечение текста (OCR Tesseract: ru+en) и описание содержимого (Gemini Vision).
*   **📄 Обработка файлов:** Анализ содержимого `.txt`, `.pdf`, `.csv`, `.xlsx` файлов с помощью Gemini.
*   **☀️ Прогноз погоды:** Получение погоды по команде `/weather <город>` (OpenWeatherMap API).
*   **🎭 Настраиваемый стиль:** Выбор стиля общения (дружелюбный, профессиональный, саркастичный) через `/mood`.
*   **🔊 Озвучивание ответов:** Генерация голосовых ответов (`gTTS`), включение/выключение озвучки (`/toggle_speak`), разовое озвучивание (`/speak <текст>`).
*   **🌐 Перевод текста:** Перевод с помощью `googletrans` (с fallback на Gemini) по команде `/translate <текст> [язык]`.
*   **🔒 Безопасность:** Доступ только для авторизованных пользователей (список ID в `.env`).
*   **📝 Логирование:** Запись действий и ошибок в `bot.log` с ротацией.
*   **💾 Оптимизация диска:** Автоматическое удаление временных файлов, ротация логов (цель < 9 ГБ общего использования).

## Технический стек

*   Python 3.11
*   aiogram 3.x
*   Google Gemini API (Generative AI)
*   SQLite (aiosqlite)
*   OpenWeatherMap API
*   Tesseract OCR
*   SpeechRecognition (Google Speech API)
*   gTTS (Google Text-to-Speech)
*   googletrans
*   Pandas, OpenPyXL, PyPDF2
*   Loguru
*   Pydub (требует ffmpeg)
*   python-dotenv

## Установка на Ubuntu 24.04

<<<<<<< HEAD
**1. Системные зависимости:**
=======
   ```bash
   git clone https://github.com/discolite/telegram_gemini_bot.git
   cd telegram_gemini_bot
   ```
>>>>>>> 3cf87d3b846be54ddd690107932bde8a9a0bb20e

```bash
sudo apt update && sudo apt upgrade -y

# Установка Python 3.11 (может быть уже установлен) и pip
sudo apt install -y python3.11 python3.11-venv python3-pip git

# Установка Tesseract OCR с русским и английским языками
sudo apt install -y tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng

<<<<<<< HEAD
# Установка ffmpeg (для обработки аудио - pydub)
sudo apt install -y ffmpeg
=======

   pip install -r requirements.txt

>>>>>>> 3cf87d3b846be54ddd690107932bde8a9a0bb20e

# Установка PortAudio (может потребоваться для SpeechRecognition, если не использовать только Google API)
# sudo apt install -y portaudio19-dev

<<<<<<< HEAD
# Проверка установки Tesseract
tesseract --version
tesseract --list-langs | grep -E 'rus|eng' # Должен показать rus и eng
=======
5. Запустите бота:

 
   python main.py
 

## Разработка

Для разработки и тестирования используйте виртуальное окружение. Все изменения в коде необходимо тестировать на локальном сервере, прежде чем отправлять в основной репозиторий.

## Логирование

Логи бота хранятся в директории `logs/` в файле `bot.log`.

## Лицензия

Этот проект лицензируется под лицензией MIT. См. файл LICENSE для подробностей.
>>>>>>> 3cf87d3b846be54ddd690107932bde8a9a0bb20e
