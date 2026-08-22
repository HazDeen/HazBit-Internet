from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User, UserEmail
from app.modules.families.models import FamilyGroup, FamilyInvitation, FamilyMember
from app.modules.vpn.enums import DesiredVpnStatus, DeviceStatus
from app.modules.vpn.models import Device, PlanVersion, Subscription, VpnAccount


class FamilyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def serialize(self, key: str) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )

    async def subscription_plan_for_owner(
        self, subscription_id: UUID, owner_user_id: UUID, *, for_update: bool = False
    ) -> tuple[Subscription, PlanVersion] | None:
        statement = (
            select(Subscription, PlanVersion)
            .join(PlanVersion, PlanVersion.id == Subscription.plan_version_id)
            .where(
                Subscription.id == subscription_id,
                Subscription.owner_user_id == owner_user_id,
            )
        )
        if for_update:
            statement = statement.with_for_update(of=Subscription)
        row = (await self.session.execute(statement)).one_or_none()
        return (row[0], row[1]) if row else None

    async def group(self, group_id: UUID, *, for_update: bool = False) -> FamilyGroup | None:
        statement = select(FamilyGroup).where(FamilyGroup.id == group_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(FamilyGroup | None, await self.session.scalar(statement))

    async def active_group_for_owner(self, owner_user_id: UUID) -> FamilyGroup | None:
        return cast(
            FamilyGroup | None,
            await self.session.scalar(
                select(FamilyGroup).where(
                    FamilyGroup.owner_user_id == owner_user_id,
                    FamilyGroup.status != "archived",
                )
            ),
        )

    async def active_group_for_member(self, user_id: UUID) -> FamilyGroup | None:
        return cast(
            FamilyGroup | None,
            await self.session.scalar(
                select(FamilyGroup)
                .join(FamilyMember, FamilyMember.family_group_id == FamilyGroup.id)
                .where(FamilyMember.user_id == user_id, FamilyMember.left_at.is_(None))
            ),
        )

    async def plan_for_group(self, group: FamilyGroup) -> PlanVersion:
        plan = await self.session.scalar(
            select(PlanVersion)
            .join(Subscription, Subscription.plan_version_id == PlanVersion.id)
            .where(Subscription.id == group.subscription_id)
        )
        if plan is None:
            raise RuntimeError("family group references no plan version")
        return plan

    async def members(self, group_id: UUID) -> list[tuple[FamilyMember, str | None]]:
        rows = await self.session.execute(
            select(FamilyMember, UserEmail.email)
            .outerjoin(
                UserEmail,
                (UserEmail.user_id == FamilyMember.user_id) & UserEmail.is_primary.is_(True),
            )
            .where(FamilyMember.family_group_id == group_id, FamilyMember.left_at.is_(None))
            .order_by(FamilyMember.joined_at, FamilyMember.id)
        )
        return [(row[0], str(row[1]) if row[1] is not None else None) for row in rows]

    async def invitations(self, group_id: UUID) -> list[FamilyInvitation]:
        result = await self.session.scalars(
            select(FamilyInvitation)
            .where(FamilyInvitation.family_group_id == group_id)
            .order_by(FamilyInvitation.created_at.desc())
        )
        return list(result.all())

    async def invitation_inbox(self, user_id: UUID, email: str | None) -> list[FamilyInvitation]:
        targets = [FamilyInvitation.invited_user_id == user_id]
        if email:
            targets.append(FamilyInvitation.invited_email == email)
        result = await self.session.scalars(
            select(FamilyInvitation)
            .where(FamilyInvitation.status == "pending", or_(*targets))
            .order_by(FamilyInvitation.created_at.desc())
        )
        return list(result.all())

    async def invitation_by_token(
        self, token_hash: bytes, *, for_update: bool = False
    ) -> FamilyInvitation | None:
        statement = select(FamilyInvitation).where(FamilyInvitation.token_hash == token_hash)
        if for_update:
            statement = statement.with_for_update()
        return cast(FamilyInvitation | None, await self.session.scalar(statement))

    async def invitation(
        self, invitation_id: UUID, *, for_update: bool = False
    ) -> FamilyInvitation | None:
        statement = select(FamilyInvitation).where(FamilyInvitation.id == invitation_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(FamilyInvitation | None, await self.session.scalar(statement))

    async def pending_invitation_for_target(
        self, group_id: UUID, *, user_id: UUID | None, email: str | None
    ) -> FamilyInvitation | None:
        target = (
            FamilyInvitation.invited_user_id == user_id
            if user_id is not None
            else FamilyInvitation.invited_email == email
        )
        return cast(
            FamilyInvitation | None,
            await self.session.scalar(
                select(FamilyInvitation).where(
                    FamilyInvitation.family_group_id == group_id,
                    FamilyInvitation.status == "pending",
                    target,
                )
            ),
        )

    async def expire_pending_invitations(self, group_id: UUID, now: datetime) -> None:
        await self.session.execute(
            update(FamilyInvitation)
            .where(
                FamilyInvitation.family_group_id == group_id,
                FamilyInvitation.status == "pending",
                FamilyInvitation.expires_at <= now,
            )
            .values(status="expired")
        )

    async def active_membership(self, user_id: UUID) -> FamilyMember | None:
        return cast(
            FamilyMember | None,
            await self.session.scalar(
                select(FamilyMember).where(
                    FamilyMember.user_id == user_id, FamilyMember.left_at.is_(None)
                )
            ),
        )

    async def active_member_count(self, group_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(FamilyMember)
                .where(FamilyMember.family_group_id == group_id, FamilyMember.left_at.is_(None))
            )
            or 0
        )

    async def pending_invitation_count(self, group_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(FamilyInvitation)
                .where(
                    FamilyInvitation.family_group_id == group_id,
                    FamilyInvitation.status == "pending",
                )
            )
            or 0
        )

    async def active_device_count(self, subscription_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Device)
                .join(VpnAccount, VpnAccount.id == Device.vpn_account_id)
                .where(
                    VpnAccount.subscription_id == subscription_id,
                    Device.status != DeviceStatus.REVOKED.value,
                )
            )
            or 0
        )

    async def user(self, user_id: UUID) -> User | None:
        return cast(User | None, await self.session.scalar(select(User).where(User.id == user_id)))

    async def primary_email(self, user_id: UUID) -> str | None:
        value = await self.session.scalar(
            select(UserEmail.email).where(
                UserEmail.user_id == user_id,
                UserEmail.is_primary.is_(True),
                UserEmail.verified_at.is_not(None),
            )
        )
        return str(value) if value is not None else None

    async def user_by_email(self, email: str) -> User | None:
        return cast(
            User | None,
            await self.session.scalar(
                select(User)
                .join(UserEmail, UserEmail.user_id == User.id)
                .where(UserEmail.email == email, UserEmail.verified_at.is_not(None))
            ),
        )

    async def vpn_account(
        self, user_id: UUID, subscription_id: UUID, *, for_update: bool = False
    ) -> VpnAccount | None:
        statement = select(VpnAccount).where(
            VpnAccount.user_id == user_id,
            VpnAccount.subscription_id == subscription_id,
            VpnAccount.desired_status != DesiredVpnStatus.REVOKED.value,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(VpnAccount | None, await self.session.scalar(statement))

    async def live_vpn_account_for_user(
        self, user_id: UUID, *, for_update: bool = False
    ) -> VpnAccount | None:
        statement = select(VpnAccount).where(
            VpnAccount.user_id == user_id,
            VpnAccount.desired_status.in_(["pending", "active", "disabled"]),
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(VpnAccount | None, await self.session.scalar(statement))

    def add(self, value: object) -> None:
        self.session.add(value)
