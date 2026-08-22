from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencies import RedisDependency, SessionDependency
from app.core.config import Settings
from app.modules.auth.runtime import AuthRuntime
from app.modules.bots.idempotency import TelegramUpdateGate
from app.modules.bots.runtime import TelegramBotsRuntime
from app.modules.bots.service import TelegramBotService
from app.modules.payments.runtime import PaymentRuntime
from app.modules.payments.service import PaymentService


def get_telegram_bot_service(
    request: Request,
    session: SessionDependency,
) -> TelegramBotService:
    settings = cast(Settings, request.app.state.settings)
    auth_runtime = cast(AuthRuntime, request.app.state.auth_runtime)
    payment_runtime = cast(PaymentRuntime, request.app.state.payment_runtime)
    bot_runtime = cast(TelegramBotsRuntime, request.app.state.telegram_bots_runtime)
    payment_service = PaymentService(
        session=session,
        settings=settings.payments,
        promo_settings=settings.promotions,
        storage=payment_runtime.storage,
        rate_limiter=auth_runtime.rate_limiter,
    )
    return TelegramBotService(
        session=session,
        settings=settings,
        rate_limiter=auth_runtime.rate_limiter,
        customer_client=bot_runtime.customer,
        operations_client=bot_runtime.operations,
        callbacks=bot_runtime.callbacks,
        payment_service=payment_service,
    )


def get_telegram_update_gate(
    request: Request,
    redis: RedisDependency,
) -> TelegramUpdateGate:
    settings = cast(Settings, request.app.state.settings)
    return TelegramUpdateGate(
        redis.client,
        key_prefix=settings.redis.key_prefix,
        lock_seconds=settings.telegram_bots.update_lock_seconds,
        receipt_ttl_seconds=settings.telegram_bots.update_receipt_ttl_seconds,
    )


TelegramBotServiceDependency = Annotated[TelegramBotService, Depends(get_telegram_bot_service)]
TelegramUpdateGateDependency = Annotated[TelegramUpdateGate, Depends(get_telegram_update_gate)]
