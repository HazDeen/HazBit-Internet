from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from remnawave_adapter.client import RemnawaveClient, RemnawaveClientError
from remnawave_adapter.config import Settings, get_settings
from remnawave_adapter.router import create_router
from remnawave_adapter.schemas import HealthResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = RemnawaveClient(resolved)
        app.state.remnawave_client = client
        try:
            yield
        finally:
            await client.close()

    app = FastAPI(
        title="Hazbit Remnawave Adapter",
        version="0.1.0",
        docs_url=None if resolved.environment == "production" else "/docs",
        lifespan=lifespan,
    )
    app.state.settings = resolved

    @app.exception_handler(RemnawaveClientError)
    async def remnawave_error(_: Request, exc: RemnawaveClientError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "detail": exc.detail, "retryable": exc.retryable},
        )

    @app.get("/health/live", response_model=HealthResponse)
    async def live() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/health/ready", response_model=HealthResponse)
    async def ready(request: Request) -> HealthResponse:
        client: RemnawaveClient = request.app.state.remnawave_client
        await client.health()
        return HealthResponse(status="ok")

    app.include_router(create_router())
    return app


app = create_app()
