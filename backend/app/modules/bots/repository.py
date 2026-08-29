from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import Permission, Role
from app.modules.auth.models import TelegramAccount, User, UserPermission, UserRole
from app.modules.auth.permissions import permissions_for_roles


@dataclass(frozen=True, slots=True)
class BotIdentity:
    user_id: UUID
    locale: str
    status: str
    roles: frozenset[str]
    permissions: frozenset[Permission]


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
        typed_roles = {Role(value) for value in roles}
        permissions = permissions_for_roles(typed_roles)
        permissions.update(
            Permission(value)
            for value in await self._session.scalars(
                select(UserPermission.permission).where(UserPermission.user_id == row.id)
            )
        )
        return BotIdentity(
            user_id=row.id,
            locale=row.locale,
            status=row.status,
            roles=roles,
            permissions=frozenset(permissions),
        )
