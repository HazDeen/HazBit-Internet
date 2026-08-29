from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, Query, Request, Response, UploadFile, status

from app.modules.auth.dependencies import PrincipalDependency, require_permissions
from app.modules.auth.enums import Permission
from app.modules.auth.service import Principal
from app.modules.payments.dependencies import PaymentServiceDependency
from app.modules.payments.enums import ReviewDecision
from app.modules.payments.schemas import (
    CreatePaymentIntentRequest,
    EvidenceUploadResponse,
    PaymentResponse,
    ReviewPaymentRequest,
    ReviewQueueItem,
)
from app.modules.payments.service import PaymentClientContext

AdminPrincipal = Annotated[
    Principal,
    Depends(require_permissions(Permission.PAYMENTS_REVIEW)),
]


def create_payment_router() -> APIRouter:
    router = APIRouter(tags=["payments"])

    @router.post(
        "/payments/intents",
        response_model=PaymentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_intent(
        payload: CreatePaymentIntentRequest,
        request: Request,
        principal: PrincipalDependency,
        service: PaymentServiceDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
        ],
    ) -> PaymentResponse:
        return await service.create_intent(
            user_id=principal.user_id,
            plan_price_id=payload.plan_price_id,
            promo_code=payload.promo_code,
            idempotency_key=idempotency_key,
            client=_client_context(request),
        )

    @router.get("/payments/{payment_id}", response_model=PaymentResponse)
    async def get_payment(
        payment_id: UUID,
        principal: PrincipalDependency,
        service: PaymentServiceDependency,
    ) -> PaymentResponse:
        return await service.get_payment(user_id=principal.user_id, payment_id=payment_id)

    @router.post(
        "/payments/{payment_id}/evidence",
        response_model=EvidenceUploadResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def upload_evidence(
        payment_id: UUID,
        request: Request,
        principal: PrincipalDependency,
        service: PaymentServiceDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
        ],
        evidence: Annotated[UploadFile, File(description="JPEG, PNG, or WebP receipt image")],
    ) -> EvidenceUploadResponse:
        return await service.upload_evidence(
            user_id=principal.user_id,
            payment_id=payment_id,
            idempotency_key=idempotency_key,
            upload=evidence,
            client=_client_context(request),
        )

    @router.get("/admin/payments/review-queue", response_model=list[ReviewQueueItem])
    async def review_queue(
        principal: AdminPrincipal,
        service: PaymentServiceDependency,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> list[ReviewQueueItem]:
        del principal
        return await service.review_queue(limit=limit)

    @router.get("/admin/payments/evidence/{evidence_id}")
    async def review_evidence(
        evidence_id: UUID,
        principal: AdminPrincipal,
        service: PaymentServiceDependency,
    ) -> Response:
        del principal
        data, content_type = await service.get_review_evidence(evidence_id)
        return Response(
            content=data,
            media_type=content_type,
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.post("/admin/payments/{payment_id}/review", response_model=PaymentResponse)
    async def review_payment(
        payment_id: UUID,
        payload: ReviewPaymentRequest,
        principal: AdminPrincipal,
        service: PaymentServiceDependency,
    ) -> PaymentResponse:
        return await service.review_payment(
            payment_id=payment_id,
            reviewer_user_id=principal.user_id,
            decision=ReviewDecision(payload.decision),
            reason=payload.reason,
            expected_version=payload.expected_version,
        )

    return router


def _client_context(request: Request) -> PaymentClientContext:
    ip_address = request.client.host if request.client is not None else "0.0.0.0"  # noqa: S104
    user_agent = request.headers.get("user-agent")
    return PaymentClientContext(
        ip_address=ip_address,
        user_agent=user_agent[:1024] if user_agent else None,
        request_id=getattr(request.state, "request_id", None),
    )
