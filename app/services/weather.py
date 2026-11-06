import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

WEATHER_API = os.getenv("WEATHER_API")
OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"


async def make_weather_request(endpoint: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Вспомогательная функция для выполнения запросов к OpenWeatherMap API.

    Args:
        endpoint: Конечная точка API (например, "weather" или "forecast")
        params: Параметры запроса

    Returns:
        JSON ответ от API или None в случае ошибки

    """
    if not WEATHER_API:
        logger.error("WEATHER_API не найден в переменных окружения")
        return None

    params["appid"] = WEATHER_API
    params["lang"] = "ru"

    url = f"{OPENWEATHER_BASE_URL}/{endpoint}"

    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Запрос к API: {url}")
            response = await client.get(url, params=params, timeout=30.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP ошибка: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при запросе к API: {e!s}")
        return None


async def get_forecast(city: str, days: int = 3, units: str = "metric") -> str | list[str]:
    """Получить прогноз погоды на несколько дней.

    Args:
        city: Название города на русском или английском
        days: Количество дней для прогноза (1-5)
        units: Система измерения - "metric" (Цельсий) или "imperial" (Фаренгейт)

    Returns:
        Строка с прогнозом погоды от API

    """
    logger.info(f"Запрос прогноза для города: {city} на {days} дней")

    days = min(max(days, 1), 5)

    params = {
        "q": city,
        "units": units,
        "cnt": days * 8,
    }

    data = await make_weather_request("forecast", params)

    if not data:
        return f"❌ Не удалось получить прогноз для города '{city}'."

    if "cod" not in data or data["cod"] != "200":
        return f"❌ Ошибка API: {data.get('message', 'Неизвестная ошибка')}"

    logger.info(f"Успешно получены сырые данные прогноза для {city}")

    times = ["15:00:00", "12:00:00", "09:00:00"]
    afternoon = [lst for lst in data["list"] if lst["dt_txt"].split()[1] in times]

    result = []
    for lst in afternoon:
        result.append(
            f"Дата время: {lst['dt_txt']}\n"
            f"Температура: {lst['main']['temp']}\n"
            f"Скорость ветра: {lst['wind']['speed']}\n"
            f"Влажность: {lst['main']['humidity']}\n"
            f"Условия: {lst['weather'][0]['description']}\n"
        )

    return result
