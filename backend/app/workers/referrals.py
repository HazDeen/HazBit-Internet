from __future__ import annotations

from app.core.config import Settings
from app.database.session import DatabaseManager
from app.modules.referrals.processor import ReferralRewardProcessor


async def run_referral_reward_batch(
    database: DatabaseManager,
    settings: Settings,
    *,
    limit: int | None = None,
) -> int:
    async with database.session() as session:
        return await ReferralRewardProcessor(
            session=session,
            settings=settings.referrals,
        ).process_batch(limit=limit)
