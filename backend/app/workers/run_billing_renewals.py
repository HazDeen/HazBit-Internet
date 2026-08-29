from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.database.session import DatabaseManager
from app.integrations.redis import RedisManager
from app.modules.auth.runtime import create_auth_runtime
from app.modules.billing.runtime import create_billing_runtime
from app.workers.billing_renewals import run_billing_renewal_batch


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(component="billing_renewal_worker")
    database = DatabaseManager(settings.database)
    redis = RedisManager(settings.redis)
    auth_runtime = create_auth_runtime(settings, redis)
    billing_runtime = create_billing_runtime(settings)
    logger.info("billing_renewal_worker_started")
    try:
        while True:
            processed = await run_billing_renewal_batch(
                database,
                settings,
                billing_runtime.platega,
                auth_runtime.rate_limiter,
            )
            if processed == 0:
                await asyncio.sleep(settings.billing.renewal_poll_interval_seconds)
    finally:
        await billing_runtime.platega.close()
        await redis.dispose()
        await database.dispose()
        logger.info("billing_renewal_worker_stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
