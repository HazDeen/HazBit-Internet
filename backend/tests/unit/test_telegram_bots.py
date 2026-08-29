from __future__ import annotations

from typing import Any

import pytest
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.main import create_app
from app.modules.bots.callbacks import CallbackCodec
from app.modules.bots.dependencies import get_telegram_bot_service, get_telegram_update_gate
from app.modules.bots.notifications import (
    TelegramNotificationClaim,
    TelegramNotificationProcessor,
)
from app.modules.bots.schemas import TelegramUpdate
from fastapi.testclient import TestClient


class FakeBotService:
    def __init__(self) -> None:
        self.customer_updates: list[int] = []
        self.operations_updates: list[int] = []

    async def customer_update(self, update: TelegramUpdate) -> None:
        self.customer_updates.append(update.update_id)

    async def operations_update(self, update: TelegramUpdate) -> None:
        self.operations_updates.append(update.update_id)


class FakeUpdateGate:
    def __init__(self, *, first: bool = True) -> None:
        self.first = first
        self.completed: list[tuple[str, int]] = []

    async def begin(self, bot: str, update_id: int) -> bool:
        del bot, update_id
        return self.first

    async def complete(self, bot: str, update_id: int) -> None:
        self.completed.append((bot, update_id))

    async def release(self, bot: str, update_id: int) -> None:
        del bot, update_id


def _update(update_id: int = 42) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 7,
            "from": {"id": 1001, "first_name": "Hazbit"},
            "chat": {"id": 1001, "type": "private"},
            "text": "/start",
        },
    }


def test_signed_callback_round_trip_and_size() -> None:
    codec = CallbackCodec("callback-secret", default_ttl_seconds=900)

    value = codec.encode("pa", f"{'a' * 32}:12", now=1_000)
    verified = codec.decode(value, now=1_001)

    assert len(value.encode()) <= 64
    assert verified.action == "pa"
    assert verified.payload == f"{'a' * 32}:12"


def test_signed_callback_rejects_tampering_and_expiry() -> None:
    codec = CallbackCodec("callback-secret", default_ttl_seconds=60)
    value = codec.encode("cs", now=1_000)

    with pytest.raises(ApplicationError, match="signature"):
        codec.decode(value[:-1] + ("a" if value[-1] != "a" else "b"), now=1_001)
    with pytest.raises(ApplicationError, match="expired"):
        codec.decode(value, now=1_061)


def test_update_parses_telegram_aliases_and_successful_payment() -> None:
    update = TelegramUpdate.model_validate(
        {
            "update_id": 8,
            "message": {
                "message_id": 9,
                "from": {"id": 77, "first_name": "User"},
                "chat": {"id": 77, "type": "private"},
                "successful_payment": {
                    "currency": "RUB",
                    "total_amount": 49900,
                    "invoice_payload": "signed",
                    "telegram_payment_charge_id": "tg-charge",
                    "provider_payment_charge_id": "provider-charge",
                },
            },
        }
    )

    assert update.actor_id == 77
    assert update.message is not None
    assert update.message.successful_payment is not None
    assert update.message.successful_payment.total_amount == 49900


def test_customer_ticket_reply_notification_uses_mini_app(test_settings: Settings) -> None:
    processor = TelegramNotificationProcessor(
        session=None,  # type: ignore[arg-type]
        settings=test_settings,
        operations_client=None,  # type: ignore[arg-type]
        customer_client=None,  # type: ignore[arg-type]
        callbacks=CallbackCodec("callback-secret", default_ttl_seconds=900),
    )

    text, markup = processor._render(
        TelegramNotificationClaim(
            event_id=uuid7(),
            event_type="support.ticket.admin_replied",
            payload={
                "ticket_id": "0192ca0f-5af7-7af5-98d6-72af6eb6fa01",
                "public_number": 1048,
                "subject": "VLESS profile disconnects",
                "user_id": "0192ca0f-5af7-7af5-98d6-72af6eb6fa02",
            },
            attempt=1,
        )
    )

    assert "Поддержка ответила" in text
    assert "VLESS" in text
    assert markup["inline_keyboard"][0][0]["web_app"]["url"].endswith(":5175")


def test_customer_webhook_requires_secret_and_deduplicates(
    test_settings: Settings,
) -> None:
    app = create_app(test_settings)
    service = FakeBotService()
    gate = FakeUpdateGate(first=True)
    app.dependency_overrides[get_telegram_bot_service] = lambda: service
    app.dependency_overrides[get_telegram_update_gate] = lambda: gate

    with TestClient(app, raise_server_exceptions=False) as client:
        forbidden = client.post("/api/v1/bots/customer/webhook", json=_update())
        accepted = client.post(
            "/api/v1/bots/customer/webhook",
            json=_update(),
            headers={"X-Telegram-Bot-Api-Secret-Token": "local-customer-webhook-secret"},
        )

    assert forbidden.status_code == 403
    assert accepted.status_code == 200
    assert service.customer_updates == [42]
    assert gate.completed == [("customer", 42)]


def test_duplicate_webhook_is_acknowledged_without_dispatch(test_settings: Settings) -> None:
    app = create_app(test_settings)
    service = FakeBotService()
    app.dependency_overrides[get_telegram_bot_service] = lambda: service
    app.dependency_overrides[get_telegram_update_gate] = lambda: FakeUpdateGate(first=False)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/bots/customer/webhook",
            json=_update(99),
            headers={"X-Telegram-Bot-Api-Secret-Token": "local-customer-webhook-secret"},
        )

    assert response.json() == {"ok": True, "duplicate": True}
    assert service.customer_updates == []
