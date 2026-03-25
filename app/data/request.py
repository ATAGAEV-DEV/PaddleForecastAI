import asyncio
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.data.models import Friends, Users, WeatherRequests, WorkDay, async_session

DB_TIMEOUT = 10


async def get_user_by_id(user_id: int) -> Users | None:
    """Получает пользователя из базы данных по его идентификатору.

    Выполняет асинхронный запрос к базе данных для поиска записи в таблице 'users'
    с указанным user_id. Возвращает объект пользователя или None, если пользователь
    не найден. В случае ошибки выводит сообщение об ошибке и возвращает None.

    Args:
        user_id (int): Уникальный идентификатор пользователя в Telegram.

    Returns:
        Users | None: Объект пользователя, если найден, иначе None.

    """
    try:
        async with async_session() as session:
            query = select(Users).where(Users.user_id == user_id)
            result = await asyncio.wait_for(session.execute(query), timeout=DB_TIMEOUT)
            return result.scalar_one_or_none()
    except TimeoutError:
        print(f"Таймаут при получении пользователя с user_id={user_id}")
        return None
    except Exception as e:
        print(f"Ошибка получения пользователя: {e}")
        return None


async def add_user(user_id: int, username: str) -> None:
    """Добавляет нового пользователя или обновляет существующего в базе данных.

    Использует upsert (INSERT ... ON CONFLICT DO UPDATE) для безопасного
    добавления пользователя. Если пользователь уже существует, обновляется username.

    Args:
        user_id (int): Уникальный идентификатор пользователя в Telegram.
        username (str): Имя пользователя в Telegram (может быть пустым).

    """
    try:
        async with async_session() as session:
            stmt = pg_insert(Users).values(user_id=user_id, username=username)
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id"],
                set_={"username": username},
            )
            await asyncio.wait_for(session.execute(stmt), timeout=DB_TIMEOUT)
            await asyncio.wait_for(session.commit(), timeout=DB_TIMEOUT)
    except TimeoutError:
        print(f"Таймаут при добавлении пользователя с user_id={user_id}")
    except Exception as e:
        print(f"Ошибка добавления пользователя: {e}")


async def save_weather_request(user_id: int, forecast_text: str, ai_response: str) -> None:
    """Сохраняет запрос прогноза погоды и ответ ИИ в базу данных.

    Создаёт новую запись в таблице 'weather_requests', содержащую идентификатор пользователя,
    текст прогноза погоды и ответ ИИ-советника. В случае ошибки выводит сообщение об ошибке.
    """
    try:
        async with async_session() as session:
            request = WeatherRequests(
                user_id=user_id, forecast_text=forecast_text, ai_response=ai_response
            )
            session.add(request)
            await session.commit()
    except Exception as e:
        print(f"Ошибка сохранения запроса погоды: {e}")


async def get_friend_by_name(name: str) -> Friends | None:
    """Получает друга по имени из базы данных."""
    try:
        async with async_session() as session:
            # Используем ilike для регистронезависимого поиска
            query = select(Friends).where(Friends.name.ilike(name))
            result = await session.execute(query)
            return result.scalar_one_or_none()
    except Exception as e:
        print(f"Ошибка получения друга: {e}")
        return None


async def get_friend_working_days(friend_id: int, start_date: date, end_date: date) -> list[date]:
    """Получает список рабочих дней друга в заданном диапазоне.

    Возвращает список дат (date), когда друг работает (is_working=True).
    """
    try:
        async with async_session() as session:
            query = (
                select(WorkDay.date)
                .where(
                    WorkDay.user_id == friend_id,
                    WorkDay.is_working.is_(True),
                    WorkDay.date >= start_date,
                    WorkDay.date <= end_date,
                )
                .order_by(WorkDay.date)
            )
            result = await session.execute(query)
            return list(result.scalars().all())
    except Exception as e:
        print(f"Ошибка получения рабочих дней друга: {e}")
        return []


async def get_all_friends() -> list[Friends]:
    """Получает список всех друзей из базы данных."""
    try:
        async with async_session() as session:
            query = select(Friends).order_by(Friends.name)
            result = await session.execute(query)
            return list(result.scalars().all())
    except Exception as e:
        print(f"Ошибка получения списка друзей: {e}")
        return []
