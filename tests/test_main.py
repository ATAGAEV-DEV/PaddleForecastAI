from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from main import main


async def test_main_initializes_database_and_starts_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wire the router and initialize storage before Telegram polling."""
    bot = AsyncMock()
    dispatcher = MagicMock()
    dispatcher.start_polling = AsyncMock()
    monkeypatch.setattr("main.Bot", lambda token: bot)
    monkeypatch.setattr("main.Dispatcher", lambda: dispatcher)
    monkeypatch.setattr("main.init_models", AsyncMock())
    monkeypatch.setenv("TG_TOKEN", "test-token")

    with patch("main.load_dotenv"):
        await main()

    dispatcher.include_router.assert_called_once()
    dispatcher.start_polling.assert_awaited_once_with(bot)
