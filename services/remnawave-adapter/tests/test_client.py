from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from remnawave_adapter.client import RemnawaveClient, RemnawaveClientError
from remnawave_adapter.config import Settings
from remnawave_adapter.schemas import ProvisionUserRequest


def _settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        panel_base_url="https://panel.example.com",
        panel_token="panel-secret",
        internal_token="internal-secret",
        max_get_attempts=3,
        **overrides,
    )


def _user_response() -> dict[str, object]:
    return {
        "response": {
            "id": 42,
            "username": "hz_123",
            "status": "ACTIVE",
            "expireAt": "2026-09-22T12:00:00Z",
            "trafficLimitBytes": 0,
            "hwidDeviceLimit": 3,
            "subscriptionUrl": "https://secret.example/sub/abc",
            "vlessUuid": "00000000-0000-0000-0000-000000000001",
        }
    }


async def test_create_user_maps_v332_contract_and_bearer_token() -> None:
    captured: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(201, json=_user_response())

    client = RemnawaveClient(_settings(), transport=httpx.MockTransport(handler))
    try:
        result = await client.create_user(
            ProvisionUserRequest(
                username="hz_123",
                expire_at=datetime(2026, 9, 22, 12, tzinfo=UTC),
                device_limit=3,
                email="person@example.com",
            )
        )
    finally:
        await client.close()

    assert captured is not None
    assert captured.headers["Authorization"] == "Bearer panel-secret"
    assert captured.url.path == "/api/users"
    body = json.loads(captured.content)
    assert body["expireAt"] == "2026-09-22T12:00:00Z"
    assert body["hwidDeviceLimit"] == 3
    assert result.id == 42
    assert result.subscription_url == "https://secret.example/sub/abc"


async def test_get_retries_transient_panel_error() -> None:
    attempts = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"message": "Server error", "errorCode": "A001"})
        return httpx.Response(200, json=_user_response())

    client = RemnawaveClient(_settings(), transport=httpx.MockTransport(handler))
    try:
        result = await client.get_user(42)
    finally:
        await client.close()

    assert attempts == 3
    assert result.id == 42


async def test_mutation_is_not_retried_and_vendor_error_is_normalized() -> None:
    attempts = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            400,
            json={"message": "User hwid device limit reached", "errorCode": "A099"},
        )

    client = RemnawaveClient(_settings(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RemnawaveClientError) as exc_info:
            await client.create_device(
                42,
                hwid="abcdefghij",
                platform=None,
                os_version=None,
                device_model=None,
                user_agent=None,
                request_ip=None,
            )
    finally:
        await client.close()

    assert attempts == 1
    assert exc_info.value.code == "panel_rejected_request_a099"
    assert exc_info.value.retryable is False


async def test_contract_mismatch_does_not_leak_response_body() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": {"subscriptionUrl": "very-secret"}})

    client = RemnawaveClient(_settings(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RemnawaveClientError) as exc_info:
            await client.get_user(42)
    finally:
        await client.close()

    assert exc_info.value.code == "panel_contract_mismatch"
    assert "very-secret" not in exc_info.value.detail


async def test_nodes_map_operational_metrics_and_actions() -> None:
    paths: list[str] = []
    node = {
        "uuid": "0192bc20-1111-7000-9000-000000000101",
        "name": "Frankfurt Core",
        "address": "de-1.hazbit.net",
        "countryCode": "DE",
        "isConnected": True,
        "isDisabled": False,
        "isConnecting": False,
        "lastStatusChange": "2026-08-29T00:00:00Z",
        "lastStatusMessage": None,
        "usersOnline": 184,
        "trafficUsedBytes": 1000,
        "trafficLimitBytes": 5000,
        "xrayUptime": 3600,
        "system": {
            "info": {"cpus": 8, "memoryTotal": 16_000},
            "stats": {
                "memoryUsed": 6_000,
                "loadAvg": [0.6, 0.5, 0.4],
                "interface": {"rxBytesPerSec": 1200, "txBytesPerSec": 2400},
            },
        },
        "versions": {"xray": "25.8.3", "node": "2.1.5"},
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        response = [node] if request.url.path == "/api/nodes" else node
        return httpx.Response(200, json={"response": response})

    client = RemnawaveClient(_settings(), transport=httpx.MockTransport(handler))
    try:
        result = await client.list_nodes()
        disabled = await client.disable_node(result.nodes[0].uuid)
    finally:
        await client.close()

    assert paths == [
        "/api/nodes",
        "/api/nodes/0192bc20-1111-7000-9000-000000000101/actions/disable",
    ]
    assert result.nodes[0].users_online == 184
    assert result.nodes[0].memory_used_bytes == 6000
    assert disabled.name == "Frankfurt Core"
