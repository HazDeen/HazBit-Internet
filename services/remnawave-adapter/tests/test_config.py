from __future__ import annotations

import pytest
from pydantic import ValidationError

from remnawave_adapter.config import Settings


def test_production_rejects_placeholder_panel() -> None:
    with pytest.raises(ValidationError, match="placeholder must be replaced"):
        Settings(
            _env_file=None,
            environment="production",
            panel_base_url="https://remnawave.example.com",
            panel_token="p" * 32,
            internal_token="i" * 32,
        )
