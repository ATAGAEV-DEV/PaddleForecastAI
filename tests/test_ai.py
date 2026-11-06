from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openai import APIConnectionError, APIError, BadRequestError

from app.core import weather_advisor


async def test_ai_generate_cleans_successful_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return model text after Markdown cleanup."""
    completion = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="**Совет**"))])
    monkeypatch.setattr(weather_advisor.client.chat.completions, "create", AsyncMock(return_value=completion))

    assert await weather_advisor.ai_generate("forecast") == "Совет"


@pytest.mark.parametrize(
    "error",
    [BadRequestError.__new__(BadRequestError), APIError.__new__(APIError), RuntimeError("unexpected")],
)
async def test_ai_generate_handles_api_errors(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    """Return no advice when the provider rejects or fails the request."""
    monkeypatch.setattr(weather_advisor.client.chat.completions, "create", AsyncMock(side_effect=error))

    assert await weather_advisor.ai_generate("forecast") is None


async def test_ai_generate_handles_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Handle a provider connection failure separately from response errors."""
    monkeypatch.setattr(
        weather_advisor.client.chat.completions,
        "create",
        AsyncMock(side_effect=APIConnectionError.__new__(APIConnectionError)),
    )

    assert await weather_advisor.ai_generate("forecast") is None


def test_prompt_contains_forecast() -> None:
    """Include the supplied forecast in the user message."""
    import asyncio

    messages = asyncio.run(weather_advisor.generate_prompt("forecast text"))
    assert messages[1]["content"] == "forecast text"
