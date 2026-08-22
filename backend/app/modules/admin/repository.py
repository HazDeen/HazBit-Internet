from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import String, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import TelegramAccount, User, UserEmail
from app.modules.families.models import FamilyGroup, FamilyInvitation, FamilyMember
from app.modules.payments.models import Payment, PlanPrice
from app.modules.promotions.models import PromoCode
from app.modules.referrals.models import Plan, SubscriptionPeriod, TrialGrant
from app.modules.support.models import Ticket
from app.modules.vpn.models import Device, PlanVersion, Subscription, VpnAccount, VpnSyncCommand


class AdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_users(self, *, status: str | None = None) -> int:
        statement = select(func.count()).select_from(User)
        if status is not None:
            statement = statement.where(User.status == status)
        return int(await self.session.scalar(statement) or 0)

    async def count_active_subscriptions(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.status.in_(["active", "grace_period"]))
            )
            or 0
        )

    async def monthly_revenue(self, *, since: datetime, currency: str) -> int:
        return int(
            await self.session.scalar(
                select(func.coalesce(func.sum(Payment.expected_amount_minor), 0)).where(
                    Payment.status.in_(["approved", "activation_pending", "activated"]),
                    Payment.approved_at >= since,
                    Payment.currency == currency,
                )
            )
            or 0
        )

    async def count_open_tickets(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(Ticket).where(Ticket.status != "closed")
            )
            or 0
        )

    async def count_pending_payments(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Payment)
                .where(Payment.status.in_(["uploaded", "analyzing", "manual_review"]))
            )
            or 0
        )

    async def count_active_vpn_accounts(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(VpnAccount)
                .where(VpnAccount.desired_status == "active")
            )
            or 0
        )

    async def count_active_promos(self, now: datetime) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(PromoCode)
                .where(
                    PromoCode.is_active.is_(True),
                    PromoCode.starts_at <= now,
                    or_(PromoCode.expires_at.is_(None), PromoCode.expires_at > now),
                )
            )
            or 0
        )

    async def daily_user_counts(self, since: datetime) -> dict[str, int]:
        rows = await self.session.execute(
            select(func.date(User.created_at), func.count())
            .where(User.created_at >= since)
            .group_by(func.date(User.created_at))
        )
        return {str(day): int(count) for day, count in rows.all()}

    async def daily_payment_totals(self, *, since: datetime, currency: str) -> dict[str, int]:
        rows = await self.session.execute(
            select(func.date(Payment.approved_at), func.sum(Payment.expected_amount_minor))
            .where(
                Payment.approved_at >= since,
                Payment.currency == currency,
                Payment.status.in_(["approved", "activation_pending", "activated"]),
            )
            .group_by(func.date(Payment.approved_at))
        )
        return {str(day): int(amount or 0) for day, amount in rows.all()}

    async def user_page(
        self,
        *,
        search: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[User, str | None, int | None, str | None]], int]:
        filters = []
        if status is not None:
            filters.append(User.status == status)
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    UserEmail.email.ilike(pattern),
                    TelegramAccount.username.ilike(pattern),
                    sql_cast(TelegramAccount.telegram_user_id, String).ilike(pattern),
                    sql_cast(User.id, String).ilike(pattern),
                )
            )
        base = (
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
            .where(*filters)
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(base.with_only_columns(User.id).subquery())
            )
            or 0
        )
        rows = await self.session.execute(
            base.order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
        return ([(row[0], row[1], row[2], row[3]) for row in rows.all()], total)

    async def user_identity(
        self, user_id: UUID
    ) -> tuple[User, str | None, int | None, str | None] | None:
        row = (
            await self.session.execute(
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

    async def user_for_update(self, user_id: UUID) -> User | None:
        return cast(
            User | None,
            await self.session.scalar(select(User).where(User.id == user_id).with_for_update()),
        )

    async def live_subscription(
        self, user_id: UUID, *, for_update: bool = False
    ) -> tuple[Subscription, PlanVersion, Plan] | None:
        statement = (
            select(Subscription, PlanVersion, Plan)
            .join(PlanVersion, PlanVersion.id == Subscription.plan_version_id)
            .join(Plan, Plan.id == PlanVersion.plan_id)
            .where(
                Subscription.owner_user_id == user_id,
                Subscription.status.in_(
                    ["pending", "active", "grace_period", "suspended", "expired"]
                ),
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update(of=Subscription)
        row = (await self.session.execute(statement)).one_or_none()
        return (row[0], row[1], row[2]) if row else None

    async def device_count(self, user_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Device)
                .where(Device.user_id == user_id, Device.status != "revoked")
            )
            or 0
        )

    async def trial_exists(self, user_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(TrialGrant.id).where(TrialGrant.user_id == user_id).limit(1)
            )
            is not None
        )

    async def payment_stats(self, user_id: UUID) -> tuple[int, int]:
        row = (
            await self.session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(Payment.expected_amount_minor), 0),
                ).where(
                    Payment.user_id == user_id,
                    Payment.status.in_(["approved", "activation_pending", "activated"]),
                )
            )
        ).one()
        return int(row[0]), int(row[1])

    async def user_payments(self, user_id: UUID, limit: int = 20) -> list[Payment]:
        return list(
            (
                await self.session.scalars(
                    select(Payment)
                    .where(Payment.user_id == user_id)
                    .order_by(Payment.created_at.desc())
                    .limit(limit)
                )
            ).all()
        )

    async def devices(
        self, *, user_id: UUID | None = None, limit: int = 100, offset: int = 0
    ) -> tuple[list[Device], int]:
        statement = select(Device)
        count_statement = select(func.count()).select_from(Device)
        if user_id is not None:
            statement = statement.where(Device.user_id == user_id)
            count_statement = count_statement.where(Device.user_id == user_id)
        total = int(await self.session.scalar(count_statement) or 0)
        devices = list(
            (
                await self.session.scalars(
                    statement.order_by(Device.created_at.desc()).limit(limit).offset(offset)
                )
            ).all()
        )
        return devices, total

    async def subscription_page(
        self, *, status: str | None, limit: int, offset: int
    ) -> tuple[list[tuple[Subscription, PlanVersion, Plan, str | None, str | None]], int]:
        statement = (
            select(Subscription, PlanVersion, Plan, UserEmail.email, VpnAccount.desired_status)
            .join(PlanVersion, PlanVersion.id == Subscription.plan_version_id)
            .join(Plan, Plan.id == PlanVersion.plan_id)
            .outerjoin(
                UserEmail,
                (UserEmail.user_id == Subscription.owner_user_id) & UserEmail.is_primary.is_(True),
            )
            .outerjoin(VpnAccount, VpnAccount.subscription_id == Subscription.id)
        )
        if status is not None:
            statement = statement.where(Subscription.status == status)
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(
                    statement.with_only_columns(Subscription.id).subquery()
                )
            )
            or 0
        )
        rows = await self.session.execute(
            statement.order_by(Subscription.created_at.desc()).limit(limit).offset(offset)
        )
        return ([(row[0], row[1], row[2], row[3], row[4]) for row in rows.all()], total)

    async def active_plan_version(self, plan_version_id: UUID, now: datetime) -> PlanVersion | None:
        return cast(
            PlanVersion | None,
            await self.session.scalar(
                select(PlanVersion).where(
                    PlanVersion.id == plan_version_id,
                    PlanVersion.valid_from <= now,
                    or_(PlanVersion.valid_until.is_(None), PlanVersion.valid_until > now),
                )
            ),
        )

    async def plans(self) -> list[Plan]:
        return list(
            (await self.session.scalars(select(Plan).order_by(Plan.sort_order, Plan.name))).all()
        )

    async def plan_by_slug(self, slug: str) -> Plan | None:
        return cast(
            Plan | None,
            await self.session.scalar(select(Plan).where(Plan.slug == slug)),
        )

    async def plan_for_update(self, plan_id: UUID) -> Plan | None:
        return cast(
            Plan | None,
            await self.session.scalar(select(Plan).where(Plan.id == plan_id).with_for_update()),
        )

    async def current_plan_versions_for_update(self, plan_id: UUID) -> list[PlanVersion]:
        return list(
            (
                await self.session.scalars(
                    select(PlanVersion)
                    .where(PlanVersion.plan_id == plan_id, PlanVersion.valid_until.is_(None))
                    .with_for_update()
                )
            ).all()
        )

    async def next_plan_version(self, plan_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.coalesce(func.max(PlanVersion.version), 0)).where(
                PlanVersion.plan_id == plan_id
            )
        )
        return int(value or 0) + 1

    async def plan_versions(self, plan_id: UUID) -> list[PlanVersion]:
        return list(
            (
                await self.session.scalars(
                    select(PlanVersion)
                    .where(PlanVersion.plan_id == plan_id)
                    .order_by(PlanVersion.version.desc())
                )
            ).all()
        )

    async def plan_prices(self, plan_version_id: UUID) -> list[PlanPrice]:
        return list(
            (
                await self.session.scalars(
                    select(PlanPrice)
                    .where(PlanPrice.plan_version_id == plan_version_id)
                    .order_by(PlanPrice.currency, PlanPrice.term_months)
                )
            ).all()
        )

    async def payment_page(
        self, *, status: str | None, limit: int, offset: int
    ) -> tuple[list[Payment], int]:
        statement = select(Payment)
        count_statement = select(func.count()).select_from(Payment)
        if status is not None:
            statement = statement.where(Payment.status == status)
            count_statement = count_statement.where(Payment.status == status)
        total = int(await self.session.scalar(count_statement) or 0)
        values = list(
            (
                await self.session.scalars(
                    statement.order_by(Payment.created_at.desc()).limit(limit).offset(offset)
                )
            ).all()
        )
        return values, total

    async def family_group_page(
        self, *, limit: int, offset: int
    ) -> tuple[list[tuple[FamilyGroup, str | None, str, str, int]], int]:
        member_count = (
            select(func.count())
            .select_from(FamilyMember)
            .where(
                FamilyMember.family_group_id == FamilyGroup.id,
                FamilyMember.left_at.is_(None),
            )
            .correlate(FamilyGroup)
            .scalar_subquery()
        )
        statement = (
            select(
                FamilyGroup,
                UserEmail.email,
                Subscription.status,
                Plan.name,
                member_count,
            )
            .join(Subscription, Subscription.id == FamilyGroup.subscription_id)
            .join(PlanVersion, PlanVersion.id == Subscription.plan_version_id)
            .join(Plan, Plan.id == PlanVersion.plan_id)
            .outerjoin(
                UserEmail,
                (UserEmail.user_id == FamilyGroup.owner_user_id) & UserEmail.is_primary.is_(True),
            )
        )
        total = int(await self.session.scalar(select(func.count()).select_from(FamilyGroup)) or 0)
        rows = await self.session.execute(
            statement.order_by(FamilyGroup.created_at.desc()).limit(limit).offset(offset)
        )
        return (
            [(row[0], row[1], row[2], row[3], int(row[4] or 0)) for row in rows.all()],
            total,
        )

    async def family_group(
        self, group_id: UUID
    ) -> tuple[FamilyGroup, str | None, str, str, int] | None:
        member_count = (
            select(func.count())
            .select_from(FamilyMember)
            .where(
                FamilyMember.family_group_id == FamilyGroup.id,
                FamilyMember.left_at.is_(None),
            )
            .correlate(FamilyGroup)
            .scalar_subquery()
        )
        row = (
            await self.session.execute(
                select(
                    FamilyGroup,
                    UserEmail.email,
                    Subscription.status,
                    Plan.name,
                    member_count,
                )
                .join(Subscription, Subscription.id == FamilyGroup.subscription_id)
                .join(PlanVersion, PlanVersion.id == Subscription.plan_version_id)
                .join(Plan, Plan.id == PlanVersion.plan_id)
                .outerjoin(
                    UserEmail,
                    (UserEmail.user_id == FamilyGroup.owner_user_id)
                    & UserEmail.is_primary.is_(True),
                )
                .where(FamilyGroup.id == group_id)
            )
        ).one_or_none()
        if row is None:
            return None
        return row[0], row[1], row[2], row[3], int(row[4] or 0)

    async def family_members(self, group_id: UUID) -> list[tuple[FamilyMember, str | None]]:
        rows = await self.session.execute(
            select(FamilyMember, UserEmail.email)
            .outerjoin(
                UserEmail,
                (UserEmail.user_id == FamilyMember.user_id) & UserEmail.is_primary.is_(True),
            )
            .where(
                FamilyMember.family_group_id == group_id,
                FamilyMember.left_at.is_(None),
            )
            .order_by(FamilyMember.joined_at)
        )
        return [(row[0], row[1]) for row in rows.all()]

    async def family_invitations(self, group_id: UUID) -> list[FamilyInvitation]:
        result = await self.session.scalars(
            select(FamilyInvitation)
            .where(FamilyInvitation.family_group_id == group_id)
            .order_by(FamilyInvitation.created_at.desc())
        )
        return list(result.all())

    async def family_group_for_update(self, group_id: UUID) -> FamilyGroup | None:
        return cast(
            FamilyGroup | None,
            await self.session.scalar(
                select(FamilyGroup).where(FamilyGroup.id == group_id).with_for_update()
            ),
        )

    async def family_member_for_update(self, group_id: UUID, user_id: UUID) -> FamilyMember | None:
        return cast(
            FamilyMember | None,
            await self.session.scalar(
                select(FamilyMember)
                .where(
                    FamilyMember.family_group_id == group_id,
                    FamilyMember.user_id == user_id,
                    FamilyMember.left_at.is_(None),
                )
                .with_for_update()
            ),
        )

    async def family_invitation_for_update(
        self, group_id: UUID, invitation_id: UUID
    ) -> FamilyInvitation | None:
        return cast(
            FamilyInvitation | None,
            await self.session.scalar(
                select(FamilyInvitation)
                .where(
                    FamilyInvitation.family_group_id == group_id,
                    FamilyInvitation.id == invitation_id,
                )
                .with_for_update()
            ),
        )

    async def family_device_summary(self, subscription_id: UUID) -> tuple[int, int]:
        device_limit = await self.session.scalar(
            select(PlanVersion.device_limit)
            .join(Subscription, Subscription.plan_version_id == PlanVersion.id)
            .where(Subscription.id == subscription_id)
        )
        active_devices = await self.session.scalar(
            select(func.count())
            .select_from(Device)
            .join(VpnAccount, VpnAccount.id == Device.vpn_account_id)
            .where(
                VpnAccount.subscription_id == subscription_id,
                Device.status != "revoked",
            )
        )
        return int(active_devices or 0), int(device_limit or 0)

    async def vpn_account_for_update(self, user_id: UUID) -> VpnAccount | None:
        return cast(
            VpnAccount | None,
            await self.session.scalar(
                select(VpnAccount)
                .where(VpnAccount.user_id == user_id, VpnAccount.desired_status != "revoked")
                .with_for_update()
            ),
        )

    async def vpn_command(self, key: str) -> VpnSyncCommand | None:
        return cast(
            VpnSyncCommand | None,
            await self.session.scalar(
                select(VpnSyncCommand).where(VpnSyncCommand.idempotency_key == key)
            ),
        )

    async def identity_contacts(self, user_id: UUID) -> tuple[str | None, int | None]:
        email = await self.session.scalar(
            select(UserEmail.email).where(
                UserEmail.user_id == user_id, UserEmail.is_primary.is_(True)
            )
        )
        telegram_id = await self.session.scalar(
            select(TelegramAccount.telegram_user_id).where(TelegramAccount.user_id == user_id)
        )
        return (str(email) if email is not None else None, telegram_id)

    def add_period(self, period: SubscriptionPeriod) -> None:
        self.session.add(period)

    def add(self, entity: object) -> None:
        self.session.add(entity)
