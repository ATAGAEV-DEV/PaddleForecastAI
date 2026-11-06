import importlib.util
import os
import re
import sys
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from dotenv import dotenv_values
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = "postgresql+asyncpg://test_user:test_password@localhost/test_database"
ModuleLoader = Callable[[str, dict[str, str]], ModuleType]


@pytest_asyncio.fixture
async def load_module(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[ModuleLoader]:
    """Load configuration without reading real environment files or opening connections."""
    modules = []

    def load(relative_path: str, environment: dict[str, str]) -> ModuleType:
        name = f"_configuration_test_{len(modules)}"
        spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("dotenv.load_dotenv", return_value=False),
        ):
            spec.loader.exec_module(module)
        modules.append(module)
        return module

    yield load

    for module in modules:
        if hasattr(module, "engine"):
            await module.engine.dispose()
        if hasattr(module, "client"):
            await module.client.close()


@pytest.fixture
def handler_dependencies(monkeypatch: pytest.MonkeyPatch) -> dict[str, ModuleType]:
    """Isolate handler tests from database, AI, and weather service initialization."""
    functions = {
        "app.core.weather_advisor": ("ai_generate",),
        "app.data.request": (
            "add_user",
            "get_all_friends",
            "get_friend_by_name",
            "get_friend_working_days",
            "get_user_by_id",
            "save_weather_request",
        ),
        "app.services.weather": ("get_forecast",),
    }
    modules = {}
    for name, attributes in functions.items():
        module = ModuleType(name)
        for attribute in attributes:
            setattr(module, attribute, AsyncMock())
        monkeypatch.setitem(sys.modules, name, module)
        modules[name] = module
    return modules


@pytest.mark.parametrize("schema", [None, "", "public", "custom_schema"])
async def test_database_uses_one_engine_and_standard_session(
    load_module: ModuleLoader, schema: str | None
) -> None:
    """Use DATABASE_URL for sessions and table initialization with the chosen search path."""
    environment = {"DATABASE_URL": DATABASE_URL}
    if schema is not None:
        environment["DATABASE_SCHEMA"] = schema

    with patch(
        "sqlalchemy.ext.asyncio.create_async_engine", wraps=create_async_engine
    ) as create_engine:
        models = load_module("app/data/models.py", environment)

    create_engine.assert_called_once()
    assert create_engine.call_args.args == (DATABASE_URL,)
    assert create_engine.call_args.kwargs["connect_args"] == {
        "server_settings": {"search_path": schema or "public"}
    }
    assert str(models.engine.url) == DATABASE_URL.replace("test_password", "***")

    async with models.async_session() as session:
        assert isinstance(session, AsyncSession)
        assert session.bind is models.engine

    connection = SimpleNamespace(run_sync=AsyncMock())
    with patch.object(type(models.engine), "begin") as begin:
        begin.return_value.__aenter__.return_value = connection
        await models.init_models()

    begin.assert_called_once_with()
    connection.run_sync.assert_awaited_once_with(models.Base.metadata.create_all)


async def test_ai_uses_token_and_provider_from_environment(load_module: ModuleLoader) -> None:
    """Configure the SDK using generic AI settings instead of a hardcoded provider."""
    advisor = load_module(
        "app/core/weather_advisor.py",
        {"AI_TOKEN": "test-ai-token", "AI_PROVIDER_URL": "https://ai.example.test/v1"},
    )

    assert advisor.client.api_key == "test-ai-token"
    assert str(advisor.client.base_url) == "https://ai.example.test/v1/"
    assert advisor.client.timeout == 60.0


@pytest.mark.parametrize("key", ["AI_TOKEN", "AI_PROVIDER_URL"])
@pytest.mark.parametrize("value", [None, ""])
async def test_ai_requires_explicit_configuration(
    load_module: ModuleLoader, key: str, value: str | None
) -> None:
    """Reject missing AI settings instead of silently selecting the SDK's default provider."""
    environment = {"AI_TOKEN": "test-ai-token", "AI_PROVIDER_URL": "https://ai.example.test/v1"}
    if value is None:
        environment.pop(key)
    else:
        environment[key] = value

    with pytest.raises(RuntimeError, match=key):
        load_module("app/core/weather_advisor.py", environment)


@pytest.mark.parametrize("value", [None, ""])
async def test_database_requires_url(load_module: ModuleLoader, value: str | None) -> None:
    """Fail clearly when the single database URL is missing or empty."""
    environment = {} if value is None else {"DATABASE_URL": value}
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        load_module("app/data/models.py", environment)


def test_environment_example_matches_deployment_configuration() -> None:
    """Document and deploy the same runtime settings, including the default database schema."""
    example = dotenv_values(ROOT / ".env.example", interpolate=False)
    expected_keys = {
        "TG_TOKEN",
        "WEATHER_API",
        "WEATHER_CITY",
        "AI_TOKEN",
        "AI_PROVIDER_URL",
        "DATABASE_URL",
        "DATABASE_SCHEMA",
    }
    assert set(example) == expected_keys
    assert example["DATABASE_SCHEMA"] == "public"
    assert example["WEATHER_CITY"] == "Червлённая"
    assert all(example.values())

    workflow = (ROOT / ".github/workflows/docker-image.yml").read_text(encoding="utf-8-sig")
    assert set(re.findall(r"-e ([A-Z_]+)=", workflow)) == expected_keys
    assert set(re.findall(r"secrets\.([A-Z_]+)", workflow)) == expected_keys


@pytest.mark.parametrize(
    ("city_setting", "expected_city"),
    [
        ("Москва", "Москва"),
        ("Saint Petersburg", "Saint Petersburg"),
        ("missing", "Червлённая"),
        ("empty", "Червлённая"),
    ],
)
async def test_weather_command_uses_configured_city(
    load_module: ModuleLoader,
    handler_dependencies: dict[str, ModuleType],
    city_setting: str,
    expected_city: str,
) -> None:
    """Pass the configured city to weather requests and retain the original default."""
    environment = {}
    if city_setting != "missing":
        environment["WEATHER_CITY"] = "" if city_setting == "empty" else city_setting
    handlers = load_module("app/core/handlers.py", environment)
    forecast = handler_dependencies["app.services.weather"].get_forecast
    forecast.return_value = ["test forecast"]
    handler_dependencies["app.core.weather_advisor"].ai_generate.return_value = "test advice"
    message = SimpleNamespace(from_user=SimpleNamespace(id=123), answer=AsyncMock())

    await handlers.get_generate(message, SimpleNamespace(args=None))

    forecast.assert_awaited_once_with(expected_city, days=5)
    message.answer.assert_awaited_once_with("test advice")


@pytest.mark.usefixtures("handler_dependencies")
async def test_help_displays_configured_city(load_module: ModuleLoader) -> None:
    """Keep the help text consistent with the actual forecast location."""
    handlers = load_module("app/core/handlers.py", {"WEATHER_CITY": "Москва"})
    message = SimpleNamespace(answer=AsyncMock())

    await handlers.help_handler(message)

    assert "для города Москва на 5 дней" in message.answer.await_args.args[0]
