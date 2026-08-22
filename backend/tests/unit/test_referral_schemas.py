from __future__ import annotations

import pytest
from app.modules.referrals.schemas import ClaimReferralRequest
from pydantic import ValidationError


def test_referral_code_is_normalized() -> None:
    assert ClaimReferralRequest(code=" abcd2345 ").code == "ABCD2345"


def test_referral_code_rejects_ambiguous_payload_characters() -> None:
    with pytest.raises(ValidationError):
        ClaimReferralRequest(code="ABCD-2345")
