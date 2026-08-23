from __future__ import annotations

import json

import pytest
from app.core.config import DatabaseSettings, LaunchSettings, Settings
from pydantic import ValidationError


def test_database_url_requires_asyncpg() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg"):
        DatabaseSettings(url="postgresql://user:password@localhost/db")


def test_safe_url_hides_password() -> None:
    settings = DatabaseSettings(url="postgresql+asyncpg://user:super-secret@localhost:5432/db")

    assert "super-secret" not in settings.safe_url()
    assert "***" in settings.safe_url()


def test_production_rejects_debug() -> None:
    with pytest.raises(ValidationError, match="debug cannot be enabled"):
        Settings(_env_file=None, environment="production", debug=True, log_format="json")


def test_production_requires_json_logging() -> None:
    with pytest.raises(ValidationError, match="production logging must use JSON"):
        Settings(_env_file=None, environment="production", log_format="console")


def test_production_requires_docs_to_be_disabled() -> None:
    with pytest.raises(ValidationError, match="documentation must be disabled"):
        Settings(_env_file=None, environment="production", log_format="json")


def test_production_rejects_wildcard_hosts() -> None:
    with pytest.raises(ValidationError, match="wildcard allowed_hosts"):
        Settings(
            _env_file=None,
            environment="production",
            log_format="json",
            docs_enabled=False,
            allowed_hosts=["*"],
        )


def test_production_rejects_local_auth_secrets() -> None:
    with pytest.raises(ValidationError, match="secret must be replaced"):
        Settings(
            _env_file=None,
            environment="production",
            log_format="json",
            docs_enabled=False,
            allowed_hosts=["api.hazbit.app"],
        )


def test_production_accepts_complete_auth_configuration() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        log_format="json",
        docs_enabled=False,
        allowed_hosts=["api.hazbit.app"],
        auth={
            "jwt": {"secret": "j" * 32},
            "otp": {"secret": "o" * 32},
            "refresh_token_secret": "r" * 32,
            "fingerprint_secret": "f" * 32,
            "telegram": {"bot_token": "123456:production-token"},
            "email": {
                "backend": "smtp",
                "from_address": "auth@hazbit.app",
                "smtp_host": "smtp.hazbit.app",
            },
            "cookies": {"secure": True},
        },
        vpn={
            "adapter": {
                "base_url": "https://remnawave.hazbit.app",
                "internal_token": "i" * 32,
            },
            "subscription_url_secret": "s" * 32,
        },
        telegram_bots={
            "customer_webhook_secret": "c" * 32,
            "operations_bot_token": "123456:" + "b" * 32,
            "operations_webhook_secret": "w" * 32,
            "callback_secret": "k" * 32,
            "webhook_base_url": "https://api.hazbit.app",
            "mini_app_url": "https://app.hazbit.app",
            "admin_app_url": "https://admin.hazbit.app",
            "operations_chat_ids": [-1001234567890],
        },
        payments={
            "gemini": {"api_key": "production-gemini-key"},
            "storage": {
                "backend": "s3",
                "endpoint_url": "https://objects.hazbit.app",
                "access_key_id": "access-key",
                "secret_access_key": "storage-secret",
            },
        },
        referrals={"share_url_prefix": "https://t.me/hazbit_bot?start=ref_"},
        launch={
            "super_admin_email": "owner@hazbit.app",
            "plan_prices": [
                {"plan_slug": "basic", "amount_minor": 49900},
                {"plan_slug": "premium", "amount_minor": 79900},
                {"plan_slug": "family", "amount_minor": 119900},
            ],
        },
    )

    assert settings.auth.cookies.secure is True


def test_production_allows_explicit_private_remnawave_adapter() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        log_format="json",
        docs_enabled=False,
        allowed_hosts=["api.hazbit.app"],
        auth={
            "jwt": {"secret": "j" * 32},
            "otp": {"secret": "o" * 32},
            "refresh_token_secret": "r" * 32,
            "fingerprint_secret": "f" * 32,
            "telegram": {"bot_token": "123456:production-token"},
            "email": {
                "backend": "smtp",
                "from_address": "auth@hazbit.app",
                "smtp_host": "smtp.hazbit.app",
            },
            "cookies": {"secure": True},
        },
        vpn={
            "adapter": {
                "base_url": "http://remnawave-adapter:8010",
                "internal_token": "i" * 32,
                "allow_insecure_private_url": True,
            },
            "subscription_url_secret": "s" * 32,
        },
        telegram_bots={
            "customer_webhook_secret": "c" * 32,
            "operations_bot_token": "123456:" + "b" * 32,
            "operations_webhook_secret": "w" * 32,
            "callback_secret": "k" * 32,
            "webhook_base_url": "https://api.hazbit.app",
            "mini_app_url": "https://app.hazbit.app",
            "admin_app_url": "https://admin.hazbit.app",
            "operations_chat_ids": [-1001234567890],
        },
        payments={
            "gemini": {"api_key": "production-gemini-key"},
            "storage": {"backend": "s3"},
        },
        referrals={"share_url_prefix": "https://t.me/hazbit_bot?start=ref_"},
        launch={
            "super_admin_email": "owner@hazbit.app",
            "plan_prices": [
                {"plan_slug": "basic", "amount_minor": 49900},
                {"plan_slug": "premium", "amount_minor": 79900},
                {"plan_slug": "family", "amount_minor": 119900},
            ],
        },
    )

    assert settings.vpn.adapter.allow_insecure_private_url is True


def test_production_rejects_public_insecure_remnawave_adapter() -> None:
    with pytest.raises(ValidationError, match="trusted private service hostname"):
        Settings(
            _env_file=None,
            environment="production",
            log_format="json",
            docs_enabled=False,
            allowed_hosts=["api.hazbit.app"],
            auth={
                "jwt": {"secret": "j" * 32},
                "otp": {"secret": "o" * 32},
                "refresh_token_secret": "r" * 32,
                "fingerprint_secret": "f" * 32,
                "telegram": {"bot_token": "123456:production-token"},
                "email": {"backend": "smtp", "smtp_host": "smtp.hazbit.app"},
                "cookies": {"secure": True},
            },
            vpn={
                "adapter": {
                    "base_url": "http://adapter.hazbit.app",
                    "internal_token": "i" * 32,
                    "allow_insecure_private_url": True,
                },
                "subscription_url_secret": "s" * 32,
            },
            telegram_bots={
                "customer_webhook_secret": "c" * 32,
                "operations_bot_token": "123456:" + "b" * 32,
                "operations_webhook_secret": "w" * 32,
                "callback_secret": "k" * 32,
                "webhook_base_url": "https://api.hazbit.app",
                "mini_app_url": "https://app.hazbit.app",
                "admin_app_url": "https://admin.hazbit.app",
                "operations_chat_ids": [-1001234567890],
            },
            payments={
                "gemini": {"api_key": "production-gemini-key"},
                "storage": {"backend": "s3"},
            },
            referrals={"share_url_prefix": "https://t.me/hazbit_bot?start=ref_"},
        )


def test_api_prefix_is_normalized() -> None:
    with pytest.raises(ValidationError, match="must not end"):
        Settings(_env_file=None, api_v1_prefix="/api/v1/")


def test_launch_prices_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        LaunchSettings(
            super_admin_email="owner@example.com",
            plan_prices=[
                {"plan_slug": "basic", "amount_minor": 49900},
                {"plan_slug": "basic", "amount_minor": 59900},
            ],
        )


def test_launch_price_rejects_zero_amount() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        LaunchSettings(
            super_admin_email="owner@example.com",
            plan_prices=[{"plan_slug": "basic", "amount_minor": 0}],
        )


def test_launch_prices_load_from_nested_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    prices = [
        {"plan_slug": "basic", "amount_minor": 49900},
        {"plan_slug": "premium", "amount_minor": 79900},
        {"plan_slug": "family", "amount_minor": 119900},
    ]
    monkeypatch.setenv("HAZBIT_LAUNCH__SUPER_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("HAZBIT_LAUNCH__PLAN_PRICES", json.dumps(prices))

    settings = Settings(_env_file=None)

    assert settings.launch.super_admin_email == "owner@example.com"
    assert [price.amount_minor for price in settings.launch.plan_prices] == [
        49900,
        79900,
        119900,
    ]
