from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.main import create_app
from app.modules.auth.enums import Permission, Role, UserStatus
from app.modules.auth.rate_limit import RateLimiter
from app.modules.bots.callbacks import CallbackCodec
from app.modules.bots.dependencies import get_telegram_bot_service, get_telegram_update_gate
from app.modules.bots.notifications import (
    TelegramNotificationClaim,
    TelegramNotificationProcessor,
)
from app.modules.bots.repository import BotIdentity
from app.modules.bots.schemas import TelegramUpdate
from app.modules.bots.service import TelegramBotService
from app.modules.bots.telegram_api import TelegramBotClient
from app.modules.payments.service import PaymentService
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


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


@pytest.mark.parametrize("kind", ["customer", "operations"])
def test_public_probe_never_dispatches_update(test_settings: Settings, kind: str) -> None:
    app = create_app(test_settings)
    service = FakeBotService()
    gate = FakeUpdateGate()
    app.dependency_overrides[get_telegram_bot_service] = lambda: service
    app.dependency_overrides[get_telegram_update_gate] = lambda: gate

    with TestClient(app) as client:
        response = client.post(f"/api/v1/bots/{kind}/webhook", json={"update_id": 0})

    assert response.status_code == 403
    assert response.json()["code"] == "telegram_webhook_forbidden"
    assert service.customer_updates == service.operations_updates == []
    assert gate.completed == []


@pytest.fixture
def real_bot_service(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TelegramBotService, AsyncMock, AsyncMock]:
    customer = AsyncMock(spec=TelegramBotClient)
    operations = AsyncMock(spec=TelegramBotClient)
    service = TelegramBotService(
        session=AsyncMock(spec=AsyncSession),
        settings=test_settings,
        rate_limiter=AsyncMock(spec=RateLimiter),
        customer_client=customer,
        operations_client=operations,
        callbacks=CallbackCodec("callback-secret", default_ttl_seconds=900),
        payment_service=Mock(spec=PaymentService),
    )
    identity = BotIdentity(
        user_id=uuid7(),
        locale="ru",
        status=UserStatus.ACTIVE.value,
        roles=frozenset({Role.SUPER_ADMIN.value}),
        permissions=frozenset(Permission),
    )
    monkeypatch.setattr(service._repository, "identity", AsyncMock(return_value=identity))
    return service, customer, operations


@pytest.mark.parametrize("kind", ["customer", "operations"])
@pytest.mark.parametrize(
    "message_fields",
    [
        {},
        {"text": None},
        {"text": ""},
        {"text": " \t\n\u00a0"},
        {"photo": [{"file_id": "test-photo"}]},
        {"sticker": {"file_id": "test-sticker"}},
        {"voice": {"file_id": "test-voice"}},
        {"new_chat_members": [{"id": 1002, "first_name": "Member"}]},
    ],
)
def test_real_webhook_acknowledges_non_text_updates(
    test_settings: Settings,
    real_bot_service: tuple[TelegramBotService, AsyncMock, AsyncMock],
    kind: str,
    message_fields: dict[str, Any],
) -> None:
    service, customer, operations = real_bot_service
    app = create_app(test_settings)
    gate = FakeUpdateGate()
    app.dependency_overrides[get_telegram_bot_service] = lambda: service
    app.dependency_overrides[get_telegram_update_gate] = lambda: gate
    payload = _update()
    del payload["message"]["text"]
    payload["message"].update(message_fields)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/api/v1/bots/{kind}/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": f"local-{kind}-webhook-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert gate.completed == [(kind, 42)]
    customer.send_message.assert_not_awaited()
    operations.send_message.assert_not_awaited()


@pytest.mark.parametrize("kind", ["customer", "operations"])
@pytest.mark.parametrize("text", ["/start", "/START@TestBot", "  /start\targument ", "/help"])
async def test_real_start_commands_still_reply(
    real_bot_service: tuple[TelegramBotService, AsyncMock, AsyncMock],
    kind: str,
    text: str,
) -> None:
    service, customer, operations = real_bot_service
    payload = _update()
    payload["message"]["text"] = text
    await getattr(service, f"{kind}_update")(TelegramUpdate.model_validate(payload))
    client = customer if kind == "customer" else operations
    client.send_message.assert_awaited_once()
    assert client.send_message.await_args.args[0] == 1001
    assert client.send_message.await_args.kwargs["reply_markup"]["inline_keyboard"]


async def test_non_text_payment_is_dispatched_before_command_parsing(
    real_bot_service: tuple[TelegramBotService, AsyncMock, AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, customer, _ = real_bot_service
    settle_payment = AsyncMock()
    monkeypatch.setattr(service, "_settle_telegram_payment", settle_payment)
    payload = _update()
    del payload["message"]["text"]
    payload["message"]["successful_payment"] = {
        "currency": "RUB",
        "total_amount": 49900,
        "invoice_payload": "signed",
        "telegram_payment_charge_id": "tg-charge",
        "provider_payment_charge_id": "provider-charge",
    }
    update = TelegramUpdate.model_validate(payload)
    await service.customer_update(update)
    settle_payment.assert_awaited_once_with(update.message)
    customer.send_message.assert_not_awaited()
