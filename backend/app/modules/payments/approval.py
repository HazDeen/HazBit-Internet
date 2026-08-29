from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.modules.auth.models import AuditLog
from app.modules.payments.enums import PaymentStatus
from app.modules.payments.ledger import ledger_account
from app.modules.payments.models import (
    OutboxEvent,
    Payment,
    Transaction,
    TransactionEntry,
)
from app.modules.promotions.models import PromoCode, PromoRedemption


async def approve_payment(
    session: AsyncSession,
    *,
    payment: Payment,
    actor_user_id: UUID | None,
    actor_type: str,
    reason: str,
) -> None:
    existing = await session.scalar(select(Transaction).where(Transaction.payment_id == payment.id))
    if existing is not None:
        if existing.status != "posted":
            raise ApplicationError(
                "payment_ledger_incomplete", "Payment ledger is incomplete.", 409
            )
        payment.status = PaymentStatus.APPROVED.value
        payment.approved_at = existing.posted_at
        return

    now = datetime.now(UTC)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"ledger:{payment.user_id}:{payment.currency}"},
    )
    wallet = await ledger_account(
        session,
        key=f"user:{payment.user_id}",
        currency=payment.currency,
        account_type="user_wallet",
        owner_user_id=payment.user_id,
    )
    clearing = await ledger_account(
        session,
        key="cash_clearing",
        currency=payment.currency,
        account_type="cash_clearing",
        owner_user_id=None,
    )
    transaction = Transaction(
        user_id=payment.user_id,
        payment_id=payment.id,
        transaction_type="payment_credit",
        status="draft",
        currency=payment.currency,
        idempotency_key=f"payment-credit:{payment.id}",
        description="Approved bank transfer",
        metadata_json={"approval_reason": reason},
    )
    session.add(transaction)
    await session.flush()
    session.add_all(
        [
            TransactionEntry(
                transaction_id=transaction.id,
                ledger_account_id=wallet.id,
                amount_minor=payment.expected_amount_minor,
            ),
            TransactionEntry(
                transaction_id=transaction.id,
                ledger_account_id=clearing.id,
                amount_minor=-payment.expected_amount_minor,
            ),
        ]
    )
    await session.flush()
    transaction.status = "posted"
    transaction.posted_at = now
    promo_row = (
        await session.execute(
            select(PromoRedemption, PromoCode)
            .join(PromoCode, PromoCode.id == PromoRedemption.promo_code_id)
            .where(
                PromoRedemption.payment_id == payment.id,
                PromoRedemption.revoked_at.is_(None),
                PromoRedemption.discount_amount_minor.is_not(None),
            )
        )
    ).one_or_none()
    if promo_row is not None:
        redemption, promo = promo_row
        discount = redemption.discount_amount_minor or 0
        if discount > 0:
            promo_expense = await ledger_account(
                session,
                key="promo_expense",
                currency=payment.currency,
                account_type="promo_expense",
                owner_user_id=None,
            )
            promo_transaction = Transaction(
                user_id=payment.user_id,
                payment_id=None,
                transaction_type="promo_credit",
                status="draft",
                currency=payment.currency,
                idempotency_key=f"promo-credit:{redemption.id}",
                description=f"Promo code {promo.code}",
                metadata_json={
                    "promo_redemption_id": str(redemption.id),
                    "promo_code_id": str(promo.id),
                    "payment_id": str(payment.id),
                },
            )
            session.add(promo_transaction)
            await session.flush()
            session.add_all(
                [
                    TransactionEntry(
                        transaction_id=promo_transaction.id,
                        ledger_account_id=wallet.id,
                        amount_minor=discount,
                    ),
                    TransactionEntry(
                        transaction_id=promo_transaction.id,
                        ledger_account_id=promo_expense.id,
                        amount_minor=-discount,
                    ),
                ]
            )
            await session.flush()
            promo_transaction.status = "posted"
            promo_transaction.posted_at = now
            session.add(
                OutboxEvent(
                    aggregate_type="promo_redemption",
                    aggregate_id=redemption.id,
                    event_type="promo.discount.redeemed",
                    payload={
                        "redemption_id": str(redemption.id),
                        "promo_code_id": str(promo.id),
                        "payment_id": str(payment.id),
                        "user_id": str(payment.user_id),
                        "discount_amount_minor": discount,
                        "currency": payment.currency,
                    },
                    idempotency_key=f"promo-discount-redeemed:{redemption.id}",
                )
            )
    payment.status = PaymentStatus.APPROVED.value
    payment.approved_at = now
    payment.version += 1
    session.add(
        OutboxEvent(
            aggregate_type="payment",
            aggregate_id=payment.id,
            event_type="payment.approved",
            payload={
                "payment_id": str(payment.id),
                "user_id": str(payment.user_id),
                "plan_price_id": str(payment.plan_price_id),
                "transaction_id": str(transaction.id),
            },
            idempotency_key=f"payment-approved:{payment.id}",
        )
    )
    session.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            action="payment.approved",
            entity_type="payment",
            entity_id=payment.id,
            reason=reason,
            after_state={"status": PaymentStatus.APPROVED.value},
        )
    )
