from __future__ import annotations

import json
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from app.core.config import Settings
from app.modules.bots.health import wait_for_public_webhooks, webhook_urls
from app.modules.bots.telegram_api import TelegramBotClient
from app.workers import check_telegram_bots, setup_telegram_bots
from app.workers.check_telegram_bots import verify_delivery


def _public_response(request: httpx.Request) -> httpx.Response:
    if request.method == "GET":
        assert request.url.path == "/health/ready"
        return httpx.Response(200, json={"status": "ok"})
    assert "X-Telegram-Bot-Api-Secret-Token" not in request.headers
    assert json.loads(request.content) == {"update_id": 0}
    return httpx.Response(403, json={"code": "telegram_webhook_forbidden"})


async def test_public_probe_reaches_health_and_both_routes(test_settings: Settings) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return _public_response(request)

    await wait_for_public_webhooks(test_settings, transport=httpx.MockTransport(handler))
    assert paths == [
        "/health/ready",
        "/api/v1/bots/customer/webhook",
        "/api/v1/bots/operations/webhook",
    ]


@pytest.mark.parametrize(
    "status,body",
    [
        (502, {}),
        (200, {"ok": True}),
        (403, {"code": "wrong_proxy"}),
        (302, {}),
    ],
)
async def test_public_probe_rejects_bad_upstream(
    test_settings: Settings,
    status: int,
    body: dict[str, Any],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return _public_response(request)
        return httpx.Response(status, json=body)

    with pytest.raises(RuntimeError, match="Public API/Caddy route is not ready"):
        await wait_for_public_webhooks(
            test_settings,
            attempts=1,
            transport=httpx.MockTransport(handler),
        )


async def test_public_probe_retries_startup_race(test_settings: Settings) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(502) if calls <= 3 else _public_response(request)

    await wait_for_public_webhooks(
        test_settings,
        attempts=2,
        retry_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    assert calls == 6


def _bot_with_webhooks(responses: list[dict[str, Any]]) -> TelegramBotClient:
    bot = Mock(spec=TelegramBotClient)
    bot.call = AsyncMock(side_effect=[{"is_bot": True, "username": "test_bot"}, *responses])
    return cast(TelegramBotClient, bot)


def _webhook(url: str, *, pending: int = 0, error_date: int | None = 100) -> dict[str, Any]:
    return {
        "url": url,
        "pending_update_count": pending,
        "last_error_message": "Wrong response from the webhook: 502 Bad Gateway",
        "last_error_date": error_date,
    }


async def test_stale_error_with_empty_queue_is_warning(
    test_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url = webhook_urls(test_settings)["customer"]
    bot = _bot_with_webhooks([_webhook(url)])
    await verify_delivery({"customer": bot}, {"customer": url}, verification_started_at=200)
    assert "historical error" in capsys.readouterr().out


async def test_stale_error_waits_for_pending_update(test_settings: Settings) -> None:
    url = webhook_urls(test_settings)["customer"]
    bot = _bot_with_webhooks([_webhook(url, pending=1), _webhook(url)])
    await verify_delivery(
        {"customer": bot},
        {"customer": url},
        verification_started_at=200,
        attempts=2,
        retry_seconds=0,
    )
    assert [call.args[0] for call in bot.call.await_args_list] == [  # type: ignore[attr-defined]
        "getMe",
        "getWebhookInfo",
        "getWebhookInfo",
    ]


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"pending_update_count": 1}, "pending=1"),
        ({"last_error_date": 200}, "new or undated"),
        ({"last_error_date": 201}, "new or undated"),
        ({"last_error_date": None}, "new or undated"),
        ({"last_error_date": 10**30}, "new or undated"),
        ({"url": ""}, "webhook URL does not match"),
        ({"pending_update_count": None}, "invalid pending_update_count"),
    ],
)
async def test_unconfirmed_delivery_fails(
    test_settings: Settings,
    overrides: dict[str, Any],
    reason: str,
) -> None:
    url = webhook_urls(test_settings)["customer"]
    bot = _bot_with_webhooks([{**_webhook(url), **overrides}])
    with pytest.raises(RuntimeError, match=reason):
        await verify_delivery(
            {"customer": bot},
            {"customer": url},
            verification_started_at=200,
            attempts=1,
        )


async def test_persistent_queue_is_not_ignored_after_retries(test_settings: Settings) -> None:
    url = webhook_urls(test_settings)["customer"]
    bot = _bot_with_webhooks([_webhook(url, pending=1)] * 3)
    with pytest.raises(RuntimeError, match="pending=1"):
        await verify_delivery(
            {"customer": bot},
            {"customer": url},
            verification_started_at=200,
            attempts=3,
            retry_seconds=0,
        )


@pytest.mark.parametrize("worker", [setup_telegram_bots, check_telegram_bots])
async def test_disabled_bots_do_not_create_clients(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    worker: Any,
) -> None:
    test_settings.features.telegram_bots = False
    monkeypatch.setattr(worker, "get_settings", lambda: test_settings)
    factory = Mock()
    probe = AsyncMock()
    monkeypatch.setattr(worker, "create_telegram_bots_runtime", factory)
    monkeypatch.setattr(worker, "wait_for_public_webhooks", probe)
    await worker.run()
    factory.assert_not_called()
    probe.assert_not_awaited()


async def test_manual_webhook_configuration_skips_setup(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAZBIT_CONFIGURE_TELEGRAM_WEBHOOKS", "false")
    monkeypatch.setattr(setup_telegram_bots, "get_settings", lambda: test_settings)
    factory = Mock()
    monkeypatch.setattr(setup_telegram_bots, "create_telegram_bots_runtime", factory)
    await setup_telegram_bots.run()
    factory.assert_not_called()


async def test_setup_checks_public_route_before_registering_webhooks(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAZBIT_CONFIGURE_TELEGRAM_WEBHOOKS", "true")
    monkeypatch.setattr(setup_telegram_bots, "get_settings", lambda: test_settings)
    monkeypatch.setattr(
        setup_telegram_bots,
        "wait_for_public_webhooks",
        AsyncMock(side_effect=RuntimeError("Public route: 502")),
    )
    factory = Mock()
    monkeypatch.setattr(setup_telegram_bots, "create_telegram_bots_runtime", factory)
    with pytest.raises(RuntimeError, match="Public route: 502"):
        await setup_telegram_bots.run()
    factory.assert_not_called()
