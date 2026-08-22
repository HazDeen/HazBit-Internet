from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from typing import Any
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PaymentSettings, PromoSettings
from app.core.errors import ApplicationError
from app.modules.auth.models import AuditLog
from app.modules.auth.rate_limit import RateLimit, RateLimiter
from app.modules.payments.approval import approve_payment
from app.modules.payments.enums import PaymentStatus, ReviewDecision
from app.modules.payments.evidence import normalize_evidence
from app.modules.payments.models import (
    Payment,
    PaymentEvidence,
    PaymentReview,
    PlanPrice,
    StorageObject,
)
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import (
    EvidenceUploadResponse,
    PaymentAnalysisSummary,
    PaymentResponse,
    ReceiptExtraction,
    ReviewQueueItem,
)
from app.modules.payments.storage import ObjectStorage
from app.modules.promotions.repository import PromotionRepository
from app.modules.promotions.service import PromotionService

PAYMENT_INTENT_USER = RateLimit("payment_intent_user", 10, 3600)
PAYMENT_UPLOAD_USER = RateLimit("payment_upload_user", 8, 3600)


@dataclass(frozen=True, slots=True)
class PaymentClientContext:
    ip_address: str
    user_agent: str | None
    request_id: UUID | None


class PaymentService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: PaymentSettings,
        promo_settings: PromoSettings | None = None,
        storage: ObjectStorage,
        rate_limiter: RateLimiter,
    ) -> None:
        self._session = session
        self._settings = settings
        self._promo_settings = promo_settings or PromoSettings()
        self._storage = storage
        self._rate_limiter = rate_limiter
        self._repository = PaymentRepository(session)
        self._promotion_repository = PromotionRepository(session)

    async def create_intent(
        self,
        *,
        user_id: UUID,
        plan_price_id: UUID,
        promo_code: str | None = None,
        idempotency_key: str,
        client: PaymentClientContext,
    ) -> PaymentResponse:
        await self._rate_limiter.enforce(PAYMENT_INTENT_USER, str(user_id))
        promo_code = promo_code.strip().upper() if promo_code else None
        now = datetime.now(UTC)
        scoped_key = f"payment:intent:{user_id}:{idempotency_key}"
        async with self._session.begin():
            await self._repository.serialize_key(scoped_key)
            existing = await self._repository.payment_by_key(user_id, idempotency_key)
            if existing is not None:
                if existing.plan_price_id != plan_price_id:
                    raise self._idempotency_conflict()
                existing_promo = await self._promotion_repository.promo_details_for_payment(
                    existing.id
                )
                existing_code = existing_promo[1].code if existing_promo is not None else None
                if existing_code != promo_code:
                    raise self._idempotency_conflict()
                return await self._response(existing)
            price = await self._repository.active_plan_price(plan_price_id, now)
            if price is None:
                raise ApplicationError("plan_price_not_found", "Plan price not found.", 404)
            if price.amount_minor <= 0:
                raise ApplicationError(
                    "plan_price_not_payable",
                    "This plan price does not require a bank-transfer payment.",
                    409,
                )
            payment = Payment(
                user_id=user_id,
                plan_price_id=price.id,
                status=PaymentStatus.AWAITING_UPLOAD.value,
                expected_amount_minor=price.amount_minor,
                currency=price.currency,
                expected_recipient=self._settings.expected_recipient,
                idempotency_key=idempotency_key,
                expires_at=now + timedelta(minutes=self._settings.intent_ttl_minutes),
                version=1,
            )
            self._session.add(payment)
            await self._session.flush()
            redemption = None
            if promo_code is not None:
                redemption = await PromotionService(
                    session=self._session,
                    settings=self._promo_settings,
                    rate_limiter=self._rate_limiter,
                ).apply_discount_to_payment(
                    user_id=user_id,
                    code_value=promo_code,
                    payment=payment,
                    price=price,
                    now=now,
                )
            self._audit(
                user_id=user_id,
                action="payment.intent_created",
                payment=payment,
                client=client,
                after={
                    "status": payment.status,
                    "plan_price_id": str(plan_price_id),
                    "amount_minor": payment.expected_amount_minor,
                    "original_amount_minor": price.amount_minor,
                    "promo_redemption_id": str(redemption.id) if redemption else None,
                    "currency": payment.currency,
                },
            )
            return await self._response(payment)

    async def get_payment(self, *, user_id: UUID, payment_id: UUID) -> PaymentResponse:
        payment = await self._repository.payment_for_user(payment_id, user_id)
        if payment is None:
            raise ApplicationError("payment_not_found", "Payment not found.", 404)
        return await self._response(payment)

    async def upload_evidence(
        self,
        *,
        user_id: UUID,
        payment_id: UUID,
        idempotency_key: str,
        upload: UploadFile,
        client: PaymentClientContext,
    ) -> EvidenceUploadResponse:
        await self._rate_limiter.enforce(PAYMENT_UPLOAD_USER, str(user_id))
        evidence_data = await normalize_evidence(upload, self._settings)
        async with self._session.begin():
            payment = await self._repository.payment_for_user(payment_id, user_id)
            if payment is None:
                raise ApplicationError("payment_not_found", "Payment not found.", 404)
            existing_evidence = await self._repository.latest_evidence(payment.id)
            if existing_evidence is not None:
                evidence, stored = existing_evidence
                if stored.sha256 == evidence_data.sha256:
                    return EvidenceUploadResponse(
                        payment=await self._response(payment),
                        evidence_id=evidence.id,
                        sha256=stored.sha256.hex(),
                    )
                raise ApplicationError(
                    "payment_evidence_already_uploaded",
                    "Different evidence has already been uploaded for this payment.",
                    409,
                )
            self._validate_upload_state(payment)

        digest = evidence_data.sha256.hex()
        object_key = f"payments/{user_id}/{payment_id}/{digest}.jpg"
        try:
            await self._storage.put(object_key, evidence_data.data, evidence_data.content_type)
        except Exception as exc:
            raise ApplicationError(
                "payment_storage_unavailable",
                "Payment evidence storage is temporarily unavailable.",
                503,
            ) from exc

        try:
            async with self._session.begin():
                await self._repository.serialize_key(
                    f"payment:evidence:{user_id}:{payment_id}:{idempotency_key}"
                )
                locked = await self._repository.payment_for_user(
                    payment_id, user_id, for_update=True
                )
                if locked is None:
                    raise ApplicationError("payment_not_found", "Payment not found.", 404)
                raced = await self._repository.latest_evidence(locked.id)
                if raced is not None:
                    raced_evidence, raced_object = raced
                    if raced_object.sha256 == evidence_data.sha256:
                        return EvidenceUploadResponse(
                            payment=await self._response(locked),
                            evidence_id=raced_evidence.id,
                            sha256=raced_object.sha256.hex(),
                        )
                    raise ApplicationError(
                        "payment_evidence_already_uploaded",
                        "Different evidence has already been uploaded for this payment.",
                        409,
                    )
                self._validate_upload_state(locked)
                storage_object = StorageObject(
                    owner_user_id=user_id,
                    bucket=self._settings.storage.bucket,
                    object_key=object_key,
                    original_filename=self._safe_filename(upload.filename),
                    content_type=evidence_data.content_type,
                    size_bytes=len(evidence_data.data),
                    sha256=evidence_data.sha256,
                    status="clean",
                    retention_until=datetime.now(UTC)
                    + timedelta(days=self._settings.evidence_retention_days),
                )
                self._session.add(storage_object)
                await self._session.flush()
                evidence = PaymentEvidence(
                    payment_id=locked.id,
                    storage_object_id=storage_object.id,
                    evidence_type="screenshot",
                )
                self._session.add(evidence)
                locked.status = PaymentStatus.UPLOADED.value
                locked.uploaded_at = datetime.now(UTC)
                locked.version += 1
                await self._session.flush()
                self._audit(
                    user_id=user_id,
                    action="payment.evidence_uploaded",
                    payment=locked,
                    client=client,
                    after={
                        "status": locked.status,
                        "evidence_id": str(evidence.id),
                        "sha256": digest,
                    },
                )
                return EvidenceUploadResponse(
                    payment=await self._response(locked),
                    evidence_id=evidence.id,
                    sha256=digest,
                )
        except Exception:
            await self._storage.delete(object_key)
            raise

    async def review_queue(self, *, limit: int = 50) -> list[ReviewQueueItem]:
        payments = list(
            (
                await self._session.scalars(
                    select(Payment)
                    .where(Payment.status == PaymentStatus.MANUAL_REVIEW.value)
                    .order_by(Payment.created_at)
                    .limit(limit)
                )
            ).all()
        )
        result: list[ReviewQueueItem] = []
        for payment in payments:
            evidence_row = await self._repository.latest_evidence(payment.id)
            if evidence_row is None:
                continue
            evidence, storage = evidence_row
            analysis = await self._repository.latest_analysis(payment.id)
            extracted = None
            if analysis is not None and analysis.status == "succeeded":
                extracted = ReceiptExtraction.model_validate(analysis.extracted_data)
            result.append(
                ReviewQueueItem(
                    payment=await self._response(payment),
                    extracted=extracted,
                    evidence_id=evidence.id,
                    evidence_content_type=storage.content_type,
                    evidence_uploaded_at=evidence.uploaded_at,
                )
            )
        return result

    async def get_review_evidence(self, evidence_id: UUID) -> tuple[bytes, str]:
        row = (
            await self._session.execute(
                select(PaymentEvidence, StorageObject)
                .join(StorageObject, StorageObject.id == PaymentEvidence.storage_object_id)
                .where(PaymentEvidence.id == evidence_id, StorageObject.status == "clean")
            )
        ).one_or_none()
        if row is None:
            raise ApplicationError("payment_evidence_not_found", "Payment evidence not found.", 404)
        try:
            return await self._storage.get(row[1].object_key), row[1].content_type
        except Exception as exc:
            raise ApplicationError(
                "payment_storage_unavailable",
                "Payment evidence storage is temporarily unavailable.",
                503,
            ) from exc

    async def review_payment(
        self,
        *,
        payment_id: UUID,
        reviewer_user_id: UUID,
        decision: ReviewDecision,
        reason: str,
        expected_version: int,
    ) -> PaymentResponse:
        now = datetime.now(UTC)
        async with self._session.begin():
            payment = await self._repository.payment_for_update(payment_id)
            if payment is None:
                raise ApplicationError("payment_not_found", "Payment not found.", 404)
            if payment.status != PaymentStatus.MANUAL_REVIEW.value:
                raise ApplicationError(
                    "payment_not_reviewable", "Payment is not awaiting manual review.", 409
                )
            if payment.version != expected_version:
                raise ApplicationError(
                    "payment_version_conflict",
                    "Payment was changed by another reviewer. Refresh and try again.",
                    409,
                )
            self._session.add(
                PaymentReview(
                    payment_id=payment.id,
                    reviewer_user_id=reviewer_user_id,
                    decision=decision.value,
                    reason=reason,
                    payment_version=expected_version,
                )
            )
            if decision == ReviewDecision.APPROVED:
                duplicate = await self._repository.duplicate_operation_exists(
                    payment_id=payment.id,
                    operation_number=payment.operation_number_normalized,
                    recipient=payment.observed_recipient_normalized,
                    currency=payment.currency,
                )
                if duplicate:
                    raise ApplicationError(
                        "payment_operation_duplicate",
                        "This bank operation is already attached to an approved payment.",
                        409,
                    )
                await approve_payment(
                    self._session,
                    payment=payment,
                    actor_user_id=reviewer_user_id,
                    actor_type="admin",
                    reason=reason,
                )
            else:
                payment.status = PaymentStatus.REJECTED.value
                payment.rejection_reason = reason
                payment.rejected_at = now
                payment.version += 1
                promo_redemption = await self._promotion_repository.redemption_for_payment(
                    payment.id
                )
                if promo_redemption is not None:
                    promo_redemption.revoked_at = now
                self._session.add(
                    AuditLog(
                        actor_user_id=reviewer_user_id,
                        actor_type="admin",
                        action="payment.rejected",
                        entity_type="payment",
                        entity_id=payment.id,
                        reason=reason,
                        after_state={"status": payment.status},
                    )
                )
            await self._session.flush()
            return await self._response(payment)

    async def _response(self, payment: Payment) -> PaymentResponse:
        analysis = await self._repository.latest_analysis(payment.id)
        price = await self._repository.active_plan_price(payment.plan_price_id, payment.created_at)
        if price is None:
            price = await self._session.get(PlanPrice, payment.plan_price_id)
        if price is None:
            raise RuntimeError("payment references no plan price")
        promo_details = await self._promotion_repository.promo_details_for_payment(payment.id)
        redemption = promo_details[0] if promo_details is not None else None
        promo = promo_details[1] if promo_details is not None else None
        summary = None
        if analysis is not None:
            summary = PaymentAnalysisSummary(
                provider=analysis.provider,
                model=analysis.model,
                status=analysis.status,
                confidence=float(analysis.confidence) if analysis.confidence is not None else None,
                rule_results=analysis.rule_results,
            )
        return PaymentResponse(
            id=payment.id,
            plan_price_id=payment.plan_price_id,
            status=payment.status,
            expected_amount_minor=payment.expected_amount_minor,
            original_amount_minor=price.amount_minor,
            discount_amount_minor=redemption.discount_amount_minor
            if redemption is not None and redemption.discount_amount_minor is not None
            else 0,
            promo_code=promo.code if promo is not None else None,
            currency=payment.currency,
            expected_recipient=payment.expected_recipient,
            expires_at=payment.expires_at,
            uploaded_at=payment.uploaded_at,
            approved_at=payment.approved_at,
            rejected_at=payment.rejected_at,
            rejection_reason=payment.rejection_reason,
            version=payment.version,
            latest_analysis=summary,
        )

    def _validate_upload_state(self, payment: Payment) -> None:
        if payment.expires_at <= datetime.now(UTC):
            raise ApplicationError("payment_intent_expired", "Payment intent has expired.", 409)
        if payment.status not in {
            PaymentStatus.AWAITING_UPLOAD.value,
            PaymentStatus.UPLOADED.value,
        }:
            raise ApplicationError(
                "payment_not_uploadable", "Payment does not accept evidence uploads.", 409
            )

    @staticmethod
    def _safe_filename(filename: str | None) -> str | None:
        if not filename:
            return None
        name = PurePath(filename).name.replace("\x00", "").strip()
        return name[:255] or None

    def _audit(
        self,
        *,
        user_id: UUID,
        action: str,
        payment: Payment,
        client: PaymentClientContext,
        after: dict[str, Any],
    ) -> None:
        self._session.add(
            AuditLog(
                actor_user_id=user_id,
                actor_type="user",
                action=action,
                entity_type="payment",
                entity_id=payment.id,
                after_state=after,
                ip_address=client.ip_address,
                user_agent=client.user_agent,
                request_id=client.request_id,
            )
        )

    @staticmethod
    def _idempotency_conflict() -> ApplicationError:
        return ApplicationError(
            "idempotency_key_conflict",
            "The idempotency key was already used with a different request.",
            409,
        )
