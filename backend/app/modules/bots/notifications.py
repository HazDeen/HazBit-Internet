from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.bots.callbacks import CallbackCodec
from app.modules.bots.telegram_api import TelegramBotClient
from app.modules.payments.models import OutboxEvent


@dataclass(frozen=True, slots=True)
class TelegramNotificationClaim:
    event_id: UUID
    event_type: str
    payload: dict[str, Any]
    attempt: int


class TelegramNotificationProcessor:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        client: TelegramBotClient,
        callbacks: CallbackCodec,
    ) -> None:
        self._session = session
        self._settings = settings
        self._client = client
        self._callbacks = callbacks

    async def claim(self, *, limit: int | None = None) -> list[TelegramNotificationClaim]:
        now = datetime.now(UTC)
        limit = limit or self._settings.telegram_bots.notification_batch_size
        urgent_ticket = and_(
            OutboxEvent.event_type == "support.ticket.created",
            OutboxEvent.payload["priority"].astext == "urgent",
        )
        async with self._session.begin():
            events = list(
                (
                    await self._session.scalars(
                        select(OutboxEvent)
                        .where(
                            OutboxEvent.published_at.is_(None),
                            OutboxEvent.available_at <= now,
                            or_(
                                OutboxEvent.event_type == "payment.manual_review_requested",
                                urgent_ticket,
                            ),
                        )
                        .order_by(OutboxEvent.occurred_at)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            claims: list[TelegramNotificationClaim] = []
            for event in events:
                event.attempt_count += 1
                event.available_at = now + timedelta(
                    seconds=self._settings.telegram_bots.notification_lock_seconds
                )
                claims.append(
                    TelegramNotificationClaim(
                        event_id=event.id,
                        event_type=event.event_type,
                        payload=dict(event.payload),
                        attempt=event.attempt_count,
                    )
                )
            return claims

    async def deliver(self, claim: TelegramNotificationClaim) -> None:
        try:
            text, markup = self._render(claim)
            for chat_id in self._settings.telegram_bots.operations_chat_ids:
                await self._client.send_message(chat_id, text, reply_markup=markup)
        except Exception as exc:
            await self._retry(claim, exc)
            return
        async with self._session.begin():
            event = await self._session.get(OutboxEvent, claim.event_id, with_for_update=True)
            if event is not None:
                event.published_at = datetime.now(UTC)
                event.last_error = None

    def _render(self, claim: TelegramNotificationClaim) -> tuple[str, dict[str, Any]]:
        payload = claim.payload
        admin_url = str(self._settings.telegram_bots.admin_app_url).rstrip("/")
        if claim.event_type == "payment.manual_review_requested":
            payment_id = UUID(str(payload["payment_id"]))
            version = int(payload["version"])
            amount = int(payload["amount_minor"]) / 100
            currency = escape(str(payload["currency"]))
            text = (
                "<b>Платёж требует проверки</b>\n\n"
                f"Сумма: <b>{amount:,.2f} {currency}</b>\n"
                f"Payment ID: <code>{payment_id}</code>"
            )
            callback_payload = f"{payment_id.hex}:{version}"
            markup = {
                "inline_keyboard": [
                    [
                        {
                            "text": "Подтвердить",
                            "callback_data": self._callbacks.encode("pa", callback_payload),
                        },
                        {
                            "text": "Отклонить",
                            "callback_data": self._callbacks.encode("pr", callback_payload),
                        },
                    ],
                    [{"text": "Открыть платёж", "url": f"{admin_url}#payments"}],
                ]
            }
            return text, markup
        ticket_number = int(payload["public_number"])
        category = escape(str(payload.get("category", "other")))
        text = (
            "<b>Срочный тикет</b>\n\n"
            f"Ticket <b>#{ticket_number}</b> · {category}\n"
            f"Ticket ID: <code>{escape(str(payload['ticket_id']))}</code>"
        )
        return text, {
            "inline_keyboard": [[{"text": "Открыть очередь", "url": f"{admin_url}#tickets"}]]
        }

    async def _retry(self, claim: TelegramNotificationClaim, error: Exception) -> None:
        delay = min(3600, 5 * (2 ** min(claim.attempt - 1, 9)))
        async with self._session.begin():
            event = await self._session.get(OutboxEvent, claim.event_id, with_for_update=True)
            if event is not None:
                event.available_at = datetime.now(UTC) + timedelta(seconds=delay)
                event.last_error = f"{type(error).__name__}: {error}"[:2000]
