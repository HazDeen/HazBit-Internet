from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = "postgresql+asyncpg://hazbit:hazbit@localhost:5432/hazbit_vpn"
    echo: bool = False
    pool_size: int = Field(default=10, ge=1, le=100)
    max_overflow: int = Field(default=20, ge=0, le=200)
    pool_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    command_timeout_seconds: float = Field(default=10.0, gt=0, le=120)

    @field_validator("url")
    @classmethod
    def validate_async_postgres_url(cls, value: str) -> str:
        parsed = make_url(value)
        if parsed.drivername != "postgresql+asyncpg":
            raise ValueError("database URL must use the postgresql+asyncpg driver")
        return value

    def sqlalchemy_url(self) -> URL:
        return make_url(self.url)

    def alembic_url(self) -> URL:
        return self.sqlalchemy_url().set(drivername="postgresql+psycopg")

    def safe_url(self) -> str:
        return self.sqlalchemy_url().render_as_string(hide_password=True)


class RedisSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = "redis://localhost:6379/0"
    key_prefix: str = "hazbit"
    socket_connect_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    socket_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    def safe_url(self) -> str:
        return make_url(self.url).render_as_string(hide_password=True)


class JwtSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issuer: str = "hazbit-vpn-api"
    audience: str = "hazbit-vpn-clients"
    secret: SecretStr = SecretStr("local-only-jwt-secret-change-me-0123456789")
    access_ttl_minutes: int = Field(default=15, ge=5, le=60)
    refresh_ttl_days: int = Field(default=30, ge=1, le=180)
    clock_skew_seconds: int = Field(default=30, ge=0, le=300)


class OtpSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: SecretStr = SecretStr("local-only-otp-secret-change-me-0123456789")
    ttl_minutes: int = Field(default=10, ge=2, le=30)
    code_length: int = Field(default=6, ge=6, le=8)
    max_attempts: int = Field(default=5, ge=3, le=5)


class TelegramSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_token: SecretStr = SecretStr("")
    bot_username: str | None = None
    init_data_max_age_seconds: int = Field(default=300, ge=30, le=3600)

    @field_validator("bot_username", mode="before")
    @classmethod
    def normalize_bot_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().removeprefix("@")
        return normalized or None


class GoogleAuthSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    client_id: str | None = None

    @field_validator("client_id", mode="before")
    @classmethod
    def normalize_client_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class TelegramBotsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_webhook_secret: SecretStr = SecretStr("local-customer-webhook-secret")
    operations_bot_token: SecretStr = SecretStr("")
    operations_webhook_secret: SecretStr = SecretStr("local-operations-webhook-secret")
    callback_secret: SecretStr = SecretStr("local-only-bot-callback-secret-change-me-0123456789")
    webhook_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8000")
    mini_app_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:5175")
    admin_app_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:5173")
    required_channel_id: str | None = None
    operations_chat_ids: list[int] = Field(default_factory=list)
    customer_updates_per_minute: int = Field(default=30, ge=5, le=300)
    operations_updates_per_minute: int = Field(default=60, ge=5, le=600)
    update_lock_seconds: int = Field(default=60, ge=10, le=300)
    update_receipt_ttl_seconds: int = Field(default=86400, ge=3600, le=604800)
    callback_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    notification_batch_size: int = Field(default=25, ge=1, le=100)
    notification_poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=60)
    notification_lock_seconds: int = Field(default=120, ge=30, le=600)


class EmailSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["console", "smtp"] = "console"
    from_address: EmailStr = "no-reply@example.com"
    from_name: str = Field(default="Hazbit", min_length=1, max_length=120)
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_start_tls: bool = True
    smtp_use_tls: bool = False
    invitation_ttl_hours: int = Field(default=72, ge=1, le=336)
    invite_limit_per_day: int = Field(default=20, ge=1, le=200)
    invitation_secret: SecretStr = SecretStr(
        "local-only-staff-invitation-secret-change-me-0123456789"
    )
    invitation_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:5173/#staff-invite")

    @field_validator("smtp_host", "smtp_username", mode="before")
    @classmethod
    def normalize_optional_smtp_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("smtp_password", mode="before")
    @classmethod
    def normalize_optional_smtp_password(
        cls, value: str | SecretStr | None
    ) -> str | SecretStr | None:
        if value is None:
            return None
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        return value if raw else None

    @model_validator(mode="after")
    def validate_smtp_transport(self) -> Self:
        if self.smtp_start_tls and self.smtp_use_tls:
            raise ValueError("SMTP STARTTLS and implicit TLS cannot both be enabled")
        if (self.smtp_username is None) != (self.smtp_password is None):
            raise ValueError("SMTP username and password must be configured together")
        return self


class CookieSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_name: str = "hazbit_refresh"
    csrf_name: str = "hazbit_csrf"
    secure: bool = False
    domain: str | None = None
    same_site: Literal["lax", "strict"] = "strict"


class AuthSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jwt: JwtSettings = Field(default_factory=JwtSettings)
    otp: OtpSettings = Field(default_factory=OtpSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    google: GoogleAuthSettings = Field(default_factory=GoogleAuthSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    cookies: CookieSettings = Field(default_factory=CookieSettings)
    refresh_token_secret: SecretStr = SecretStr("local-only-refresh-secret-change-me-0123456789")
    fingerprint_secret: SecretStr = SecretStr("local-only-fingerprint-secret-change-me-0123456789")


class RemnawaveAdapterSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8010")
    internal_token: SecretStr = SecretStr("local-internal-token-change-me")
    allow_insecure_private_url: bool = False
    connect_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    read_timeout_seconds: float = Field(default=10.0, gt=0, le=120)


class VpnSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: RemnawaveAdapterSettings = Field(default_factory=RemnawaveAdapterSettings)
    subscription_url_secret: SecretStr = SecretStr("local-only-subscription-url-secret-change-me")
    command_max_attempts: int = Field(default=8, ge=1, le=20)
    command_lock_timeout_seconds: int = Field(default=300, ge=30, le=3600)
    command_poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=60)
    retry_base_seconds: int = Field(default=5, ge=1, le=300)
    retry_max_seconds: int = Field(default=3600, ge=60, le=86400)


class GeminiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr = SecretStr("")
    model: str = Field(default="gemini-2.5-flash", min_length=3, max_length=120)
    prompt_version: str = Field(default="payment-receipt-v1", min_length=3, max_length=40)
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)


class PaymentStorageSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["local", "s3"] = "local"
    bucket: str = Field(default="hazbit-payment-evidence", min_length=3, max_length=120)
    local_directory: Path = Path(".data/payment-evidence")
    endpoint_url: AnyHttpUrl | None = None
    region: str = Field(default="us-east-1", min_length=2, max_length=80)
    access_key_id: str | None = None
    secret_access_key: SecretStr | None = None

    @model_validator(mode="after")
    def validate_static_credentials(self) -> Self:
        if (self.access_key_id is None) != (self.secret_access_key is None):
            raise ValueError("payment storage access key and secret must be configured together")
        return self


class PaymentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    storage: PaymentStorageSettings = Field(default_factory=PaymentStorageSettings)
    expected_recipient: str = Field(default="HAZBIT VPN", min_length=2, max_length=255)
    intent_ttl_minutes: int = Field(default=60, ge=10, le=1440)
    evidence_retention_days: int = Field(default=180, ge=30, le=3650)
    max_upload_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    max_image_pixels: int = Field(default=20_000_000, ge=1_000_000, le=50_000_000)
    auto_approve_confidence: float = Field(default=0.92, ge=0.5, le=1.0)
    operation_max_age_days: int = Field(default=7, ge=1, le=31)
    operation_future_tolerance_days: int = Field(default=1, ge=0, le=3)
    analysis_max_attempts: int = Field(default=3, ge=1, le=10)
    analysis_lock_timeout_seconds: int = Field(default=120, ge=30, le=600)
    analysis_poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=60)


def _default_platega_payment_methods() -> list[Literal[2, 10, 13]]:
    return [2, 10, 13]


class PlategaSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    base_url: AnyHttpUrl = AnyHttpUrl("https://app.platega.io")
    merchant_id: SecretStr = SecretStr("")
    secret: SecretStr = SecretStr("")
    success_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:5174/#billing/success")
    failed_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:5174/#billing/failed")
    timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    allowed_payment_methods: list[Literal[2, 10, 13]] = Field(
        default_factory=_default_platega_payment_methods
    )

    @model_validator(mode="after")
    def validate_credentials(self) -> Self:
        merchant_id = self.merchant_id.get_secret_value()
        secret = self.secret.get_secret_value()
        if self.enabled and (not merchant_id or not secret):
            raise ValueError("Platega merchant ID and secret are required when enabled")
        if len(self.allowed_payment_methods) != len(set(self.allowed_payment_methods)):
            raise ValueError("Platega payment methods must be unique")
        return self


class BillingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platega: PlategaSettings = Field(default_factory=PlategaSettings)
    currency: str = Field(default="RUB", pattern=r"^[A-Z]{3}$")
    minimum_top_up_minor: int = Field(default=10_000, ge=100)
    maximum_top_up_minor: int = Field(default=1_000_000_00, ge=100)
    renewal_poll_interval_seconds: float = Field(default=30.0, ge=1.0, le=3600)
    renewal_retry_seconds: int = Field(default=3600, ge=60, le=86400)

    @model_validator(mode="after")
    def validate_top_up_limits(self) -> Self:
        if self.maximum_top_up_minor < self.minimum_top_up_minor:
            raise ValueError("maximum wallet top-up must be at least the minimum")
        return self


class ReferralSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    referred_days: int = Field(default=3, ge=1, le=30)
    referrer_days: int = Field(default=5, ge=1, le=90)
    default_plan_slug: str = Field(default="basic", min_length=2, max_length=80)
    code_length: int = Field(default=10, ge=8, le=16)
    claim_new_user_max_age_days: int = Field(default=14, ge=1, le=90)
    shared_ip_review_threshold: int = Field(default=5, ge=2, le=100)
    shared_device_review_threshold: int = Field(default=2, ge=1, le=20)
    claim_rate_limit_per_hour: int = Field(default=8, ge=1, le=100)
    worker_batch_size: int = Field(default=25, ge=1, le=200)
    worker_poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=60)
    share_url_prefix: str = Field(
        default="https://t.me/example_bot?start=ref_", min_length=10, max_length=500
    )

    @field_validator("share_url_prefix")
    @classmethod
    def validate_share_url_prefix(cls, value: str) -> str:
        if not value.startswith("https://") or "start=ref_" not in value:
            raise ValueError("referral share URL must be HTTPS and contain start=ref_")
        return value


class PromoSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_plan_slug: str = Field(default="basic", min_length=2, max_length=80)
    preview_rate_limit_per_hour: int = Field(default=30, ge=1, le=1000)
    redeem_rate_limit_per_hour: int = Field(default=10, ge=1, le=100)


class SupportSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    create_rate_limit_per_day: int = Field(default=10, ge=1, le=100)
    message_rate_limit_per_hour: int = Field(default=120, ge=1, le=1000)
    idempotency_ttl_hours: int = Field(default=24, ge=1, le=168)
    initial_message_limit: int = Field(default=100, ge=1, le=500)


class FamilySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_ttl_hours: int = Field(default=72, ge=1, le=336)
    invite_limit_per_day: int = Field(default=20, ge=1, le=200)


class FeatureSettings(BaseModel):
    """Deployment-level feature availability.

    Runtime controls may pause an enabled feature, but can never enable a feature
    that was disabled by the deployment configuration.
    """

    model_config = ConfigDict(extra="forbid")

    vpn_provisioning: bool = True
    billing: bool = True
    payment_ai: bool = True
    referrals: bool = True
    promotions: bool = True
    families: bool = True
    support: bool = True
    telegram_bots: bool = True


class LaunchPlanPriceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_slug: Literal["basic", "premium", "family"]
    term_months: Literal[1, 3, 6, 12] = 1
    duration_days: int = Field(default=30, ge=1, le=3660)
    currency: str = Field(default="RUB", pattern=r"^[A-Z]{3}$")
    amount_minor: int = Field(gt=0)


class LaunchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    super_admin_email: EmailStr | None = None
    plan_prices: list[LaunchPlanPriceSettings] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_prices(self) -> Self:
        keys = [(price.plan_slug, price.term_months, price.currency) for price in self.plan_prices]
        if len(keys) != len(set(keys)):
            raise ValueError("launch plan prices must be unique by plan, term, and currency")
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_prefix="HAZBIT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Hazbit Platform API"
    app_version: str = "0.1.0"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    docs_enabled: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    request_id_header: str = "X-Request-ID"
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:5175",
            "http://127.0.0.1:5175",
        ]
    )
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    telegram_bots: TelegramBotsSettings = Field(default_factory=TelegramBotsSettings)
    vpn: VpnSettings = Field(default_factory=VpnSettings)
    payments: PaymentSettings = Field(default_factory=PaymentSettings)
    billing: BillingSettings = Field(default_factory=BillingSettings)
    referrals: ReferralSettings = Field(default_factory=ReferralSettings)
    promotions: PromoSettings = Field(default_factory=PromoSettings)
    support: SupportSettings = Field(default_factory=SupportSettings)
    families: FamilySettings = Field(default_factory=FamilySettings)
    features: FeatureSettings = Field(default_factory=FeatureSettings)
    launch: LaunchSettings = Field(default_factory=LaunchSettings)

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError("api_v1_prefix must start with '/' and must not end with '/'")
        return value

    @model_validator(mode="after")
    def validate_production_safety(self) -> Self:
        if self.environment == "production" and self.debug:
            raise ValueError("debug cannot be enabled in production")
        if self.environment == "production" and self.log_format != "json":
            raise ValueError("production logging must use JSON")
        if self.environment == "production" and self.docs_enabled:
            raise ValueError("API documentation must be disabled in production")
        if self.environment == "production" and "*" in self.allowed_hosts:
            raise ValueError("wildcard allowed_hosts is forbidden in production")
        if self.environment == "production" and "*" in self.cors_origins:
            raise ValueError("wildcard CORS origins are forbidden in production")
        if self.environment == "production":
            self._validate_production_auth()
            if self.features.telegram_bots:
                self._validate_production_bots()
            if self.features.payment_ai:
                self._validate_production_payments()
            if self.features.billing:
                self._validate_production_billing()
            if self.features.referrals:
                self._validate_production_referrals()
            self._validate_production_launch()
            self._validate_production_hosts()
        return self

    def _validate_production_auth(self) -> None:
        secrets = {
            "JWT": self.auth.jwt.secret.get_secret_value(),
            "OTP": self.auth.otp.secret.get_secret_value(),
            "refresh": self.auth.refresh_token_secret.get_secret_value(),
            "fingerprint": self.auth.fingerprint_secret.get_secret_value(),
            "staff invitation": self.auth.email.invitation_secret.get_secret_value(),
        }
        for label, secret in secrets.items():
            if len(secret) < 32 or secret.startswith("local-only"):
                raise ValueError(f"{label} secret must be replaced for production")
        if self.features.telegram_bots and not self.auth.telegram.bot_token.get_secret_value():
            raise ValueError("Telegram bot token is required in production")
        if self.features.telegram_bots and not self.auth.telegram.bot_username:
            raise ValueError("Telegram bot username is required in production")
        if self.auth.google.enabled and not self.auth.google.client_id:
            raise ValueError(
                "Google OAuth client ID is required when Google authentication is enabled"
            )
        if self.auth.email.backend != "smtp" or not self.auth.email.smtp_host:
            raise ValueError("SMTP email backend is required in production")
        if self.auth.email.invitation_url.scheme != "https":
            raise ValueError("staff invitation URL must use HTTPS in production")
        if not self.auth.cookies.secure:
            raise ValueError("secure authentication cookies are required in production")
        vpn_secrets = {
            "Remnawave adapter": self.vpn.adapter.internal_token.get_secret_value(),
            "subscription URL": self.vpn.subscription_url_secret.get_secret_value(),
        }
        for label, secret in vpn_secrets.items():
            if len(secret) < 32 or secret.startswith("local-"):
                raise ValueError(f"{label} secret must be replaced for production")
        adapter = self.vpn.adapter
        if adapter.base_url.scheme != "https":
            hostname = adapter.base_url.host or ""
            private_service = hostname == "remnawave-adapter" or hostname.endswith(".internal")
            if not adapter.allow_insecure_private_url or not private_service:
                raise ValueError(
                    "Remnawave adapter must use HTTPS in production unless an explicitly "
                    "trusted private service hostname is configured"
                )

    def _validate_production_payments(self) -> None:
        if not self.payments.gemini.api_key.get_secret_value():
            raise ValueError("Gemini API key is required in production")
        storage = self.payments.storage
        if storage.backend != "s3":
            raise ValueError("S3 payment evidence storage is required in production")

    def _validate_production_billing(self) -> None:
        provider = self.billing.platega
        if not provider.enabled:
            raise ValueError("Platega billing must be enabled in production")
        if provider.base_url.scheme != "https":
            raise ValueError("Platega base URL must use HTTPS in production")
        if provider.success_url.scheme != "https" or provider.failed_url.scheme != "https":
            raise ValueError("Platega return URLs must use HTTPS in production")

    def _validate_production_bots(self) -> None:
        bots = self.telegram_bots
        required_secrets = {
            "customer webhook": bots.customer_webhook_secret.get_secret_value(),
            "operations bot": bots.operations_bot_token.get_secret_value(),
            "operations webhook": bots.operations_webhook_secret.get_secret_value(),
            "bot callback": bots.callback_secret.get_secret_value(),
        }
        for label, secret in required_secrets.items():
            if len(secret) < 24 or secret.startswith("local-"):
                raise ValueError(f"{label} secret must be replaced for production")
        if (
            bots.webhook_base_url.scheme != "https"
            or bots.mini_app_url.scheme != "https"
            or bots.admin_app_url.scheme != "https"
        ):
            raise ValueError("Telegram bot application URLs must use HTTPS in production")
        if not bots.operations_chat_ids:
            raise ValueError("at least one operations chat ID is required in production")

    def _validate_production_referrals(self) -> None:
        if "example_bot" in self.referrals.share_url_prefix:
            raise ValueError("production referral share URL must use the real Telegram bot")

    def _validate_production_launch(self) -> None:
        if self.launch.super_admin_email is None:
            raise ValueError("first super admin email is required in production")
        configured_plans = {price.plan_slug for price in self.launch.plan_prices}
        missing_plans = {"basic", "premium", "family"} - configured_plans
        if missing_plans:
            missing = ", ".join(sorted(missing_plans))
            raise ValueError(f"production launch prices are missing for: {missing}")

    def _validate_production_hosts(self) -> None:
        values = [
            *self.allowed_hosts,
            *self.cors_origins,
            str(self.auth.email.from_address),
            self.auth.email.smtp_host or "",
            str(self.launch.super_admin_email or ""),
            str(self.telegram_bots.webhook_base_url),
            str(self.telegram_bots.mini_app_url),
            str(self.telegram_bots.admin_app_url),
        ]
        if any("example.com" in value.casefold() for value in values):
            raise ValueError("example.com placeholders must be replaced for production")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
