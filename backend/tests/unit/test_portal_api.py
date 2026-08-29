from __future__ import annotations

from app.core.config import Settings
from app.main import create_app


def test_customer_portal_routes_are_registered_and_protected(test_settings: Settings) -> None:
    schema = create_app(test_settings).openapi()
    for path in (
        "/api/v1/portal/overview",
        "/api/v1/portal/plans",
        "/api/v1/portal/payments",
    ):
        assert path in schema["paths"]
        assert schema["paths"][path]["get"]["security"] == [{"HTTPBearer": []}]

    assert "/api/v1/catalog/plans" in schema["paths"]
    assert "security" not in schema["paths"]["/api/v1/catalog/plans"]["get"]
