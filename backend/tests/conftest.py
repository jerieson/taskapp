"""Test setup.

- Tests use a separate database: DATABASE_URL's database name + "_test". It is dropped,
  recreated and migrated with Alembic (so the migrations themselves are exercised) once
  per test run. The dev database is never touched.
- Each test gets `db`, an AsyncSession inside a transaction that is rolled back at the
  end of the test. Code under test may commit: commits become savepoints.
- `client` is an HTTP client for the app whose requests use that same session.
  `new_client()` makes more of them (e.g. a second browser for session tests).
- `settings_override(**changes)` changes app settings for one test.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.db.engine import get_engine, get_sessionmaker
from app.db.session import get_session
from app.main import create_app


def settings_with(**changes: Any) -> Settings:
    """Current settings with some values changed (validated, so str -> SecretStr)."""
    return Settings.model_validate({**get_settings().model_dump(), **changes})


ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _test_database_url() -> URL:
    url = make_url(get_settings().database_url)
    assert url.database, "DATABASE_URL must name a database"
    if url.database.endswith("_test"):
        return url
    return url.set(database=f"{url.database}_test")


TEST_DATABASE_URL = _test_database_url()

# Point everything that reads settings (including the app's own engine) at the test DB.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL.render_as_string(hide_password=False)
get_settings.cache_clear()
get_engine.cache_clear()
get_sessionmaker.cache_clear()


def alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = TEST_DATABASE_URL.render_as_string(hide_password=False)
    config.attributes["configure_logging"] = False
    return config


async def _recreate_test_database() -> None:
    name = TEST_DATABASE_URL.database
    maintenance = create_async_engine(
        TEST_DATABASE_URL.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with maintenance.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await maintenance.dispose()


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> None:
    asyncio.run(_recreate_test_database())
    command.upgrade(alembic_config(), "head")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    # NullPool: each test runs in its own event loop, so connections must not be reused.
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            session = AsyncSession(
                bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
            try:
                yield session
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
async def client(app: FastAPI, db: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _session() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def new_client(app: FastAPI, client: AsyncClient) -> AsyncIterator[Callable[[], AsyncClient]]:
    """Factory for extra clients (separate cookie jars) sharing the test session."""
    extra: list[AsyncClient] = []

    def _new() -> AsyncClient:
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        extra.append(c)
        return c

    yield _new
    for c in extra:
        await c.aclose()


@pytest.fixture
def settings_override(app: FastAPI) -> Callable[..., Settings]:
    def _override(**changes: Any) -> Settings:
        settings = settings_with(**changes)
        app.dependency_overrides[get_settings] = lambda: settings
        return settings

    return _override
