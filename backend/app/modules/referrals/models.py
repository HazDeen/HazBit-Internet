from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.database.base import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(CITEXT, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id"), nullable=False)
    code: Mapped[str] = mapped_column(CITEXT, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    usage_limit: Mapped[int | None] = mapped_column()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    referral_code_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.referral_codes.id"), nullable=False
    )
    referrer_user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id"), nullable=False)
    referred_user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    attributed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReferralReward(Base):
    __tablename__ = "referral_rewards"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    referral_id: Mapped[UUID] = mapped_column(ForeignKey("app.referrals.id"), nullable=False)
    beneficiary_user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id"), nullable=False)
    reward_side: Mapped[str] = mapped_column(String, nullable=False)
    reward_type: Mapped[str] = mapped_column(String, nullable=False)
    days: Mapped[int | None] = mapped_column(SmallInteger)
    amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(String(3))
    transaction_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.transactions.id"))
    subscription_period_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app.subscription_periods.id")
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SubscriptionPeriod(Base):
    __tablename__ = "subscription_periods"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.subscriptions.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[UUID | None] = mapped_column()
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    plan_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    price_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(String(3))


class TrialGrant(Base):
    __tablename__ = "trial_grants"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id"), nullable=False)
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.subscriptions.id"), nullable=False
    )
    duration_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    risk_score: Mapped[int | None] = mapped_column(SmallInteger)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
