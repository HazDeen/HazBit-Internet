from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import TelegramSettings


class TelegramUserData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(gt=0)
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    language_code: str | None = Field(default=None, max_length=16)


@dataclass(frozen=True, slots=True)
class ValidatedTelegramData:
    user: TelegramUserData
    auth_date: datetime
    query_id: str | None
    start_param: str | None


class TelegramValidationError(ValueError):
    pass


class TelegramInitDataValidator:
    def __init__(self, settings: TelegramSettings) -> None:
        self._bot_token = settings.bot_token.get_secret_value()
        self._max_age_seconds = settings.init_data_max_age_seconds

    def validate(
        self,
        init_data: str,
        *,
        now: datetime | None = None,
    ) -> ValidatedTelegramData:
        if not self._bot_token:
            raise TelegramValidationError("Telegram authentication is not configured")

        try:
            pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        except ValueError as exc:
            raise TelegramValidationError("Malformed Telegram initData") from exc

        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            raise TelegramValidationError("Duplicate Telegram initData fields")
        fields = dict(pairs)

        received_hash = fields.pop("hash", None)
        if received_hash is None or len(received_hash) != 64:
            raise TelegramValidationError("Missing Telegram initData hash")

        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret_key = hmac.digest(b"WebAppData", self._bot_token.encode(), hashlib.sha256)
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(calculated_hash, received_hash.lower()):
            raise TelegramValidationError("Invalid Telegram initData signature")

        current_time = now or datetime.now(UTC)
        try:
            auth_date = datetime.fromtimestamp(int(fields["auth_date"]), tz=UTC)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise TelegramValidationError("Invalid Telegram auth_date") from exc
        age_seconds = (current_time - auth_date).total_seconds()
        if age_seconds < -30 or age_seconds > self._max_age_seconds:
            raise TelegramValidationError("Telegram initData is expired")

        try:
            raw_user = json.loads(fields["user"])
            user = TelegramUserData.model_validate(raw_user)
        except (KeyError, json.JSONDecodeError, ValidationError) as exc:
            raise TelegramValidationError("Invalid Telegram user data") from exc

        return ValidatedTelegramData(
            user=user,
            auth_date=auth_date,
            query_id=fields.get("query_id"),
            start_param=fields.get("start_param"),
        )
