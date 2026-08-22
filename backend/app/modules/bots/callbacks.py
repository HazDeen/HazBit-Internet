from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

from app.core.errors import ApplicationError


def _base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    encoded = ""
    while value:
        value, remainder = divmod(value, 36)
        encoded = alphabet[remainder] + encoded
    return encoded


@dataclass(frozen=True, slots=True)
class VerifiedCallback:
    action: str
    payload: str


class CallbackCodec:
    """Compact HMAC callbacks that stay inside Telegram's 64-byte limit."""

    def __init__(self, secret: str, *, default_ttl_seconds: int) -> None:
        self._secret = secret.encode()
        self._default_ttl_seconds = default_ttl_seconds

    def encode(
        self,
        action: str,
        payload: str = "",
        *,
        now: int | None = None,
        ttl_seconds: int | None = None,
    ) -> str:
        issued_at = int(time.time()) if now is None else now
        expires = _base36(issued_at + (ttl_seconds or self._default_ttl_seconds))
        unsigned = f"{action}.{payload}.{expires}"
        signature = (
            base64.urlsafe_b64encode(
                hmac.new(self._secret, unsigned.encode(), hashlib.sha256).digest()[:8]
            )
            .decode()
            .rstrip("=")
        )
        value = f"{unsigned}.{signature}"
        if len(value.encode()) > 64:
            raise ValueError("Telegram callback data exceeds 64 bytes")
        return value

    def decode(self, value: str, *, now: int | None = None) -> VerifiedCallback:
        try:
            action, payload, expires_raw, signature = value.split(".", 3)
            expires_at = int(expires_raw, 36)
        except (ValueError, TypeError) as exc:
            raise self._invalid() from exc
        unsigned = f"{action}.{payload}.{expires_raw}"
        expected = (
            base64.urlsafe_b64encode(
                hmac.new(self._secret, unsigned.encode(), hashlib.sha256).digest()[:8]
            )
            .decode()
            .rstrip("=")
        )
        if not hmac.compare_digest(signature, expected):
            raise self._invalid()
        current = int(time.time()) if now is None else now
        if expires_at < current:
            raise ApplicationError(
                "telegram_callback_expired",
                "This Telegram action has expired. Refresh the message and try again.",
                409,
            )
        return VerifiedCallback(action=action, payload=payload)

    @staticmethod
    def _invalid() -> ApplicationError:
        return ApplicationError(
            "telegram_callback_invalid", "Telegram callback signature is invalid.", 403
        )
