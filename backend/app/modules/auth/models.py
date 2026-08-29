from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column

from app.core.ids import uuid7
from app.database.base import Base


def datetime_column(*, server_now: bool = False) -> MappedColumn[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now() if server_now else None,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    public_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="ru", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = datetime_column(server_now=True)
    updated_at: Mapped[datetime] = datetime_column(server_now=True)


class UserEmail(Base):
    __tablename__ = "user_emails"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = datetime_column(server_now=True)
    updated_at: Mapped[datetime] = datetime_column(server_now=True)


class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(CITEXT)
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(16))
    channel_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    linked_at: Mapped[datetime] = datetime_column(server_now=True)
    updated_at: Mapped[datetime] = datetime_column(server_now=True)


class PasswordCredential(Base):
    __tablename__ = "password_credentials"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = datetime_column(server_now=True)
    created_at: Mapped[datetime] = datetime_column(server_now=True)


class GoogleAccount(Base):
    __tablename__ = "google_accounts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    google_subject: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    created_at: Mapped[datetime] = datetime_column(server_now=True)
    updated_at: Mapped[datetime] = datetime_column(server_now=True)


class RegistrationChallenge(Base):
    __tablename__ = "registration_challenges"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    token_hash: Mapped[bytes] = mapped_column(nullable=False, unique=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    public_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    telegram_username: Mapped[str | None] = mapped_column(CITEXT)
    telegram_first_name: Mapped[str | None] = mapped_column(String(255))
    telegram_last_name: Mapped[str | None] = mapped_column(String(255))
    telegram_language_code: Mapped[str | None] = mapped_column(String(16))
    requested_ip: Mapped[str | None] = mapped_column(INET)
    device_fingerprint_hash: Mapped[bytes | None] = mapped_column()
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    telegram_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = datetime_column()
    created_at: Mapped[datetime] = datetime_column(server_now=True)


class TelegramLoginChallenge(Base):
    __tablename__ = "telegram_login_challenges"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    token_hash: Mapped[bytes] = mapped_column(nullable=False, unique=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requested_ip: Mapped[str | None] = mapped_column(INET)
    device_fingerprint_hash: Mapped[bytes | None] = mapped_column()
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = datetime_column()
    created_at: Mapped[datetime] = datetime_column(server_now=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String, primary_key=True)
    granted_by: Mapped[UUID | None] = mapped_column(ForeignKey("app.users.id", ondelete="SET NULL"))
    granted_at: Mapped[datetime] = datetime_column(server_now=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserPermission(Base):
    __tablename__ = "user_permissions"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(String(120), primary_key=True)
    granted_by: Mapped[UUID | None] = mapped_column(ForeignKey("app.users.id", ondelete="SET NULL"))
    granted_at: Mapped[datetime] = datetime_column(server_now=True)


class StaffInvitation(Base):
    __tablename__ = "staff_invitations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    token_hash: Mapped[bytes] = mapped_column(nullable=False, unique=True)
    roles: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    invited_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False
    )
    accepted_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app.users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = datetime_column()
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = datetime_column(server_now=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="CASCADE"), nullable=False
    )
    token_family_id: Mapped[UUID] = mapped_column(nullable=False)
    refresh_token_hash: Mapped[bytes] = mapped_column(nullable=False, unique=True)
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(INET)
    device_fingerprint_hash: Mapped[bytes | None] = mapped_column()
    created_at: Mapped[datetime] = datetime_column(server_now=True)
    last_used_at: Mapped[datetime] = datetime_column(server_now=True)
    expires_at: Mapped[datetime] = datetime_column()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(Text)
    replaced_by_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app.auth_sessions.id", ondelete="SET NULL")
    )


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    purpose: Mapped[str] = mapped_column(String, nullable=False)
    code_hash: Mapped[bytes] = mapped_column(nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, default=5, nullable=False)
    requested_ip: Mapped[str | None] = mapped_column(INET)
    device_fingerprint_hash: Mapped[bytes | None] = mapped_column()
    created_at: Mapped[datetime] = datetime_column(server_now=True)
    expires_at: Mapped[datetime] = datetime_column()
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RiskSignal(Base):
    __tablename__ = "risk_signals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.users.id", ondelete="SET NULL"))
    signal_type: Mapped[str] = mapped_column(String, nullable=False)
    signal_hash: Mapped[bytes] = mapped_column(nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = datetime_column(server_now=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app.users.id", ondelete="SET NULL")
    )
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column()
    reason: Mapped[str | None] = mapped_column(Text)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = datetime_column(server_now=True)
