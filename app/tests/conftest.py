"""
Provides the `db_session` fixture used by test_loader_integration.py (and
any future DB-backed test). Requires a real PostgreSQL reachable at
DATABASE_URL (or TEST_DATABASE_URL, if set separately to avoid touching a
dev database) — these fixtures do nothing useful without one, and pytest
will error clearly on connection failure rather than silently skip.

Each test runs inside a transaction that's rolled back at the end, so
tests never leave data behind or depend on run order. Tables are created
once per test session via Base.metadata.create_all() (not via Alembic) —
fast for testing, but means this does NOT validate the Alembic migration
itself. Run `alembic upgrade head` separately against a real database to
verify the migration file.

Not exercised in the build sandbox this project was assembled in — no
network/DB access there. Syntax-checked only.
"""
import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
import app.models  # noqa: F401 — registers all model classes on Base.metadata

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get("DATABASE_URL", "postgresql+asyncpg://cped:cped@localhost:5432/cped_test"),
)


@pytest_asyncio.fixture(scope="session")
async def _engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine) -> AsyncSession:
    connection = await _engine.connect()
    transaction = await connection.begin()
    # join_transaction_mode="create_savepoint": lets tests call
    # session.commit() normally (load_cases()/import code does this) while
    # still rolling back everything at the end of the test, via a SAVEPOINT
    # instead of the outer transaction itself.
    session_factory = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    session = session_factory()

    yield session

    await session.close()
    await transaction.rollback()
    await connection.close()
