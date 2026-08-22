from __future__ import annotations

from app.core.config import Settings
from app.main import create_app


def test_support_routes_are_registered(test_settings: Settings) -> None:
    paths = set(create_app(test_settings).openapi()["paths"])

    assert {
        "/api/v1/tickets",
        "/api/v1/tickets/{ticket_id}",
        "/api/v1/tickets/{ticket_id}/messages",
        "/api/v1/admin/tickets",
        "/api/v1/admin/tickets/{ticket_id}",
        "/api/v1/admin/tickets/{ticket_id}/messages",
    }.issubset(paths)
