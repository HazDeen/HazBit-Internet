from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status

from app.modules.auth.dependencies import PrincipalDependency, require_roles
from app.modules.auth.enums import Role
from app.modules.auth.service import Principal
from app.modules.referrals.dependencies import ReferralServiceDependency
from app.modules.referrals.schemas import (
    ClaimReferralRequest,
    ReferralClaimResponse,
    ReferralCodeResponse,
    ReferralReviewItem,
    ReferralStatisticsResponse,
    ReviewReferralRequest,
)
from app.modules.referrals.service import ReferralClientContext

AdminPrincipal = Annotated[
    Principal,
    Depends(require_roles(Role.ADMIN, Role.SUPER_ADMIN)),
]


def create_referral_router() -> APIRouter:
    router = APIRouter(tags=["referrals"])

    @router.post("/referrals/code", response_model=ReferralCodeResponse)
    async def get_or_create_code(
        principal: PrincipalDependency,
        service: ReferralServiceDependency,
    ) -> ReferralCodeResponse:
        return await service.get_or_create_code(principal.user_id)

    @router.post(
        "/referrals/claim",
        response_model=ReferralClaimResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def claim_referral(
        payload: ClaimReferralRequest,
        request: Request,
        principal: PrincipalDependency,
        service: ReferralServiceDependency,
        device_fingerprint: Annotated[
            str | None,
            Header(alias="X-Device-Fingerprint", min_length=8, max_length=512),
        ] = None,
    ) -> ReferralClaimResponse:
        return await service.claim(
            user_id=principal.user_id,
            code_value=payload.code,
            client=_client_context(request, device_fingerprint),
        )

    @router.get("/referrals/statistics", response_model=ReferralStatisticsResponse)
    async def statistics(
        principal: PrincipalDependency,
        service: ReferralServiceDependency,
    ) -> ReferralStatisticsResponse:
        return await service.statistics(principal.user_id)

    @router.get("/admin/referrals/review-queue", response_model=list[ReferralReviewItem])
    async def review_queue(
        principal: AdminPrincipal,
        service: ReferralServiceDependency,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> list[ReferralReviewItem]:
        del principal
        return await service.review_queue(limit)

    @router.post("/admin/referrals/{referral_id}/review", response_model=ReferralClaimResponse)
    async def review_referral(
        referral_id: UUID,
        payload: ReviewReferralRequest,
        principal: AdminPrincipal,
        service: ReferralServiceDependency,
    ) -> ReferralClaimResponse:
        return await service.review(
            referral_id=referral_id,
            reviewer_user_id=principal.user_id,
            decision=payload.decision,
            reason=payload.reason,
        )

    return router


def _client_context(request: Request, device_fingerprint: str | None) -> ReferralClientContext:
    ip_address = request.client.host if request.client is not None else "0.0.0.0"  # noqa: S104
    user_agent = request.headers.get("user-agent")
    return ReferralClientContext(
        ip_address=ip_address,
        device_fingerprint=device_fingerprint,
        user_agent=user_agent[:1024] if user_agent else None,
        request_id=getattr(request.state, "request_id", None),
    )
