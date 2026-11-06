import logging
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services import weather


def response(payload: dict, error: Exception | None = None) -> MagicMock:
    """Build the httpx response methods used by the weather client."""
    result = MagicMock()
    result.raise_for_status.side_effect = error
    result.json.return_value = payload
    result.status_code = 500
    result.text = "failure"
    return result


async def test_weather_request_handles_missing_key_and_errors(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Cover missing credentials, HTTP failures, and unexpected client failures."""
    monkeypatch.setattr(weather, "WEATHER_API", "")
    assert await weather.make_weather_request("forecast", {}) is None

    monkeypatch.setattr(weather, "WEATHER_API", "key")
    client = AsyncMock()
    client.get.side_effect = [
        response({"ok": True}),
        response({}, httpx.HTTPStatusError("bad", request=MagicMock(), response=response({}))),
    ]
    context = MagicMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(weather.httpx, "AsyncClient", lambda: context)
    with caplog.at_level(logging.ERROR):
        assert await weather.make_weather_request("forecast", {}) == {"ok": True}
        assert await weather.make_weather_request("forecast", {}) is None

    context.__aenter__.side_effect = RuntimeError("network")
    assert await weather.make_weather_request("forecast", {}) is None


async def test_forecast_formats_selected_hours_and_api_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clamp the day count and return only the supported afternoon slots."""
    payloads = [
        None,
        {"cod": "404", "message": "missing"},
        {
            "cod": "200",
            "list": [
                {
                    "dt_txt": "2026-01-01 12:00:00",
                    "main": {"temp": 18, "humidity": 40},
                    "wind": {"speed": 2},
                    "weather": [{"description": "ясно"}],
                },
                {
                    "dt_txt": "2026-01-01 00:00:00",
                    "main": {"temp": 1, "humidity": 1},
                    "wind": {"speed": 1},
                    "weather": [{"description": "ночь"}],
                },
            ],
        },
    ]
    monkeypatch.setattr(weather, "make_weather_request", AsyncMock(side_effect=payloads))

    assert "Не удалось" in await weather.get_forecast("City", days=0)
    assert "missing" in await weather.get_forecast("City", days=9)
    result = await weather.get_forecast("City")
    assert isinstance(result, list)
    assert len(result) == 1
    assert "ясно" in result[0]
