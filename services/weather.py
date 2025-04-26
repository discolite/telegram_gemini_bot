# /home/telegram_gemini_bot/services/weather.py

import aiohttp
import asyncio
from loguru import logger
from typing import Optional, Dict

# Импортируем настройки и хелпер экранирования
from config import settings
from utils.helpers import escape_markdown_v2 # <--- ИМПОРТ ХЕЛПЕРА

API_KEY = settings.OPENWEATHERMAP_API_KEY
BASE_URL = "http://api.openweathermap.org/data/2.5/weather"

async def get_weather(city: str = "Moscow") -> Optional[str]:
    """Fetches weather data from OpenWeatherMap and formats it for MarkdownV2."""
    if not API_KEY:
        logger.warning("OpenWeatherMap API key is missing. Cannot fetch weather.")
        # Возвращаем строку БЕЗ Markdown, т.к. это сообщение об ошибке
        return "Сервис погоды недоступен (отсутствует API ключ)"

    params = {
        'q': city,
        'appid': API_KEY,
        'units': 'metric', # Градусы Цельсия
        'lang': 'ru'       # Русский язык
    }

    request_timeout = 15
    timeout = aiohttp.ClientTimeout(total=request_timeout)
    logger.debug(f"Requesting weather for {city} with timeout {request_timeout}s")

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(BASE_URL, params=params) as response:
                response_text = await response.text()
                logger.debug(f"OpenWeatherMap response status for {city}: {response.status}")
                if response.status == 200:
                    try:
                        # Используем response.json(), т.к. text() уже прочитал тело
                        data = await response.json(content_type=None)
                        logger.info(f"Successfully fetched weather for {city}")
                        # <--- ВЫЗЫВАЕМ ОБНОВЛЕННЫЙ ФОРМАТТЕР ---
                        return await _format_weather_data_markdownv2(data, city)
                    except Exception as json_err:
                        logger.error(f"Failed to parse JSON response from OpenWeatherMap for {city}: {json_err}. Response text: {response_text[:200]}...")
                        # Сообщения об ошибках БЕЗ Markdown
                        return f"Ошибка обработки ответа от сервиса погоды для '{escape_markdown_v2(city)}'"
                elif response.status == 404:
                    logger.warning(f"City not found on OpenWeatherMap: {city}")
                    return f"Город '{escape_markdown_v2(city)}' не найден\\. Попробуйте указать другой город"
                elif response.status == 401:
                    logger.error(f"Invalid OpenWeatherMap API key. Response: {response_text[:200]}...")
                    return "Ошибка авторизации в сервисе погоды\\. Проверьте API ключ"
                elif response.status == 429:
                    logger.warning(f"Rate limit exceeded for OpenWeatherMap API. Response: {response_text[:200]}...")
                    return "Превышен лимит запросов к сервису погоды\\. Попробуйте позже"
                else:
                    logger.error(f"Error fetching weather for {city}. Status: {response.status}, Response: {response_text[:200]}...")
                    return f"Не удалось получить погоду для '{escape_markdown_v2(city)}'\\. Статус: {response.status}"
    except asyncio.TimeoutError:
         logger.error(f"Timeout error ({request_timeout}s) fetching weather for {city}")
         return f"Время ожидания ответа от сервиса погоды для '{escape_markdown_v2(city)}' истекло \\({request_timeout} сек\\)"
    except aiohttp.ClientConnectorError as e:
        logger.error(f"Network connection error fetching weather for {city}: {e}")
        return f"Ошибка сети при получении погоды для '{escape_markdown_v2(city)}'"
    except aiohttp.ClientError as e:
        logger.error(f"AIOHTTP client error fetching weather for {city}: {e}")
        return f"Ошибка клиента при получении погоды для '{escape_markdown_v2(city)}'"
    except Exception as e:
        logger.error(f"Unexpected error fetching weather for {city}: {e}")
        logger.exception(e)
        return f"Непредвиденная ошибка при получении погоды для '{escape_markdown_v2(city)}'"

# <--- ПЕРЕИМЕНОВАНА И ИЗМЕНЕНА ФУНКЦИЯ ФОРМАТИРОВАНИЯ ---
async def _format_weather_data_markdownv2(data: Dict, city_name: str) -> str:
    """Formats the raw weather data into a MarkdownV2 string."""
    try:
        main = data.get('main', {})
        weather_list = data.get('weather', [])
        weather_desc_raw = weather_list[0].get('description', 'нет данных') if weather_list else 'нет данных'
        wind = data.get('wind', {})

        # Получаем значения или 'N/A', если ключа нет
        temp_raw = main.get('temp')
        feels_like_raw = main.get('feels_like')
        humidity_raw = main.get('humidity')
        wind_speed_raw = wind.get('speed')

        # Преобразуем в строки и экранируем для MarkdownV2
        city_display_name = escape_markdown_v2(data.get('name', city_name))
        temp = escape_markdown_v2(f"{temp_raw:.2f}") if isinstance(temp_raw, (int, float)) else 'N/A'
        feels_like = escape_markdown_v2(f"{feels_like_raw:.2f}") if isinstance(feels_like_raw, (int, float)) else 'N/A'
        humidity = escape_markdown_v2(str(humidity_raw)) if humidity_raw is not None else 'N/A'
        wind_speed = escape_markdown_v2(str(wind_speed_raw)) if wind_speed_raw is not None else 'N/A'
        weather_desc = escape_markdown_v2(weather_desc_raw.capitalize())

        # Формируем строку с MarkdownV2 разметкой и экранированными данными
        # Экранируем ТОЛЬКО статические точки
        weather_report = (
            f"☀️ *Погода в городе {city_display_name}*:\n\n"
            f"🌡️ Температура: `{temp}`°C \\(ощущается как `{feels_like}`°C\\)\n"
            f"📝 Состояние: {weather_desc}\n"
            f"💧 Влажность: `{humidity}`%\n"
            # Экранируем точку в "м/с"
            f"💨 Ветер: `{wind_speed}` м\\/с"
        )
        logger.debug(f"Formatted MarkdownV2 weather report for {city_name}: {weather_report}")
        return weather_report

    except Exception as e:
        logger.error(f"Error formatting weather data for {city_name}: {e}")
        logger.exception(e)
        # Возвращаем сообщение об ошибке БЕЗ Markdown
        return f"Ошибка обработки данных о погоде для {escape_markdown_v2(city_name)}"