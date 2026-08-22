from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.dependencies import SessionDependency
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.modules.auth.enums import Role
from app.modules.auth.runtime import AuthRuntime
from app.modules.auth.service import AuthService, Principal

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(request: Request, session: SessionDependency) -> AuthService:
    settings = cast(Settings, request.app.state.settings)
    runtime = cast(AuthRuntime, request.app.state.auth_runtime)
    return AuthService(
        session=session,
        settings=settings.auth,
        otp_codec=runtime.otp_codec,
        opaque_token_codec=runtime.opaque_token_codec,
        access_token_codec=runtime.access_token_codec,
        signal_hasher=runtime.signal_hasher,
        telegram_validator=runtime.telegram_validator,
        rate_limiter=runtime.rate_limiter,
        email_sender=runtime.email_sender,
    )


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_principal(
    service: AuthServiceDependency,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Principal:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise ApplicationError(
            code="authentication_required",
            detail="A Bearer access token is required.",
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await service.authenticate_access_token(credentials.credentials)


PrincipalDependency = Annotated[Principal, Depends(get_current_principal)]
RoleDependency = Callable[..., Coroutine[Any, Any, Principal]]


def require_roles(*required: Role) -> RoleDependency:
    required_roles = frozenset(required)

    async def role_checker(principal: PrincipalDependency) -> Principal:
        if not principal.roles.intersection(required_roles):
            raise ApplicationError(
                code="insufficient_permissions",
                detail="The authenticated user does not have the required role.",
                status_code=403,
            )
        return principal

    return role_checker
