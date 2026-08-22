from __future__ import annotations

import pytest
from app.core.config import DatabaseSettings, Settings


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        debug=False,
        docs_enabled=False,
        log_format="json",
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@127.0.0.1:9/hazbit_test",
            pool_size=1,
            max_overflow=0,
            pool_timeout_seconds=0.1,
            command_timeout_seconds=0.1,
        ),
    )
