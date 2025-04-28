<div align="center">
  
  <h1>🤖 Telegram Gemini Bot</h1>
  
  <p>Многофункциональный ИИ-бот для Telegram, который понимает текст, голос, изображения и документы.</p>
  
  <img src="https://img.shields.io/badge/Python-3.11-blue?logo=python">
  <img src="https://img.shields.io/badge/Aiogram-3.x-lightgrey?logo=telegram">
  <img src="https://img.shields.io/badge/Status-Active-brightgreen">
  
</div>

---

# 📋 Описание

Многофункциональный Telegram-бот с поддержкой текста, голоса, изображений и файлов, использующий Google Gemini AI и другие сервисы.

## 🚀 Основные возможности
- Ответы с ИИ (Google Gemini).
- Распознавание речи и преобразование голосовых сообщений в текст.
- Анализ изображений (OCR и Vision API).
- Работа с текстовыми, PDF, CSV, Excel файлами.
- Прогноз погоды по команде `/weather`.
- Настройка стиля общения с ИИ.
- Озвучивание ответов и генерация голосовых сообщений.
- Перевод текста на разные языки.
- Авторизация пользователей через список ID.

## 🛠️ Технологии
- Python 3.11
- aiogram
- Google Gemini API
- SQLite (aiosqlite)
- OpenWeatherMap API
- Tesseract OCR
- SpeechRecognition
- gTTS, Pydub (FFmpeg)
- Pandas, OpenPyXL, PyPDF2
- googletrans
- Loguru
- python-dotenv

## 📦 Установка

```bash
git clone https://github.com/discolite/telegram_gemini_bot.git
cd telegram_gemini_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Скопируйте `.env.example` в `.env` и заполните необходимые переменные окружения.

## ▶️ Запуск
```bash
python main.py
```

## 📁 Структура проекта
- `/bot` — обработчики Telegram-сообщений
- `/config` — настройки
- `/services` — работа с внешними API
- `/utils` — вспомогательные функции
- `main.py` — стартовый скрипт
- `requirements.txt` — зависимости проекта

---
