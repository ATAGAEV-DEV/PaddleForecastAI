import os

from dotenv import load_dotenv
from openai import APIConnectionError, APIError, AsyncOpenAI, BadRequestError
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from app.tools.utils import clean_text

load_dotenv()

AI_TOKEN_POLZA = os.getenv("AI_TOKEN_POLZA")
polza = "https://api.polza.ai/api/v1"

client = AsyncOpenAI(
    api_key=AI_TOKEN_POLZA,
    base_url=polza,
)


async def ai_generate(weather_forecast: str) -> str | None:
    """Генерирует рекомендации по сёрфингу на основе прогноза погоды с использованием ИИ.

    Формирует промпт с пользовательскими предпочтениями, отправляет запрос в модель ИИ
    и возвращает очищенный текст с рекомендациями. В случае ошибок — выводит сообщение
    в консоль и возвращает None.
    """
    message = await generate_prompt(weather_forecast)
    try:
        completion = await client.chat.completions.create(
            model="openai/gpt-4o",
            messages=message,
            temperature=0.8,
        )

        response_text = completion.choices[0].message.content
        response = clean_text(response_text)
        return response

    except BadRequestError as e:
        print(f"Ошибка запроса к API: {e}")

    except APIConnectionError as e:
        print(f"Ошибка подключения к API: {e}")

    except APIError as e:
        print(f"Ошибка API: {e}")

    except Exception as e:
        print(f"Неожиданная ошибка: {e}")


async def generate_prompt(
    weather_forecast: str,
) -> list[ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam]:
    """Формирует системный и пользовательский промпты для ИИ-модели.

    Создаёт список сообщений, включающий системное сообщение с ролью консультанта
    и пользовательское сообщение с прогнозом погоды. Промпт нацелен на получение
    практических, дружелюбных рекомендаций для сап-сёрфинга в заданном формате.
    """
    prompt = """Ты дружелюбный метео-консультант для сап-серфера. 
    Проанализируй прогноз погоды и дай практические рекомендации в разговорном стиле.

    Мои предпочтения:
    - Катаюсь обычно с 11:00 до 14:00 около 1 часа
    - Минимальная температура: от 12°C
    - Предпочитаю слабый ветер (до 5 м/с)

    Проанализируй каждый день и посоветуй:
    1. В какое конкретное время ЛУЧШЕ ВСЕГО начинать кататься в этот день
    2. Как изменятся условия в течение дня (если существенно)
    3. Есть ли ограничения или риски

    ФОРМАТ ОТВЕТА:
    Начинай сразу с рекомендаций, без вступлений. Говори как друг-советчик.

    Пример хорошего ответа:
    "В понедельник 10 ноября - идеальный день! Начинай в 11:30, будет 18°C и почти нет ветра. 
    Можно кататься до 14:00 без проблем.
    Во вторник 11 ноября - тоже отлично, но лучше начать в 12:00,
    когда станет немного теплее. После 15:00 ветер может усилиться.
    В среду 12 ноября - хорошие условия, но с утра может быть прохладно,
    рекомендую начать в 11:30..."

    Используй естественный язык, не перечисляй все данные подряд.
    Сосредоточься на временном окне 11:00-14:00."""

    message = [
        ChatCompletionSystemMessageParam(role="system", content=prompt),
        ChatCompletionUserMessageParam(role="user", content=f"{weather_forecast}"),
    ]

    return message
