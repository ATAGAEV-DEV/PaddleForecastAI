import os
from datetime import UTC, datetime

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
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SCHEMA = "public"


def get_engine(schema: str) -> AsyncEngine:
    """Создаёт и возвращает асинхронный движок SQLAlchemy с указанным схемой.

    Устанавливает параметр search_path в соединении, чтобы все запросы выполнялись
    в заданной схеме PostgreSQL.

    Args:
        schema (str): Название схемы в базе данных.

    Returns:
        AsyncEngine: Асинхронный движок SQLAlchemy.

    """
    return create_async_engine(
        DATABASE_URL,
        connect_args={"server_settings": {"search_path": schema}},
        pool_pre_ping=True,
        pool_recycle=1800,
    )


if SCHEMA is None or SCHEMA == "":
    engine = get_engine("public")
else:
    engine = get_engine(SCHEMA)
async_session = async_sessionmaker(engine)


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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
