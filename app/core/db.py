"""
Async SQLAlchemy engine + session factory, and a declarative Base that every
model in app/models inherits from.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# Managed Postgres (Neon, Supabase, RDS, etc.) requires TLS. asyncpg takes
# this as a connect_args kwarg, not a URL query string — see
# DATABASE_SSL_REQUIRED in config.py and DEPLOYMENT.md for the exact value
# each provider expects (usually "require", sometimes a full SSL context).
_connect_args = {"ssl": "require"} if settings.database_ssl_required else {}

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
