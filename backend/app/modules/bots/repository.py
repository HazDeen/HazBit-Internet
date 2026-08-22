from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import TelegramAccount, User, UserRole


@dataclass(frozen=True, slots=True)
class BotIdentity:
    user_id: UUID
    locale: str
    status: str
    roles: frozenset[str]


class BotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def identity(self, telegram_user_id: int) -> BotIdentity | None:
        row = (
            await self._session.execute(
                select(User.id, User.locale, User.status)
                .join(TelegramAccount, TelegramAccount.user_id == User.id)
                .where(TelegramAccount.telegram_user_id == telegram_user_id)
            )
        ).one_or_none()
        if row is None:
            return None
        roles = frozenset(
            await self._session.scalars(
                select(UserRole.role).where(
                    UserRole.user_id == row.id,
                    UserRole.revoked_at.is_(None),
                )
            )
        )
        return BotIdentity(user_id=row.id, locale=row.locale, status=row.status, roles=roles)
