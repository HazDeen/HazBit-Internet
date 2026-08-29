from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from app.core.config import TelegramSettings
from app.modules.auth.telegram import (
    TelegramInitDataValidator,
    TelegramValidationError,
    TelegramWidgetValidator,
)

BOT_TOKEN = "123456:telegram-test-token"


def _signed_init_data(fields: dict[str, str]) -> str:
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.digest(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256)
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def test_validates_signed_telegram_init_data() -> None:
    now = datetime(2026, 8, 22, 12, tzinfo=UTC)
    init_data = _signed_init_data(
        {
            "auth_date": str(int(now.timestamp())),
            "query_id": "AAExample",
            "user": json.dumps(
                {
                    "id": 424242,
                    "first_name": "Haz",
                    "username": "hazbit",
                    "language_code": "ru",
                },
                separators=(",", ":"),
            ),
        }
    )

    result = TelegramInitDataValidator(TelegramSettings(bot_token=BOT_TOKEN)).validate(
        init_data, now=now
    )

    assert result.user.id == 424242
    assert result.user.username == "hazbit"
    assert result.query_id == "AAExample"


@pytest.mark.parametrize("age", [timedelta(minutes=6), timedelta(seconds=-31)])
def test_rejects_stale_or_far_future_init_data(age: timedelta) -> None:
    now = datetime(2026, 8, 22, 12, tzinfo=UTC)
    init_data = _signed_init_data(
        {
            "auth_date": str(int((now - age).timestamp())),
            "user": json.dumps({"id": 1, "first_name": "Test"}),
        }
    )

    with pytest.raises(TelegramValidationError, match="expired"):
        TelegramInitDataValidator(TelegramSettings(bot_token=BOT_TOKEN)).validate(
            init_data, now=now
        )


def test_rejects_tampering_and_duplicate_fields() -> None:
    now = datetime(2026, 8, 22, 12, tzinfo=UTC)
    valid = _signed_init_data(
        {
            "auth_date": str(int(now.timestamp())),
            "user": json.dumps({"id": 1, "first_name": "Test"}),
        }
    )
    validator = TelegramInitDataValidator(TelegramSettings(bot_token=BOT_TOKEN))

    with pytest.raises(TelegramValidationError, match="signature"):
        validator.validate(valid.replace("Test", "Mallory"), now=now)
    with pytest.raises(TelegramValidationError, match="Duplicate"):
        validator.validate(f"{valid}&auth_date={int(now.timestamp())}", now=now)


def test_validates_login_widget_payload() -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    fields: dict[str, str | int | None] = {
        "id": 424242,
        "first_name": "Haz",
        "last_name": "Bit",
        "username": "hazbit",
        "photo_url": "https://t.me/i/userpic/example.jpg",
        "auth_date": int(now.timestamp()),
    }
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items()) if value is not None
    )
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    fields["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    result = TelegramWidgetValidator(TelegramSettings(bot_token=BOT_TOKEN)).validate(
        fields, now=now
    )

    assert result.user.id == 424242
    assert result.user.first_name == "Haz"
    assert result.user.last_name == "Bit"
