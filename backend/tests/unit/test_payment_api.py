from __future__ import annotations

from app.core.config import Settings
from app.main import create_app


def test_payment_routes_are_registered(test_settings: Settings) -> None:
    paths = set(create_app(test_settings).openapi()["paths"])

    assert {
        "/api/v1/payments/intents",
        "/api/v1/payments/{payment_id}",
        "/api/v1/payments/{payment_id}/evidence",
        "/api/v1/admin/payments/review-queue",
        "/api/v1/admin/payments/evidence/{evidence_id}",
        "/api/v1/admin/payments/{payment_id}/review",
    }.issubset(paths)
