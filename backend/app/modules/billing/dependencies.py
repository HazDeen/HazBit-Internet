from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencies import SessionDependency
from app.core.config import Settings
from app.modules.auth.runtime import AuthRuntime
from app.modules.billing.runtime import BillingRuntime
from app.modules.billing.service import BillingService


def get_billing_service(request: Request, session: SessionDependency) -> BillingService:
    settings = cast(Settings, request.app.state.settings)
    billing_runtime = cast(BillingRuntime, request.app.state.billing_runtime)
    auth_runtime = cast(AuthRuntime, request.app.state.auth_runtime)
    return BillingService(
        session=session,
        settings=settings.billing,
        platega=billing_runtime.platega,
        rate_limiter=auth_runtime.rate_limiter,
    )


BillingServiceDependency = Annotated[BillingService, Depends(get_billing_service)]
