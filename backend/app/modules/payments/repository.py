from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import PaymentStatus
from app.modules.payments.models import (
    Payment,
    PaymentAnalysis,
    PaymentEvidence,
    PlanPrice,
    StorageObject,
)


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def serialize_key(self, key: str) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": key},
        )

    async def active_plan_price(self, price_id: UUID, now: datetime) -> PlanPrice | None:
        return cast(
            PlanPrice | None,
            await self.session.scalar(
                select(PlanPrice).where(
                    PlanPrice.id == price_id,
                    PlanPrice.is_active.is_(True),
                    PlanPrice.valid_from <= now,
                    or_(PlanPrice.valid_until.is_(None), PlanPrice.valid_until > now),
                )
            ),
        )

    async def payment_by_key(self, user_id: UUID, key: str) -> Payment | None:
        return cast(
            Payment | None,
            await self.session.scalar(
                select(Payment).where(Payment.user_id == user_id, Payment.idempotency_key == key)
            ),
        )

    async def payment_for_user(
        self,
        payment_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> Payment | None:
        statement = select(Payment).where(Payment.id == payment_id, Payment.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(Payment | None, await self.session.scalar(statement))

    async def payment_for_update(self, payment_id: UUID) -> Payment | None:
        return cast(
            Payment | None,
            await self.session.scalar(
                select(Payment).where(Payment.id == payment_id).with_for_update()
            ),
        )

    async def latest_analysis(self, payment_id: UUID) -> PaymentAnalysis | None:
        return cast(
            PaymentAnalysis | None,
            await self.session.scalar(
                select(PaymentAnalysis)
                .where(PaymentAnalysis.payment_id == payment_id)
                .order_by(PaymentAnalysis.attempt.desc())
                .limit(1)
            ),
        )

    async def latest_evidence(
        self, payment_id: UUID
    ) -> tuple[PaymentEvidence, StorageObject] | None:
        result = await self.session.execute(
            select(PaymentEvidence, StorageObject)
            .join(StorageObject, StorageObject.id == PaymentEvidence.storage_object_id)
            .where(PaymentEvidence.payment_id == payment_id)
            .order_by(PaymentEvidence.uploaded_at.desc())
            .limit(1)
        )
        row = result.one_or_none()
        return (row[0], row[1]) if row else None

    async def analysis_attempt_count(self, payment_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(PaymentAnalysis)
                .where(PaymentAnalysis.payment_id == payment_id)
            )
            or 0
        )

    async def duplicate_operation_exists(
        self,
        *,
        payment_id: UUID,
        operation_number: str | None,
        recipient: str | None,
        currency: str,
    ) -> bool:
        if operation_number is None or recipient is None:
            return False
        result = await self.session.scalar(
            select(Payment.id).where(
                Payment.id != payment_id,
                Payment.operation_number_normalized == operation_number,
                Payment.observed_recipient_normalized == recipient,
                Payment.currency == currency,
                Payment.status.in_(
                    [
                        PaymentStatus.AUTO_APPROVED.value,
                        PaymentStatus.APPROVED.value,
                        PaymentStatus.ACTIVATION_PENDING.value,
                        PaymentStatus.ACTIVATED.value,
                    ]
                ),
            )
        )
        return result is not None

    async def claim_payments(
        self,
        *,
        now: datetime,
        stale_before: datetime,
        max_attempts: int,
        limit: int,
    ) -> list[Payment]:
        attempt_count = (
            select(func.count(PaymentAnalysis.id))
            .where(PaymentAnalysis.payment_id == Payment.id)
            .correlate(Payment)
            .scalar_subquery()
        )
        evidence_exists = (
            select(PaymentEvidence.id).where(PaymentEvidence.payment_id == Payment.id).exists()
        )
        result = await self.session.scalars(
            select(Payment)
            .where(
                or_(
                    Payment.status == PaymentStatus.UPLOADED.value,
                    (Payment.status == PaymentStatus.ANALYZING.value)
                    & (Payment.updated_at < stale_before),
                ),
                Payment.expires_at > now,
                attempt_count < max_attempts,
                evidence_exists,
            )
            .order_by(Payment.uploaded_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        payments = list(result.all())
        for payment in payments:
            payment.status = PaymentStatus.ANALYZING.value
            payment.version += 1
        return payments
