from __future__ import annotations

from app.core.config import Settings
from app.database.session import DatabaseManager
from app.modules.vpn.processor import VpnCommandProcessor
from app.modules.vpn.runtime import VpnRuntime


async def run_vpn_sync_batch(
    database: DatabaseManager,
    settings: Settings,
    runtime: VpnRuntime,
    *,
    limit: int = 25,
) -> int:
    async with database.session() as session:
        command_ids = await VpnCommandProcessor(
            session=session,
            settings=settings.vpn,
            adapter=runtime.adapter,
            cipher=runtime.subscription_url_cipher,
        ).claim(limit=limit)

    for command_id in command_ids:
        async with database.session() as session:
            await VpnCommandProcessor(
                session=session,
                settings=settings.vpn,
                adapter=runtime.adapter,
                cipher=runtime.subscription_url_cipher,
            ).process(command_id)
    return len(command_ids)
