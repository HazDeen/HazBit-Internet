from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencies import SessionDependency
from app.core.config import Settings
from app.modules.auth.runtime import AuthRuntime
from app.modules.payments.runtime import PaymentRuntime
from app.modules.payments.service import PaymentService


def get_payment_service(request: Request, session: SessionDependency) -> PaymentService:
    settings = cast(Settings, request.app.state.settings)
    runtime = cast(PaymentRuntime, request.app.state.payment_runtime)
    auth_runtime = cast(AuthRuntime, request.app.state.auth_runtime)
    return PaymentService(
        session=session,
        settings=settings.payments,
        promo_settings=settings.promotions,
        storage=runtime.storage,
        rate_limiter=auth_runtime.rate_limiter,
    )


PaymentServiceDependency = Annotated[PaymentService, Depends(get_payment_service)]
