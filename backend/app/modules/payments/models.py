from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.database.base import Base


class PlanPrice(Base):
    __tablename__ = "plan_prices"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    plan_version_id: Mapped[UUID] = mapped_column(ForeignKey("app.plan_versions.id"))
    term_months: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    duration_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StorageObject(Base):
    __tablename__ = "storage_objects"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.users.id"))
    bucket: Mapped[str] = mapped_column(String(120), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[bytes] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id"), nullable=False)
    plan_price_id: Mapped[UUID] = mapped_column(ForeignKey("app.plan_prices.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    expected_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    expected_recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    operation_number_normalized: Mapped[str | None] = mapped_column(String(255))
    observed_recipient_normalized: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PaymentEvidence(Base):
    __tablename__ = "payment_evidence"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    payment_id: Mapped[UUID] = mapped_column(ForeignKey("app.payments.id"), nullable=False)
    storage_object_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.storage_objects.id"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PaymentAnalysis(Base):
    __tablename__ = "payment_analyses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    payment_id: Mapped[UUID] = mapped_column(ForeignKey("app.payments.id"), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(ForeignKey("app.payment_evidence.id"), nullable=False)
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(String(3))
    operation_date: Mapped[date | None] = mapped_column(Date)
    operation_number: Mapped[str | None] = mapped_column(String(255))
    bank_name: Mapped[str | None] = mapped_column(String(255))
    recipient: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rule_results: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaymentReview(Base):
    __tablename__ = "payment_reviews"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    payment_id: Mapped[UUID] = mapped_column(ForeignKey("app.payments.id"), nullable=False)
    reviewer_user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payment_version: Mapped[int] = mapped_column(nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    account_key: Mapped[str] = mapped_column(String(160), nullable=False)
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.users.id"))
    account_type: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.users.id"))
    payment_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.payments.id"))
    transaction_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TransactionEntry(Base):
    __tablename__ = "transaction_entries"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    transaction_id: Mapped[UUID] = mapped_column(ForeignKey("app.transactions.id"), nullable=False)
    ledger_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.ledger_accounts.id"), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    aggregate_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
