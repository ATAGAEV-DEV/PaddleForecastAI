from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import handlers
from app.tools.utils import clean_text, hash_password


def message(text: str = "", user_id: int = 1, username: str | None = "tester") -> SimpleNamespace:
    """Build the Telegram message fields used by the handlers."""
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=user_id, username=username),
        answer=AsyncMock(),
    )


def forecast(day: str) -> str:
    """Build one forecast block in the parser's expected format."""
    return f"Дата время: {day} 12:00:00\nТемпература: 18"


async def test_start_welcomes_existing_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip registration when the Telegram user already exists."""
    monkeypatch.setattr(handlers, "get_user_by_id", AsyncMock(return_value=object()))
    incoming = message()
    state = AsyncMock()

    await handlers.start_handler(incoming, state)

    incoming.answer.assert_awaited_once_with("Добро пожаловать!")
    state.set_state.assert_not_awaited()


async def test_start_requests_password_for_new_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Move an unknown user into the password state."""
    monkeypatch.setattr(handlers, "get_user_by_id", AsyncMock(return_value=None))
    incoming = message()
    state = AsyncMock()

    await handlers.start_handler(incoming, state)

    state.set_state.assert_awaited_once_with(handlers.RegisterState.waiting_for_password)


async def test_password_accepts_valid_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Store a newly authorized user and clear registration state."""
    add_user = AsyncMock()
    monkeypatch.setattr(handlers, "add_user", add_user)
    incoming = message("secret", username=None)
    def hashed(value: str) -> str:
        return handlers.ACCESS_PASSWORD if value == "secret" else ""

    monkeypatch.setattr(handlers, "hash_password", hashed)
    state = AsyncMock()

    await handlers.password_handler(incoming, state)

    add_user.assert_awaited_once_with(1, "")
    state.clear.assert_awaited_once_with()


async def test_password_rejects_invalid_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the user in registration after a wrong password."""
    monkeypatch.setattr(handlers, "hash_password", lambda value: "wrong")
    incoming = message("bad")
    state = AsyncMock()

    await handlers.password_handler(incoming, state)

    incoming.answer.assert_awaited_once_with("Неверный пароль. Попробуйте еще раз:")
    state.clear.assert_not_awaited()


async def test_get_returns_unfiltered_forecast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate advice directly when no friend filter is requested."""
    monkeypatch.setattr(handlers, "get_forecast", AsyncMock(return_value="raw forecast"))
    monkeypatch.setattr(handlers, "ai_generate", AsyncMock(return_value="advice"))
    save_request = AsyncMock()
    monkeypatch.setattr(handlers, "save_weather_request", save_request)
    incoming = message()

    await handlers.get_generate(incoming, SimpleNamespace(args=None))

    save_request.assert_awaited_once()
    incoming.answer.assert_awaited_once_with("advice")


async def test_get_filters_friend_working_days(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove only the selected friend's working dates from the forecast."""
    lines = [forecast("2026-01-01"), forecast("2026-01-02")]
    monkeypatch.setattr(handlers, "get_forecast", AsyncMock(return_value=lines))
    friend = SimpleNamespace(id=7)
    working_days = AsyncMock(side_effect=[[], [date(2026, 1, 1)]])
    monkeypatch.setattr(handlers, "get_friend_by_name", AsyncMock(return_value=friend))
    monkeypatch.setattr(handlers, "get_friend_working_days", working_days)
    generate = AsyncMock(return_value="advice")
    monkeypatch.setattr(handlers, "ai_generate", generate)
    monkeypatch.setattr(handlers, "save_weather_request", AsyncMock())
    incoming = message()

    await handlers.get_generate(incoming, SimpleNamespace(args=" Arbi "))
    await handlers.get_generate(incoming, SimpleNamespace(args=" Arbi "))

    generated = generate.await_args_list[1]
    assert generated is not None
    assert forecast("2026-01-02") in generated.args[0]
    assert forecast("2026-01-01") not in generated.args[0]


async def test_get_reports_missing_friend_and_fully_busy_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stop before AI generation for unknown friends and fully occupied dates."""
    forecast_result = AsyncMock(return_value=[forecast("2026-01-01")])
    friends = AsyncMock(side_effect=[None, SimpleNamespace(id=7)])
    working_days = AsyncMock(return_value=[date(2026, 1, 1)])
    monkeypatch.setattr(handlers, "get_forecast", forecast_result)
    monkeypatch.setattr(handlers, "get_friend_by_name", friends)
    monkeypatch.setattr(handlers, "get_friend_working_days", working_days)
    generate = AsyncMock()
    monkeypatch.setattr(handlers, "ai_generate", generate)
    incoming = message()

    await handlers.get_generate(incoming, SimpleNamespace(args="Missing"))
    await handlers.get_generate(incoming, SimpleNamespace(args="Busy"))

    assert incoming.answer.await_count == 2
    generate.assert_not_awaited()


async def test_meet_validates_period_and_reports_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover invalid periods, empty data, no overlap, and every declension branch."""
    incoming = message()
    for args in ("0", "31", "bad"):
        await handlers.meet_command(incoming, SimpleNamespace(args=args))
    assert incoming.answer.await_count == 3

    monkeypatch.setattr(handlers, "get_all_friends", AsyncMock(return_value=[]))
    await handlers.meet_command(incoming, SimpleNamespace(args=None))

    frozen_today = date(2026, 1, 1)
    clock = SimpleNamespace(date=lambda: frozen_today)
    fake_datetime = SimpleNamespace(now=lambda: clock, strptime=handlers.datetime.strptime)
    monkeypatch.setattr(handlers, "datetime", fake_datetime)
    monkeypatch.setattr(handlers, "get_all_friends", AsyncMock(return_value=[SimpleNamespace(id=1)]))
    monkeypatch.setattr(handlers, "get_friend_working_days", AsyncMock(return_value=[frozen_today]))
    await handlers.meet_command(incoming, SimpleNamespace(args="1"))
    await handlers.meet_command(incoming, SimpleNamespace(args="2"))
    monkeypatch.setattr(handlers, "get_friend_working_days", AsyncMock(return_value=[]))
    await handlers.meet_command(incoming, SimpleNamespace(args="11"))
    await handlers.meet_command(incoming, SimpleNamespace(args="22"))

    answers = [call.args[0] for call in incoming.answer.await_args_list]
    assert any("нет ни одного друга" in answer for answer in answers)
    assert any("общих выходных нет" in answer for answer in answers)
    assert any("1 день" in answer for answer in answers)


def test_modules_support_direct_execution() -> None:
    """Exercise both command-line entry points without starting their services."""
    import runpy
    from pathlib import Path
    from unittest.mock import patch

    with patch("asyncio.run", return_value=None) as run_main:
        runpy.run_path(str(Path(__file__).parents[1] / "main.py"), run_name="__main__")
        run_main.call_args.args[0].close()
    with patch("asyncio.run", return_value=None) as run_fill:
        runpy.run_path(str(Path(__file__).parents[1] / "fill_db.py"), run_name="__main__")
        run_fill.call_args.args[0].close()

    run_main.assert_called_once()
    run_fill.assert_called_once()


def test_helpers_hash_and_clean_text() -> None:
    """Hash passwords deterministically and strip supported Markdown markers."""
    assert hash_password("secret") == hash_password("secret")
    assert clean_text("### **bold** *text*") == " bold text"
