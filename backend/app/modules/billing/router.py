from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response, status

from app.modules.auth.dependencies import PrincipalDependency
from app.modules.billing.dependencies import BillingServiceDependency
from app.modules.billing.schemas import (
    CreateWalletTopUpRequest,
    PlategaCallbackPayload,
    PurchaseFromWalletRequest,
    UpdateAutoRenewRequest,
    WalletPurchaseResponse,
    WalletResponse,
    WalletTopUpResponse,
)
from app.modules.billing.service import BillingClientContext


def create_billing_router() -> APIRouter:
    router = APIRouter(prefix="/billing", tags=["billing"])

    @router.get("/wallet", response_model=WalletResponse)
    async def wallet(
        principal: PrincipalDependency, service: BillingServiceDependency
    ) -> WalletResponse:
        return await service.wallet(principal.user_id)

    @router.post(
        "/top-ups", response_model=WalletTopUpResponse, status_code=status.HTTP_201_CREATED
    )
    async def create_top_up(
        payload: CreateWalletTopUpRequest,
        request: Request,
        principal: PrincipalDependency,
        service: BillingServiceDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
        ],
    ) -> WalletTopUpResponse:
        return await service.create_top_up(
            user_id=principal.user_id,
            amount_minor=payload.amount_minor,
            currency=payload.currency,
            payment_method=payload.payment_method,
            idempotency_key=idempotency_key,
            client=_client_context(request),
        )

    @router.get("/top-ups/{top_up_id}", response_model=WalletTopUpResponse)
    async def top_up(
        top_up_id: UUID,
        principal: PrincipalDependency,
        service: BillingServiceDependency,
    ) -> WalletTopUpResponse:
        return await service.top_up(principal.user_id, top_up_id)

    @router.post("/purchases", response_model=WalletPurchaseResponse)
    async def purchase(
        payload: PurchaseFromWalletRequest,
        request: Request,
        principal: PrincipalDependency,
        service: BillingServiceDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
        ],
    ) -> WalletPurchaseResponse:
        return await service.purchase(
            user_id=principal.user_id,
            plan_price_id=payload.plan_price_id,
            auto_renew=payload.auto_renew,
            idempotency_key=idempotency_key,
            client=_client_context(request),
        )

    @router.patch("/auto-renew", response_model=WalletResponse)
    async def update_auto_renew(
        payload: UpdateAutoRenewRequest,
        principal: PrincipalDependency,
        service: BillingServiceDependency,
    ) -> WalletResponse:
        return await service.update_auto_renew(principal.user_id, payload.enabled)

    @router.post("/platega/webhook", include_in_schema=False)
    async def platega_webhook(
        payload: PlategaCallbackPayload,
        service: BillingServiceDependency,
        merchant_id: Annotated[str, Header(alias="X-MerchantId", min_length=1)],
        secret: Annotated[str, Header(alias="X-Secret", min_length=1)],
    ) -> Response:
        await service.process_platega_callback(
            merchant_id=merchant_id,
            secret=secret,
            payload=payload,
        )
        return Response(status_code=status.HTTP_200_OK)

    return router


def _client_context(request: Request) -> BillingClientContext:
    ip_address = request.client.host if request.client is not None else "0.0.0.0"  # noqa: S104
    user_agent = request.headers.get("user-agent")
    return BillingClientContext(
        ip_address=ip_address,
        user_agent=user_agent[:1024] if user_agent else None,
        request_id=getattr(request.state, "request_id", None),
    )
