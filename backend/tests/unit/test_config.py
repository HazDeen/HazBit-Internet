from __future__ import annotations

import pytest
from app.core.config import DatabaseSettings, Settings
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
            allowed_hosts=["api.example.com"],
        )


def test_production_accepts_complete_auth_configuration() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        log_format="json",
        docs_enabled=False,
        allowed_hosts=["api.example.com"],
        auth={
            "jwt": {"secret": "j" * 32},
            "otp": {"secret": "o" * 32},
            "refresh_token_secret": "r" * 32,
            "fingerprint_secret": "f" * 32,
            "telegram": {"bot_token": "123456:production-token"},
            "email": {
                "backend": "smtp",
                "from_address": "auth@example.com",
                "smtp_host": "smtp.example.com",
            },
            "cookies": {"secure": True},
        },
        vpn={
            "adapter": {
                "base_url": "https://remnawave-adapter.example.com",
                "internal_token": "i" * 32,
            },
            "subscription_url_secret": "s" * 32,
        },
        telegram_bots={
            "customer_webhook_secret": "c" * 32,
            "operations_bot_token": "123456:" + "b" * 32,
            "operations_webhook_secret": "w" * 32,
            "callback_secret": "k" * 32,
            "webhook_base_url": "https://api.example.com",
            "mini_app_url": "https://app.example.com",
            "admin_app_url": "https://admin.example.com",
            "operations_chat_ids": [-1001234567890],
        },
        payments={
            "gemini": {"api_key": "production-gemini-key"},
            "storage": {
                "backend": "s3",
                "endpoint_url": "https://objects.example.com",
                "access_key_id": "access-key",
                "secret_access_key": "storage-secret",
            },
        },
        referrals={"share_url_prefix": "https://t.me/hazbit_bot?start=ref_"},
    )

    assert settings.auth.cookies.secure is True


def test_production_allows_explicit_private_remnawave_adapter() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        log_format="json",
        docs_enabled=False,
        allowed_hosts=["api.example.com"],
        auth={
            "jwt": {"secret": "j" * 32},
            "otp": {"secret": "o" * 32},
            "refresh_token_secret": "r" * 32,
            "fingerprint_secret": "f" * 32,
            "telegram": {"bot_token": "123456:production-token"},
            "email": {"backend": "smtp", "smtp_host": "smtp.example.com"},
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
            "webhook_base_url": "https://api.example.com",
            "mini_app_url": "https://app.example.com",
            "admin_app_url": "https://admin.example.com",
            "operations_chat_ids": [-1001234567890],
        },
        payments={
            "gemini": {"api_key": "production-gemini-key"},
            "storage": {"backend": "s3"},
        },
        referrals={"share_url_prefix": "https://t.me/hazbit_bot?start=ref_"},
    )

    assert settings.vpn.adapter.allow_insecure_private_url is True


def test_production_rejects_public_insecure_remnawave_adapter() -> None:
    with pytest.raises(ValidationError, match="trusted private service hostname"):
        Settings(
            _env_file=None,
            environment="production",
            log_format="json",
            docs_enabled=False,
            allowed_hosts=["api.example.com"],
            auth={
                "jwt": {"secret": "j" * 32},
                "otp": {"secret": "o" * 32},
                "refresh_token_secret": "r" * 32,
                "fingerprint_secret": "f" * 32,
                "telegram": {"bot_token": "123456:production-token"},
                "email": {"backend": "smtp", "smtp_host": "smtp.example.com"},
                "cookies": {"secure": True},
            },
            vpn={
                "adapter": {
                    "base_url": "http://adapter.example.com",
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
                "webhook_base_url": "https://api.example.com",
                "mini_app_url": "https://app.example.com",
                "admin_app_url": "https://admin.example.com",
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
