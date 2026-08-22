from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import DatabaseSettings, Settings
from app.core.errors import ApplicationError
from app.database.session import DatabaseManager
from app.modules.auth.crypto import AccessTokenCodec, OpaqueTokenCodec, OtpCodec, SignalHasher
from app.modules.auth.service import AuthService, ClientContext
from app.modules.auth.telegram import TelegramInitDataValidator
from sqlalchemy import text
from sqlalchemy.engine import make_url


class MemoryEmailSender:
    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    async def send_otp(self, *, email: str, code: str, expires_minutes: int) -> None:
        self.codes[email] = code


class NoopRateLimiter:
    async def enforce(self, *args: Any, **kwargs: Any) -> None:
        return None


def _test_database_url() -> str:
    database_url = os.getenv("HAZBIT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("HAZBIT_TEST_DATABASE_URL is not configured")
    return (
        make_url(database_url)
        .set(drivername="postgresql+asyncpg")
        .render_as_string(hide_password=False)
    )


def _upgrade_schema(database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAZBIT_DATABASE__URL", database_url)
    backend_root = Path(__file__).resolve().parents[2]
    command.upgrade(Config(str(backend_root / "alembic.ini")), "head")


def _service(
    *,
    session: Any,
    settings: Settings,
    sender: MemoryEmailSender,
) -> AuthService:
    auth = settings.auth
    return AuthService(
        session=session,
        settings=auth,
        otp_codec=OtpCodec(auth),
        opaque_token_codec=OpaqueTokenCodec(auth),
        access_token_codec=AccessTokenCodec(auth),
        signal_hasher=SignalHasher(auth),
        telegram_validator=TelegramInitDataValidator(auth.telegram),
        rate_limiter=NoopRateLimiter(),  # type: ignore[arg-type]
        email_sender=sender,
    )


@pytest.mark.integration
async def test_email_otp_refresh_rotation_and_reuse_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    _upgrade_schema(database_url, monkeypatch)
    settings = Settings(
        _env_file=None,
        environment="test",
        database=DatabaseSettings(url=database_url, pool_size=1, max_overflow=0),
    )
    database = DatabaseManager(settings.database)
    sender = MemoryEmailSender()
    email = f"auth-{uuid4()}@example.com"
    client = ClientContext("203.0.113.10", "pytest", "device-1")

    try:
        async with database.session() as session:
            await _service(session=session, settings=settings, sender=sender).start_email_auth(
                email=email,
                client=client,
            )

        async with database.session() as session:
            with pytest.raises(ApplicationError) as exc_info:
                await _service(session=session, settings=settings, sender=sender).verify_email(
                    email=email,
                    code="999999" if sender.codes[email] != "999999" else "888888",
                    client=client,
                )
            assert exc_info.value.code == "invalid_otp"

        async with database.session() as session:
            attempts = await session.scalar(
                text("SELECT attempts FROM app.otp_challenges WHERE email = :email"),
                {"email": email},
            )
            assert attempts == 1

        async with database.session() as session:
            authenticated = await _service(
                session=session, settings=settings, sender=sender
            ).verify_email(email=email, code=sender.codes[email], client=client)
        assert authenticated.user.email == email
        assert authenticated.user.roles == ["user"]

        async with database.session() as session:
            principal = await _service(
                session=session, settings=settings, sender=sender
            ).authenticate_access_token(authenticated.access_token)
        assert principal.user_id == authenticated.user.id

        async with database.session() as session:
            rotated = await _service(session=session, settings=settings, sender=sender).refresh(
                refresh_token=authenticated.refresh_token,
                client=client,
            )
        assert rotated.refresh_token != authenticated.refresh_token

        async with database.session() as session:
            with pytest.raises(ApplicationError) as exc_info:
                await _service(session=session, settings=settings, sender=sender).refresh(
                    refresh_token=authenticated.refresh_token,
                    client=client,
                )
            assert exc_info.value.code == "refresh_token_reuse"

        async with database.session() as session:
            with pytest.raises(ApplicationError) as exc_info:
                await _service(
                    session=session, settings=settings, sender=sender
                ).authenticate_access_token(rotated.access_token)
            assert exc_info.value.code == "invalid_access_token"

        async with database.session() as session:
            actions = set(
                await session.scalars(
                    text(
                        "SELECT action FROM app.audit_logs "
                        "WHERE actor_user_id = :user_id ORDER BY created_at"
                    ),
                    {"user_id": authenticated.user.id},
                )
            )
            assert {
                "auth.email_otp.succeeded",
                "auth.refresh.rotated",
                "auth.refresh.reuse_detected",
            }.issubset(actions)
    finally:
        await database.dispose()
