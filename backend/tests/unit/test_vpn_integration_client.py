from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from app.core.config import RemnawaveAdapterSettings, VpnSettings
from app.integrations.remnawave_adapter import AdapterError, RemnawaveAdapterClient
from app.modules.vpn.crypto import SubscriptionUrlCipher


async def test_adapter_client_maps_internal_contract_and_authenticates() -> None:
    captured: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(
            201,
            json={
                "id": 42,
                "username": "hz_user",
                "status": "ACTIVE",
                "expire_at": "2026-09-22T12:00:00Z",
                "traffic_limit_bytes": 0,
                "device_limit": 3,
                "subscription_url": "https://subscription.example/secret",
            },
        )

    settings = RemnawaveAdapterSettings(
        base_url="https://adapter.example.com",
        internal_token="internal-secret",
    )
    client = RemnawaveAdapterClient(settings, transport=httpx.MockTransport(handler))
    try:
        result = await client.create_user(
            username="hz_user",
            expire_at=datetime(2026, 9, 22, 12, tzinfo=UTC),
            traffic_limit_bytes=0,
            device_limit=3,
            email="person@example.com",
            telegram_id=None,
            internal_squad_ids=[],
        )
    finally:
        await client.close()

    assert captured is not None
    assert captured.headers["Authorization"] == "Bearer internal-secret"
    assert captured.url.path == "/internal/v1/users"
    assert json.loads(captured.content)["device_limit"] == 3
    assert result.id == 42


async def test_adapter_client_normalizes_safe_error() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={
                "code": "panel_server_error_a001",
                "detail": "contains-vendor-detail",
                "retryable": True,
            },
        )

    client = RemnawaveAdapterClient(
        RemnawaveAdapterSettings(base_url="https://adapter.example.com"),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(AdapterError) as exc_info:
            await client.get_user(42)
    finally:
        await client.close()

    assert exc_info.value.code == "panel_server_error_a001"
    assert exc_info.value.retryable is True
    assert "vendor" not in exc_info.value.detail


def test_subscription_url_cipher_round_trip() -> None:
    cipher = SubscriptionUrlCipher(VpnSettings())
    value = "https://subscription.example/very-secret-token"
    ciphertext = cipher.encrypt(value)

    assert value.encode() not in ciphertext
    assert cipher.decrypt(ciphertext) == value
