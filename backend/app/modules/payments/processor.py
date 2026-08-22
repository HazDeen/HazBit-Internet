from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PaymentSettings
from app.modules.auth.models import AuditLog
from app.modules.payments.approval import approve_payment
from app.modules.payments.enums import PaymentStatus
from app.modules.payments.gemini import ReceiptAnalysisError, ReceiptExtractor
from app.modules.payments.models import OutboxEvent, PaymentAnalysis
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.rules import evaluate_payment_rules
from app.modules.payments.storage import ObjectStorage


@dataclass(frozen=True, slots=True)
class PaymentClaim:
    payment_id: UUID
    version: int


class PaymentAnalysisProcessor:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: PaymentSettings,
        storage: ObjectStorage,
        extractor: ReceiptExtractor,
    ) -> None:
        self._session = session
        self._settings = settings
        self._storage = storage
        self._extractor = extractor
        self._repository = PaymentRepository(session)

    async def claim(self, *, limit: int = 10) -> list[PaymentClaim]:
        now = datetime.now(UTC)
        async with self._session.begin():
            payments = await self._repository.claim_payments(
                now=now,
                stale_before=now - timedelta(seconds=self._settings.analysis_lock_timeout_seconds),
                max_attempts=self._settings.analysis_max_attempts,
                limit=limit,
            )
            return [PaymentClaim(payment.id, payment.version) for payment in payments]

    async def process(self, claim: PaymentClaim) -> None:
        started_at = datetime.now(UTC)
        async with self._session.begin():
            payment = await self._repository.payment_for_update(claim.payment_id)
            if not self._is_current_claim(payment, claim):
                return
            evidence_row = await self._repository.latest_evidence(claim.payment_id)
            attempt = await self._repository.analysis_attempt_count(claim.payment_id) + 1
            if evidence_row is None:
                await self._record_failure_locked(
                    claim=claim,
                    evidence_id=None,
                    attempt=attempt,
                    started_at=started_at,
                    error=ReceiptAnalysisError("payment_evidence_missing", retryable=False),
                )
                return
            evidence, storage_object = evidence_row
            evidence_id = evidence.id
            object_key = storage_object.object_key
            content_type = storage_object.content_type

        try:
            image = await self._storage.get(object_key)
        except Exception as exc:
            error = ReceiptAnalysisError("payment_storage_read_failed", retryable=True)
            error.__cause__ = exc
            await self._record_failure(claim, evidence_id, attempt, started_at, error)
            return

        try:
            extraction = await self._extractor.extract(image, content_type)
        except ReceiptAnalysisError as exc:
            await self._record_failure(claim, evidence_id, attempt, started_at, exc)
            return

        completed_at = datetime.now(UTC)
        async with self._session.begin():
            payment = await self._repository.payment_for_update(claim.payment_id)
            if not self._is_current_claim(payment, claim):
                return
            assert payment is not None
            preliminary = evaluate_payment_rules(
                payment=payment,
                extraction=extraction,
                settings=self._settings,
                duplicate_operation=False,
            )
            duplicate = await self._repository.duplicate_operation_exists(
                payment_id=payment.id,
                operation_number=preliminary.operation_number_normalized,
                recipient=preliminary.recipient_normalized,
                currency=payment.currency,
            )
            decision = evaluate_payment_rules(
                payment=payment,
                extraction=extraction,
                settings=self._settings,
                duplicate_operation=duplicate,
            )
            self._session.add(
                PaymentAnalysis(
                    payment_id=payment.id,
                    evidence_id=evidence_id,
                    attempt=attempt,
                    provider="gemini",
                    model=self._settings.gemini.model,
                    prompt_version=self._settings.gemini.prompt_version,
                    status="succeeded",
                    amount_minor=extraction.amount_minor,
                    currency=extraction.currency,
                    operation_date=extraction.operation_date,
                    operation_number=extraction.operation_number,
                    bank_name=extraction.bank_name,
                    recipient=extraction.recipient,
                    confidence=Decimal(str(extraction.confidence)),
                    extracted_data=extraction.model_dump(mode="json"),
                    rule_results=decision.results,
                    error_code=None,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            )
            payment.operation_number_normalized = decision.operation_number_normalized
            payment.observed_recipient_normalized = decision.recipient_normalized
            if decision.auto_approve:
                payment.status = PaymentStatus.AUTO_APPROVED.value
                payment.version += 1
                self._session.add(
                    AuditLog(
                        actor_type="service",
                        action="payment.auto_approved",
                        entity_type="payment",
                        entity_id=payment.id,
                        reason="deterministic_rules_passed",
                        after_state={"status": payment.status, "rules": decision.results},
                    )
                )
                await approve_payment(
                    self._session,
                    payment=payment,
                    actor_user_id=None,
                    actor_type="service",
                    reason="deterministic_rules_passed",
                )
            else:
                payment.status = PaymentStatus.MANUAL_REVIEW.value
                payment.version += 1
                self._session.add(
                    OutboxEvent(
                        aggregate_type="payment",
                        aggregate_id=payment.id,
                        event_type="payment.manual_review_requested",
                        payload={
                            "payment_id": str(payment.id),
                            "user_id": str(payment.user_id),
                            "amount_minor": payment.expected_amount_minor,
                            "currency": payment.currency,
                            "version": payment.version,
                        },
                        idempotency_key=f"payment-manual-review:{payment.id}:{payment.version}",
                    )
                )
                self._session.add(
                    AuditLog(
                        actor_type="service",
                        action="payment.manual_review_requested",
                        entity_type="payment",
                        entity_id=payment.id,
                        reason="deterministic_rules_failed",
                        after_state={"status": payment.status, "rules": decision.results},
                    )
                )

    async def _record_failure(
        self,
        claim: PaymentClaim,
        evidence_id: UUID,
        attempt: int,
        started_at: datetime,
        error: ReceiptAnalysisError,
    ) -> None:
        async with self._session.begin():
            await self._record_failure_locked(
                claim=claim,
                evidence_id=evidence_id,
                attempt=attempt,
                started_at=started_at,
                error=error,
            )

    async def _record_failure_locked(
        self,
        *,
        claim: PaymentClaim,
        evidence_id: UUID | None,
        attempt: int,
        started_at: datetime,
        error: ReceiptAnalysisError,
    ) -> None:
        payment = await self._repository.payment_for_update(claim.payment_id)
        if not self._is_current_claim(payment, claim):
            return
        assert payment is not None
        if evidence_id is not None:
            self._session.add(
                PaymentAnalysis(
                    payment_id=payment.id,
                    evidence_id=evidence_id,
                    attempt=attempt,
                    provider="gemini",
                    model=self._settings.gemini.model,
                    prompt_version=self._settings.gemini.prompt_version,
                    status="failed",
                    extracted_data={},
                    rule_results={"decision": "analysis_failed", "retryable": error.retryable},
                    error_code=error.code,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                )
            )
        should_retry = (
            error.retryable
            and attempt < self._settings.analysis_max_attempts
            and payment.expires_at > datetime.now(UTC)
        )
        payment.status = (
            PaymentStatus.UPLOADED.value if should_retry else PaymentStatus.MANUAL_REVIEW.value
        )
        payment.version += 1
        if not should_retry:
            self._session.add(
                AuditLog(
                    actor_type="service",
                    action="payment.manual_review_requested",
                    entity_type="payment",
                    entity_id=payment.id,
                    reason=error.code,
                    after_state={"status": payment.status, "analysis_error": error.code},
                )
            )

    @staticmethod
    def _is_current_claim(payment: object | None, claim: PaymentClaim) -> bool:
        return (
            payment is not None
            and getattr(payment, "status", None) == PaymentStatus.ANALYZING.value
            and getattr(payment, "version", None) == claim.version
        )
