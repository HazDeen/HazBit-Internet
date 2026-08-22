from __future__ import annotations

from app.core.config import ReferralSettings
from app.modules.referrals.risk import assess_referral_risk


def test_clean_referral_is_automatically_allowed() -> None:
    result = assess_referral_risk(
        settings=ReferralSettings(),
        fingerprint_present=True,
        same_referrer_ip=False,
        same_referrer_device=False,
        ip_user_count=1,
        device_user_count=1,
    )

    assert result.decision == "allow"
    assert result.score == 0


def test_same_referrer_device_is_denied() -> None:
    result = assess_referral_risk(
        settings=ReferralSettings(),
        fingerprint_present=True,
        same_referrer_ip=False,
        same_referrer_device=True,
        ip_user_count=1,
        device_user_count=1,
    )

    assert result.decision == "deny"
    assert result.score == 100
    assert result.reasons == ("referrer_device_match",)


def test_shared_ip_and_missing_fingerprint_require_review() -> None:
    result = assess_referral_risk(
        settings=ReferralSettings(),
        fingerprint_present=False,
        same_referrer_ip=True,
        same_referrer_device=False,
        ip_user_count=2,
        device_user_count=0,
    )

    assert result.decision == "review"
    assert result.score == 80
