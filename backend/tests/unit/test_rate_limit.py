from __future__ import annotations

from typing import Any

import pytest
from app.core.errors import ApplicationError
from app.modules.auth.rate_limit import RateLimit, RateLimiter
from redis.exceptions import RedisError


class FakeRedis:
    def __init__(self, result: list[int] | Exception) -> None:
        self.result = result
        self.calls: list[tuple[Any, ...]] = []

    async def eval(self, *args: Any) -> list[int]:
        self.calls.append(args)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


async def test_rate_limiter_allows_request_and_namespaces_key() -> None:
    redis = FakeRedis([1, 60_000])
    limiter = RateLimiter(redis, key_prefix="hazbit")  # type: ignore[arg-type]

    await limiter.enforce(RateLimit("login", 3, 60), "identity-hash")

    assert redis.calls[0][2] == "hazbit:rate:login:identity-hash"


async def test_rate_limiter_returns_retry_after() -> None:
    limiter = RateLimiter(FakeRedis([0, 1_001]), key_prefix="hazbit")  # type: ignore[arg-type]

    with pytest.raises(ApplicationError) as exc_info:
        await limiter.enforce(RateLimit("login", 3, 60), "identity-hash")

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "2"}


async def test_rate_limiter_fails_closed_when_redis_is_unavailable() -> None:
    limiter = RateLimiter(  # type: ignore[arg-type]
        FakeRedis(RedisError("unavailable")), key_prefix="hazbit"
    )

    with pytest.raises(ApplicationError) as exc_info:
        await limiter.enforce(RateLimit("login", 3, 60), "identity-hash")

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "rate_limit_unavailable"
