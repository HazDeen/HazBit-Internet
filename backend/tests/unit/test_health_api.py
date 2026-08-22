from __future__ import annotations

from collections.abc import Generator
from uuid import UUID, uuid4

from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


class FakeDatabase:
    def __init__(self, *, healthy: bool) -> None:
        self.healthy = healthy

    async def ping(self) -> None:
        if not self.healthy:
            raise ConnectionError("database unavailable")


class FakeRedis(FakeDatabase):
    pass


def client_with_database(
    settings: Settings,
    *,
    healthy: bool,
) -> Generator[TestClient, None, None]:
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.database = FakeDatabase(healthy=healthy)
        app.state.redis = FakeRedis(healthy=healthy)
        yield client


def test_liveness_does_not_depend_on_database(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Hazbit VPN Platform API",
        "version": "0.1.0",
        "environment": "test",
        "checks": None,
    }
    UUID(response.headers["X-Request-ID"])


def test_request_id_is_propagated(test_settings: Settings) -> None:
    request_id = str(uuid4())
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/health/live", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id


def test_invalid_request_id_is_replaced(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "not-a-uuid"})

    assert response.headers["X-Request-ID"] != "not-a-uuid"
    UUID(response.headers["X-Request-ID"])


def test_readiness_reports_database_up(test_settings: Settings) -> None:
    for client in client_with_database(test_settings, healthy=True):
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["checks"]["database"]["status"] == "up"
    assert response.json()["checks"]["redis"]["status"] == "up"


def test_readiness_returns_503_when_database_is_down(test_settings: Settings) -> None:
    for client in client_with_database(test_settings, healthy=False):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"]["status"] == "down"
    assert response.json()["checks"]["redis"]["status"] == "down"


def test_unknown_route_uses_problem_details(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "http_error"


def test_docs_can_be_disabled(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/docs")

    assert response.status_code == 404
