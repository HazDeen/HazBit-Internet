from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencies import SessionDependency
from app.core.config import Settings
from app.modules.auth.runtime import AuthRuntime
from app.modules.support.service import SupportService


def get_support_service(request: Request, session: SessionDependency) -> SupportService:
    settings = cast(Settings, request.app.state.settings)
    auth_runtime = cast(AuthRuntime, request.app.state.auth_runtime)
    return SupportService(
        session=session,
        settings=settings.support,
        rate_limiter=auth_runtime.rate_limiter,
    )


SupportServiceDependency = Annotated[SupportService, Depends(get_support_service)]
