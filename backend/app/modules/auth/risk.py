from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.modules.auth.crypto import SignalHasher
from app.modules.auth.enums import RiskDecision
from app.modules.auth.models import RiskSignal
from app.modules.auth.repository import AuthRepository


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    decision: RiskDecision
    score: int
    reasons: tuple[str, ...]


class AntiAbuseService:
    def __init__(self, repository: AuthRepository, hasher: SignalHasher) -> None:
        self._repository = repository
        self._hasher = hasher

    async def assess_and_record(
        self,
        *,
        user_id: UUID,
        ip_address: str,
        device_fingerprint: str | None,
        method: str,
        now: datetime | None = None,
    ) -> RiskAssessment:
        current_time = now or datetime.now(UTC)
        since = current_time - timedelta(days=30)
        score = 0
        reasons: list[str] = []

        ip_hash = self._hasher.digest("ip", ip_address)
        ip_users = await self._repository.count_signal_users_since(
            signal_type="ip", signal_hash=ip_hash, since=since
        )
        if ip_users >= 5:
            score += 35
            reasons.append("shared_ip_velocity")

        fingerprint_hash: bytes | None = None
        fingerprint_users = 0
        if device_fingerprint:
            fingerprint_hash = self._hasher.digest("device", device_fingerprint)
            fingerprint_users = await self._repository.count_signal_users_since(
                signal_type="device", signal_hash=fingerprint_hash, since=since
            )
            if fingerprint_users >= 2:
                score += 60
                reasons.append("reused_device_fingerprint")
        else:
            score += 10
            reasons.append("missing_device_fingerprint")

        decision = RiskDecision.REVIEW if score >= 50 else RiskDecision.ALLOW
        expiry = current_time + timedelta(days=90)
        self._repository.add_risk_signal(
            RiskSignal(
                user_id=user_id,
                signal_type="ip",
                signal_hash=ip_hash,
                score=score,
                decision=decision.value,
                context={"method": method, "distinct_users_30d": ip_users},
                expires_at=expiry,
            )
        )
        if fingerprint_hash is not None:
            self._repository.add_risk_signal(
                RiskSignal(
                    user_id=user_id,
                    signal_type="device",
                    signal_hash=fingerprint_hash,
                    score=score,
                    decision=decision.value,
                    context={"method": method, "distinct_users_30d": fingerprint_users},
                    expires_at=expiry,
                )
            )
        return RiskAssessment(decision=decision, score=score, reasons=tuple(reasons))
