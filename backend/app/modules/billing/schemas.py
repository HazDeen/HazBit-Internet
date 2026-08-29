from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    field_validator,
)

PaymentMethod = Literal[2, 10, 13]


class CreateWalletTopUpRequest(BaseModel):
    amount_minor: int = Field(gt=0)
    currency: str = Field(default="RUB", pattern=r"^[A-Z]{3}$")
    payment_method: PaymentMethod


class WalletTopUpResponse(BaseModel):
    id: UUID
    provider: str
    provider_transaction_id: UUID | None
    payment_method: int
    status: str
    amount_minor: int
    currency: str
    checkout_url: str | None
    expires_at: datetime | None
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime


class WalletTransactionResponse(BaseModel):
    id: UUID
    transaction_type: str
    amount_minor: int
    currency: str
    description: str | None
    created_at: datetime


class WalletResponse(BaseModel):
    balance_minor: int
    currency: str
    auto_renew_enabled: bool
    auto_renew_plan_price_id: UUID | None
    next_renewal_at: datetime | None
    last_renewal_failure: str | None
    top_ups: list[WalletTopUpResponse] = Field(default_factory=list)
    transactions: list[WalletTransactionResponse] = Field(default_factory=list)


class PurchaseFromWalletRequest(BaseModel):
    plan_price_id: UUID
    auto_renew: bool = True


class WalletPurchaseResponse(BaseModel):
    transaction_id: UUID
    subscription_id: UUID
    balance_minor: int
    currency: str
    current_period_ends_at: datetime
    auto_renew_enabled: bool


class UpdateAutoRenewRequest(BaseModel):
    enabled: bool


class PlategaCallbackPayload(BaseModel):
    id: UUID = Field(validation_alias=AliasChoices("id", "Id"))
    amount: Decimal = Field(gt=0, validation_alias=AliasChoices("amount", "Amount"))
    currency: str = Field(validation_alias=AliasChoices("currency", "Currency"))
    status: str = Field(validation_alias=AliasChoices("status", "Status"))
    payment_method: int = Field(validation_alias=AliasChoices("paymentMethod", "PaymentMethod"))
    payload: str | None = Field(default=None, validation_alias=AliasChoices("payload", "Payload"))

    @field_validator("currency", "status")
    @classmethod
    def uppercase(cls, value: str) -> str:
        return value.strip().upper()
