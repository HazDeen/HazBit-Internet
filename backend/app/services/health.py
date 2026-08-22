from __future__ import annotations

from time import perf_counter

from app.database.session import DatabaseManager
from app.integrations.redis import RedisManager
from app.schemas.health import ComponentHealth


class HealthService:
    def __init__(self, database: DatabaseManager, redis: RedisManager) -> None:
        self._database = database
        self._redis = redis

    async def database_check(self) -> ComponentHealth:
        started = perf_counter()
        try:
            await self._database.ping()
        except Exception:
            return ComponentHealth(status="down", latency_ms=self._latency(started))
        return ComponentHealth(status="up", latency_ms=self._latency(started))

    async def redis_check(self) -> ComponentHealth:
        started = perf_counter()
        try:
            await self._redis.ping()
        except Exception:
            return ComponentHealth(status="down", latency_ms=self._latency(started))
        return ComponentHealth(status="up", latency_ms=self._latency(started))

    @staticmethod
    def _latency(started: float) -> float:
        return round((perf_counter() - started) * 1000, 2)
