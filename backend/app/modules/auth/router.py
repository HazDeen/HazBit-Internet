from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Header, Request, Response, status

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.modules.auth.dependencies import AuthServiceDependency, PrincipalDependency
from app.modules.auth.schemas import (
    AuthenticatedUser,
    EmailStartRequest,
    EmailVerifyRequest,
    MessageResponse,
    TelegramAuthRequest,
    TokenResponse,
)
from app.modules.auth.service import AuthResult, AuthService, ClientContext


def create_auth_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["authentication"])

    @router.post(
        "/email/start",
        response_model=MessageResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_email_auth(
        payload: EmailStartRequest,
        request: Request,
        service: AuthServiceDependency,
    ) -> MessageResponse:
        await service.start_email_auth(
            email=str(payload.email),
            client=_client_context(request, payload.device_fingerprint),
        )
        return MessageResponse(
            message="If the address can receive mail, a verification code has been sent."
        )

    @router.post("/email/verify", response_model=TokenResponse)
    async def verify_email(
        payload: EmailVerifyRequest,
        request: Request,
        response: Response,
        service: AuthServiceDependency,
    ) -> TokenResponse:
        result = await service.verify_email(
            email=str(payload.email),
            code=payload.code,
            client=_client_context(request, payload.device_fingerprint),
        )
        _set_session_cookies(response, result, settings)
        return _token_response(result)

    @router.post("/telegram", response_model=TokenResponse)
    async def authenticate_telegram(
        payload: TelegramAuthRequest,
        request: Request,
        response: Response,
        service: AuthServiceDependency,
    ) -> TokenResponse:
        result = await service.authenticate_telegram(
            init_data=payload.init_data,
            client=_client_context(request, payload.device_fingerprint),
        )
        _set_session_cookies(response, result, settings)
        return _token_response(result)

    @router.post("/refresh", response_model=TokenResponse)
    async def refresh_session(
        request: Request,
        response: Response,
        service: AuthServiceDependency,
        refresh_token: str | None = Cookie(
            default=None,
            alias=settings.auth.cookies.refresh_name,
        ),
        csrf_cookie: str | None = Cookie(
            default=None,
            alias=settings.auth.cookies.csrf_name,
        ),
        csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> TokenResponse:
        AuthService.verify_csrf(csrf_cookie, csrf_header)
        if not refresh_token:
            raise ApplicationError(
                code="invalid_refresh_token",
                detail="The refresh token is invalid or expired.",
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        result = await service.refresh(
            refresh_token=refresh_token,
            client=_client_context(request, None),
        )
        _set_session_cookies(response, result, settings)
        return _token_response(result)

    @router.post("/logout", response_model=MessageResponse)
    async def logout(
        request: Request,
        response: Response,
        service: AuthServiceDependency,
        refresh_token: str | None = Cookie(
            default=None,
            alias=settings.auth.cookies.refresh_name,
        ),
        csrf_cookie: str | None = Cookie(
            default=None,
            alias=settings.auth.cookies.csrf_name,
        ),
        csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> MessageResponse:
        AuthService.verify_csrf(csrf_cookie, csrf_header)
        if refresh_token:
            await service.logout(
                refresh_token=refresh_token,
                client=_client_context(request, None),
            )
        _clear_session_cookies(response, settings)
        return MessageResponse(message="Session closed.")

    @router.get("/me", response_model=AuthenticatedUser)
    async def current_user(
        principal: PrincipalDependency,
        service: AuthServiceDependency,
    ) -> AuthenticatedUser:
        return await service.current_user(principal)

    return router


def _client_context(request: Request, fingerprint: str | None) -> ClientContext:
    ip_address = (
        request.client.host if request.client is not None else "0.0.0.0"  # noqa: S104
    )
    user_agent = request.headers.get("user-agent")
    return ClientContext(
        ip_address=ip_address,
        user_agent=user_agent[:1024] if user_agent else None,
        device_fingerprint=fingerprint,
        request_id=getattr(request.state, "request_id", None),
    )


def _token_response(result: AuthResult) -> TokenResponse:
    return TokenResponse(
        access_token=result.access_token,
        expires_in=result.access_expires_in,
        user=result.user,
    )


def _set_session_cookies(response: Response, result: AuthResult, settings: Settings) -> None:
    cookies = settings.auth.cookies
    max_age = max(0, int((result.refresh_expires_at - datetime.now(UTC)).total_seconds()))
    path = f"{settings.api_v1_prefix}/auth"
    response.set_cookie(
        key=cookies.refresh_name,
        value=result.refresh_token,
        max_age=max_age,
        expires=result.refresh_expires_at,
        path=path,
        domain=cookies.domain,
        secure=cookies.secure,
        httponly=True,
        samesite=cookies.same_site,
    )
    response.set_cookie(
        key=cookies.csrf_name,
        value=result.csrf_token,
        max_age=max_age,
        expires=result.refresh_expires_at,
        path=path,
        domain=cookies.domain,
        secure=cookies.secure,
        httponly=False,
        samesite=cookies.same_site,
    )


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    cookies = settings.auth.cookies
    path = f"{settings.api_v1_prefix}/auth"
    response.delete_cookie(
        cookies.refresh_name,
        path=path,
        domain=cookies.domain,
        secure=cookies.secure,
        httponly=True,
        samesite=cookies.same_site,
    )
    response.delete_cookie(
        cookies.csrf_name,
        path=path,
        domain=cookies.domain,
        secure=cookies.secure,
        httponly=False,
        samesite=cookies.same_site,
    )
