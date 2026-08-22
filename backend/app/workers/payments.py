from __future__ import annotations

from app.core.config import Settings
from app.database.session import DatabaseManager
from app.modules.payments.processor import PaymentAnalysisProcessor
from app.modules.payments.runtime import PaymentRuntime


async def run_payment_analysis_batch(
    database: DatabaseManager,
    settings: Settings,
    runtime: PaymentRuntime,
    *,
    limit: int = 10,
) -> int:
    async with database.session() as session:
        claims = await PaymentAnalysisProcessor(
            session=session,
            settings=settings.payments,
            storage=runtime.storage,
            extractor=runtime.extractor,
        ).claim(limit=limit)

    for claim in claims:
        async with database.session() as session:
            await PaymentAnalysisProcessor(
                session=session,
                settings=settings.payments,
                storage=runtime.storage,
                extractor=runtime.extractor,
            ).process(claim)
    return len(claims)
