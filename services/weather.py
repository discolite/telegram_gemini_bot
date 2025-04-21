import aiohttp
from loguru import logger
from typing import Optional, Dict
from config import settings
# from services.gemini import generate_text_response # Опционально для Gemini-описания

API_KEY = settings.OPENWEATHERMAP_API_KEY
BASE_URL = "http://api.openweathermap.org/data/2.5/weather"

async def get_weather(city: str = "Moscow") -> Optional[str]:
    """Fetches weather data from OpenWeatherMap and formats it."""
    if not API_KEY:
        logger.warning("OpenWeatherMap API key is missing. Cannot fetch weather.")
        return "Сервис погоды недоступен (отсутствует API ключ)."

    params = {
        'q': city,
        'appid': API_KEY,
        'units': 'metric', # Градусы Цельсия
        'lang': 'ru'       # Русский язык
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BASE_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Successfully fetched weather for {city}")
                    return await _format_weather_data(data, city)
                elif response.status == 404:
                    logger.warning(f"City not found on OpenWeatherMap: {city}")
                    return f"Город '{city}' не найден. Попробуйте указать другой город."
                elif response.status == 401:
                    logger.error("Invalid OpenWeatherMap API key.")
                    return "Ошибка авторизации в сервисе погоды. Проверьте API ключ."
                else:
                    logger.error(f"Error fetching weather for {city}. Status: {response.status}, Response: {await response.text()}")
                    return f"Не удалось получить погоду для '{city}'. Статус: {response.status}"
    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching weather for {city}: {e}")
        return f"Сетевая ошибка при получении погоды для '{city}'."
    except Exception as e:
        logger.error(f"Unexpected error fetching weather for {city}: {e}")
        logger.exception(e)
        return f"Непредвиденная ошибка при получении погоды для '{city}'."

async def _format_weather_data(data: Dict, city_name: str) -> str:
    """Formats the raw weather data into a user-friendly string."""
    try:
        main = data.get('main', {})
        weather_desc = data.get('weather', [{}])[0].get('description', 'нет данных')
        wind = data.get('wind', {})

        temp = main.get('temp', 'N/A')
        feels_like = main.get('feels_like', 'N/A')
        humidity = main.get('humidity', 'N/A')
        wind_speed = wind.get('speed', 'N/A')

        # Базовое форматирование
        weather_report = (
            f"☀️ **Погода в городе {data.get('name', city_name)}:**\n"
            f"🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n"
            f"📝 Состояние: {weather_desc.capitalize()}\n"
            f"💧 Влажность: {humidity}%\n"
            f"💨 Ветер: {wind_speed} м/с"
        )

        # --- Опционально: Интеграция с Gemini для "естественного" описания ---
        # try:
        #     # Создаем промпт для Gemini
        #     gemini_prompt = f"На основе этих данных о погоде в {data.get('name', city_name)}: температура {temp}°C, ощущается как {feels_like}°C, состояние '{weather_desc}', влажность {humidity}%, ветер {wind_speed} м/с. Дай краткий совет или комментарий в дружелюбном тоне (например, 'Возьмите зонт!', 'Отличный день для прогулки!'). Не повторяй цифры, просто дай совет."
        #
        #     # Важно: Используйте ID фиктивного пользователя или специальный ID,
        #     # чтобы не смешивать контекст погоды с обычным чатом пользователя.
        #     # Или передавайте user_id=None (если функция gemini это поддерживает)
        #     # или реализуйте отдельную функцию в gemini.py без user_id.
        #     # Здесь предполагаем, что generate_text_response может работать без user_id
        #     # или используется ID = 0 для системных запросов.
        #     # ПРЕДУПРЕЖДЕНИЕ: Это может потребовать доработки generate_text_response
        #
        #     # Пример вызова (требует адаптации generate_text_response):
        #     # natural_comment = await generate_text_response(user_id=0, user_prompt=gemini_prompt)
        #     natural_comment = None # Заглушка
        #
        #     if natural_comment and "ошибка" not in natural_comment.lower():
        #         weather_report += f"\n\n💡 {natural_comment}"
        #     else:
        #         logger.warning(f"Could not get natural weather comment from Gemini for {city_name}.")
        #
        # except Exception as e:
        #     logger.error(f"Error getting natural weather comment from Gemini: {e}")
        # --- Конец опциональной части ---

        return weather_report

    except Exception as e:
        logger.error(f"Error formatting weather data for {city_name}: {e}")
        logger.exception(e)
        return f"Ошибка обработки данных о погоде для {city_name}."