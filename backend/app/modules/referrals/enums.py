from __future__ import annotations

from enum import StrEnum


class ReferralStatus(StrEnum):
    ATTRIBUTED = "attributed"
    QUALIFIED = "qualified"
    REWARDED = "rewarded"
    REJECTED = "rejected"


class RewardSide(StrEnum):
    REFERRER = "referrer"
    REFERRED = "referred"


class RewardStatus(StrEnum):
    PENDING = "pending"
    GRANTED = "granted"
    REVOKED = "revoked"
