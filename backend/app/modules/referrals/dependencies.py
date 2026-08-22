from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencies import SessionDependency
from app.core.config import Settings
from app.modules.auth.runtime import AuthRuntime
from app.modules.referrals.service import ReferralService


def get_referral_service(request: Request, session: SessionDependency) -> ReferralService:
    settings = cast(Settings, request.app.state.settings)
    auth_runtime = cast(AuthRuntime, request.app.state.auth_runtime)
    return ReferralService(
        session=session,
        settings=settings.referrals,
        rate_limiter=auth_runtime.rate_limiter,
        signal_hasher=auth_runtime.signal_hasher,
    )


ReferralServiceDependency = Annotated[ReferralService, Depends(get_referral_service)]
