from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.database.session import DatabaseManager
from app.workers.referrals import run_referral_reward_batch


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(component="referral_reward_worker")
    database = DatabaseManager(settings.database)
    logger.info("referral_reward_worker_started")
    try:
        while True:
            processed = await run_referral_reward_batch(database, settings)
            if processed == 0:
                await asyncio.sleep(settings.referrals.worker_poll_interval_seconds)
    finally:
        await database.dispose()
        logger.info("referral_reward_worker_stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
