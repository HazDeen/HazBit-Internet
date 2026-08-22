from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.health import create_health_router
from app.api.router import create_api_router
from app.core.config import Settings, get_settings
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.database.session import DatabaseManager
from app.integrations.redis import RedisManager
from app.modules.auth.runtime import create_auth_runtime
from app.modules.bots.runtime import create_telegram_bots_runtime
from app.modules.payments.runtime import create_payment_runtime
from app.modules.vpn.runtime import create_vpn_runtime


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings)
    logger = get_logger(component="lifecycle")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = DatabaseManager(resolved_settings.database)
        redis = RedisManager(resolved_settings.redis)
        app.state.database = database
        app.state.redis = redis
        app.state.auth_runtime = create_auth_runtime(resolved_settings, redis)
        app.state.telegram_bots_runtime = create_telegram_bots_runtime(resolved_settings)
        app.state.vpn_runtime = create_vpn_runtime(resolved_settings)
        app.state.payment_runtime = create_payment_runtime(resolved_settings)
        logger.info(
            "application_started",
            environment=resolved_settings.environment,
            database=resolved_settings.database.safe_url(),
            redis=resolved_settings.redis.safe_url(),
        )
        try:
            yield
        finally:
            await app.state.payment_runtime.extractor.close()
            await app.state.payment_runtime.storage.close()
            await app.state.telegram_bots_runtime.close()
            await app.state.vpn_runtime.adapter.close()
            await redis.dispose()
            await database.dispose()
            logger.info("application_stopped")

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        debug=resolved_settings.debug,
        docs_url="/docs" if resolved_settings.docs_enabled else None,
        redoc_url="/redoc" if resolved_settings.docs_enabled else None,
        openapi_url="/openapi.json" if resolved_settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Request-ID",
            "X-Device-Fingerprint",
        ],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=resolved_settings.allowed_hosts)
    app.add_middleware(
        RequestContextMiddleware,
        request_id_header=resolved_settings.request_id_header,
    )
    install_exception_handlers(app)
    app.include_router(create_health_router(resolved_settings))
    app.include_router(create_api_router(resolved_settings))
    return app


app = create_app()
