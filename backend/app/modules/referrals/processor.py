from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ReferralSettings
from app.modules.auth.models import AuditLog
from app.modules.payments.models import OutboxEvent
from app.modules.referrals.enums import ReferralStatus, RewardSide, RewardStatus
from app.modules.referrals.models import Referral, ReferralReward, SubscriptionPeriod, TrialGrant
from app.modules.referrals.repository import ReferralRepository
from app.modules.vpn.enums import CommandStatus, CommandType, DesiredVpnStatus
from app.modules.vpn.models import PlanVersion, Subscription, VpnAccount, VpnSyncCommand


class ReferralRewardProcessor:
    def __init__(self, *, session: AsyncSession, settings: ReferralSettings) -> None:
        self._session = session
        self._settings = settings
        self._repository = ReferralRepository(session)

    async def process_batch(self, *, limit: int | None = None) -> int:
        batch_limit = limit or self._settings.worker_batch_size
        processed = 0
        while processed < batch_limit:
            async with self._session.begin():
                referrals = await self._repository.claim_qualified(1)
                if not referrals:
                    return processed
                referral = referrals[0]
                await self._grant_referral(referral)
            processed += 1
        return processed

    async def _grant_referral(self, referral: Referral) -> None:
        now = datetime.now(UTC)
        referrer = await self._repository.user(referral.referrer_user_id, for_update=True)
        referred = await self._repository.user(referral.referred_user_id, for_update=True)
        if referrer is None or referred is None:
            raise RuntimeError("referral references no user")
        if referrer.status != "active" or referred.status != "active":
            await self._reject(referral, "referral_user_inactive")
            return
        rewards = await self._repository.rewards(referral.id)
        if len(rewards) != 2:
            raise RuntimeError("qualified referral must have exactly two rewards")
        if all(reward.status == RewardStatus.GRANTED.value for reward in rewards):
            referral.status = ReferralStatus.REWARDED.value
            referral.rewarded_at = referral.rewarded_at or now
            return
        if await self._repository.trial_for_user(referral.referred_user_id) is not None:
            await self._reject(referral, "referral_trial_conflict")
            return

        default_plan = await self._repository.active_default_plan_version(
            self._settings.default_plan_slug, now
        )
        if default_plan is None:
            raise RuntimeError("default referral plan is not configured")

        for reward in rewards:
            if reward.status == RewardStatus.GRANTED.value:
                continue
            subscription, plan, period = await self._grant_days(
                reward=reward,
                default_plan=default_plan[1],
                now=now,
            )
            if reward.reward_side == RewardSide.REFERRED.value:
                risk = await self._repository.latest_referral_risk(referral.id)
                self._session.add(
                    TrialGrant(
                        user_id=reward.beneficiary_user_id,
                        subscription_id=subscription.id,
                        duration_days=reward.days or 0,
                        decision="granted",
                        risk_score=risk.score if risk is not None else 0,
                        decision_reason="qualified_referral",
                        granted_at=now,
                    )
                )
            reward.subscription_period_id = period.id
            reward.status = RewardStatus.GRANTED.value
            reward.granted_at = now
            await self._enqueue_vpn_sync(
                reward=reward,
                subscription=subscription,
                plan=plan,
                now=now,
            )
            if subscription.current_period_ends_at is None:
                raise RuntimeError("rewarded subscription has no expiry")
            self._session.add(
                OutboxEvent(
                    aggregate_type="referral_reward",
                    aggregate_id=reward.id,
                    event_type="referral.reward.granted",
                    payload={
                        "referral_id": str(referral.id),
                        "reward_id": str(reward.id),
                        "beneficiary_user_id": str(reward.beneficiary_user_id),
                        "days": reward.days,
                        "subscription_id": str(subscription.id),
                        "subscription_ends_at": subscription.current_period_ends_at.isoformat(),
                    },
                    idempotency_key=f"referral-reward-granted:{reward.id}",
                )
            )

        referral.status = ReferralStatus.REWARDED.value
        referral.rewarded_at = now
        self._session.add(
            OutboxEvent(
                aggregate_type="referral",
                aggregate_id=referral.id,
                event_type="referral.rewarded",
                payload={
                    "referral_id": str(referral.id),
                    "referrer_user_id": str(referral.referrer_user_id),
                    "referred_user_id": str(referral.referred_user_id),
                },
                idempotency_key=f"referral-rewarded:{referral.id}",
            )
        )
        self._session.add(
            AuditLog(
                actor_type="service",
                action="referral.rewards_granted",
                entity_type="referral",
                entity_id=referral.id,
                after_state={"status": referral.status},
            )
        )

    async def _reject(self, referral: Referral, reason: str) -> None:
        rewards = await self._repository.rewards(referral.id)
        for reward in rewards:
            if reward.status == RewardStatus.PENDING.value:
                await self._session.delete(reward)
        referral.status = ReferralStatus.REJECTED.value
        referral.rejection_reason = reason
        self._session.add(
            AuditLog(
                actor_type="service",
                action="referral.reward_rejected",
                entity_type="referral",
                entity_id=referral.id,
                reason=reason,
                after_state={"status": referral.status},
            )
        )

    async def _grant_days(
        self,
        *,
        reward: ReferralReward,
        default_plan: PlanVersion,
        now: datetime,
    ) -> tuple[Subscription, PlanVersion, SubscriptionPeriod]:
        days = reward.days or 0
        if days <= 0:
            raise RuntimeError("subscription-day reward must be positive")
        subscription = await self._repository.live_subscription_for_update(
            reward.beneficiary_user_id
        )
        if subscription is None:
            plan = default_plan
            starts_at = now
            ends_at = now + timedelta(days=days)
            subscription = Subscription(
                owner_user_id=reward.beneficiary_user_id,
                plan_version_id=plan.id,
                status="active",
                source="referral",
                starts_at=starts_at,
                current_period_ends_at=ends_at,
                grace_ends_at=None,
                cancel_at_period_end=False,
                cancelled_at=None,
                suspended_at=None,
                suspension_reason=None,
                version=1,
            )
            self._session.add(subscription)
            await self._session.flush()
        else:
            plan = await self._repository.plan_version(subscription.plan_version_id)
            starts_at = max(subscription.current_period_ends_at or now, now)
            ends_at = starts_at + timedelta(days=days)
            subscription.starts_at = subscription.starts_at or now
            subscription.current_period_ends_at = ends_at
            if subscription.status in {"pending", "grace_period"}:
                subscription.status = "active"
            subscription.version += 1

        period = SubscriptionPeriod(
            subscription_id=subscription.id,
            source_type="referral",
            source_id=reward.id,
            starts_at=starts_at,
            ends_at=ends_at,
            plan_snapshot=self._plan_snapshot(plan),
            price_minor=None,
            currency=None,
        )
        self._session.add(period)
        await self._session.flush()
        return subscription, plan, period

    async def _enqueue_vpn_sync(
        self,
        *,
        reward: ReferralReward,
        subscription: Subscription,
        plan: PlanVersion,
        now: datetime,
    ) -> None:
        if subscription.current_period_ends_at is None:
            raise RuntimeError("rewarded subscription has no expiry")
        account = await self._repository.vpn_account_for_update(reward.beneficiary_user_id)
        if account is None:
            account = VpnAccount(
                user_id=reward.beneficiary_user_id,
                subscription_id=subscription.id,
                username=f"hz_{reward.beneficiary_user_id.hex[:24]}",
                desired_status=DesiredVpnStatus.ACTIVE.value,
                desired_expires_at=subscription.current_period_ends_at,
            )
            self._session.add(account)
            await self._session.flush()
        else:
            account.subscription_id = subscription.id
            account.desired_expires_at = subscription.current_period_ends_at
            if subscription.status != "suspended":
                account.desired_status = DesiredVpnStatus.ACTIVE.value

        if subscription.status == "suspended":
            return
        command_key = f"vpn:referral:{account.id}:{reward.id}"
        if await self._repository.vpn_command_by_key(command_key) is not None:
            return
        if account.remnawave_user_id is None:
            email, telegram_id = await self._repository.identity_contacts(
                reward.beneficiary_user_id
            )
            command_type = CommandType.ENSURE_ACCOUNT.value
            payload: dict[str, Any] = {
                "username": account.username,
                "expire_at": subscription.current_period_ends_at.isoformat(),
                "traffic_limit_bytes": plan.traffic_limit_bytes or 0,
                "device_limit": plan.device_limit,
                "email": email,
                "telegram_id": telegram_id,
                "internal_squad_ids": self._squad_ids(plan.remnawave_policy),
            }
        else:
            command_type = CommandType.EXTEND.value
            payload = {"expires_at": subscription.current_period_ends_at.isoformat()}
        self._session.add(
            VpnSyncCommand(
                vpn_account_id=account.id,
                command_type=command_type,
                idempotency_key=command_key,
                payload=payload,
                status=CommandStatus.PENDING.value,
                attempt_count=0,
                next_attempt_at=now,
            )
        )

    @staticmethod
    def _plan_snapshot(plan: PlanVersion) -> dict[str, Any]:
        return {
            "plan_version_id": str(plan.id),
            "version": plan.version,
            "device_limit": plan.device_limit,
            "family_member_limit": plan.family_member_limit,
            "traffic_limit_bytes": plan.traffic_limit_bytes,
            "remnawave_policy": plan.remnawave_policy,
        }

    @staticmethod
    def _squad_ids(policy: dict[str, Any]) -> list[str]:
        values = policy.get("internal_squad_ids", [])
        if not isinstance(values, list):
            raise RuntimeError("invalid referral plan Remnawave policy")
        try:
            return [str(UUID(str(value))) for value in values]
        except ValueError as exc:
            raise RuntimeError("invalid referral plan Remnawave squad ID") from exc
