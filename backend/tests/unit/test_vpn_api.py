from __future__ import annotations

from app.core.config import Settings
from app.main import create_app


def test_vpn_routes_are_registered(test_settings: Settings) -> None:
    paths = set(create_app(test_settings).openapi()["paths"])

    assert {
        "/api/v1/vpn/account",
        "/api/v1/vpn/config",
        "/api/v1/devices",
        "/api/v1/devices/{device_id}",
    }.issubset(paths)
