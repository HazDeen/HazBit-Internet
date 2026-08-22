from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ReferralCodeResponse(BaseModel):
    code: str
    share_url: str
    status: str
    usage_limit: int | None
    expires_at: datetime | None


class ClaimReferralRequest(BaseModel):
    code: str = Field(min_length=8, max_length=16)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]+", normalized):
            raise ValueError("referral code must contain only ASCII letters and digits")
        return normalized


class ReferralRewardResponse(BaseModel):
    side: str
    beneficiary_user_id: UUID
    days: int
    status: str
    granted_at: datetime | None


class ReferralClaimResponse(BaseModel):
    id: UUID
    status: str
    attributed_at: datetime
    qualified_at: datetime | None
    rewarded_at: datetime | None
    rejection_reason: str | None
    risk_decision: str
    risk_score: int
    risk_reasons: list[str]
    rewards: list[ReferralRewardResponse]


class ReferralStatisticsResponse(BaseModel):
    code: ReferralCodeResponse | None
    total: int
    attributed: int
    qualified: int
    rewarded: int
    rejected: int
    pending_referrer_days: int
    granted_referrer_days: int
    referred_by_status: str | None
    referred_reward_days: int


class ReferralReviewItem(BaseModel):
    referral_id: UUID
    code: str
    referrer_user_id: UUID
    referred_user_id: UUID
    attributed_at: datetime
    risk_score: int
    risk_reasons: list[str]


class ReviewReferralRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=3, max_length=1000)
