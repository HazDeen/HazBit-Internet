from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import (
    LedgerAccount,
    Transaction,
    TransactionEntry,
)


async def ledger_account(
    session: AsyncSession,
    *,
    key: str,
    currency: str,
    account_type: str,
    owner_user_id: UUID | None,
) -> LedgerAccount:
    account = await session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.account_key == key,
            LedgerAccount.currency == currency,
        )
    )
    if account is not None:
        return account
    account = LedgerAccount(
        account_key=key,
        owner_user_id=owner_user_id,
        account_type=account_type,
        currency=currency,
        status="active",
    )
    session.add(account)
    await session.flush()
    return account


async def wallet_balance(session: AsyncSession, user_id: UUID, currency: str) -> int:
    value = await session.scalar(
        select(func.coalesce(func.sum(TransactionEntry.amount_minor), 0))
        .select_from(TransactionEntry)
        .join(LedgerAccount, LedgerAccount.id == TransactionEntry.ledger_account_id)
        .join(Transaction, Transaction.id == TransactionEntry.transaction_id)
        .where(
            LedgerAccount.owner_user_id == user_id,
            LedgerAccount.account_type == "user_wallet",
            LedgerAccount.currency == currency,
            Transaction.status == "posted",
        )
    )
    return int(value or 0)


async def post_transaction(
    session: AsyncSession,
    *,
    user_id: UUID,
    transaction_type: str,
    currency: str,
    idempotency_key: str,
    description: str,
    entries: list[tuple[LedgerAccount, int]],
    metadata: dict[str, Any],
    payment_id: UUID | None = None,
    reverses_transaction_id: UUID | None = None,
) -> Transaction:
    existing = await session.scalar(
        select(Transaction).where(Transaction.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing
    transaction = Transaction(
        user_id=user_id,
        payment_id=payment_id,
        transaction_type=transaction_type,
        status="draft",
        currency=currency,
        idempotency_key=idempotency_key,
        description=description,
        reverses_transaction_id=reverses_transaction_id,
        metadata_json=metadata,
    )
    session.add(transaction)
    await session.flush()
    session.add_all(
        TransactionEntry(
            transaction_id=transaction.id,
            ledger_account_id=account.id,
            amount_minor=amount,
        )
        for account, amount in entries
    )
    await session.flush()
    transaction.status = "posted"
    transaction.posted_at = datetime.now(UTC)
    await session.flush()
    return transaction
