from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.data.models import Friends, Users, WeatherRequests, WorkDay
from app.data.request import (
    add_user,
    get_all_friends,
    get_friend_by_name,
    get_friend_working_days,
    get_user_by_id,
    save_weather_request,
)

pytestmark = pytest.mark.integration


async def test_database_round_trip_preserves_users_friends_and_schedules(db_session, monkeypatch) -> None:
    """Persist and read all application records through the real request helpers."""
    session_factory = async_sessionmaker(db_session, expire_on_commit=False)
    monkeypatch.setattr("app.data.request.async_session", session_factory)

    await add_user(10, "first")
    await add_user(10, "updated")
    await save_weather_request(10, "forecast", "advice")

    async with session_factory() as session:
        session.add_all(
            [
                Friends(id=1, name="Arbi"),
                Friends(id=2, name="Zelim"),
                WorkDay(user_id=1, date=date(2026, 1, 1), is_working=True),
                WorkDay(user_id=1, date=date(2026, 1, 2), is_working=False),
                WorkDay(user_id=2, date=date(2026, 1, 3), is_working=True),
            ]
        )
        await session.commit()

    user = await get_user_by_id(10)
    missing = await get_user_by_id(99)
    friend = await get_friend_by_name("arbi")
    working_days = await get_friend_working_days(1, date(2026, 1, 1), date(2026, 1, 3))
    friends = await get_all_friends()

    async with session_factory() as session:
        saved_user = await session.scalar(select(Users).where(Users.user_id == 10))
        saved_request = await session.scalar(select(WeatherRequests))

    assert user is not None
    assert user.username == "updated"
    assert missing is None
    assert saved_user is not None
    assert saved_user.username == "updated"
    assert saved_request is not None
    assert saved_request.forecast_text == "forecast"
    assert saved_request.ai_response == "advice"
    assert friend is not None
    assert friend.name == "Arbi"
    assert working_days == [date(2026, 1, 1)]
    assert [item.name for item in friends] == ["Arbi", "Zelim"]
