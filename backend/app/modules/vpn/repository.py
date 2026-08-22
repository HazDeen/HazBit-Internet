from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import TelegramAccount, UserEmail
from app.modules.vpn.enums import CommandStatus, DesiredVpnStatus, DeviceStatus
from app.modules.vpn.models import Device, PlanVersion, Subscription, VpnAccount, VpnSyncCommand


class VpnRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_subscription_plan_for_update(
        self, subscription_id: UUID, user_id: UUID
    ) -> tuple[Subscription, PlanVersion] | None:
        result = await self.session.execute(
            select(Subscription, PlanVersion)
            .join(PlanVersion, PlanVersion.id == Subscription.plan_version_id)
            .where(
                Subscription.id == subscription_id,
                Subscription.owner_user_id == user_id,
            )
            .with_for_update(of=Subscription)
        )
        row = result.one_or_none()
        return (row[0], row[1]) if row else None

    async def get_account_for_user(
        self, user_id: UUID, *, for_update: bool = False
    ) -> VpnAccount | None:
        statement = select(VpnAccount).where(
            VpnAccount.user_id == user_id,
            VpnAccount.desired_status != DesiredVpnStatus.REVOKED.value,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(VpnAccount | None, await self.session.scalar(statement))

    async def get_account(self, account_id: UUID, *, for_update: bool = False) -> VpnAccount:
        statement = select(VpnAccount).where(VpnAccount.id == account_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.scalar(statement)
        if result is None:
            raise LookupError("VPN account not found")
        return result

    def add_account(self, account: VpnAccount) -> None:
        self.session.add(account)

    async def identity_contacts(self, user_id: UUID) -> tuple[str | None, int | None]:
        email = await self.session.scalar(
            select(UserEmail.email).where(
                UserEmail.user_id == user_id,
                UserEmail.is_primary.is_(True),
            )
        )
        telegram_id = await self.session.scalar(
            select(TelegramAccount.telegram_user_id).where(TelegramAccount.user_id == user_id)
        )
        return (str(email) if email is not None else None, telegram_id)

    async def device_limit_for_subscription(self, subscription_id: UUID) -> int | None:
        return cast(
            int | None,
            await self.session.scalar(
                select(PlanVersion.device_limit)
                .join(Subscription, Subscription.plan_version_id == PlanVersion.id)
                .where(Subscription.id == subscription_id)
            ),
        )

    async def list_devices(self, account_id: UUID) -> list[Device]:
        result = await self.session.scalars(
            select(Device)
            .where(
                Device.vpn_account_id == account_id,
                Device.status != DeviceStatus.REVOKED.value,
            )
            .order_by(Device.slot_number)
        )
        return list(result.all())

    async def active_device_count_for_subscription(self, subscription_id: UUID) -> int:
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

    async def get_device_for_update(self, device_id: UUID, user_id: UUID) -> Device | None:
        return cast(
            Device | None,
            await self.session.scalar(
                select(Device)
                .where(Device.id == device_id, Device.user_id == user_id)
                .with_for_update()
            ),
        )

    def add_device(self, device: Device) -> None:
        self.session.add(device)

    async def command_by_idempotency_key(self, key: str) -> VpnSyncCommand | None:
        return cast(
            VpnSyncCommand | None,
            await self.session.scalar(
                select(VpnSyncCommand).where(VpnSyncCommand.idempotency_key == key)
            ),
        )

    async def serialize_idempotency_key(self, key: str) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": key},
        )

    def add_command(self, command: VpnSyncCommand) -> None:
        self.session.add(command)

    async def claim_commands(
        self,
        *,
        now: datetime,
        stale_before: datetime,
        limit: int,
    ) -> list[VpnSyncCommand]:
        result = await self.session.scalars(
            select(VpnSyncCommand)
            .where(
                or_(
                    VpnSyncCommand.status.in_(
                        [CommandStatus.PENDING.value, CommandStatus.RETRY_SCHEDULED.value]
                    )
                    & (VpnSyncCommand.next_attempt_at <= now),
                    (VpnSyncCommand.status == CommandStatus.PROCESSING.value)
                    & (VpnSyncCommand.locked_at < stale_before),
                ),
            )
            .order_by(VpnSyncCommand.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        commands = list(result.all())
        for command in commands:
            command.status = CommandStatus.PROCESSING.value
            command.locked_at = now
            command.attempt_count += 1
        return commands

    async def get_processing_command_for_update(self, command_id: UUID) -> VpnSyncCommand:
        command = await self.session.scalar(
            select(VpnSyncCommand)
            .where(
                VpnSyncCommand.id == command_id,
                VpnSyncCommand.status == CommandStatus.PROCESSING.value,
            )
            .with_for_update()
        )
        if command is None:
            raise LookupError("processing VPN command not found")
        return command
