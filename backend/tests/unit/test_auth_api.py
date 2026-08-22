from __future__ import annotations

from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_auth_routes_are_registered(test_settings: Settings) -> None:
    paths = set(create_app(test_settings).openapi()["paths"])

    assert {
        "/api/v1/auth/email/start",
        "/api/v1/auth/email/verify",
        "/api/v1/auth/telegram",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
    }.issubset(paths)


def test_refresh_requires_double_submit_csrf(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings), raise_server_exceptions=False) as client:
        response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_validation_failed"


def test_auth_payloads_forbid_unknown_fields(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings), raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/auth/email/start",
            json={"email": "person@example.com", "unexpected": True},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
