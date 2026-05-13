import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship

load_dotenv()

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
DATABASE_URL_LOCAL: str = os.getenv("DATABASE_URL_LOCAL", "")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL не задан в переменных окружения. "
        "Установите переменную для подключения к удаленному PostgreSQL."
    )

if not DATABASE_URL_LOCAL:
    raise RuntimeError(
        "DATABASE_URL_LOCAL не задан в переменных окружения. "
        "Установите переменную для подключения к локальному PostgreSQL."
    )

SCHEMA = "pictures"


def get_engine(schema: str, db_url: str) -> AsyncEngine:
    """Создаёт и возвращает асинхронный движок SQLAlchemy с указанным схемой.

    Устанавливает параметр search_path в соединении, чтобы все запросы выполнялись
    в заданной схеме PostgreSQL.
    """
    return create_async_engine(
        db_url,
        connect_args={"server_settings": {"search_path": schema}},
        pool_pre_ping=True,
        pool_recycle=1800,
    )


if SCHEMA is None or SCHEMA == "":
    engine_remote = get_engine("public", DATABASE_URL)
    engine_local = get_engine("public", DATABASE_URL_LOCAL)
else:
    engine_remote = get_engine(SCHEMA, DATABASE_URL)
    engine_local = get_engine(SCHEMA, DATABASE_URL_LOCAL)

async_session_local_maker = async_sessionmaker(engine_local)
async_session_remote_maker = async_sessionmaker(engine_remote)


class DualSessionProxy:
    """Прокси-класс для выполнения операций в двух базах данных.

    Чтение выполняется только из локальной БД.
    Запись (INSERT, UPDATE, DELETE) дублируется в обе БД.
    """

    def __init__(self, local_session: AsyncSession, remote_session: AsyncSession) -> None:
        """Инициализирует прокси-сессию."""
        self.local = local_session
        self.remote = remote_session

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        """Выполняет запрос. DML-запросы дублируются в удаленную БД."""
        if getattr(statement, "is_dml", False):
            try:
                await self.remote.execute(statement, *args, **kwargs)
            except Exception as e:
                print(f"Ошибка выполнения запроса в удаленной БД: {e}")
        return await self.local.execute(statement, *args, **kwargs)

    def add(self, instance: Any) -> None:
        """Добавляет объект в обе сессии."""
        self.local.add(instance)
        state = instance.__dict__.copy()
        state.pop("_sa_instance_state", None)
        remote_instance = instance.__class__(**state)
        self.remote.add(remote_instance)

    async def commit(self) -> None:
        """Фиксирует транзакцию в обеих БД."""
        await self.local.commit()
        try:
            await self.remote.commit()
        except Exception as e:
            print(f"Ошибка коммита в удаленной БД: {e}")
            await self.remote.rollback()

    async def delete(self, instance: Any) -> None:
        """Удаляет объект из обеих БД.

        Для удалённой БД находит запись по первичному ключу и удаляет её отдельно,
        поскольку ORM-объект привязан к локальной сессии.
        """
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(instance.__class__)
        pk_cols = [col.key for col in mapper.primary_key]
        pk_values = {col: getattr(instance, col) for col in pk_cols}

        await self.local.delete(instance)

        try:
            from sqlalchemy import select as sa_select

            stmt = sa_select(instance.__class__)
            for col, val in pk_values.items():
                stmt = stmt.where(getattr(instance.__class__, col) == val)
            remote_result = await self.remote.execute(stmt)
            remote_instance = remote_result.scalar_one_or_none()
            if remote_instance is not None:
                await self.remote.delete(remote_instance)
        except Exception as e:
            print(f"Ошибка удаления из удалённой БД: {e}")

    async def rollback(self) -> None:
        """Откатывает транзакцию в обеих БД."""
        await self.local.rollback()
        await self.remote.rollback()


@asynccontextmanager
async def async_session() -> AsyncGenerator[DualSessionProxy]:
    """Контекстный менеджер для работы с прокси-сессией DualSessionProxy."""
    async with (
        async_session_local_maker() as local_session,
        async_session_remote_maker() as remote_session,
    ):
        yield DualSessionProxy(local_session, remote_session)


class Base(AsyncAttrs, DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy с поддержкой асинхронности.

    Наследуется от AsyncAttrs и DeclarativeBase, обеспечивая совместимость
    с асинхронным режимом работы SQLAlchemy.
    """

    pass


class Users(Base):
    """Модель пользователя в базе данных.

    Представляет таблицу 'users', хранящую идентификаторы Telegram-пользователей
    и их имена пользователей.
    """

    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, autoincrement=False)
    username = Column(String)


class WeatherRequests(Base):
    """Модель запросов к погоде в базе данных.

    Представляет таблицу 'weather_requests', хранящую историю запросов пользователей:
    прогноз погоды, ответ ИИ, временные метки и идентификатор пользователя.
    """

    __tablename__ = "weather_requests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    forecast_text = Column(Text)
    ai_response = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class Friends(Base):
    """Модель друзей для отслеживания их рабочих графиков."""

    __tablename__ = "friends"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)

    work_days = relationship("WorkDay", back_populates="user")


class WorkDay(Base):
    """Модель для хранения рабочих дней друзей."""

    __tablename__ = "work_days"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("friends.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)  # индекс для быстрого поиска по дате
    is_working = Column(Boolean, default=True)

    user = relationship("Friends", back_populates="work_days")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "date", name="uq_user_date"
        ),  # один день = одна запись на человека
    )


async def init_models() -> None:
    """Инициализирует модели базы данных.

    Создаёт таблицы в базе данных, если они ещё не существуют.
    Использует метаданные Base для синхронизации схемы.
    """
    async with engine_local.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with engine_remote.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        print(f"Ошибка создания таблиц в удаленной БД: {e}")
