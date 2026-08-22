from __future__ import annotations

from fastapi.testclient import TestClient

from remnawave_adapter.config import Settings
from remnawave_adapter.main import create_app


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        panel_base_url="https://panel.example.com",
        panel_token="panel-secret",
        internal_token="internal-secret",
        max_get_attempts=1,
    )


def test_internal_api_rejects_missing_service_token() -> None:
    with TestClient(create_app(_settings()), raise_server_exceptions=False) as client:
        response = client.get("/internal/v1/users/42")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_liveness_does_not_call_panel() -> None:
    with TestClient(create_app(_settings())) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
