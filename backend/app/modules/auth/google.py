from __future__ import annotations

import asyncio
from dataclasses import dataclass

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

from app.core.config import GoogleAuthSettings


@dataclass(frozen=True, slots=True)
class VerifiedGoogleIdentity:
    subject: str
    email: str
    name: str | None


class GoogleTokenValidationError(ValueError):
    pass


class GoogleIdTokenValidator:
    def __init__(self, settings: GoogleAuthSettings) -> None:
        self._enabled = settings.enabled
        self._client_id = settings.client_id

    async def validate(self, credential: str) -> VerifiedGoogleIdentity:
        if not self._enabled or not self._client_id:
            raise GoogleTokenValidationError("Google authentication is not configured")
        try:
            claims = await asyncio.to_thread(
                id_token.verify_oauth2_token,
                credential,
                GoogleRequest(),
                self._client_id,
            )
        except (GoogleAuthError, ValueError) as exc:
            raise GoogleTokenValidationError("Invalid Google ID token") from exc
        subject = claims.get("sub")
        email = claims.get("email")
        if not isinstance(subject, str) or not subject:
            raise GoogleTokenValidationError("Google subject is missing")
        if not isinstance(email, str) or not email or claims.get("email_verified") is not True:
            raise GoogleTokenValidationError("Google email is not verified")
        name = claims.get("name")
        return VerifiedGoogleIdentity(
            subject=subject,
            email=email.strip().casefold(),
            name=name.strip()[:120] if isinstance(name, str) and name.strip() else None,
        )
