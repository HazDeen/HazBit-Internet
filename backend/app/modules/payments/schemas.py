from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CreatePaymentIntentRequest(BaseModel):
    plan_price_id: UUID
    promo_code: str | None = Field(default=None, min_length=3, max_length=64)

    @field_validator("promo_code")
    @classmethod
    def normalize_promo_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None


class PaymentAnalysisSummary(BaseModel):
    provider: str
    model: str
    status: str
    confidence: float | None
    rule_results: dict[str, object]


class PaymentResponse(BaseModel):
    id: UUID
    plan_price_id: UUID
    status: str
    expected_amount_minor: int
    original_amount_minor: int
    discount_amount_minor: int = 0
    promo_code: str | None = None
    currency: str
    expected_recipient: str
    expires_at: datetime
    uploaded_at: datetime | None
    approved_at: datetime | None
    rejected_at: datetime | None
    rejection_reason: str | None
    version: int
    telegram_invoice_url: str | None = Field(
        default=None,
        description="Optional t.me invoice link opened by Telegram Mini App.",
    )
    latest_analysis: PaymentAnalysisSummary | None = None


class EvidenceUploadResponse(BaseModel):
    payment: PaymentResponse
    evidence_id: UUID
    sha256: str


class ReceiptExtraction(BaseModel):
    is_payment_receipt: bool = Field(
        description="Whether the image is a bank payment receipt or transfer confirmation."
    )
    amount_minor: int | None = Field(
        default=None,
        ge=0,
        description="Transferred amount in minor currency units, never a floating point value.",
    )
    currency: str | None = Field(default=None, description="ISO 4217 uppercase currency code.")
    operation_date: date | None = Field(default=None, description="Date printed on the receipt.")
    operation_number: str | None = Field(
        default=None, max_length=255, description="Bank operation/reference/transaction number."
    )
    bank_name: str | None = Field(default=None, max_length=255)
    recipient: str | None = Field(default=None, max_length=255)
    confidence: Annotated[float, Field(ge=0, le=1)]
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @field_validator("operation_number", "bank_name", "recipient")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ReviewPaymentRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=3, max_length=1000)
    expected_version: int = Field(ge=1)


class ReviewQueueItem(BaseModel):
    payment: PaymentResponse
    extracted: ReceiptExtraction | None
    evidence_id: UUID
    evidence_content_type: str
    evidence_uploaded_at: datetime
