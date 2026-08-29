from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.auth.models import TelegramAccount
from app.modules.bots.callbacks import CallbackCodec
from app.modules.bots.telegram_api import TelegramBotClient
from app.modules.payments.models import OutboxEvent
from app.modules.vpn.models import Subscription


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
        operations_client: TelegramBotClient,
        customer_client: TelegramBotClient,
        callbacks: CallbackCodec,
    ) -> None:
        self._session = session
        self._settings = settings
        self._operations = operations_client
        self._customer = customer_client
        self._callbacks = callbacks

    async def claim(self, *, limit: int | None = None) -> list[TelegramNotificationClaim]:
        now = datetime.now(UTC)
        limit = limit or self._settings.telegram_bots.notification_batch_size
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
                                OutboxEvent.event_type == "support.ticket.created",
                                OutboxEvent.event_type == "support.ticket.user_replied",
                                OutboxEvent.event_type == "support.ticket.admin_replied",
                                OutboxEvent.event_type == "subscription.expiry_reminder",
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
            if claim.event_type in {
                "support.ticket.admin_replied",
                "subscription.expiry_reminder",
            }:
                chat_id = await self._customer_chat_id(claim)
                if chat_id is not None and self._customer.configured:
                    await self._customer.send_message(chat_id, text, reply_markup=markup)
            elif self._operations.configured:
                for chat_id in self._settings.telegram_bots.operations_chat_ids:
                    await self._operations.send_message(chat_id, text, reply_markup=markup)
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
        if claim.event_type == "subscription.expiry_reminder":
            mini_url = str(self._settings.telegram_bots.mini_app_url).rstrip("/")
            ends_at = datetime.fromisoformat(str(payload["ends_at"]))
            text = (
                "<b>Подписка закончится завтра</b>\n\n"
                f"Доступ активен до <b>{ends_at.astimezone(UTC):%d.%m.%Y %H:%M} UTC</b>. "
                "Пополните баланс заранее, чтобы автопродление прошло без паузы."
            )
            return text, {
                "inline_keyboard": [[{"text": "Пополнить баланс", "web_app": {"url": mini_url}}]]
            }
        ticket_number = int(payload.get("public_number", 0))
        subject = escape(str(payload.get("subject", "Обращение в поддержку")))
        if claim.event_type == "support.ticket.admin_replied":
            mini_url = str(self._settings.telegram_bots.mini_app_url).rstrip("/")
            text = (
                "<b>Поддержка ответила</b>\n\n"
                f"Тикет <b>#{ticket_number}</b> · {subject}\n"
                "Откройте обращение, чтобы прочитать ответ."
            )
            return text, {
                "inline_keyboard": [[{"text": "Открыть поддержку", "web_app": {"url": mini_url}}]]
            }
        category = escape(str(payload.get("category", "other")))
        heading = (
            "Новое сообщение клиента"
            if claim.event_type == "support.ticket.user_replied"
            else "Новый тикет поддержки"
        )
        text = (
            f"<b>{heading}</b>\n\n"
            f"Тикет <b>#{ticket_number}</b> · {subject}\n"
            f"Категория: {category}\n"
            f"Ticket ID: <code>{escape(str(payload['ticket_id']))}</code>"
        )
        return text, {
            "inline_keyboard": [[{"text": "Открыть очередь", "url": f"{admin_url}#tickets"}]]
        }

    async def enqueue_expiry_reminders(self) -> int:
        now = datetime.now(UTC)
        window_start = now + timedelta(hours=23)
        window_end = now + timedelta(hours=25)
        already_queued = exists(
            select(OutboxEvent.id).where(
                OutboxEvent.aggregate_type == "subscription",
                OutboxEvent.aggregate_id == Subscription.id,
                OutboxEvent.event_type == "subscription.expiry_reminder",
            )
        )
        rows = (
            await self._session.execute(
                select(
                    Subscription.id, Subscription.owner_user_id, Subscription.current_period_ends_at
                )
                .where(
                    Subscription.status.in_(["active", "grace_period"]),
                    Subscription.current_period_ends_at >= window_start,
                    Subscription.current_period_ends_at < window_end,
                    ~already_queued,
                )
                .limit(self._settings.telegram_bots.notification_batch_size)
            )
        ).all()
        if not rows:
            return 0
        async with self._session.begin_nested():
            for subscription_id, user_id, ends_at in rows:
                await self._session.execute(
                    insert(OutboxEvent)
                    .values(
                        aggregate_type="subscription",
                        aggregate_id=subscription_id,
                        event_type="subscription.expiry_reminder",
                        payload={
                            "subscription_id": str(subscription_id),
                            "user_id": str(user_id),
                            "ends_at": ends_at.isoformat(),
                        },
                        idempotency_key=f"subscription-expiry-reminder:{subscription_id}",
                    )
                    .on_conflict_do_nothing(index_elements=["idempotency_key"])
                )
        await self._session.commit()
        return len(rows)

    async def _customer_chat_id(self, claim: TelegramNotificationClaim) -> int | None:
        raw_user_id = claim.payload.get("user_id")
        if raw_user_id is None:
            return None
        value = await self._session.scalar(
            select(TelegramAccount.telegram_user_id).where(
                TelegramAccount.user_id == UUID(str(raw_user_id))
            )
        )
        return int(value) if value is not None else None

    async def _retry(self, claim: TelegramNotificationClaim, error: Exception) -> None:
        delay = min(3600, 5 * (2 ** min(claim.attempt - 1, 9)))
        async with self._session.begin():
            event = await self._session.get(OutboxEvent, claim.event_id, with_for_update=True)
            if event is not None:
                event.available_at = datetime.now(UTC) + timedelta(seconds=delay)
                event.last_error = f"{type(error).__name__}: {error}"[:2000]
