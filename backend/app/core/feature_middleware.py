from __future__ import annotations

import json

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import FeatureSettings, RedisSettings
from app.core.features import FeatureControlStore, FeatureKey
from app.integrations.redis import RedisManager

_CUSTOMER_PREFIXES: tuple[tuple[str, FeatureKey], ...] = (
    ("/api/v1/billing", FeatureKey.BILLING),
    ("/api/v1/payments", FeatureKey.PAYMENT_AI),
    ("/api/v1/referrals", FeatureKey.REFERRALS),
    ("/api/v1/promo-codes", FeatureKey.PROMOTIONS),
    ("/api/v1/family", FeatureKey.FAMILIES),
    ("/api/v1/tickets", FeatureKey.SUPPORT),
    ("/api/v1/vpn", FeatureKey.VPN_PROVISIONING),
    ("/api/v1/devices", FeatureKey.VPN_PROVISIONING),
    ("/api/v1/bots", FeatureKey.TELEGRAM_BOTS),
)


class FeatureGateMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        features: FeatureSettings,
        redis_settings: RedisSettings,
    ) -> None:
        self.app = app
        self.features = features
        self.redis_settings = redis_settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path", ""))
        feature = next((key for prefix, key in _CUSTOMER_PREFIXES if path.startswith(prefix)), None)
        app = scope.get("app")
        redis = app.state.redis if app is not None and hasattr(app.state, "redis") else None
        if feature is None or not isinstance(redis, RedisManager):
            await self.app(scope, receive, send)
            return
        store = FeatureControlStore(redis.client, redis_settings=self.redis_settings)
        if await store.enabled(feature, self.features):
            await self.app(scope, receive, send)
            return
        body = json.dumps(
            {
                "type": "https://api.hazbit.example/problems/feature_paused",
                "title": "Service temporarily unavailable",
                "status": 503,
                "detail": "This service is temporarily paused by an administrator.",
                "instance": path,
                "code": "feature_paused",
                "feature": feature.value,
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    (b"content-type", b"application/problem+json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"retry-after", b"60"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
