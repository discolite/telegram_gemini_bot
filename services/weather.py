import aiohttp
import asyncio # <--- ИЗМЕНЕНИЕ: Добавлен импорт asyncio
from loguru import logger
from typing import Optional, Dict
from config import settings

API_KEY = settings.OPENWEATHERMAP_API_KEY
BASE_URL = "http://api.openweathermap.org/data/2.5/weather"

async def get_weather(city: str = "Moscow") -> Optional[str]:
    """Fetches weather data from OpenWeatherMap and formats it."""
    if not API_KEY:
        logger.warning("OpenWeatherMap API key is missing. Cannot fetch weather.")
        return "Сервис погоды недоступен (отсутствует API ключ)"

    params = {
        'q': city,
        'appid': API_KEY,
        'units': 'metric', # Градусы Цельсия
        'lang': 'ru'       # Русский язык
    }

    # <--- ИЗМЕНЕНИЕ: Устанавливаем таймаут, например, 15 секунд --->
    request_timeout = 15
    timeout = aiohttp.ClientTimeout(total=request_timeout)
    logger.debug(f"Requesting weather for {city} with timeout {request_timeout}s")

    try:
        # <--- ИЗМЕНЕНИЕ: Добавляем timeout в ClientSession --->
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(BASE_URL, params=params) as response:
                response_text = await response.text() # Читаем ответ один раз
                logger.debug(f"OpenWeatherMap response status for {city}: {response.status}")
                if response.status == 200:
                    try:
                        data = await response.json(content_type=None) # Иногда content-type бывает неверным
                        logger.info(f"Successfully fetched weather for {city}")
                        return await _format_weather_data(data, city)
                    except Exception as json_err:
                        logger.error(f"Failed to parse JSON response from OpenWeatherMap for {city}: {json_err}. Response text: {response_text[:200]}...")
                        return f"Ошибка обработки ответа от сервиса погоды для '{city}'"
                elif response.status == 404:
                    logger.warning(f"City not found on OpenWeatherMap: {city}")
                    return f"Город '{city}' не найден. Попробуйте указать другой город"
                elif response.status == 401:
                    logger.error(f"Invalid OpenWeatherMap API key. Response: {response_text[:200]}...")
                    return "Ошибка авторизации в сервисе погоды. Проверьте API ключ"
                elif response.status == 429:
                    logger.warning(f"Rate limit exceeded for OpenWeatherMap API. Response: {response_text[:200]}...")
                    return "Превышен лимит запросов к сервису погоды. Попробуйте позже"
                else:
                    logger.error(f"Error fetching weather for {city}. Status: {response.status}, Response: {response_text[:200]}...")
                    return f"Не удалось получить погоду для '{city}'. Статус: {response.status}"
    # <--- ИЗМЕНЕНИЕ: Обработка исключения таймаута --->
    except asyncio.TimeoutError:
         logger.error(f"Timeout error ({request_timeout}s) fetching weather for {city}")
         return f"Время ожидания ответа от сервиса погоды для '{city}' истекло ({request_timeout} сек)"
    except aiohttp.ClientConnectorError as e:
        logger.error(f"Network connection error fetching weather for {city}: {e}")
        return f"Ошибка сети при получении погоды для '{city}'"
    except aiohttp.ClientError as e: # Ловим другие ошибки aiohttp
        logger.error(f"AIOHTTP client error fetching weather for {city}: {e}")
        return f"Ошибка клиента при получении погоды для '{city}'"
    except Exception as e:
        logger.error(f"Unexpected error fetching weather for {city}: {e}")
        logger.exception(e)
        return f"Непредвиденная ошибка при получении погоды для '{city}'"

async def _format_weather_data(data: Dict, city_name: str) -> str:
    """Formats the raw weather data into a user-friendly string."""
    try:
        main = data.get('main', {})
        weather_list = data.get('weather', [])
        weather_desc = weather_list[0].get('description', 'нет данных') if weather_list else 'нет данных'
        wind = data.get('wind', {})

        temp = main.get('temp', 'N/A')
        feels_like = main.get('feels_like', 'N/A')
        humidity = main.get('humidity', 'N/A')
        wind_speed = wind.get('speed', 'N/A')

        # Используем f-string с экранированием для MarkdownV2
        weather_report = (
            f"☀️ **Погода в городе {data.get('name', city_name).replace('.', r'.')}**:\n" # Экранируем точку в названии города
            f"🌡️ Температура: {temp}°C \(ощущается как {feels_like}°C\)\n"
            f"📝 Состояние: {weather_desc.capitalize().replace('.', r'.')}\n" # Экранируем точку в описании
            f"💧 Влажность: {humidity}%\n"
            f"💨 Ветер: {wind_speed} м/с"
        )
        logger.debug(f"Formatted weather report for {city_name}: {weather_report}")
        return weather_report

    except Exception as e:
        logger.error(f"Error formatting weather data for {city_name}: {e}")
        logger.exception(e)
        return f"Ошибка обработки данных о погоде для {city_name}"