from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from app.core.config import DatabaseSettings
from app.database.session import DatabaseManager
from sqlalchemy import text
from sqlalchemy.engine import make_url


def _test_database_url() -> str:
    database_url = os.getenv("HAZBIT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("HAZBIT_TEST_DATABASE_URL is not configured")
    return database_url


@pytest.mark.integration
def test_upgrade_head_creates_complete_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    async_url = make_url(_test_database_url()).set(drivername="postgresql+asyncpg")
    monkeypatch.setenv("HAZBIT_DATABASE__URL", async_url.render_as_string(hide_password=False))

    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    command.upgrade(config, "head")

    psycopg_url = async_url.set(drivername="postgresql")
    with psycopg.connect(psycopg_url.render_as_string(hide_password=False)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM information_schema.tables
                WHERE table_schema = 'app' AND table_type = 'BASE TABLE'
                """
            )
            assert cursor.fetchone() == (39,)

            cursor.execute("SELECT version_num FROM public.alembic_version")
            assert cursor.fetchone() == ("20260822_0004",)


@pytest.mark.integration
async def test_async_database_manager_connects() -> None:
    async_url = make_url(_test_database_url()).set(drivername="postgresql+asyncpg")
    database = DatabaseManager(
        DatabaseSettings(
            url=async_url.render_as_string(hide_password=False),
            pool_size=1,
            max_overflow=0,
        )
    )

    try:
        await database.ping()
        async with database.session() as session:
            assert session.is_active
            result = await session.execute(text("SELECT current_schema()"))
            assert result.scalar_one() == "public"
    finally:
        await database.dispose()
