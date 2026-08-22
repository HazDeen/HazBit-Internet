from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class DashboardTrendPoint(BaseModel):
    date: str
    users: int
    payments_minor: int


class AdminDashboardResponse(BaseModel):
    total_users: int
    active_users: int
    active_subscriptions: int
    monthly_revenue_minor: int
    revenue_currency: str
    open_tickets: int
    pending_payments: int
    active_vpn_accounts: int
    active_promo_codes: int
    trend: list[DashboardTrendPoint]


class AdminSubscriptionSummary(BaseModel):
    id: UUID
    plan_version_id: UUID
    plan_slug: str
    plan_name: str
    status: str
    source: str
    starts_at: datetime | None
    current_period_ends_at: datetime | None
    device_limit: int
    version: int


class AdminUserListItem(BaseModel):
    id: UUID
    email: str | None
    telegram_id: int | None
    telegram_username: str | None
    status: str
    created_at: datetime
    subscription: AdminSubscriptionSummary | None
    devices: int
    trial: bool
    approved_payments: int
    paid_total_minor: int


class AdminUserPage(BaseModel):
    items: list[AdminUserListItem]
    total: int
    limit: int
    offset: int


class AdminDeviceResponse(BaseModel):
    id: UUID
    user_id: UUID
    vpn_account_id: UUID
    slot_number: int
    label: str | None
    external_hwid: str | None
    platform: str | None
    status: str
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    created_at: datetime


class AdminPaymentSummary(BaseModel):
    id: UUID
    user_id: UUID
    status: str
    amount_minor: int
    currency: str
    plan_price_id: UUID
    created_at: datetime
    approved_at: datetime | None
    version: int


class AdminUserDetail(AdminUserListItem):
    public_name: str | None
    locale: str
    timezone: str
    blocked_at: datetime | None
    blocked_reason: str | None
    devices_detail: list[AdminDeviceResponse]
    payments: list[AdminPaymentSummary]


class BlockUserRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class ExtendSubscriptionRequest(BaseModel):
    days: int = Field(ge=1, le=365)
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class ChangePlanRequest(BaseModel):
    plan_version_id: UUID
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class AdminSubscriptionListItem(AdminSubscriptionSummary):
    owner_user_id: UUID
    owner_email: str | None
    vpn_status: str | None


class AdminSubscriptionPage(BaseModel):
    items: list[AdminSubscriptionListItem]
    total: int
    limit: int
    offset: int


class AdminPlanPriceResponse(BaseModel):
    id: UUID
    term_months: int
    duration_days: int
    currency: str
    amount_minor: int
    is_active: bool


class AdminPlanVersionResponse(BaseModel):
    id: UUID
    version: int
    device_limit: int
    family_member_limit: int
    traffic_limit_bytes: int | None
    valid_from: datetime
    valid_until: datetime | None
    prices: list[AdminPlanPriceResponse]


class AdminPlanResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None
    is_active: bool
    sort_order: int
    versions: list[AdminPlanVersionResponse]


class AdminPlanPriceInput(BaseModel):
    term_months: int = Field(ge=1, le=12)
    duration_days: int = Field(ge=1, le=366)
    currency: str = Field(min_length=3, max_length=3)
    amount_minor: int = Field(ge=0)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("term_months")
    @classmethod
    def validate_term(cls, value: int) -> int:
        if value not in {1, 3, 6, 12}:
            raise ValueError("term must be 1, 3, 6, or 12 months")
        return value


class CreateAdminPlanRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int = Field(default=0, ge=0, le=10000)
    device_limit: int = Field(ge=1, le=100)
    family_member_limit: int = Field(default=0, ge=0, le=100)
    traffic_limit_bytes: int | None = Field(default=None, ge=1)
    prices: list[AdminPlanPriceInput] = Field(min_length=1, max_length=12)
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("slug", "name", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_unique_prices(self) -> CreateAdminPlanRequest:
        price_keys = {(price.term_months, price.currency) for price in self.prices}
        if len(price_keys) != len(self.prices):
            raise ValueError("plan prices must have unique term and currency pairs")
        return self


class UpdateAdminPlanRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def require_change(self) -> UpdateAdminPlanRequest:
        if not self.model_fields_set.intersection(
            {"name", "description", "sort_order", "is_active"}
        ):
            raise ValueError("at least one plan field must be provided")
        return self


class CreateAdminPlanVersionRequest(BaseModel):
    device_limit: int = Field(ge=1, le=100)
    family_member_limit: int = Field(default=0, ge=0, le=100)
    traffic_limit_bytes: int | None = Field(default=None, ge=1)
    prices: list[AdminPlanPriceInput] = Field(min_length=1, max_length=12)
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def require_unique_prices(self) -> CreateAdminPlanVersionRequest:
        price_keys = {(price.term_months, price.currency) for price in self.prices}
        if len(price_keys) != len(self.prices):
            raise ValueError("plan prices must have unique term and currency pairs")
        return self


class ArchiveAdminPlanRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class AdminFamilyActionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class AdminFamilyMemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: str | None
    joined_at: datetime


class AdminFamilyInvitationResponse(BaseModel):
    id: UUID
    invited_user_id: UUID | None
    invited_email: str | None
    status: str
    expires_at: datetime
    created_at: datetime


class AdminFamilyGroupResponse(BaseModel):
    id: UUID
    owner_user_id: UUID
    owner_email: str | None
    subscription_id: UUID
    plan_name: str
    subscription_status: str
    name: str
    status: str
    member_limit: int
    active_member_count: int
    pending_invitation_count: int = 0
    device_limit: int = 0
    active_device_count: int = 0
    created_at: datetime
    members: list[AdminFamilyMemberResponse] = Field(default_factory=list)
    invitations: list[AdminFamilyInvitationResponse] = Field(default_factory=list)


class AdminFamilyGroupPage(BaseModel):
    items: list[AdminFamilyGroupResponse]
    total: int
    limit: int
    offset: int


class AdminPaymentPage(BaseModel):
    items: list[AdminPaymentSummary]
    total: int
    limit: int
    offset: int


class AdminDevicePage(BaseModel):
    items: list[AdminDeviceResponse]
    total: int
    limit: int
    offset: int


class AdminSettingsResponse(BaseModel):
    environment: str
    app_version: str
    log_level: str
    payment_ai_model: str
    payment_prompt_version: str
    remnawave_adapter_url: str
    referral_days: int
    referrer_days: int
    default_promo_plan: str
    support_create_limit_per_day: int
    support_message_limit_per_hour: int
