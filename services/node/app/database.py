from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    """Base class for future EchoVault persistence models."""


def _database_options() -> tuple[str, dict[str, object]]:
    if not settings.database_url:
        return "", {}

    database_url = make_url(settings.database_url)
    # Neon examples commonly use `postgresql://`; force SQLAlchemy's
    # asynchronous dialect so it never attempts to import psycopg2.
    if database_url.drivername == "postgresql":
        database_url = database_url.set(drivername="postgresql+asyncpg")
    elif database_url.drivername != "postgresql+asyncpg":
        raise ValueError("DATABASE_URL must use postgresql+asyncpg://")
    query = dict(database_url.query)
    sslmode = query.pop("sslmode", None)
    # libpq-style channel_binding is not an asyncpg.connect keyword. Neon
    # remains protected by the explicit SSL connection argument below.
    query.pop("channel_binding", None)
    database_url = database_url.set(query=query)
    connect_args: dict[str, object] = {}
    if sslmode == "require":
        connect_args["ssl"] = True
    return database_url.render_as_string(hide_password=False), connect_args


def get_async_database_url() -> str:
    """Return the normalized URL used by both SQLAlchemy and Alembic."""
    return _database_options()[0]


_database_url, _connect_args = _database_options()
engine: AsyncEngine | None = (
    create_async_engine(
        _database_url, poolclass=NullPool, pool_pre_ping=True, connect_args=_connect_args
    )
    if _database_url
    else None
)
async_session_factory = (
    async_sessionmaker(engine, expire_on_commit=False) if engine is not None else None
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    if async_session_factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with async_session_factory() as session:
        yield session


async def check_database_connection() -> None:
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
