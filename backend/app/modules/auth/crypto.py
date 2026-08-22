from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import AuthSettings
from app.core.ids import uuid7
from app.modules.auth.enums import Role


class OtpCodec:
    def __init__(self, settings: AuthSettings) -> None:
        self._secret = settings.otp.secret.get_secret_value().encode()
        self._length = settings.otp.code_length

    def generate(self) -> str:
        upper_bound = 10**self._length
        return f"{secrets.randbelow(upper_bound):0{self._length}d}"

    def digest(self, challenge_id: UUID, code: str) -> bytes:
        message = challenge_id.bytes + b":" + code.encode("ascii")
        return hmac.digest(self._secret, message, "sha256")

    def verify(self, challenge_id: UUID, code: str, expected: bytes) -> bool:
        return hmac.compare_digest(self.digest(challenge_id, code), expected)


class OpaqueTokenCodec:
    def __init__(self, settings: AuthSettings) -> None:
        self._secret = settings.refresh_token_secret.get_secret_value().encode()

    @staticmethod
    def generate() -> str:
        return secrets.token_urlsafe(48)

    @staticmethod
    def generate_csrf() -> str:
        return secrets.token_urlsafe(32)

    def digest(self, token: str) -> bytes:
        return hmac.digest(self._secret, token.encode(), "sha256")


class SignalHasher:
    def __init__(self, settings: AuthSettings) -> None:
        self._secret = settings.fingerprint_secret.get_secret_value().encode()

    def digest(self, namespace: str, value: str) -> bytes:
        normalized = value.strip().casefold()
        return hmac.digest(self._secret, f"{namespace}:{normalized}".encode(), "sha256")


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID
    roles: frozenset[Role]
    token_id: UUID


class AccessTokenCodec:
    algorithm = "HS256"

    def __init__(self, settings: AuthSettings) -> None:
        self._settings = settings.jwt
        self._secret = settings.jwt.secret.get_secret_value()

    @property
    def expires_in_seconds(self) -> int:
        return self._settings.access_ttl_minutes * 60

    def encode(self, *, user_id: UUID, session_id: UUID, roles: set[Role]) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "iss": self._settings.issuer,
            "aud": self._settings.audience,
            "sub": str(user_id),
            "sid": str(session_id),
            "jti": str(uuid7()),
            "roles": sorted(role.value for role in roles),
            "token_type": "access",
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=self._settings.access_ttl_minutes),
        }
        return jwt.encode(payload, self._secret, algorithm=self.algorithm)

    def decode(self, token: str) -> AccessClaims:
        payload = jwt.decode(
            token,
            self._secret,
            algorithms=[self.algorithm],
            audience=self._settings.audience,
            issuer=self._settings.issuer,
            leeway=self._settings.clock_skew_seconds,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "sid", "jti"]},
        )
        if payload.get("token_type") != "access":
            raise jwt.InvalidTokenError("unexpected token type")
        try:
            roles = frozenset(Role(value) for value in payload.get("roles", []))
            return AccessClaims(
                user_id=UUID(payload["sub"]),
                session_id=UUID(payload["sid"]),
                roles=roles,
                token_id=UUID(payload["jti"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise jwt.InvalidTokenError("invalid access token claims") from exc


class PasswordCodec:
    """Argon2id helper for future password credentials and admin bootstrap."""

    def __init__(self) -> None:
        self._hasher = Argon2PasswordHasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, encoded: str, password: str) -> bool:
        try:
            return self._hasher.verify(encoded, password)
        except (VerifyMismatchError, InvalidHashError):
            return False
