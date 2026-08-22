from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.database.session import DatabaseManager
from app.modules.payments.runtime import create_payment_runtime
from app.workers.payments import run_payment_analysis_batch


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(component="payment_analysis_worker")
    database = DatabaseManager(settings.database)
    runtime = create_payment_runtime(settings)
    logger.info(
        "payment_analysis_worker_started",
        provider="gemini",
        model=settings.payments.gemini.model,
    )
    try:
        while True:
            processed = await run_payment_analysis_batch(database, settings, runtime)
            if processed == 0:
                await asyncio.sleep(settings.payments.analysis_poll_interval_seconds)
    finally:
        await runtime.extractor.close()
        await runtime.storage.close()
        await database.dispose()
        logger.info("payment_analysis_worker_stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
