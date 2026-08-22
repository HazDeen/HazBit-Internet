from __future__ import annotations

import hmac
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.logging import get_logger
from app.modules.bots.dependencies import (
    TelegramBotServiceDependency,
    TelegramUpdateGateDependency,
)
from app.modules.bots.schemas import TelegramUpdate

BotKind = Literal["customer", "operations"]


def create_telegram_bots_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/bots", tags=["telegram-bots"])
    logger = get_logger(component="telegram_webhook")

    async def process(
        *,
        kind: BotKind,
        update: TelegramUpdate,
        supplied_secret: str | None,
        service: TelegramBotServiceDependency,
        gate: TelegramUpdateGateDependency,
    ) -> JSONResponse:
        expected = (
            settings.telegram_bots.customer_webhook_secret.get_secret_value()
            if kind == "customer"
            else settings.telegram_bots.operations_webhook_secret.get_secret_value()
        )
        if not supplied_secret or not hmac.compare_digest(supplied_secret, expected):
            raise ApplicationError(
                "telegram_webhook_forbidden", "Telegram webhook secret is invalid.", 403
            )
        if not await gate.begin(kind, update.update_id):
            return JSONResponse({"ok": True, "duplicate": True})
        try:
            if kind == "customer":
                await service.customer_update(update)
            else:
                await service.operations_update(update)
        except ApplicationError as exc:
            logger.warning(
                "telegram_update_rejected",
                bot=kind,
                update_id=update.update_id,
                code=exc.code,
            )
            await gate.complete(kind, update.update_id)
            return JSONResponse({"ok": True})
        except Exception:
            await gate.release(kind, update.update_id)
            raise
        await gate.complete(kind, update.update_id)
        return JSONResponse({"ok": True})

    @router.post("/customer/webhook", include_in_schema=False)
    async def customer_webhook(
        request: Request,
        update: TelegramUpdate,
        service: TelegramBotServiceDependency,
        gate: TelegramUpdateGateDependency,
        secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
    ) -> JSONResponse:
        del request
        return await process(
            kind="customer",
            update=update,
            supplied_secret=secret,
            service=service,
            gate=gate,
        )

    @router.post("/operations/webhook", include_in_schema=False)
    async def operations_webhook(
        request: Request,
        update: TelegramUpdate,
        service: TelegramBotServiceDependency,
        gate: TelegramUpdateGateDependency,
        secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
    ) -> JSONResponse:
        del request
        return await process(
            kind="operations",
            update=update,
            supplied_secret=secret,
            service=service,
            gate=gate,
        )

    return router
