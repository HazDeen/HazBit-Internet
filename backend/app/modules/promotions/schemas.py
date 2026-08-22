from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class PromoCodeValue(BaseModel):
    code: str = Field(min_length=3, max_length=64)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]+", normalized):
            raise ValueError("promo code must contain only ASCII letters, digits, _ or -")
        return normalized


class PreviewPromoCodeRequest(PromoCodeValue):
    plan_price_id: UUID | None = None
    plan_version_id: UUID | None = None


class RedeemPromoCodeRequest(PromoCodeValue):
    plan_version_id: UUID | None = None


class PromoPreviewResponse(BaseModel):
    code: str
    promo_type: str
    value: int
    starts_at: datetime
    expires_at: datetime | None
    plan_version_id: UUID | None
    original_amount_minor: int | None
    discount_amount_minor: int | None
    final_amount_minor: int | None
    currency: str | None


class PromoRedemptionResponse(BaseModel):
    id: UUID
    code: str
    promo_type: str
    value: int
    payment_id: UUID | None
    subscription_period_id: UUID | None
    discount_amount_minor: int | None
    free_days: int | None
    redeemed_at: datetime
    revoked_at: datetime | None
    subscription_ends_at: datetime | None = None


class CreatePromoCodeRequest(PromoCodeValue):
    promo_type: Literal["discount_percent", "free_days"]
    value: int = Field(ge=1, le=32767)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    usage_limit: int | None = Field(default=None, ge=1)
    per_user_limit: int = Field(default=1, ge=1, le=100)
    starts_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    plan_version_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @model_validator(mode="after")
    def validate_promotion(self) -> Self:
        if self.promo_type == "discount_percent" and self.value > 99:
            raise ValueError("discount percent must be between 1 and 99")
        if self.promo_type == "free_days" and self.currency is not None:
            raise ValueError("currency is only valid for discount promo codes")
        if self.expires_at is not None and self.expires_at <= self.starts_at:
            raise ValueError("expiration must be after the start time")
        if len(set(self.plan_version_ids)) != len(self.plan_version_ids):
            raise ValueError("plan version IDs must be unique")
        return self


class UpdatePromoCodeRequest(BaseModel):
    is_active: bool | None = None
    expires_at: datetime | None = None
    usage_limit: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class ArchivePromoCodeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class AdminPromoCodeResponse(BaseModel):
    id: UUID
    code: str
    promo_type: str
    value: int
    currency: str | None
    usage_limit: int | None
    per_user_limit: int
    starts_at: datetime
    expires_at: datetime | None
    is_active: bool
    plan_version_ids: list[UUID]
    usage_count: int
    created_by_user_id: UUID | None
    created_at: datetime
