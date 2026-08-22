from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import TelegramAccount, User, UserEmail
from app.modules.payments.enums import PaymentStatus
from app.modules.payments.models import Payment, PlanPrice
from app.modules.promotions.models import PromoCode, PromoCodePlanVersion, PromoRedemption
from app.modules.referrals.models import Plan
from app.modules.vpn.models import PlanVersion, Subscription, VpnAccount, VpnSyncCommand


class PromotionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def serialize_key(self, key: str) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )

    async def user(self, user_id: UUID, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(User | None, await self.session.scalar(statement))

    async def code(self, value: str, *, for_update: bool = False) -> PromoCode | None:
        statement = select(PromoCode).where(PromoCode.code == value)
        if for_update:
            statement = statement.with_for_update()
        return cast(PromoCode | None, await self.session.scalar(statement))

    async def code_by_id(self, promo_id: UUID, *, for_update: bool = False) -> PromoCode | None:
        statement = select(PromoCode).where(PromoCode.id == promo_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(PromoCode | None, await self.session.scalar(statement))

    async def plan_version_ids(self, promo_id: UUID) -> list[UUID]:
        return list(
            (
                await self.session.scalars(
                    select(PromoCodePlanVersion.plan_version_id).where(
                        PromoCodePlanVersion.promo_code_id == promo_id
                    )
                )
            ).all()
        )

    async def plan_versions_exist(self, ids: list[UUID]) -> bool:
        if not ids:
            return True
        count = await self.session.scalar(
            select(func.count()).select_from(PlanVersion).where(PlanVersion.id.in_(ids))
        )
        return int(count or 0) == len(ids)

    async def active_plan_price(self, price_id: UUID, now: datetime) -> PlanPrice | None:
        return cast(
            PlanPrice | None,
            await self.session.scalar(
                select(PlanPrice).where(
                    PlanPrice.id == price_id,
                    PlanPrice.is_active.is_(True),
                    PlanPrice.valid_from <= now,
                    or_(PlanPrice.valid_until.is_(None), PlanPrice.valid_until > now),
                )
            ),
        )

    async def active_plan_version(self, version_id: UUID, now: datetime) -> PlanVersion | None:
        return cast(
            PlanVersion | None,
            await self.session.scalar(
                select(PlanVersion).where(
                    PlanVersion.id == version_id,
                    PlanVersion.valid_from <= now,
                    or_(PlanVersion.valid_until.is_(None), PlanVersion.valid_until > now),
                )
            ),
        )

    async def active_default_plan_version(self, slug: str, now: datetime) -> PlanVersion | None:
        return cast(
            PlanVersion | None,
            await self.session.scalar(
                select(PlanVersion)
                .join(Plan, Plan.id == PlanVersion.plan_id)
                .where(
                    Plan.slug == slug,
                    Plan.is_active.is_(True),
                    PlanVersion.valid_from <= now,
                    or_(PlanVersion.valid_until.is_(None), PlanVersion.valid_until > now),
                )
                .order_by(PlanVersion.version.desc())
                .limit(1)
            ),
        )

    async def active_usage_count(self, promo_id: UUID, now: datetime) -> int:
        return await self._redemption_count(promo_id=promo_id, user_id=None, now=now)

    async def active_user_usage_count(self, promo_id: UUID, user_id: UUID, now: datetime) -> int:
        return await self._redemption_count(promo_id=promo_id, user_id=user_id, now=now)

    async def _redemption_count(
        self, *, promo_id: UUID, user_id: UUID | None, now: datetime
    ) -> int:
        active_payment = or_(
            PromoRedemption.payment_id.is_(None),
            Payment.status.in_(
                [
                    PaymentStatus.APPROVED.value,
                    PaymentStatus.ACTIVATION_PENDING.value,
                    PaymentStatus.ACTIVATED.value,
                ]
            ),
            (
                Payment.status.not_in([PaymentStatus.REJECTED.value, PaymentStatus.CANCELLED.value])
                & (Payment.expires_at > now)
            ),
        )
        statement = (
            select(func.count())
            .select_from(PromoRedemption)
            .outerjoin(Payment, Payment.id == PromoRedemption.payment_id)
            .where(
                PromoRedemption.promo_code_id == promo_id,
                PromoRedemption.revoked_at.is_(None),
                active_payment,
            )
        )
        if user_id is not None:
            statement = statement.where(PromoRedemption.user_id == user_id)
        return int(await self.session.scalar(statement) or 0)

    async def redemption_for_payment(self, payment_id: UUID) -> PromoRedemption | None:
        return cast(
            PromoRedemption | None,
            await self.session.scalar(
                select(PromoRedemption).where(
                    PromoRedemption.payment_id == payment_id,
                    PromoRedemption.revoked_at.is_(None),
                )
            ),
        )

    async def promo_details_for_payment(
        self, payment_id: UUID
    ) -> tuple[PromoRedemption, PromoCode] | None:
        row = (
            await self.session.execute(
                select(PromoRedemption, PromoCode)
                .join(PromoCode, PromoCode.id == PromoRedemption.promo_code_id)
                .where(PromoRedemption.payment_id == payment_id)
                .order_by(PromoRedemption.redeemed_at.desc())
                .limit(1)
            )
        ).one_or_none()
        return (row[0], row[1]) if row else None

    async def redemptions_for_user(
        self, user_id: UUID, *, limit: int = 100
    ) -> list[tuple[PromoRedemption, PromoCode]]:
        rows = await self.session.execute(
            select(PromoRedemption, PromoCode)
            .join(PromoCode, PromoCode.id == PromoRedemption.promo_code_id)
            .where(PromoRedemption.user_id == user_id)
            .order_by(PromoRedemption.redeemed_at.desc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in rows.all()]

    async def list_codes(self, *, limit: int = 100) -> list[PromoCode]:
        return list(
            (
                await self.session.scalars(
                    select(PromoCode).order_by(PromoCode.created_at.desc()).limit(limit)
                )
            ).all()
        )

    async def live_subscription_for_update(self, user_id: UUID) -> Subscription | None:
        return cast(
            Subscription | None,
            await self.session.scalar(
                select(Subscription)
                .where(
                    Subscription.owner_user_id == user_id,
                    Subscription.status.in_(["pending", "active", "grace_period", "suspended"]),
                )
                .with_for_update()
            ),
        )

    async def plan_version(self, plan_version_id: UUID) -> PlanVersion:
        plan = await self.session.scalar(
            select(PlanVersion).where(PlanVersion.id == plan_version_id)
        )
        if plan is None:
            raise RuntimeError("subscription references no plan version")
        return plan

    async def vpn_account_for_update(self, user_id: UUID) -> VpnAccount | None:
        return cast(
            VpnAccount | None,
            await self.session.scalar(
                select(VpnAccount)
                .where(VpnAccount.user_id == user_id)
                .order_by(VpnAccount.created_at.desc())
                .limit(1)
                .with_for_update()
            ),
        )

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
