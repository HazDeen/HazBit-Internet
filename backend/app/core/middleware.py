from __future__ import annotations

from time import perf_counter
from uuid import UUID, uuid4

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger


def _request_id(candidate: str | None) -> str:
    if candidate is None:
        return str(uuid4())
    try:
        return str(UUID(candidate))
    except ValueError:
        return str(uuid4())


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, request_id_header: str = "X-Request-ID") -> None:
        self.app = app
        self.header_name = request_id_header
        self.header_name_bytes = request_id_header.lower().encode("latin-1")
        self.logger = get_logger(component="http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        incoming = headers.get(self.header_name_bytes)
        request_id = _request_id(incoming.decode("latin-1") if incoming else None)
        scope.setdefault("state", {})["request_id"] = UUID(request_id)
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "")
        started = perf_counter()
        status_code = 500

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            http_method=method,
            http_path=path,
        )

        async def send_with_context(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.append((self.header_name_bytes, request_id.encode("latin-1")))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        finally:
            duration_ms = round((perf_counter() - started) * 1000, 2)
            self.logger.info(
                "http_request_completed",
                status_code=status_code,
                duration_ms=duration_ms,
            )
            structlog.contextvars.clear_contextvars()
