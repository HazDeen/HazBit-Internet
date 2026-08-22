from __future__ import annotations

from dataclasses import dataclass

from app.core.config import ReferralSettings


@dataclass(frozen=True, slots=True)
class ReferralRiskAssessment:
    decision: str
    score: int
    reasons: tuple[str, ...]


def assess_referral_risk(
    *,
    settings: ReferralSettings,
    fingerprint_present: bool,
    same_referrer_ip: bool,
    same_referrer_device: bool,
    ip_user_count: int,
    device_user_count: int,
) -> ReferralRiskAssessment:
    if same_referrer_device:
        return ReferralRiskAssessment("deny", 100, ("referrer_device_match",))

    score = 0
    reasons: list[str] = []
    if same_referrer_ip:
        score += 60
        reasons.append("referrer_ip_match")
    if ip_user_count >= settings.shared_ip_review_threshold:
        score += 35
        reasons.append("shared_ip_velocity")
    if not fingerprint_present:
        score += 20
        reasons.append("missing_device_fingerprint")
    elif device_user_count >= settings.shared_device_review_threshold:
        score += 60
        reasons.append("reused_device_fingerprint")

    return ReferralRiskAssessment(
        decision="review" if score >= 50 else "allow",
        score=min(score, 100),
        reasons=tuple(reasons),
    )
