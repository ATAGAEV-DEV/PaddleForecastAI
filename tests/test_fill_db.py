from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

import fill_db


async def test_fill_db_commits_generated_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate both schedules and commit them through the configured session."""
    session = MagicMock()
    session.merge = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    context = MagicMock()
    context.__aenter__.return_value = session
    context.__aexit__.return_value = None
    monkeypatch.setattr(fill_db, "init_models", AsyncMock())
    monkeypatch.setattr(fill_db, "async_session", lambda: context)

    await fill_db.main()

    session.commit.assert_awaited_once()
    assert session.add.call_count > 0


async def test_fill_db_rolls_back_after_commit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Roll back when persisting the generated schedule fails."""
    session = MagicMock()
    session.merge = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock(side_effect=RuntimeError("duplicate"))
    session.rollback = AsyncMock()
    context = MagicMock()
    context.__aenter__.return_value = session
    context.__aexit__.return_value = None
    monkeypatch.setattr(fill_db, "init_models", AsyncMock())
    monkeypatch.setattr(fill_db, "async_session", lambda: context)

    await fill_db.main()

    session.rollback.assert_awaited_once()
    assert date(2026, 1, 1)
