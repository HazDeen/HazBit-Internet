from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.database.session import DatabaseManager
from app.modules.auth.rate_limit import RateLimiter
from app.modules.billing.platega import PlategaClient
from app.modules.billing.service import BillingService


async def run_billing_renewal_batch(
    database: DatabaseManager,
    settings: Settings,
    platega: PlategaClient,
    rate_limiter: RateLimiter,
    *,
    limit: int = 25,
) -> int:
    now = datetime.now(UTC)
    async with database.session() as session:
        due = await BillingService(
            session=session,
            settings=settings.billing,
            platega=platega,
            rate_limiter=rate_limiter,
        ).due_renewals(now, limit)

    for user_id, plan_price_id, due_at in due:
        key = f"wallet:renewal:{user_id}:{int(due_at.timestamp())}"
        try:
            async with database.session() as session:
                await BillingService(
                    session=session,
                    settings=settings.billing,
                    platega=platega,
                    rate_limiter=rate_limiter,
                ).purchase(
                    user_id=user_id,
                    plan_price_id=plan_price_id,
                    auto_renew=True,
                    idempotency_key=key,
                    client=None,
                    renewal=True,
                )
        except ApplicationError as exc:
            async with database.session() as session:
                await BillingService(
                    session=session,
                    settings=settings.billing,
                    platega=platega,
                    rate_limiter=rate_limiter,
                ).record_renewal_failure(user_id, exc.code)
    return len(due)
