from __future__ import annotations

from app.core.config import Settings
from app.main import create_app


def test_promotion_routes_are_registered(test_settings: Settings) -> None:
    openapi_paths = create_app(test_settings).openapi()["paths"]
    paths = set(openapi_paths)

    assert {
        "/api/v1/promo-codes/preview",
        "/api/v1/promo-codes/redeem",
        "/api/v1/promo-codes/redemptions",
        "/api/v1/admin/promo-codes",
        "/api/v1/admin/promo-codes/{promo_id}",
    }.issubset(paths)
    assert "delete" in openapi_paths["/api/v1/admin/promo-codes/{promo_id}"]
