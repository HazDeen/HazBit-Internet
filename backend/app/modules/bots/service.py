from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.modules.auth.crypto import OpaqueTokenCodec
from app.modules.auth.enums import Permission, Role, UserStatus
from app.modules.auth.models import RegistrationChallenge, TelegramAccount, TelegramLoginChallenge
from app.modules.auth.rate_limit import RateLimit, RateLimiter
from app.modules.bots.callbacks import CallbackCodec
from app.modules.bots.repository import BotIdentity, BotRepository
from app.modules.bots.schemas import TelegramCallbackQuery, TelegramMessage, TelegramUpdate
from app.modules.bots.telegram_api import TelegramBotClient
from app.modules.payments.approval import approve_payment
from app.modules.payments.enums import PaymentStatus, ReviewDecision
from app.modules.payments.ledger import wallet_balance
from app.modules.payments.models import Payment
from app.modules.payments.service import PaymentService
from app.modules.portal.service import PortalService

OPERATIONS_ROLES = {
    Role.SUPER_ADMIN.value,
    Role.ADMIN.value,
    Role.SUPPORT.value,
    Role.NETWORK.value,
    Role.FINANCE.value,
    Role.CONTENT.value,
}
PAYMENT_REVIEW_ROLES = {Role.SUPER_ADMIN.value, Role.ADMIN.value, Role.FINANCE.value}


def _mini_app_button(text: str, url: str) -> dict[str, Any]:
    return {"text": text, "web_app": {"url": url}}


def _url_button(text: str, url: str) -> dict[str, Any]:
    return {"text": text, "url": url}


def _message_command(text: str | None) -> str:
    # Media/service messages have no text; whitespace also produces an empty list.
    words = (text or "").split(maxsplit=1)
    return words[0].split("@", 1)[0].lower() if words else ""


class TelegramBotService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        rate_limiter: RateLimiter,
        customer_client: TelegramBotClient,
        operations_client: TelegramBotClient,
        callbacks: CallbackCodec,
        payment_service: PaymentService,
    ) -> None:
        self._session = session
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._customer = customer_client
        self._operations = operations_client
        self._callbacks = callbacks
        self._payments = payment_service
        self._repository = BotRepository(session)
        self._auth_tokens = OpaqueTokenCodec(settings.auth)

    async def customer_update(self, update: TelegramUpdate) -> None:
        actor_id = update.actor_id
        if actor_id is None:
            return
        await self._rate_limiter.enforce(
            RateLimit(
                "telegram_customer_update",
                self._settings.telegram_bots.customer_updates_per_minute,
                60,
            ),
            str(actor_id),
        )
        if update.callback_query is not None:
            await self._customer_callback(update.callback_query)
            return
        message = update.message
        if message is None:
            return
        try:
            if message.successful_payment is not None:
                await self._settle_telegram_payment(message)
                return
            command = _message_command(message.text)
            if not command:
                return
            if command in {"/start", "/help"}:
                await self._customer_start(message)
            elif command in {"/status", "/profile", "/subscription", "/balance"}:
                await self._customer_status(message.chat.id, actor_id)
            elif command == "/vpn":
                await self._send_customer_route(message.chat.id, "devices")
            elif command in {"/pay", "/payment"}:
                await self._send_customer_route(message.chat.id, "plans")
            elif command == "/support":
                await self._send_customer_route(message.chat.id, "support")
            else:
                await self._customer.send_message(
                    message.chat.id,
                    "Не понял команду. Используйте /status, /balance, /vpn, /pay или /support.",
                    reply_markup=self._customer_menu(),
                )
        except ApplicationError as exc:
            await self._customer.send_message(
                message.chat.id,
                f"<b>Действие недоступно</b>\n\n{escape(exc.detail)}",
                reply_markup=self._customer_menu(),
            )

    async def operations_update(self, update: TelegramUpdate) -> None:
        actor_id = update.actor_id
        if actor_id is None:
            return
        await self._rate_limiter.enforce(
            RateLimit(
                "telegram_operations_update",
                self._settings.telegram_bots.operations_updates_per_minute,
                60,
            ),
            str(actor_id),
        )
        try:
            identity = await self._require_operations_identity(actor_id)
        except ApplicationError as exc:
            if update.callback_query is not None:
                await self._operations.answer_callback(update.callback_query.id, exc.detail[:180])
            elif update.message is not None:
                await self._operations.send_message(
                    update.message.chat.id,
                    "Доступ к Hazbit Operations запрещён.",
                )
            return
        if update.callback_query is not None:
            await self._operations_callback(update.callback_query, identity)
            return
        message = update.message
        if message is None:
            return
        command = _message_command(message.text)
        if command in {"/start", "/help", "/queue"}:
            await self._operations.send_message(
                message.chat.id,
                (
                    "<b>Hazbit Operations</b>\n\n"
                    "Здесь приходят новые тикеты, ответы клиентов и платежи на ручную проверку. "
                    "Действия подписаны, имеют TTL и повторно не исполняются."
                ),
                reply_markup={
                    "inline_keyboard": [[_url_button("Открыть Admin Panel", self._admin_url())]]
                },
            )

    async def _customer_start(self, message: TelegramMessage) -> None:
        actor = message.from_user
        if actor is None:
            return
        start_parameter = (message.text or "").split(maxsplit=1)
        if len(start_parameter) == 2 and start_parameter[1].startswith(("reg_", "login_")):
            await self._approve_auth_challenge(message, start_parameter[1])
            return
        required_channel = self._settings.telegram_bots.required_channel_id
        if required_channel:
            status = await self._customer.get_chat_member(required_channel, actor.id)
            if status not in {"member", "administrator", "creator"}:
                rows: list[list[dict[str, Any]]] = []
                if required_channel.startswith("@"):
                    rows.append(
                        [
                            _url_button(
                                "Подписаться на канал", f"https://t.me/{required_channel[1:]}"
                            )
                        ]
                    )
                rows.append(
                    [
                        {
                            "text": "Проверить подписку",
                            "callback_data": self._callbacks.encode("cc"),
                        }
                    ]
                )
                await self._customer.send_message(
                    message.chat.id,
                    "Для продолжения подпишитесь на официальный канал Hazbit.",
                    reply_markup={"inline_keyboard": rows},
                )
                return
        identity = await self._repository.identity(actor.id)
        name = escape(actor.first_name or "друг")
        if identity is None:
            text = (
                f"Привет, <b>{name}</b>!\n\n"
                "Откройте Hazbit Mini App — Telegram безопасно привяжет аккаунт."
            )
        else:
            text = (
                f"С возвращением, <b>{name}</b>. Аккаунт подключён — всё управление доступно ниже."
            )
        await self._customer.send_message(message.chat.id, text, reply_markup=self._customer_menu())

    async def _approve_auth_challenge(self, message: TelegramMessage, start_parameter: str) -> None:
        actor = message.from_user
        if actor is None:
            return
        action, raw_token = start_parameter.split("_", 1)
        digest = self._auth_tokens.digest(raw_token)
        now = datetime.now(UTC)
        approved = False
        async with self._session.begin():
            if action == "reg":
                challenge = await self._session.scalar(
                    select(RegistrationChallenge)
                    .where(RegistrationChallenge.token_hash == digest)
                    .with_for_update()
                )
                if (
                    challenge is not None
                    and challenge.consumed_at is None
                    and challenge.expires_at > now
                    and challenge.telegram_user_id == actor.id
                ):
                    challenge.telegram_verified_at = now
                    challenge.telegram_username = actor.username
                    challenge.telegram_first_name = actor.first_name
                    challenge.telegram_last_name = actor.last_name
                    challenge.telegram_language_code = actor.language_code
                    approved = True
            elif action == "login":
                challenge = await self._session.scalar(
                    select(TelegramLoginChallenge)
                    .where(TelegramLoginChallenge.token_hash == digest)
                    .with_for_update()
                )
                linked_account = await self._session.scalar(
                    select(TelegramAccount.id).where(TelegramAccount.telegram_user_id == actor.id)
                )
                if (
                    challenge is not None
                    and linked_account is not None
                    and challenge.consumed_at is None
                    and challenge.expires_at > now
                    and challenge.telegram_user_id == actor.id
                ):
                    challenge.approved_at = now
                    approved = True
        if approved:
            await self._customer.send_message(
                message.chat.id,
                "<b>Подтверждение принято.</b>\n\nВернитесь в браузер и продолжите вход.",
                reply_markup=self._customer_menu(),
            )
            return
        await self._customer.send_message(
            message.chat.id,
            "Ссылка подтверждения недействительна, истекла или относится к другому аккаунту.",
            reply_markup=self._customer_menu(),
        )

    async def _customer_status(self, chat_id: int, telegram_user_id: int) -> None:
        identity = await self._require_customer_identity(telegram_user_id)
        overview = await PortalService(self._session).overview(identity.user_id)
        subscription = overview.subscription
        if subscription is None:
            subscription_text = "Нет активной подписки"
        else:
            end = (
                subscription.current_period_ends_at.astimezone(UTC).strftime("%d.%m.%Y")
                if subscription.current_period_ends_at
                else "без даты"
            )
            subscription_text = (
                f"{escape(subscription.plan_name)} · {escape(subscription.status)} · до {end}"
            )
        vpn = overview.vpn.observed_status if overview.vpn else "не создан"
        balance = await wallet_balance(
            self._session, identity.user_id, self._settings.billing.currency
        )
        text = (
            "<b>Статус Hazbit</b>\n\n"
            f"Подписка: <b>{subscription_text}</b>\n"
            f"Баланс: <b>{balance / 100:,.2f} {escape(self._settings.billing.currency)}</b>\n"
            f"VPN: <b>{escape(vpn or 'синхронизация')}</b>\n"
            f"Устройства: <b>{overview.active_device_count}</b>\n"
            f"Открытые тикеты: <b>{overview.open_ticket_count}</b>"
        )
        await self._customer.send_message(
            chat_id,
            text,
            reply_markup={
                "inline_keyboard": [
                    [_mini_app_button("Открыть Hazbit", self._mini_url("overview"))],
                    [
                        {
                            "text": "Обновить",
                            "callback_data": self._callbacks.encode("cs"),
                        }
                    ],
                ]
            },
        )

    async def _send_customer_route(self, chat_id: int, route: str) -> None:
        labels = {
            "devices": ("VPN и устройства", "Открыть устройства"),
            "plans": ("Баланс, оплата и тарифы", "Открыть оплату"),
            "support": ("Поддержка Hazbit", "Открыть поддержку"),
        }
        title, button = labels[route]
        await self._customer.send_message(
            chat_id,
            f"<b>{title}</b>\n\nПродолжите в защищённом Mini App.",
            reply_markup={"inline_keyboard": [[_mini_app_button(button, self._mini_url(route))]]},
        )

    async def _customer_callback(self, callback: TelegramCallbackQuery) -> None:
        if not callback.data or callback.message is None:
            await self._customer.answer_callback(callback.id)
            return
        try:
            verified = self._callbacks.decode(callback.data)
            if verified.action == "cs":
                await self._customer_status(callback.message.chat.id, callback.from_user.id)
            elif verified.action == "cc":
                await self._customer_start(
                    callback.message.model_copy(update={"from_user": callback.from_user})
                )
            else:
                raise ApplicationError("telegram_callback_unknown", "Unknown action.", 400)
        except ApplicationError as exc:
            await self._customer.answer_callback(callback.id, exc.detail[:180])
            return
        await self._customer.answer_callback(callback.id, "Готово")

    async def _operations_callback(
        self, callback: TelegramCallbackQuery, identity: BotIdentity
    ) -> None:
        if not callback.data or callback.message is None:
            await self._operations.answer_callback(callback.id)
            return
        try:
            verified = self._callbacks.decode(callback.data)
            if verified.action not in {"pa", "pr"}:
                raise ApplicationError("telegram_callback_unknown", "Unknown action.", 400)
            if Permission.PAYMENTS_REVIEW not in identity.permissions:
                raise ApplicationError(
                    "telegram_operations_forbidden",
                    "Payment review permission is required.",
                    403,
                )
            payment_hex, version_raw = verified.payload.split(":", 1)
            payment_id = UUID(hex=payment_hex)
            decision = (
                ReviewDecision.APPROVED if verified.action == "pa" else ReviewDecision.REJECTED
            )
            payment = await self._payments.review_payment(
                payment_id=payment_id,
                reviewer_user_id=identity.user_id,
                decision=decision,
                reason=f"{decision.value.title()} via Telegram operations bot",
                expected_version=int(version_raw),
            )
            await self._operations.edit_message(
                callback.message.chat.id,
                callback.message.message_id,
                (
                    f"<b>Платёж {payment.id}</b>\n\n"
                    f"Решение: <b>{escape(payment.status)}</b>\n"
                    f"Проверил Telegram user <code>{callback.from_user.id}</code>."
                ),
            )
        except (ApplicationError, ValueError) as exc:
            detail = exc.detail if isinstance(exc, ApplicationError) else "Invalid payment action."
            await self._operations.answer_callback(callback.id, detail[:180])
            return
        await self._operations.answer_callback(callback.id, "Решение сохранено")

    async def _settle_telegram_payment(self, message: TelegramMessage) -> None:
        successful = message.successful_payment
        actor = message.from_user
        if successful is None or actor is None:
            return
        verified = self._callbacks.decode(successful.invoice_payload)
        if verified.action != "inv":
            raise ApplicationError(
                "telegram_invoice_payload_invalid", "Invoice payload is invalid.", 403
            )
        payment_id = UUID(hex=verified.payload)
        identity = await self._require_customer_identity(actor.id)
        now = datetime.now(UTC)
        async with self._session.begin():
            payment = await self._session.scalar(
                select(Payment)
                .where(Payment.id == payment_id, Payment.user_id == identity.user_id)
                .with_for_update()
            )
            if payment is None:
                raise ApplicationError("payment_not_found", "Payment not found.", 404)
            if payment.status in {
                PaymentStatus.APPROVED.value,
                PaymentStatus.ACTIVATION_PENDING.value,
                PaymentStatus.ACTIVATED.value,
            }:
                pass
            else:
                if payment.status != PaymentStatus.AWAITING_UPLOAD.value:
                    raise ApplicationError(
                        "telegram_payment_state_invalid",
                        "Payment cannot be settled from its current state.",
                        409,
                    )
                if (
                    successful.total_amount != payment.expected_amount_minor
                    or successful.currency.upper() != payment.currency
                ):
                    raise ApplicationError(
                        "telegram_payment_amount_mismatch",
                        "Telegram payment amount does not match the intent.",
                        409,
                    )
                payment.uploaded_at = now
                payment.operation_number_normalized = successful.telegram_payment_charge_id
                payment.observed_recipient_normalized = "telegram"
                await approve_payment(
                    self._session,
                    payment=payment,
                    actor_user_id=identity.user_id,
                    actor_type="telegram_bot",
                    reason=f"Telegram charge {successful.telegram_payment_charge_id}",
                )
        await self._customer.send_message(
            message.chat.id,
            (
                "<b>Платёж подтверждён</b>\n\n"
                "Подписка активируется автоматически. "
                "Статус можно проверить в Mini App."
            ),
            reply_markup={
                "inline_keyboard": [
                    [_mini_app_button("Проверить статус", self._mini_url("overview"))]
                ]
            },
        )

    async def _require_customer_identity(self, telegram_user_id: int) -> BotIdentity:
        identity = await self._repository.identity(telegram_user_id)
        if identity is None:
            raise ApplicationError(
                "telegram_account_not_linked", "Open Mini App to link your account.", 401
            )
        if identity.status != UserStatus.ACTIVE.value:
            raise ApplicationError("user_inactive", "Account is not active.", 403)
        return identity

    async def _require_operations_identity(self, telegram_user_id: int) -> BotIdentity:
        identity = await self._require_customer_identity(telegram_user_id)
        if not identity.roles.intersection(OPERATIONS_ROLES) or not identity.permissions:
            raise ApplicationError(
                "telegram_operations_forbidden", "Operations access is not allowed.", 403
            )
        return identity

    def _customer_menu(self) -> dict[str, Any]:
        return {
            "inline_keyboard": [
                [_mini_app_button("Открыть Hazbit", self._mini_url("overview"))],
                [
                    {"text": "Статус", "callback_data": self._callbacks.encode("cs")},
                    _mini_app_button("VPN", self._mini_url("devices")),
                ],
                [
                    _mini_app_button("Баланс и тарифы", self._mini_url("plans")),
                    _mini_app_button("Поддержка", self._mini_url("support")),
                ],
            ]
        }

    def _mini_url(self, route: str) -> str:
        return f"{str(self._settings.telegram_bots.mini_app_url).rstrip('/')}#{route}"

    def _admin_url(self) -> str:
        return str(self._settings.telegram_bots.admin_app_url).rstrip("/")
