from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.database.session import DatabaseManager
from app.modules.vpn.runtime import create_vpn_runtime
from app.workers.vpn_sync import run_vpn_sync_batch


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(component="vpn_sync_worker")
    database = DatabaseManager(settings.database)
    runtime = create_vpn_runtime(settings)
    logger.info("vpn_sync_worker_started")
    try:
        while True:
            processed = await run_vpn_sync_batch(database, settings, runtime)
            if processed == 0:
                await asyncio.sleep(settings.vpn.command_poll_interval_seconds)
    finally:
        await runtime.adapter.close()
        await database.dispose()
        logger.info("vpn_sync_worker_stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
