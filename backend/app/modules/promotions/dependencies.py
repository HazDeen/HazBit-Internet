from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencies import SessionDependency
from app.core.config import Settings
from app.modules.auth.runtime import AuthRuntime
from app.modules.promotions.service import PromotionService


def get_promotion_service(request: Request, session: SessionDependency) -> PromotionService:
    settings = cast(Settings, request.app.state.settings)
    auth_runtime = cast(AuthRuntime, request.app.state.auth_runtime)
    return PromotionService(
        session=session,
        settings=settings.promotions,
        rate_limiter=auth_runtime.rate_limiter,
    )


PromotionServiceDependency = Annotated[PromotionService, Depends(get_promotion_service)]
