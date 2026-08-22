from __future__ import annotations

from app.core.config import Settings
from app.main import create_app


def test_referral_routes_are_registered(test_settings: Settings) -> None:
    paths = set(create_app(test_settings).openapi()["paths"])

    assert {
        "/api/v1/referrals/code",
        "/api/v1/referrals/claim",
        "/api/v1/referrals/statistics",
        "/api/v1/admin/referrals/review-queue",
        "/api/v1/admin/referrals/{referral_id}/review",
    }.issubset(paths)
