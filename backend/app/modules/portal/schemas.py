from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PortalIdentityResponse(BaseModel):
    id: UUID
    public_name: str | None
    email: str | None
    telegram_user_id: int | None
    telegram_username: str | None
    locale: str
    created_at: datetime


class PortalSubscriptionResponse(BaseModel):
    id: UUID
    status: str
    source: str
    plan_version_id: UUID
    plan_slug: str
    plan_name: str
    starts_at: datetime | None
    current_period_ends_at: datetime | None
    device_limit: int
    family_member_limit: int


class PortalVpnResponse(BaseModel):
    desired_status: str
    observed_status: str | None
    expires_at: datetime | None
    provisioning: bool


class PortalOverviewResponse(BaseModel):
    user: PortalIdentityResponse
    subscription: PortalSubscriptionResponse | None
    vpn: PortalVpnResponse | None
    active_device_count: int
    open_ticket_count: int
    family_group_id: UUID | None
    family_group_name: str | None


class PortalPlanPriceResponse(BaseModel):
    id: UUID
    term_months: int
    duration_days: int
    currency: str
    amount_minor: int


class PortalPlanResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None
    plan_version_id: UUID
    device_limit: int
    family_member_limit: int
    traffic_limit_bytes: int | None
    prices: list[PortalPlanPriceResponse] = Field(default_factory=list)


class PortalPaymentResponse(BaseModel):
    id: UUID
    plan_price_id: UUID
    status: str
    amount_minor: int
    currency: str
    expires_at: datetime
    uploaded_at: datetime | None
    approved_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
