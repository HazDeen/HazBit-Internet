from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.database.base import Base


class WalletTopUp(Base):
    __tablename__ = "wallet_top_ups"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    provider_transaction_id: Mapped[UUID | None] = mapped_column()
    payment_method: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    checkout_url: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SubscriptionBillingSetting(Base):
    __tablename__ = "subscription_billing_settings"

    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.subscriptions.id"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id"), nullable=False)
    plan_price_id: Mapped[UUID] = mapped_column(ForeignKey("app.plan_prices.id"), nullable=False)
    auto_renew_enabled: Mapped[bool] = mapped_column(nullable=False)
    next_renewal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
