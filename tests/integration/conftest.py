import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.data.models import Base


def pytest_configure(config: pytest.Config) -> None:
    """Register the explicit opt-in marker for database integration tests."""
    config.addinivalue_line(
        "markers",
        "integration: test against the configured PostgreSQL database",
    )


def _test_database_url() -> str:
    values = dotenv_values(Path(__file__).parents[2] / ".env.test", interpolate=False)
    database_url = values.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("TEST_DATABASE_URL is missing from .env.test", pytrace=False)
    return database_url


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[object]:
    """Create an isolated schema and remove it even when the test fails."""
    schema = f"test_{uuid.uuid4().hex}"
    engine = create_async_engine(
        _test_database_url(),
        connect_args={"server_settings": {"search_path": schema}},
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
        verifier = create_async_engine(_test_database_url())
        try:
            async with verifier.connect() as connection:
                remaining = await connection.scalar(
                    text(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name = :schema"
                    ),
                    {"schema": schema},
                )
            assert remaining is None
        finally:
            await verifier.dispose()
