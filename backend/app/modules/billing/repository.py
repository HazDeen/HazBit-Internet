from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import TelegramAccount, UserEmail
from app.modules.billing.models import SubscriptionBillingSetting, WalletTopUp
from app.modules.payments.models import (
    LedgerAccount,
    PlanPrice,
    Transaction,
    TransactionEntry,
)
from app.modules.referrals.models import Plan
from app.modules.vpn.models import PlanVersion, Subscription, VpnAccount, VpnSyncCommand


class BillingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def serialize(self, key: str) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )

    async def top_up_by_key(self, user_id: UUID, key: str) -> WalletTopUp | None:
        return cast(
            WalletTopUp | None,
            await self.session.scalar(
                select(WalletTopUp).where(
                    WalletTopUp.user_id == user_id, WalletTopUp.idempotency_key == key
                )
            ),
        )

    async def top_up(self, top_up_id: UUID, user_id: UUID | None = None) -> WalletTopUp | None:
        query = select(WalletTopUp).where(WalletTopUp.id == top_up_id)
        if user_id is not None:
            query = query.where(WalletTopUp.user_id == user_id)
        return cast(WalletTopUp | None, await self.session.scalar(query))

    async def top_up_by_provider_id(
        self, provider_transaction_id: UUID, *, for_update: bool = False
    ) -> WalletTopUp | None:
        query = select(WalletTopUp).where(
            WalletTopUp.provider == "platega",
            WalletTopUp.provider_transaction_id == provider_transaction_id,
        )
        if for_update:
            query = query.with_for_update()
        return cast(WalletTopUp | None, await self.session.scalar(query))

    async def user_top_ups(self, user_id: UUID, limit: int = 20) -> list[WalletTopUp]:
        return list(
            (
                await self.session.scalars(
                    select(WalletTopUp)
                    .where(WalletTopUp.user_id == user_id)
                    .order_by(WalletTopUp.created_at.desc())
                    .limit(limit)
                )
            ).all()
        )

    async def wallet_transactions(
        self, user_id: UUID, currency: str, limit: int = 30
    ) -> list[tuple[Transaction, int]]:
        rows = await self.session.execute(
            select(Transaction, TransactionEntry.amount_minor)
            .join(TransactionEntry, TransactionEntry.transaction_id == Transaction.id)
            .join(LedgerAccount, LedgerAccount.id == TransactionEntry.ledger_account_id)
            .where(
                Transaction.user_id == user_id,
                Transaction.status == "posted",
                LedgerAccount.owner_user_id == user_id,
                LedgerAccount.account_type == "user_wallet",
                LedgerAccount.currency == currency,
            )
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        return [(row[0], int(row[1])) for row in rows]

    async def transaction_by_key(self, key: str) -> Transaction | None:
        return cast(
            Transaction | None,
            await self.session.scalar(
                select(Transaction).where(Transaction.idempotency_key == key)
            ),
        )

    async def active_price(
        self, price_id: UUID, now: datetime
    ) -> tuple[PlanPrice, PlanVersion, Plan] | None:
        row = (
            await self.session.execute(
                select(PlanPrice, PlanVersion, Plan)
                .join(PlanVersion, PlanVersion.id == PlanPrice.plan_version_id)
                .join(Plan, Plan.id == PlanVersion.plan_id)
                .where(
                    PlanPrice.id == price_id,
                    PlanPrice.is_active.is_(True),
                    PlanPrice.valid_from <= now,
                    or_(PlanPrice.valid_until.is_(None), PlanPrice.valid_until > now),
                    PlanVersion.valid_from <= now,
                    or_(PlanVersion.valid_until.is_(None), PlanVersion.valid_until > now),
                    Plan.is_active.is_(True),
                )
            )
        ).one_or_none()
        return (row[0], row[1], row[2]) if row else None

    async def live_subscription(
        self, user_id: UUID, *, for_update: bool = False
    ) -> Subscription | None:
        query = select(Subscription).where(
            Subscription.owner_user_id == user_id,
            Subscription.status.in_(["pending", "active", "grace_period", "suspended"]),
        )
        if for_update:
            query = query.with_for_update()
        return cast(Subscription | None, await self.session.scalar(query))

    async def billing_setting(self, user_id: UUID) -> SubscriptionBillingSetting | None:
        return cast(
            SubscriptionBillingSetting | None,
            await self.session.scalar(
                select(SubscriptionBillingSetting).where(
                    SubscriptionBillingSetting.user_id == user_id
                )
            ),
        )

    async def billing_setting_for_update(self, user_id: UUID) -> SubscriptionBillingSetting | None:
        return cast(
            SubscriptionBillingSetting | None,
            await self.session.scalar(
                select(SubscriptionBillingSetting)
                .where(SubscriptionBillingSetting.user_id == user_id)
                .with_for_update()
            ),
        )

    async def due_billing_settings(
        self, now: datetime, limit: int
    ) -> list[SubscriptionBillingSetting]:
        return list(
            (
                await self.session.scalars(
                    select(SubscriptionBillingSetting)
                    .where(
                        SubscriptionBillingSetting.auto_renew_enabled.is_(True),
                        SubscriptionBillingSetting.next_renewal_at.is_not(None),
                        SubscriptionBillingSetting.next_renewal_at <= now,
                    )
                    .order_by(SubscriptionBillingSetting.next_renewal_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )

    async def vpn_account(self, user_id: UUID, *, for_update: bool = False) -> VpnAccount | None:
        query = select(VpnAccount).where(VpnAccount.user_id == user_id)
        if for_update:
            query = query.with_for_update()
        return cast(VpnAccount | None, await self.session.scalar(query))

    async def vpn_command_by_key(self, key: str) -> VpnSyncCommand | None:
        return cast(
            VpnSyncCommand | None,
            await self.session.scalar(
                select(VpnSyncCommand).where(VpnSyncCommand.idempotency_key == key)
            ),
        )

    async def identity_contacts(self, user_id: UUID) -> tuple[str | None, int | None]:
        email = await self.session.scalar(
            select(UserEmail.email).where(
                UserEmail.user_id == user_id, UserEmail.is_primary.is_(True)
            )
        )
        telegram_id = await self.session.scalar(
            select(TelegramAccount.telegram_user_id).where(TelegramAccount.user_id == user_id)
        )
        return (str(email) if email is not None else None, telegram_id)
