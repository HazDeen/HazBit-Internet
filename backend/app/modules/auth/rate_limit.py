from __future__ import annotations

import secrets
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import ApplicationError

SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local member = ARGV[3]
local current = redis.call('TIME')
local now_ms = (current[1] * 1000) + math.floor(current[2] / 1000)
local cutoff = now_ms - window_ms
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
local count = redis.call('ZCARD', key)
if count >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_ms = window_ms
    if oldest[2] then
        retry_ms = math.max(1, window_ms - (now_ms - tonumber(oldest[2])))
    end
    redis.call('PEXPIRE', key, window_ms)
    return {0, retry_ms}
end
redis.call('ZADD', key, now_ms, member)
redis.call('PEXPIRE', key, window_ms)
return {1, window_ms}
"""


@dataclass(frozen=True, slots=True)
class RateLimit:
    name: str
    limit: int
    window_seconds: int


class RateLimiter:
    def __init__(self, redis: Redis, *, key_prefix: str) -> None:
        self._redis = redis
        self._key_prefix = key_prefix

    async def enforce(self, policy: RateLimit, identity: str) -> None:
        key = f"{self._key_prefix}:rate:{policy.name}:{identity}"
        try:
            result = await cast(
                Awaitable[list[Any]],
                self._redis.eval(
                    SLIDING_WINDOW_SCRIPT,
                    1,
                    key,
                    policy.limit,
                    policy.window_seconds * 1000,
                    secrets.token_urlsafe(12),
                ),
            )
        except RedisError as exc:
            raise ApplicationError(
                code="rate_limit_unavailable",
                detail="Authentication protection is temporarily unavailable.",
                status_code=503,
            ) from exc

        allowed = bool(result[0])
        if allowed:
            return
        retry_after = max(1, (int(result[1]) + 999) // 1000)
        raise ApplicationError(
            code="rate_limit_exceeded",
            detail="Too many authentication attempts. Try again later.",
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
