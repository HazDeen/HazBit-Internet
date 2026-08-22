from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencies import SessionDependency
from app.core.config import Settings
from app.modules.auth.runtime import AuthRuntime
from app.modules.families.service import FamilyService


def get_family_service(request: Request, session: SessionDependency) -> FamilyService:
    settings = cast(Settings, request.app.state.settings)
    runtime = cast(AuthRuntime, request.app.state.auth_runtime)
    return FamilyService(
        session=session,
        settings=settings.families,
        rate_limiter=runtime.rate_limiter,
        token_codec=runtime.opaque_token_codec,
        signal_hasher=runtime.signal_hasher,
    )


FamilyServiceDependency = Annotated[FamilyService, Depends(get_family_service)]
