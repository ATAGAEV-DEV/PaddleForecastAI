from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.data import request


def session_with(result: object) -> MagicMock:
    """Build an async session context returning the supplied query result."""
    session = AsyncMock()
    session.execute.return_value = result
    context = MagicMock()
    context.__aenter__.return_value = session
    context.__aexit__.return_value = None
    return context


async def test_request_helpers_handle_timeouts_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return safe fallbacks when database operations time out or fail."""
    context = MagicMock()
    context.__aenter__.side_effect = TimeoutError
    monkeypatch.setattr(request, "async_session", lambda: context)
    assert await request.get_user_by_id(1) is None

    context.__aenter__.side_effect = RuntimeError("db down")
    assert await request.get_user_by_id(1) is None
    await request.add_user(1, "name")
    await request.save_weather_request(1, "forecast", "advice")
    assert await request.get_friend_by_name("Arbi") is None
    assert await request.get_friend_working_days(1, date(2026, 1, 1), date(2026, 1, 2)) == []
    assert await request.get_all_friends() == []


async def test_add_user_timeout_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Handle a timeout raised by the upsert itself."""
    session = AsyncMock()
    session.execute.side_effect = TimeoutError
    context = session_with(None)
    context.__aenter__.return_value = session
    monkeypatch.setattr(request, "async_session", lambda: context)

    await request.add_user(1, "name")
