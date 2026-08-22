from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import RiskSignal, User
from app.modules.payments.enums import PaymentStatus
from app.modules.payments.models import Payment
from app.modules.referrals.enums import ReferralStatus, RewardSide
from app.modules.referrals.models import (
    Plan,
    Referral,
    ReferralCode,
    ReferralReward,
    TrialGrant,
)
from app.modules.vpn.models import PlanVersion, Subscription, VpnAccount, VpnSyncCommand


@dataclass(frozen=True, slots=True)
class ReferralHistory:
    has_referral: bool
    has_trial: bool
    has_subscription: bool
    has_approved_payment: bool


class ReferralRepository:
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

    async def active_code_for_owner(self, owner_id: UUID) -> ReferralCode | None:
        return cast(
            ReferralCode | None,
            await self.session.scalar(
                select(ReferralCode).where(
                    ReferralCode.owner_user_id == owner_id,
                    ReferralCode.status == "active",
                )
            ),
        )

    async def code_for_claim(self, code: str) -> ReferralCode | None:
        return cast(
            ReferralCode | None,
            await self.session.scalar(
                select(ReferralCode)
                .where(ReferralCode.code == code, ReferralCode.status == "active")
                .with_for_update()
            ),
        )

    async def code_by_value(self, code: str) -> ReferralCode | None:
        return cast(
            ReferralCode | None,
            await self.session.scalar(select(ReferralCode).where(ReferralCode.code == code)),
        )

    async def referral_for_referred(self, user_id: UUID) -> Referral | None:
        return cast(
            Referral | None,
            await self.session.scalar(select(Referral).where(Referral.referred_user_id == user_id)),
        )

    async def referral_for_update(self, referral_id: UUID) -> Referral | None:
        return cast(
            Referral | None,
            await self.session.scalar(
                select(Referral).where(Referral.id == referral_id).with_for_update()
            ),
        )

    async def non_rejected_usage_count(self, code_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Referral)
                .where(
                    Referral.referral_code_id == code_id,
                    Referral.status != ReferralStatus.REJECTED.value,
                )
            )
            or 0
        )

    async def referred_history(self, user_id: UUID) -> ReferralHistory:
        has_referral = await self.session.scalar(
            select(Referral.id).where(Referral.referred_user_id == user_id).limit(1)
        )
        has_trial = await self.session.scalar(
            select(TrialGrant.id).where(TrialGrant.user_id == user_id).limit(1)
        )
        has_subscription = await self.session.scalar(
            select(Subscription.id).where(Subscription.owner_user_id == user_id).limit(1)
        )
        has_payment = await self.session.scalar(
            select(Payment.id)
            .where(
                Payment.user_id == user_id,
                Payment.status.in_(
                    [
                        PaymentStatus.APPROVED.value,
                        PaymentStatus.ACTIVATION_PENDING.value,
                        PaymentStatus.ACTIVATED.value,
                    ]
                ),
            )
            .limit(1)
        )
        return ReferralHistory(
            has_referral=has_referral is not None,
            has_trial=has_trial is not None,
            has_subscription=has_subscription is not None,
            has_approved_payment=has_payment is not None,
        )

    async def signal_user_count(self, signal_type: str, signal_hash: bytes, since: datetime) -> int:
        return int(
            await self.session.scalar(
                select(func.count(func.distinct(RiskSignal.user_id))).where(
                    RiskSignal.signal_type == signal_type,
                    RiskSignal.signal_hash == signal_hash,
                    RiskSignal.created_at >= since,
                    RiskSignal.user_id.is_not(None),
                )
            )
            or 0
        )

    async def signal_seen_for_user(
        self, signal_type: str, signal_hash: bytes, user_id: UUID, since: datetime
    ) -> bool:
        return (
            await self.session.scalar(
                select(RiskSignal.id)
                .where(
                    RiskSignal.signal_type == signal_type,
                    RiskSignal.signal_hash == signal_hash,
                    RiskSignal.user_id == user_id,
                    RiskSignal.created_at >= since,
                )
                .limit(1)
            )
            is not None
        )

    async def rewards(self, referral_id: UUID) -> list[ReferralReward]:
        return list(
            (
                await self.session.scalars(
                    select(ReferralReward)
                    .where(ReferralReward.referral_id == referral_id)
                    .order_by(ReferralReward.reward_side)
                )
            ).all()
        )

    async def claim_qualified(self, limit: int) -> list[Referral]:
        return list(
            (
                await self.session.scalars(
                    select(Referral)
                    .where(Referral.status == ReferralStatus.QUALIFIED.value)
                    .order_by(Referral.qualified_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )

    async def active_default_plan_version(
        self, slug: str, now: datetime
    ) -> tuple[Plan, PlanVersion] | None:
        row = (
            await self.session.execute(
                select(Plan, PlanVersion)
                .join(PlanVersion, PlanVersion.plan_id == Plan.id)
                .where(
                    Plan.slug == slug,
                    Plan.is_active.is_(True),
                    PlanVersion.valid_from <= now,
                    or_(PlanVersion.valid_until.is_(None), PlanVersion.valid_until > now),
                )
                .order_by(PlanVersion.version.desc())
                .limit(1)
            )
        ).one_or_none()
        return (row[0], row[1]) if row else None

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

    async def trial_for_user(self, user_id: UUID) -> TrialGrant | None:
        return cast(
            TrialGrant | None,
            await self.session.scalar(select(TrialGrant).where(TrialGrant.user_id == user_id)),
        )

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
        from app.modules.auth.models import TelegramAccount, UserEmail

        email = await self.session.scalar(
            select(UserEmail.email).where(
                UserEmail.user_id == user_id, UserEmail.is_primary.is_(True)
            )
        )
        telegram_id = await self.session.scalar(
            select(TelegramAccount.telegram_user_id).where(TelegramAccount.user_id == user_id)
        )
        return (str(email) if email is not None else None, telegram_id)

    async def review_queue(self, limit: int) -> list[tuple[Referral, ReferralCode]]:
        rows = await self.session.execute(
            select(Referral, ReferralCode)
            .join(ReferralCode, ReferralCode.id == Referral.referral_code_id)
            .where(Referral.status == ReferralStatus.ATTRIBUTED.value)
            .order_by(Referral.attributed_at)
            .limit(limit)
        )
        return [(row[0], row[1]) for row in rows.all()]

    async def latest_referral_risk(self, referral_id: UUID) -> RiskSignal | None:
        return cast(
            RiskSignal | None,
            await self.session.scalar(
                select(RiskSignal)
                .where(
                    RiskSignal.signal_type == "referral",
                    RiskSignal.context["referral_id"].astext == str(referral_id),
                )
                .order_by(RiskSignal.created_at.desc())
                .limit(1)
            ),
        )

    async def owner_counts(self, owner_id: UUID) -> dict[str, int]:
        rows = await self.session.execute(
            select(Referral.status, func.count())
            .where(Referral.referrer_user_id == owner_id)
            .group_by(Referral.status)
        )
        return {str(status): int(count) for status, count in rows.all()}

    async def owner_reward_days(self, owner_id: UUID) -> tuple[int, int]:
        rows = await self.session.execute(
            select(ReferralReward.status, func.coalesce(func.sum(ReferralReward.days), 0))
            .where(
                ReferralReward.beneficiary_user_id == owner_id,
                ReferralReward.reward_side == RewardSide.REFERRER.value,
            )
            .group_by(ReferralReward.status)
        )
        values = {str(status): int(days) for status, days in rows.all()}
        return values.get("pending", 0), values.get("granted", 0)
