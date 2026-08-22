from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.database.session import DatabaseManager
from app.modules.bots.runtime import create_telegram_bots_runtime
from app.workers.telegram_notifications import run_telegram_notification_batch


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(component="telegram_notification_worker")
    database = DatabaseManager(settings.database)
    runtime = create_telegram_bots_runtime(settings)
    logger.info("telegram_notification_worker_started")
    try:
        while True:
            processed = await run_telegram_notification_batch(database, settings, runtime)
            if processed == 0:
                await asyncio.sleep(settings.telegram_bots.notification_poll_interval_seconds)
    finally:
        await runtime.close()
        await database.dispose()
        logger.info("telegram_notification_worker_stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
