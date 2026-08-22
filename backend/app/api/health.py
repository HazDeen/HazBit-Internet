from __future__ import annotations

import asyncio

from fastapi import APIRouter, Response, status

from app.api.dependencies import DatabaseDependency, RedisDependency
from app.core.config import Settings
from app.schemas.health import HealthResponse
from app.services.health import HealthService


def create_health_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("/live", response_model=HealthResponse)
    async def liveness() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
        )

    @router.get(
        "/ready",
        response_model=HealthResponse,
        responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
    )
    async def readiness(
        database: DatabaseDependency,
        redis: RedisDependency,
        response: Response,
    ) -> HealthResponse:
        health_service = HealthService(database, redis)
        database_health, redis_health = await asyncio.gather(
            health_service.database_check(),
            health_service.redis_check(),
        )
        ready = database_health.status == "up" and redis_health.status == "up"
        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="ok" if ready else "not_ready",
            service=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
            checks={"database": database_health, "redis": redis_health},
        )

    return router
