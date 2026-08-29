from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import FeatureSettings, RedisSettings


class FeatureKey(StrEnum):
    VPN_PROVISIONING = "vpn_provisioning"
    BILLING = "billing"
    PAYMENT_AI = "payment_ai"
    REFERRALS = "referrals"
    PROMOTIONS = "promotions"
    FAMILIES = "families"
    SUPPORT = "support"
    TELEGRAM_BOTS = "telegram_bots"


FEATURE_LABELS: dict[FeatureKey, tuple[str, str]] = {
    FeatureKey.VPN_PROVISIONING: ("VPN provisioning", "VLESS accounts and devices"),
    FeatureKey.BILLING: ("Billing", "Wallet, top-ups and renewals"),
    FeatureKey.PAYMENT_AI: ("Payment AI", "Gemini receipt analysis"),
    FeatureKey.REFERRALS: ("Referrals", "Codes, claims and rewards"),
    FeatureKey.PROMOTIONS: ("Promo codes", "Preview and redemption"),
    FeatureKey.FAMILIES: ("Family groups", "Invitations and shared access"),
    FeatureKey.SUPPORT: ("Support", "Customer tickets and messages"),
    FeatureKey.TELEGRAM_BOTS: ("Telegram bots", "Customer and operations webhooks"),
}


@dataclass(frozen=True, slots=True)
class FeatureState:
    key: FeatureKey
    configured: bool
    runtime_enabled: bool

    @property
    def enabled(self) -> bool:
        return self.configured and self.runtime_enabled


class FeatureControlStore:
    def __init__(self, redis: Redis, *, redis_settings: RedisSettings) -> None:
        self._redis = redis
        self._key = f"{redis_settings.key_prefix}:operations:features"

    async def states(self, configured: FeatureSettings) -> list[FeatureState]:
        overrides: dict[bytes, bytes] = {}
        try:
            overrides = await cast(Awaitable[dict[bytes, bytes]], self._redis.hgetall(self._key))
        except RedisError:
            # Deployment configuration remains the safe source of truth when Redis is down.
            pass
        return [
            FeatureState(
                key=key,
                configured=bool(getattr(configured, key.value)),
                runtime_enabled=overrides.get(key.value.encode(), b"1") != b"0",
            )
            for key in FeatureKey
        ]

    async def set_runtime(self, key: FeatureKey, enabled: bool) -> None:
        await cast(
            Awaitable[int],
            self._redis.hset(self._key, key.value, "1" if enabled else "0"),
        )

    async def enabled(self, key: FeatureKey, configured: FeatureSettings) -> bool:
        if not bool(getattr(configured, key.value)):
            return False
        try:
            override = await cast(Awaitable[bytes | None], self._redis.hget(self._key, key.value))
        except RedisError:
            return True
        return override != b"0"
