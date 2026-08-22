from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import TelegramAccount, User, UserEmail
from app.modules.families.models import FamilyGroup, FamilyMember
from app.modules.payments.models import Payment, PlanPrice
from app.modules.referrals.models import Plan
from app.modules.support.models import Ticket
from app.modules.vpn.models import Device, PlanVersion, Subscription, VpnAccount


class PortalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def identity(
        self, user_id: UUID
    ) -> tuple[User, str | None, int | None, str | None] | None:
        row = (
            await self._session.execute(
                select(
                    User,
                    UserEmail.email,
                    TelegramAccount.telegram_user_id,
                    TelegramAccount.username,
                )
                .outerjoin(
                    UserEmail,
                    (UserEmail.user_id == User.id) & UserEmail.is_primary.is_(True),
                )
                .outerjoin(TelegramAccount, TelegramAccount.user_id == User.id)
                .where(User.id == user_id)
            )
        ).one_or_none()
        return (row[0], row[1], row[2], row[3]) if row else None

    async def subscription(self, user_id: UUID) -> tuple[Subscription, PlanVersion, Plan] | None:
        row = (
            await self._session.execute(
                select(Subscription, PlanVersion, Plan)
                .join(PlanVersion, PlanVersion.id == Subscription.plan_version_id)
                .join(Plan, Plan.id == PlanVersion.plan_id)
                .where(Subscription.owner_user_id == user_id)
                .order_by(
                    Subscription.current_period_ends_at.desc().nullslast(),
                    Subscription.created_at.desc(),
                )
                .limit(1)
            )
        ).one_or_none()
        return (row[0], row[1], row[2]) if row else None

    async def vpn_account(self, user_id: UUID) -> VpnAccount | None:
        return cast(
            VpnAccount | None,
            await self._session.scalar(
                select(VpnAccount)
                .where(VpnAccount.user_id == user_id, VpnAccount.desired_status != "revoked")
                .order_by(VpnAccount.created_at.desc())
                .limit(1)
            ),
        )

    async def active_device_count(self, user_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count())
                .select_from(Device)
                .where(Device.user_id == user_id, Device.status != "revoked")
            )
            or 0
        )

    async def open_ticket_count(self, user_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count())
                .select_from(Ticket)
                .where(Ticket.user_id == user_id, Ticket.status != "closed")
            )
            or 0
        )

    async def family_group(self, user_id: UUID) -> FamilyGroup | None:
        return cast(
            FamilyGroup | None,
            await self._session.scalar(
                select(FamilyGroup)
                .join(FamilyMember, FamilyMember.family_group_id == FamilyGroup.id)
                .where(FamilyMember.user_id == user_id, FamilyMember.left_at.is_(None))
                .limit(1)
            ),
        )

    async def catalog(self, now: datetime) -> list[tuple[Plan, PlanVersion, PlanPrice]]:
        rows = await self._session.execute(
            select(Plan, PlanVersion, PlanPrice)
            .join(PlanVersion, PlanVersion.plan_id == Plan.id)
            .join(PlanPrice, PlanPrice.plan_version_id == PlanVersion.id)
            .where(
                Plan.is_active.is_(True),
                PlanVersion.valid_from <= now,
                or_(PlanVersion.valid_until.is_(None), PlanVersion.valid_until > now),
                PlanPrice.is_active.is_(True),
                PlanPrice.valid_from <= now,
                or_(PlanPrice.valid_until.is_(None), PlanPrice.valid_until > now),
            )
            .order_by(Plan.sort_order, Plan.name, PlanPrice.term_months)
        )
        return [(row[0], row[1], row[2]) for row in rows]

    async def payments(self, user_id: UUID, limit: int) -> list[Payment]:
        return list(
            (
                await self._session.scalars(
                    select(Payment)
                    .where(Payment.user_id == user_id)
                    .order_by(Payment.created_at.desc())
                    .limit(limit)
                )
            ).all()
        )
