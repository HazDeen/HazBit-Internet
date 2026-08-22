from __future__ import annotations

from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis

from app.core.config import RedisSettings


class RedisManager:
    def __init__(self, settings: RedisSettings) -> None:
        self._client: Redis = Redis.from_url(
            settings.url,
            decode_responses=False,
            socket_connect_timeout=settings.socket_connect_timeout_seconds,
            socket_timeout=settings.socket_timeout_seconds,
            health_check_interval=30,
        )

    @property
    def client(self) -> Redis:
        return self._client

    async def ping(self) -> None:
        await cast(Awaitable[bool], self._client.ping())

    async def dispose(self) -> None:
        await self._client.aclose()
