from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.modules.auth.dependencies import PrincipalDependency, require_roles
from app.modules.auth.enums import Role
from app.modules.auth.service import Principal
from app.modules.promotions.dependencies import PromotionServiceDependency
from app.modules.promotions.schemas import (
    AdminPromoCodeResponse,
    ArchivePromoCodeRequest,
    CreatePromoCodeRequest,
    PreviewPromoCodeRequest,
    PromoPreviewResponse,
    PromoRedemptionResponse,
    RedeemPromoCodeRequest,
    UpdatePromoCodeRequest,
)
from app.modules.promotions.service import PromoClientContext

AdminPrincipal = Annotated[
    Principal,
    Depends(require_roles(Role.ADMIN, Role.SUPER_ADMIN)),
]


def create_promotion_router() -> APIRouter:
    router = APIRouter(tags=["promo-codes"])

    @router.post("/promo-codes/preview", response_model=PromoPreviewResponse)
    async def preview(
        payload: PreviewPromoCodeRequest,
        principal: PrincipalDependency,
        service: PromotionServiceDependency,
    ) -> PromoPreviewResponse:
        return await service.preview(
            user_id=principal.user_id,
            code_value=payload.code,
            plan_price_id=payload.plan_price_id,
            plan_version_id=payload.plan_version_id,
        )

    @router.post(
        "/promo-codes/redeem",
        response_model=PromoRedemptionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def redeem(
        payload: RedeemPromoCodeRequest,
        request: Request,
        principal: PrincipalDependency,
        service: PromotionServiceDependency,
    ) -> PromoRedemptionResponse:
        return await service.redeem_free_days(
            user_id=principal.user_id,
            code_value=payload.code,
            plan_version_id=payload.plan_version_id,
            client=_client_context(request),
        )

    @router.get("/promo-codes/redemptions", response_model=list[PromoRedemptionResponse])
    async def redemptions(
        principal: PrincipalDependency,
        service: PromotionServiceDependency,
    ) -> list[PromoRedemptionResponse]:
        return await service.user_redemptions(principal.user_id)

    @router.post(
        "/admin/promo-codes",
        response_model=AdminPromoCodeResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_code(
        payload: CreatePromoCodeRequest,
        principal: AdminPrincipal,
        service: PromotionServiceDependency,
    ) -> AdminPromoCodeResponse:
        return await service.create_code(payload=payload, admin_user_id=principal.user_id)

    @router.get("/admin/promo-codes", response_model=list[AdminPromoCodeResponse])
    async def list_codes(
        principal: AdminPrincipal,
        service: PromotionServiceDependency,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> list[AdminPromoCodeResponse]:
        del principal
        return await service.list_codes(limit)

    @router.patch("/admin/promo-codes/{promo_id}", response_model=AdminPromoCodeResponse)
    async def update_code(
        promo_id: UUID,
        payload: UpdatePromoCodeRequest,
        principal: AdminPrincipal,
        service: PromotionServiceDependency,
    ) -> AdminPromoCodeResponse:
        return await service.update_code(
            promo_id=promo_id, payload=payload, admin_user_id=principal.user_id
        )

    @router.delete("/admin/promo-codes/{promo_id}", response_model=AdminPromoCodeResponse)
    async def archive_code(
        promo_id: UUID,
        payload: ArchivePromoCodeRequest,
        principal: AdminPrincipal,
        service: PromotionServiceDependency,
    ) -> AdminPromoCodeResponse:
        return await service.archive_code(
            promo_id=promo_id,
            reason=payload.reason,
            admin_user_id=principal.user_id,
        )

    return router


def _client_context(request: Request) -> PromoClientContext:
    ip_address = request.client.host if request.client is not None else "0.0.0.0"  # noqa: S104
    user_agent = request.headers.get("user-agent")
    return PromoClientContext(
        ip_address=ip_address,
        user_agent=user_agent[:1024] if user_agent else None,
        request_id=getattr(request.state, "request_id", None),
    )
