from __future__ import annotations

from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import ApplicationError


class TelegramUpdateGate:
    def __init__(
        self,
        redis: Redis,
        *,
        key_prefix: str,
        lock_seconds: int,
        receipt_ttl_seconds: int,
    ) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self._lock_seconds = lock_seconds
        self._receipt_ttl_seconds = receipt_ttl_seconds

    def _key(self, bot: str, update_id: int) -> str:
        return f"{self._key_prefix}:telegram-update:{bot}:{update_id}"

    async def begin(self, bot: str, update_id: int) -> bool:
        try:
            result = await cast(
                Awaitable[bool | None],
                self._redis.set(
                    self._key(bot, update_id),
                    b"processing",
                    ex=self._lock_seconds,
                    nx=True,
                ),
            )
        except RedisError as exc:
            raise self._unavailable() from exc
        return bool(result)

    async def complete(self, bot: str, update_id: int) -> None:
        try:
            await cast(
                Awaitable[bool | None],
                self._redis.set(self._key(bot, update_id), b"done", ex=self._receipt_ttl_seconds),
            )
        except RedisError as exc:
            raise self._unavailable() from exc

    async def release(self, bot: str, update_id: int) -> None:
        try:
            await cast(Awaitable[int], self._redis.delete(self._key(bot, update_id)))
        except RedisError:
            return

    @staticmethod
    def _unavailable() -> ApplicationError:
        return ApplicationError(
            "telegram_idempotency_unavailable",
            "Telegram update protection is temporarily unavailable.",
            503,
        )
