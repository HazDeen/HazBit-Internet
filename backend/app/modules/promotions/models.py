from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.database.base import Base


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(CITEXT, nullable=False)
    promo_type: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[int] = mapped_column(nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3))
    usage_limit: Mapped[int | None] = mapped_column()
    per_user_limit: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PromoCodePlanVersion(Base):
    __tablename__ = "promo_code_plan_versions"

    promo_code_id: Mapped[UUID] = mapped_column(ForeignKey("app.promo_codes.id"), primary_key=True)
    plan_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.plan_versions.id"), primary_key=True
    )


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    promo_code_id: Mapped[UUID] = mapped_column(ForeignKey("app.promo_codes.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id"), nullable=False)
    payment_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.payments.id"))
    subscription_period_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app.subscription_periods.id")
    )
    discount_amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    free_days: Mapped[int | None] = mapped_column(SmallInteger)
    redeemed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
