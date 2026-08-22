from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger


@dataclass(slots=True)
class ApplicationError(Exception):
    code: str
    detail: str
    status_code: int = 400
    headers: dict[str, str] | None = None


def _problem(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str,
    code: str,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://api.hazbit.example/problems/{code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
        "code": code,
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(
        body,
        status_code=status_code,
        media_type="application/problem+json",
        headers=headers,
    )


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        return _problem(
            request,
            status_code=exc.status_code,
            title="Application error",
            detail=exc.detail,
            code=exc.code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = [
            {
                "location": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return _problem(
            request,
            status_code=422,
            title="Validation error",
            detail="The request payload is invalid.",
            code="validation_error",
            errors=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        return _problem(
            request,
            status_code=exc.status_code,
            title="HTTP error",
            detail=str(exc.detail),
            code="http_error",
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        get_logger(component="exceptions").exception(
            "unhandled_exception",
            exception_type=type(exc).__name__,
        )
        return _problem(
            request,
            status_code=500,
            title="Internal server error",
            detail="An unexpected error occurred.",
            code="internal_error",
        )
