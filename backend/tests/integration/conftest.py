from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from sqlalchemy.engine import make_url


@pytest.fixture(autouse=True)
def isolate_integration_database() -> Iterator[None]:
    database_url = os.getenv("HAZBIT_TEST_DATABASE_URL")
    if database_url:
        sync_url = (
            make_url(database_url)
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )
        with psycopg.connect(sync_url, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS app CASCADE")
            connection.execute("DROP TABLE IF EXISTS public.alembic_version")
    yield
