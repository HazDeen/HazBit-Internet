from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BillingSettings
from app.core.errors import ApplicationError
from app.modules.auth.models import AuditLog
from app.modules.auth.rate_limit import RateLimit, RateLimiter
from app.modules.billing.models import SubscriptionBillingSetting, WalletTopUp
from app.modules.billing.platega import PlategaClient
from app.modules.billing.repository import BillingRepository
from app.modules.billing.schemas import (
    PlategaCallbackPayload,
    WalletPurchaseResponse,
    WalletResponse,
    WalletTopUpResponse,
    WalletTransactionResponse,
)
from app.modules.payments.ledger import ledger_account, post_transaction, wallet_balance
from app.modules.payments.models import LedgerAccount, Transaction, TransactionEntry
from app.modules.referrals.models import Plan, SubscriptionPeriod
from app.modules.vpn.enums import CommandStatus, CommandType, DesiredVpnStatus
from app.modules.vpn.models import PlanVersion, Subscription, VpnAccount, VpnSyncCommand

TOP_UP_RATE = RateLimit("wallet_top_up_user", 10, 3600)
PURCHASE_RATE = RateLimit("wallet_purchase_user", 20, 3600)


@dataclass(frozen=True, slots=True)
class BillingClientContext:
    ip_address: str
    user_agent: str | None
    request_id: UUID | None


class BillingService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: BillingSettings,
        platega: PlategaClient,
        rate_limiter: RateLimiter,
    ) -> None:
        self._session = session
        self._settings = settings
        self._platega = platega
        self._rate_limiter = rate_limiter
        self._repository = BillingRepository(session)

    async def wallet(self, user_id: UUID) -> WalletResponse:
        currency = self._settings.currency
        setting = await self._repository.billing_setting(user_id)
        top_ups = await self._repository.user_top_ups(user_id)
        transactions = await self._repository.wallet_transactions(user_id, currency)
        return WalletResponse(
            balance_minor=await wallet_balance(self._session, user_id, currency),
            currency=currency,
            auto_renew_enabled=bool(setting and setting.auto_renew_enabled),
            auto_renew_plan_price_id=setting.plan_price_id if setting else None,
            next_renewal_at=setting.next_renewal_at if setting else None,
            last_renewal_failure=setting.last_failure_code if setting else None,
            top_ups=[self._top_up_response(value) for value in top_ups],
            transactions=[
                WalletTransactionResponse(
                    id=transaction.id,
                    transaction_type=transaction.transaction_type,
                    amount_minor=amount,
                    currency=transaction.currency,
                    description=transaction.description,
                    created_at=transaction.created_at,
                )
                for transaction, amount in transactions
            ],
        )

    async def create_top_up(
        self,
        *,
        user_id: UUID,
        amount_minor: int,
        currency: str,
        payment_method: int,
        idempotency_key: str,
        client: BillingClientContext,
    ) -> WalletTopUpResponse:
        await self._rate_limiter.enforce(TOP_UP_RATE, str(user_id))
        self._validate_top_up(amount_minor, currency, payment_method)
        scoped_key = f"wallet:top-up:{user_id}:{idempotency_key}"
        async with self._session.begin():
            await self._repository.serialize(scoped_key)
            existing = await self._repository.top_up_by_key(user_id, idempotency_key)
            if existing is not None:
                if (
                    existing.amount_minor != amount_minor
                    or existing.currency != currency
                    or existing.payment_method != payment_method
                ):
                    raise ApplicationError(
                        "wallet_top_up_idempotency_conflict",
                        "This idempotency key was used for another top-up.",
                        409,
                    )
                return self._top_up_response(existing)
            top_up = WalletTopUp(
                user_id=user_id,
                provider="platega",
                payment_method=payment_method,
                status="creating",
                amount_minor=amount_minor,
                currency=currency,
                idempotency_key=idempotency_key,
            )
            self._session.add(top_up)
            await self._session.flush()

        try:
            checkout = await self._platega.create_checkout(
                top_up_id=top_up.id,
                user_id=user_id,
                amount_minor=amount_minor,
                currency=currency,
                payment_method=payment_method,
                client_ip=client.ip_address,
            )
        except Exception:
            async with self._session.begin():
                failed = await self._repository.top_up(top_up.id, user_id)
                if failed is not None and failed.status == "creating":
                    failed.status = "failed"
            raise

        async with self._session.begin():
            saved = await self._repository.top_up(top_up.id, user_id)
            if saved is None:
                raise RuntimeError("wallet top-up disappeared during provider creation")
            saved.provider_transaction_id = checkout.transaction_id
            saved.checkout_url = checkout.redirect_url
            saved.expires_at = checkout.expires_at
            saved.status = "pending"
            self._session.add(
                AuditLog(
                    actor_user_id=user_id,
                    actor_type="user",
                    action="wallet.top_up_created",
                    entity_type="wallet_top_up",
                    entity_id=saved.id,
                    after_state={
                        "amount_minor": amount_minor,
                        "currency": currency,
                        "payment_method": payment_method,
                        "provider_transaction_id": str(checkout.transaction_id),
                    },
                    ip_address=client.ip_address,
                    user_agent=client.user_agent,
                    request_id=client.request_id,
                )
            )
            await self._session.flush()
            return self._top_up_response(saved)

    async def top_up(self, user_id: UUID, top_up_id: UUID) -> WalletTopUpResponse:
        value = await self._repository.top_up(top_up_id, user_id)
        if value is None:
            raise ApplicationError("wallet_top_up_not_found", "Wallet top-up not found.", 404)
        return self._top_up_response(value)

    async def process_platega_callback(
        self,
        *,
        merchant_id: str,
        secret: str,
        payload: PlategaCallbackPayload,
    ) -> None:
        provider = self._settings.platega
        if not (
            hmac.compare_digest(merchant_id, provider.merchant_id.get_secret_value())
            and hmac.compare_digest(secret, provider.secret.get_secret_value())
        ):
            raise ApplicationError("platega_callback_forbidden", "Invalid callback secret.", 403)
        async with self._session.begin():
            await self._repository.serialize(f"platega:callback:{payload.id}")
            top_up = await self._repository.top_up_by_provider_id(payload.id, for_update=True)
            if top_up is None:
                raise ApplicationError("wallet_top_up_not_found", "Wallet top-up not found.", 404)
            amount_minor = self._provider_amount_minor(payload.amount)
            if (
                top_up.amount_minor != amount_minor
                or top_up.currency != payload.currency
                or top_up.payment_method != payload.payment_method
            ):
                raise ApplicationError(
                    "platega_callback_mismatch", "Callback payment details do not match.", 409
                )
            if payload.payload and not hmac.compare_digest(payload.payload, str(top_up.id)):
                raise ApplicationError(
                    "platega_callback_payload_mismatch", "Callback payload does not match.", 409
                )
            if payload.status == "CONFIRMED":
                await self._confirm_top_up(top_up)
            elif payload.status in {"CANCELED", "EXPIRED", "FAILED"}:
                if top_up.status not in {"confirmed", "chargebacked"}:
                    top_up.status = payload.status.casefold().replace("canceled", "cancelled")
                    if top_up.status == "cancelled":
                        top_up.cancelled_at = datetime.now(UTC)
            elif payload.status == "CHARGEBACKED":
                await self._chargeback_top_up(top_up)
            else:
                raise ApplicationError(
                    "platega_callback_status_unknown", "Unknown callback status.", 422
                )

    async def purchase(
        self,
        *,
        user_id: UUID,
        plan_price_id: UUID,
        auto_renew: bool,
        idempotency_key: str,
        client: BillingClientContext | None,
        renewal: bool = False,
    ) -> WalletPurchaseResponse:
        if not renewal:
            await self._rate_limiter.enforce(PURCHASE_RATE, str(user_id))
        now = datetime.now(UTC)
        transaction_key = (
            idempotency_key if renewal else f"wallet:purchase:{user_id}:{idempotency_key}"
        )
        async with self._session.begin():
            await self._repository.serialize(f"ledger:{user_id}:{self._settings.currency}")
            existing = await self._repository.transaction_by_key(transaction_key)
            if existing is not None:
                return await self._existing_purchase_response(existing, user_id)
            price_row = await self._repository.active_price(plan_price_id, now)
            if price_row is None:
                raise ApplicationError("plan_price_not_found", "Plan price not found.", 404)
            price, plan_version, plan = price_row
            if price.currency != self._settings.currency:
                raise ApplicationError(
                    "wallet_currency_mismatch", "Plan currency does not match the wallet.", 409
                )
            balance = await wallet_balance(self._session, user_id, price.currency)
            if balance < price.amount_minor:
                raise ApplicationError(
                    "wallet_insufficient_funds",
                    "Wallet balance is insufficient for this purchase.",
                    409,
                )
            subscription = await self._repository.live_subscription(user_id, for_update=True)
            if subscription is not None and subscription.plan_version_id != plan_version.id:
                raise ApplicationError(
                    "wallet_plan_change_requires_confirmation",
                    "Changing an active plan requires a separate plan-change flow.",
                    409,
                )
            wallet = await ledger_account(
                self._session,
                key=f"user:{user_id}",
                currency=price.currency,
                account_type="user_wallet",
                owner_user_id=user_id,
            )
            revenue = await ledger_account(
                self._session,
                key="revenue",
                currency=price.currency,
                account_type="revenue",
                owner_user_id=None,
            )
            transaction = await post_transaction(
                self._session,
                user_id=user_id,
                transaction_type="subscription_debit",
                currency=price.currency,
                idempotency_key=transaction_key,
                description=f"{plan.name}, {price.term_months} month(s)",
                entries=[(wallet, -price.amount_minor), (revenue, price.amount_minor)],
                metadata={
                    "plan_price_id": str(price.id),
                    "plan_version_id": str(plan_version.id),
                    "renewal": renewal,
                },
            )
            starts_at = (
                max(subscription.current_period_ends_at or now, now) if subscription else now
            )
            ends_at = starts_at + timedelta(days=price.duration_days)
            if subscription is None:
                subscription = Subscription(
                    owner_user_id=user_id,
                    plan_version_id=plan_version.id,
                    status="active",
                    source="purchase",
                    starts_at=starts_at,
                    current_period_ends_at=ends_at,
                    grace_ends_at=None,
                    cancel_at_period_end=not auto_renew,
                    cancelled_at=None,
                    suspended_at=None,
                    suspension_reason=None,
                    version=1,
                )
                self._session.add(subscription)
                await self._session.flush()
            else:
                subscription.status = "active"
                subscription.current_period_ends_at = ends_at
                subscription.grace_ends_at = None
                subscription.cancel_at_period_end = not auto_renew
                subscription.version += 1
            period = SubscriptionPeriod(
                subscription_id=subscription.id,
                source_type="renewal" if renewal else "payment",
                source_id=transaction.id,
                starts_at=starts_at,
                ends_at=ends_at,
                plan_snapshot=self._plan_snapshot(plan, plan_version),
                price_minor=price.amount_minor,
                currency=price.currency,
            )
            self._session.add(period)
            setting = await self._repository.billing_setting_for_update(user_id)
            if setting is None:
                setting = SubscriptionBillingSetting(
                    subscription_id=subscription.id,
                    user_id=user_id,
                    plan_price_id=price.id,
                    auto_renew_enabled=auto_renew,
                    next_renewal_at=ends_at,
                )
                self._session.add(setting)
            else:
                setting.subscription_id = subscription.id
                setting.plan_price_id = price.id
                setting.auto_renew_enabled = auto_renew
                setting.next_renewal_at = ends_at
                setting.last_attempt_at = now if renewal else setting.last_attempt_at
                setting.last_failure_code = None
            await self._enqueue_vpn(
                user_id=user_id,
                subscription=subscription,
                plan=plan_version,
                source_id=transaction.id,
                now=now,
            )
            self._session.add(
                AuditLog(
                    actor_user_id=user_id,
                    actor_type="system" if renewal else "user",
                    action=(
                        "subscription.wallet_renewed"
                        if renewal
                        else "subscription.wallet_purchased"
                    ),
                    entity_type="subscription",
                    entity_id=subscription.id,
                    after_state={
                        "transaction_id": str(transaction.id),
                        "plan_price_id": str(price.id),
                        "amount_minor": price.amount_minor,
                        "auto_renew": auto_renew,
                        "ends_at": ends_at.isoformat(),
                    },
                    ip_address=client.ip_address if client else None,
                    user_agent=client.user_agent if client else None,
                    request_id=client.request_id if client else None,
                )
            )
            await self._session.flush()
            return WalletPurchaseResponse(
                transaction_id=transaction.id,
                subscription_id=subscription.id,
                balance_minor=balance - price.amount_minor,
                currency=price.currency,
                current_period_ends_at=ends_at,
                auto_renew_enabled=auto_renew,
            )

    async def update_auto_renew(self, user_id: UUID, enabled: bool) -> WalletResponse:
        async with self._session.begin():
            setting = await self._repository.billing_setting_for_update(user_id)
            subscription = await self._repository.live_subscription(user_id, for_update=True)
            if setting is None or subscription is None:
                raise ApplicationError(
                    "billing_subscription_not_found", "No paid subscription is configured.", 404
                )
            setting.auto_renew_enabled = enabled
            setting.next_renewal_at = subscription.current_period_ends_at
            setting.last_failure_code = None
            subscription.cancel_at_period_end = not enabled
            subscription.version += 1
        return await self.wallet(user_id)

    async def due_renewals(
        self, now: datetime, limit: int = 25
    ) -> list[tuple[UUID, UUID, datetime]]:
        settings = await self._repository.due_billing_settings(now, limit)
        return [
            (value.user_id, value.plan_price_id, value.next_renewal_at)
            for value in settings
            if value.next_renewal_at is not None
        ]

    async def record_renewal_failure(self, user_id: UUID, code: str) -> None:
        async with self._session.begin():
            setting = await self._repository.billing_setting_for_update(user_id)
            if setting is None:
                return
            setting.last_attempt_at = datetime.now(UTC)
            setting.last_failure_code = code[:80]
            setting.next_renewal_at = datetime.now(UTC) + timedelta(
                seconds=self._settings.renewal_retry_seconds
            )

    async def _confirm_top_up(self, top_up: WalletTopUp) -> None:
        if top_up.status == "confirmed":
            return
        if top_up.status == "chargebacked":
            raise ApplicationError(
                "wallet_top_up_already_chargebacked", "Top-up was already charged back.", 409
            )
        wallet = await ledger_account(
            self._session,
            key=f"user:{top_up.user_id}",
            currency=top_up.currency,
            account_type="user_wallet",
            owner_user_id=top_up.user_id,
        )
        clearing = await ledger_account(
            self._session,
            key="cash_clearing",
            currency=top_up.currency,
            account_type="cash_clearing",
            owner_user_id=None,
        )
        transaction = await post_transaction(
            self._session,
            user_id=top_up.user_id,
            transaction_type="payment_credit",
            currency=top_up.currency,
            idempotency_key=f"platega-top-up:{top_up.id}",
            description="Пополнение баланса через Platega",
            entries=[(wallet, top_up.amount_minor), (clearing, -top_up.amount_minor)],
            metadata={
                "wallet_top_up_id": str(top_up.id),
                "provider_transaction_id": str(top_up.provider_transaction_id),
                "payment_method": top_up.payment_method,
            },
        )
        top_up.status = "confirmed"
        top_up.confirmed_at = transaction.posted_at
        top_up.cancelled_at = None
        self._session.add(
            AuditLog(
                actor_user_id=None,
                actor_type="provider",
                action="wallet.top_up_confirmed",
                entity_type="wallet_top_up",
                entity_id=top_up.id,
                after_state={
                    "transaction_id": str(transaction.id),
                    "amount_minor": top_up.amount_minor,
                    "currency": top_up.currency,
                },
            )
        )

    async def _chargeback_top_up(self, top_up: WalletTopUp) -> None:
        if top_up.status == "chargebacked":
            return
        credit = await self._repository.transaction_by_key(f"platega-top-up:{top_up.id}")
        if credit is None or credit.status != "posted":
            raise ApplicationError(
                "wallet_top_up_not_confirmed", "Cannot charge back an unconfirmed top-up.", 409
            )
        entries = list(
            (
                await self._session.execute(
                    select(TransactionEntry).where(TransactionEntry.transaction_id == credit.id)
                )
            ).scalars()
        )
        accounts_and_amounts = []
        for entry in entries:
            account = await self._session.get(LedgerAccount, entry.ledger_account_id)
            if account is None:
                raise RuntimeError("chargeback references missing ledger account")
            accounts_and_amounts.append((account, -entry.amount_minor))
        await post_transaction(
            self._session,
            user_id=top_up.user_id,
            transaction_type="reversal",
            currency=top_up.currency,
            idempotency_key=f"platega-chargeback:{top_up.id}",
            description="Возврат пополнения Platega",
            entries=accounts_and_amounts,
            metadata={"wallet_top_up_id": str(top_up.id)},
            reverses_transaction_id=credit.id,
        )
        top_up.status = "chargebacked"
        top_up.cancelled_at = datetime.now(UTC)
        top_up.confirmed_at = None

    async def _existing_purchase_response(
        self, transaction: Transaction, user_id: UUID
    ) -> WalletPurchaseResponse:
        subscription = await self._repository.live_subscription(user_id)
        setting = await self._repository.billing_setting(user_id)
        if subscription is None or subscription.current_period_ends_at is None:
            raise RuntimeError("wallet purchase transaction has no subscription")
        return WalletPurchaseResponse(
            transaction_id=transaction.id,
            subscription_id=subscription.id,
            balance_minor=await wallet_balance(self._session, user_id, transaction.currency),
            currency=transaction.currency,
            current_period_ends_at=subscription.current_period_ends_at,
            auto_renew_enabled=bool(setting and setting.auto_renew_enabled),
        )

    async def _enqueue_vpn(
        self,
        *,
        user_id: UUID,
        subscription: Subscription,
        plan: PlanVersion,
        source_id: UUID,
        now: datetime,
    ) -> None:
        if subscription.current_period_ends_at is None:
            raise RuntimeError("paid subscription has no expiration")
        account = await self._repository.vpn_account(user_id, for_update=True)
        if account is None:
            account = VpnAccount(
                user_id=user_id,
                subscription_id=subscription.id,
                username=f"hz_{user_id.hex[:24]}",
                desired_status=DesiredVpnStatus.ACTIVE.value,
                desired_expires_at=subscription.current_period_ends_at,
            )
            self._session.add(account)
            await self._session.flush()
        else:
            account.subscription_id = subscription.id
            account.desired_status = DesiredVpnStatus.ACTIVE.value
            account.desired_expires_at = subscription.current_period_ends_at
        key = f"vpn:billing:{account.id}:{source_id}"
        if await self._repository.vpn_command_by_key(key) is not None:
            return
        if account.remnawave_user_id is None:
            email, telegram_id = await self._repository.identity_contacts(user_id)
            command_type = CommandType.ENSURE_ACCOUNT.value
            payload: dict[str, Any] = {
                "username": account.username,
                "expire_at": subscription.current_period_ends_at.isoformat(),
                "traffic_limit_bytes": plan.traffic_limit_bytes or 0,
                "device_limit": plan.device_limit,
                "email": email,
                "telegram_id": telegram_id,
                "internal_squad_ids": list(plan.remnawave_policy.get("internal_squad_ids", [])),
            }
        else:
            command_type = CommandType.EXTEND.value
            payload = {"expires_at": subscription.current_period_ends_at.isoformat()}
        self._session.add(
            VpnSyncCommand(
                vpn_account_id=account.id,
                command_type=command_type,
                idempotency_key=key,
                payload=payload,
                status=CommandStatus.PENDING.value,
                attempt_count=0,
                next_attempt_at=now,
            )
        )

    def _validate_top_up(self, amount_minor: int, currency: str, payment_method: int) -> None:
        if not self._settings.platega.enabled:
            raise ApplicationError(
                "platega_not_configured", "Real payments are not configured.", 503
            )
        if currency != self._settings.currency:
            raise ApplicationError("wallet_currency_unsupported", "Currency is unsupported.", 422)
        if not (
            self._settings.minimum_top_up_minor
            <= amount_minor
            <= self._settings.maximum_top_up_minor
        ):
            raise ApplicationError(
                "wallet_top_up_out_of_range", "Wallet top-up amount is outside allowed limits.", 422
            )
        if payment_method not in self._settings.platega.allowed_payment_methods:
            raise ApplicationError(
                "platega_payment_method_unsupported", "Payment method is unavailable.", 422
            )

    @staticmethod
    def _provider_amount_minor(amount: Decimal) -> int:
        minor = amount * Decimal(100)
        if minor != minor.to_integral_value():
            raise ApplicationError(
                "platega_callback_amount_invalid", "Callback amount has invalid precision.", 422
            )
        return int(minor)

    @staticmethod
    def _plan_snapshot(plan: Plan, version: PlanVersion) -> dict[str, Any]:
        return {
            "plan_id": str(plan.id),
            "plan_slug": plan.slug,
            "plan_name": plan.name,
            "plan_version_id": str(version.id),
            "device_limit": version.device_limit,
            "family_member_limit": version.family_member_limit,
            "traffic_limit_bytes": version.traffic_limit_bytes,
        }

    @staticmethod
    def _top_up_response(value: WalletTopUp) -> WalletTopUpResponse:
        return WalletTopUpResponse(
            id=value.id,
            provider=value.provider,
            provider_transaction_id=value.provider_transaction_id,
            payment_method=value.payment_method,
            status=value.status,
            amount_minor=value.amount_minor,
            currency=value.currency,
            checkout_url=value.checkout_url,
            expires_at=value.expires_at,
            confirmed_at=value.confirmed_at,
            cancelled_at=value.cancelled_at,
            created_at=value.created_at,
        )
