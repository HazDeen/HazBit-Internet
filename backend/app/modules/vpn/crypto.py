from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import VpnSettings


class SubscriptionUrlCipher:
    def __init__(self, settings: VpnSettings) -> None:
        secret = settings.subscription_url_secret.get_secret_value().encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode())

    def decrypt(self, value: bytes) -> str:
        try:
            return self._fernet.decrypt(value).decode()
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise ValueError("subscription URL ciphertext is invalid") from exc
