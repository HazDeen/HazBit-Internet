from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.modules.auth.dependencies import PrincipalDependency
from app.modules.portal.dependencies import PortalServiceDependency
from app.modules.portal.schemas import (
    PortalOverviewResponse,
    PortalPaymentResponse,
    PortalPlanResponse,
)


def create_portal_router() -> APIRouter:
    router = APIRouter(prefix="/portal", tags=["customer-portal"])

    @router.get("/overview", response_model=PortalOverviewResponse)
    async def overview(
        principal: PrincipalDependency, service: PortalServiceDependency
    ) -> PortalOverviewResponse:
        return await service.overview(principal.user_id)

    @router.get("/plans", response_model=list[PortalPlanResponse])
    async def plans(
        principal: PrincipalDependency, service: PortalServiceDependency
    ) -> list[PortalPlanResponse]:
        del principal
        return await service.catalog()

    @router.get("/payments", response_model=list[PortalPaymentResponse])
    async def payments(
        principal: PrincipalDependency,
        service: PortalServiceDependency,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> list[PortalPaymentResponse]:
        return await service.payments(principal.user_id, limit)

    return router
