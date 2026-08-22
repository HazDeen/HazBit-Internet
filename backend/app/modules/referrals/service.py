from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ReferralSettings
from app.core.errors import ApplicationError
from app.modules.auth.crypto import SignalHasher
from app.modules.auth.models import AuditLog, RiskSignal
from app.modules.auth.rate_limit import RateLimit, RateLimiter
from app.modules.referrals.enums import ReferralStatus, RewardSide, RewardStatus
from app.modules.referrals.models import Referral, ReferralCode, ReferralReward
from app.modules.referrals.repository import ReferralRepository
from app.modules.referrals.risk import ReferralRiskAssessment, assess_referral_risk
from app.modules.referrals.schemas import (
    ReferralClaimResponse,
    ReferralCodeResponse,
    ReferralReviewItem,
    ReferralRewardResponse,
    ReferralStatisticsResponse,
)

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass(frozen=True, slots=True)
class ReferralClientContext:
    ip_address: str
    device_fingerprint: str | None
    user_agent: str | None
    request_id: UUID | None


class ReferralService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: ReferralSettings,
        rate_limiter: RateLimiter,
        signal_hasher: SignalHasher,
    ) -> None:
        self._session = session
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._signals = signal_hasher
        self._repository = ReferralRepository(session)

    async def get_or_create_code(self, user_id: UUID) -> ReferralCodeResponse:
        async with self._session.begin():
            await self._repository.serialize_key(f"referral:code:{user_id}")
            owner = await self._repository.user(user_id, for_update=True)
            if owner is None:
                raise ApplicationError("user_not_found", "User not found.", 404)
            existing = await self._repository.active_code_for_owner(user_id)
            if existing is not None:
                return self._code_response(existing)
            code = ReferralCode(
                owner_user_id=user_id,
                code="".join(
                    secrets.choice(CODE_ALPHABET) for _ in range(self._settings.code_length)
                ),
                status="active",
            )
            self._session.add(code)
            await self._session.flush()
            self._session.add(
                AuditLog(
                    actor_user_id=user_id,
                    actor_type="user",
                    action="referral.code_created",
                    entity_type="referral_code",
                    entity_id=code.id,
                    after_state={"status": code.status},
                )
            )
            return self._code_response(code)

    async def claim(
        self,
        *,
        user_id: UUID,
        code_value: str,
        client: ReferralClientContext,
    ) -> ReferralClaimResponse:
        policy = RateLimit(
            "referral_claim_user",
            self._settings.claim_rate_limit_per_hour,
            3600,
        )
        await self._rate_limiter.enforce(policy, str(user_id))
        await self._rate_limiter.enforce(
            RateLimit("referral_claim_ip", self._settings.claim_rate_limit_per_hour * 2, 3600),
            self._signals.digest("ip", client.ip_address).hex(),
        )

        now = datetime.now(UTC)
        async with self._session.begin():
            await self._repository.serialize_key(f"referral:claim:{user_id}")
            referred = await self._repository.user(user_id, for_update=True)
            if referred is None:
                raise ApplicationError("user_not_found", "User not found.", 404)
            existing = await self._repository.referral_for_referred(user_id)
            if existing is not None:
                code = await self._repository.code_by_value(code_value)
                if code is None or existing.referral_code_id != code.id:
                    raise ApplicationError(
                        "referral_already_attributed",
                        "This account is already attributed to another referral.",
                        409,
                    )
                return await self._claim_response(existing)

            code = await self._repository.code_for_claim(code_value)
            if code is None or (code.expires_at is not None and code.expires_at <= now):
                raise ApplicationError(
                    "referral_code_invalid", "Referral code is invalid or expired.", 404
                )
            if code.owner_user_id == user_id:
                raise ApplicationError(
                    "referral_self_claim_forbidden", "You cannot use your own referral code.", 409
                )
            referrer = await self._repository.user(code.owner_user_id, for_update=True)
            if referrer is None or referrer.status != "active":
                raise ApplicationError(
                    "referral_code_unavailable", "Referral code is unavailable.", 409
                )
            if referred.created_at < now - timedelta(
                days=self._settings.claim_new_user_max_age_days
            ):
                raise ApplicationError(
                    "referral_account_not_eligible",
                    "Referral codes can only be claimed by new accounts.",
                    409,
                )
            history = await self._repository.referred_history(user_id)
            if any(
                (
                    history.has_referral,
                    history.has_trial,
                    history.has_subscription,
                    history.has_approved_payment,
                )
            ):
                raise ApplicationError(
                    "referral_account_not_eligible",
                    "This account is not eligible for a referral trial.",
                    409,
                )
            usage = await self._repository.non_rejected_usage_count(code.id)
            if code.usage_limit is not None and usage >= code.usage_limit:
                raise ApplicationError(
                    "referral_code_usage_limit_reached",
                    "Referral code usage limit has been reached.",
                    409,
                )

            assessment = await self._assess_risk(
                referrer_user_id=referrer.id,
                client=client,
                now=now,
            )
            referral = Referral(
                referral_code_id=code.id,
                referrer_user_id=referrer.id,
                referred_user_id=user_id,
                status=ReferralStatus.ATTRIBUTED.value,
                attributed_at=now,
            )
            self._session.add(referral)
            await self._session.flush()
            self._record_risk(referral, assessment, client, now)
            if assessment.decision == "allow":
                self._qualify(referral, now)
            elif assessment.decision == "deny":
                referral.status = ReferralStatus.REJECTED.value
                referral.rejection_reason = ",".join(assessment.reasons)

            self._session.add(
                AuditLog(
                    actor_user_id=user_id,
                    actor_type="user",
                    action="referral.claimed",
                    entity_type="referral",
                    entity_id=referral.id,
                    reason=(referral.rejection_reason if assessment.decision == "deny" else None),
                    after_state={
                        "status": referral.status,
                        "risk_decision": assessment.decision,
                        "risk_score": assessment.score,
                    },
                    ip_address=client.ip_address,
                    user_agent=client.user_agent,
                    request_id=client.request_id,
                )
            )
            await self._session.flush()
            return await self._claim_response(referral, assessment=assessment)

    async def statistics(self, user_id: UUID) -> ReferralStatisticsResponse:
        code = await self._repository.active_code_for_owner(user_id)
        counts = await self._repository.owner_counts(user_id)
        pending_days, granted_days = await self._repository.owner_reward_days(user_id)
        referred_by = await self._repository.referral_for_referred(user_id)
        referred_days = 0
        if referred_by is not None:
            rewards = await self._repository.rewards(referred_by.id)
            referred_days = sum(
                reward.days or 0
                for reward in rewards
                if reward.reward_side == RewardSide.REFERRED.value
                and reward.status == RewardStatus.GRANTED.value
            )
        return ReferralStatisticsResponse(
            code=self._code_response(code) if code is not None else None,
            total=sum(counts.values()),
            attributed=counts.get(ReferralStatus.ATTRIBUTED.value, 0),
            qualified=counts.get(ReferralStatus.QUALIFIED.value, 0),
            rewarded=counts.get(ReferralStatus.REWARDED.value, 0),
            rejected=counts.get(ReferralStatus.REJECTED.value, 0),
            pending_referrer_days=pending_days,
            granted_referrer_days=granted_days,
            referred_by_status=referred_by.status if referred_by is not None else None,
            referred_reward_days=referred_days,
        )

    async def review_queue(self, limit: int) -> list[ReferralReviewItem]:
        rows = await self._repository.review_queue(limit)
        result: list[ReferralReviewItem] = []
        for referral, code in rows:
            risk = await self._repository.latest_referral_risk(referral.id)
            context = risk.context if risk is not None else {}
            result.append(
                ReferralReviewItem(
                    referral_id=referral.id,
                    code=code.code,
                    referrer_user_id=referral.referrer_user_id,
                    referred_user_id=referral.referred_user_id,
                    attributed_at=referral.attributed_at,
                    risk_score=risk.score if risk is not None else 0,
                    risk_reasons=[str(value) for value in context.get("reasons", [])],
                )
            )
        return result

    async def review(
        self,
        *,
        referral_id: UUID,
        reviewer_user_id: UUID,
        decision: str,
        reason: str,
    ) -> ReferralClaimResponse:
        now = datetime.now(UTC)
        async with self._session.begin():
            referral = await self._repository.referral_for_update(referral_id)
            if referral is None:
                raise ApplicationError("referral_not_found", "Referral not found.", 404)
            if referral.status != ReferralStatus.ATTRIBUTED.value:
                raise ApplicationError(
                    "referral_not_reviewable", "Referral is not awaiting review.", 409
                )
            if decision == "approved":
                self._qualify(referral, now)
                action = "referral.review_approved"
            else:
                referral.status = ReferralStatus.REJECTED.value
                referral.rejection_reason = reason
                action = "referral.review_rejected"
            self._session.add(
                AuditLog(
                    actor_user_id=reviewer_user_id,
                    actor_type="admin",
                    action=action,
                    entity_type="referral",
                    entity_id=referral.id,
                    reason=reason,
                    after_state={"status": referral.status},
                )
            )
            await self._session.flush()
            return await self._claim_response(referral)

    async def _assess_risk(
        self,
        *,
        referrer_user_id: UUID,
        client: ReferralClientContext,
        now: datetime,
    ) -> ReferralRiskAssessment:
        since = now - timedelta(days=30)
        ip_hash = self._signals.digest("ip", client.ip_address)
        ip_count = await self._repository.signal_user_count("ip", ip_hash, since)
        same_ip = await self._repository.signal_seen_for_user(
            "ip", ip_hash, referrer_user_id, since
        )
        device_hash = (
            self._signals.digest("device", client.device_fingerprint)
            if client.device_fingerprint
            else None
        )
        device_count = 0
        same_device = False
        if device_hash is not None:
            device_count = await self._repository.signal_user_count("device", device_hash, since)
            same_device = await self._repository.signal_seen_for_user(
                "device", device_hash, referrer_user_id, since
            )
        return assess_referral_risk(
            settings=self._settings,
            fingerprint_present=device_hash is not None,
            same_referrer_ip=same_ip,
            same_referrer_device=same_device,
            ip_user_count=ip_count,
            device_user_count=device_count,
        )

    def _record_risk(
        self,
        referral: Referral,
        assessment: ReferralRiskAssessment,
        client: ReferralClientContext,
        now: datetime,
    ) -> None:
        expiry = now + timedelta(days=90)
        self._session.add(
            RiskSignal(
                user_id=referral.referred_user_id,
                signal_type="referral",
                signal_hash=self._signals.digest(
                    "referral", f"{referral.referrer_user_id}:{referral.referred_user_id}"
                ),
                score=assessment.score,
                decision=assessment.decision,
                context={
                    "referral_id": str(referral.id),
                    "reasons": list(assessment.reasons),
                },
                expires_at=expiry,
            )
        )
        self._session.add(
            RiskSignal(
                user_id=referral.referred_user_id,
                signal_type="ip",
                signal_hash=self._signals.digest("ip", client.ip_address),
                score=assessment.score,
                decision=assessment.decision,
                context={"method": "referral_claim"},
                expires_at=expiry,
            )
        )
        if client.device_fingerprint:
            self._session.add(
                RiskSignal(
                    user_id=referral.referred_user_id,
                    signal_type="device",
                    signal_hash=self._signals.digest("device", client.device_fingerprint),
                    score=assessment.score,
                    decision=assessment.decision,
                    context={"method": "referral_claim"},
                    expires_at=expiry,
                )
            )

    def _qualify(self, referral: Referral, now: datetime) -> None:
        referral.status = ReferralStatus.QUALIFIED.value
        referral.qualified_at = now
        self._session.add_all(
            [
                ReferralReward(
                    referral_id=referral.id,
                    beneficiary_user_id=referral.referred_user_id,
                    reward_side=RewardSide.REFERRED.value,
                    reward_type="subscription_days",
                    days=self._settings.referred_days,
                    status=RewardStatus.PENDING.value,
                ),
                ReferralReward(
                    referral_id=referral.id,
                    beneficiary_user_id=referral.referrer_user_id,
                    reward_side=RewardSide.REFERRER.value,
                    reward_type="subscription_days",
                    days=self._settings.referrer_days,
                    status=RewardStatus.PENDING.value,
                ),
            ]
        )

    async def _claim_response(
        self,
        referral: Referral,
        *,
        assessment: ReferralRiskAssessment | None = None,
    ) -> ReferralClaimResponse:
        rewards = await self._repository.rewards(referral.id)
        if assessment is None:
            signal = await self._repository.latest_referral_risk(referral.id)
            context = signal.context if signal is not None else {}
            assessment = ReferralRiskAssessment(
                decision=signal.decision if signal is not None else "allow",
                score=signal.score if signal is not None else 0,
                reasons=tuple(str(value) for value in context.get("reasons", [])),
            )
        return ReferralClaimResponse(
            id=referral.id,
            status=referral.status,
            attributed_at=referral.attributed_at,
            qualified_at=referral.qualified_at,
            rewarded_at=referral.rewarded_at,
            rejection_reason=referral.rejection_reason,
            risk_decision=assessment.decision,
            risk_score=assessment.score,
            risk_reasons=list(assessment.reasons),
            rewards=[self._reward_response(reward) for reward in rewards],
        )

    def _code_response(self, code: ReferralCode) -> ReferralCodeResponse:
        return ReferralCodeResponse(
            code=code.code,
            share_url=f"{self._settings.share_url_prefix}{code.code}",
            status=code.status,
            usage_limit=code.usage_limit,
            expires_at=code.expires_at,
        )

    @staticmethod
    def _reward_response(reward: ReferralReward) -> ReferralRewardResponse:
        return ReferralRewardResponse(
            side=reward.reward_side,
            beneficiary_user_id=reward.beneficiary_user_id,
            days=reward.days or 0,
            status=reward.status,
            granted_at=reward.granted_at,
        )
