from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.database.base import Base


class PlanVersion(Base):
    __tablename__ = "plan_versions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("app.plans.id"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    device_limit: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    family_member_limit: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    traffic_limit_bytes: Mapped[int | None] = mapped_column(BigInteger)
    remnawave_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False
    )
    plan_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.plan_versions.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grace_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspension_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class VpnAccount(Base):
    __tablename__ = "vpn_accounts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False
    )
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.subscriptions.id", ondelete="RESTRICT"), nullable=False
    )
    remnawave_user_id: Mapped[int | None] = mapped_column(BigInteger)
    remnawave_user_uuid: Mapped[UUID | None] = mapped_column()
    username: Mapped[str] = mapped_column(CITEXT, nullable=False)
    desired_status: Mapped[str] = mapped_column(String, nullable=False)
    observed_status: Mapped[str | None] = mapped_column(String)
    desired_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_url_ciphertext: Mapped[bytes | None] = mapped_column()
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False
    )
    vpn_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.vpn_accounts.id", ondelete="CASCADE"), nullable=False
    )
    slot_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    label: Mapped[str | None] = mapped_column(String(120))
    external_hwid: Mapped[str | None] = mapped_column(String(255))
    fingerprint_hash: Mapped[bytes | None] = mapped_column()
    platform: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class VpnSyncCommand(Base):
    __tablename__ = "vpn_sync_commands"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    vpn_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.vpn_accounts.id", ondelete="CASCADE"), nullable=False
    )
    command_type: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False)
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
