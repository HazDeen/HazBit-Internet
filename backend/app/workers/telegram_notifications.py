from __future__ import annotations

from app.core.config import Settings
from app.database.session import DatabaseManager
from app.modules.bots.notifications import TelegramNotificationProcessor
from app.modules.bots.runtime import TelegramBotsRuntime


async def run_telegram_notification_batch(
    database: DatabaseManager,
    settings: Settings,
    runtime: TelegramBotsRuntime,
    *,
    limit: int | None = None,
) -> int:
    if not settings.telegram_bots.operations_chat_ids or not runtime.operations.configured:
        return 0
    async with database.session() as session:
        processor = TelegramNotificationProcessor(
            session=session,
            settings=settings,
            client=runtime.operations,
            callbacks=runtime.callbacks,
        )
        claims = await processor.claim(limit=limit)
        for claim in claims:
            await processor.deliver(claim)
        return len(claims)
