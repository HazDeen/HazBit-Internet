from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import VpnSettings
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.modules.auth.models import AuditLog
from app.modules.vpn.crypto import SubscriptionUrlCipher
from app.modules.vpn.enums import CommandStatus, CommandType, DesiredVpnStatus, DeviceStatus
from app.modules.vpn.models import Device, VpnAccount, VpnSyncCommand
from app.modules.vpn.repository import VpnRepository
from app.modules.vpn.schemas import DeviceResponse, VpnAccountResponse

LIVE_SUBSCRIPTION_STATUSES = {"active", "grace_period"}


@dataclass(frozen=True, slots=True)
class VpnClientContext:
    ip_address: str
    user_agent: str | None
    request_id: UUID | None


class VpnService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: VpnSettings,
        cipher: SubscriptionUrlCipher,
    ) -> None:
        self._session = session
        self._settings = settings
        self._cipher = cipher
        self._repository = VpnRepository(session)

    async def ensure_account(
        self,
        *,
        user_id: UUID,
        subscription_id: UUID,
    ) -> tuple[VpnAccount, VpnSyncCommand]:
        now = datetime.now(UTC)
        async with self._session.begin():
            subscription_plan = await self._repository.get_subscription_plan_for_update(
                subscription_id, user_id
            )
            if subscription_plan is None:
                raise ApplicationError("subscription_not_found", "Subscription not found.", 404)
            subscription, plan = subscription_plan
            if (
                subscription.status not in LIVE_SUBSCRIPTION_STATUSES
                or subscription.current_period_ends_at is None
                or subscription.current_period_ends_at <= now
            ):
                raise ApplicationError(
                    "subscription_not_active",
                    "An active subscription is required for VPN provisioning.",
                    409,
                )
            account = await self._repository.get_account_for_user(user_id, for_update=True)
            if account is None:
                account = VpnAccount(
                    user_id=user_id,
                    subscription_id=subscription.id,
                    username=f"hz_{user_id.hex[:24]}",
                    desired_status=DesiredVpnStatus.ACTIVE.value,
                    desired_expires_at=subscription.current_period_ends_at,
                )
                self._repository.add_account(account)
                await self._session.flush()
            else:
                account.subscription_id = subscription.id
                account.desired_status = DesiredVpnStatus.ACTIVE.value
                account.desired_expires_at = subscription.current_period_ends_at

            command_key = f"vpn:ensure:{account.id}:v{subscription.version}"
            existing = await self._repository.command_by_idempotency_key(command_key)
            if existing is not None:
                return account, existing
            email, telegram_id = await self._repository.identity_contacts(user_id)
            command = self._new_command(
                account.id,
                CommandType.ENSURE_ACCOUNT,
                command_key,
                {
                    "username": account.username,
                    "expire_at": subscription.current_period_ends_at.isoformat(),
                    "traffic_limit_bytes": plan.traffic_limit_bytes or 0,
                    "device_limit": plan.device_limit,
                    "email": email,
                    "telegram_id": telegram_id,
                    "internal_squad_ids": self._squad_ids(plan.remnawave_policy),
                },
                now,
            )
            self._repository.add_command(command)
            return account, command

    async def get_account(self, user_id: UUID) -> VpnAccountResponse:
        account = await self._repository.get_account_for_user(user_id)
        if account is None:
            raise ApplicationError("vpn_account_not_found", "VPN account not found.", 404)
        return self._account_response(account)

    async def get_user_status(self, user_id: UUID) -> VpnAccountResponse:
        return await self.get_account(user_id)

    async def get_subscription_url(self, user_id: UUID) -> str:
        account = await self._repository.get_account_for_user(user_id)
        if account is None:
            raise ApplicationError("vpn_account_not_found", "VPN account not found.", 404)
        if (
            account.desired_status != DesiredVpnStatus.ACTIVE.value
            or account.subscription_url_ciphertext is None
        ):
            raise ApplicationError(
                "vpn_config_not_ready",
                "VPN configuration is not ready yet.",
                409,
            )
        try:
            return self._cipher.decrypt(account.subscription_url_ciphertext)
        except ValueError as exc:
            raise ApplicationError(
                "vpn_config_unavailable",
                "VPN configuration is temporarily unavailable.",
                503,
            ) from exc

    async def list_devices(self, user_id: UUID) -> list[DeviceResponse]:
        account = await self._repository.get_account_for_user(user_id)
        if account is None:
            return []
        return [
            self.device_response(device)
            for device in await self._repository.list_devices(account.id)
        ]

    async def create_device(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
        hwid: str,
        label: str | None,
        platform: str | None,
        os_version: str | None,
        device_model: str | None,
        client: VpnClientContext,
    ) -> tuple[Device, VpnSyncCommand]:
        now = datetime.now(UTC)
        scoped_key = f"vpn:device:create:{user_id}:{idempotency_key}"
        async with self._session.begin():
            await self._repository.serialize_idempotency_key(scoped_key)
            existing_command = await self._repository.command_by_idempotency_key(scoped_key)
            if existing_command is not None:
                if not hmac.compare_digest(str(existing_command.payload.get("hwid", "")), hwid):
                    raise self._idempotency_conflict()
                device_id = UUID(str(existing_command.payload["device_id"]))
                device = await self._repository.get_device_for_update(device_id, user_id)
                if device is None:
                    raise RuntimeError("idempotent device command references no device")
                return device, existing_command

            account = await self._require_provisioned_account(user_id, for_update=True)
            devices = await self._repository.list_devices(account.id)
            if any(device.external_hwid == hwid for device in devices):
                raise ApplicationError("device_already_exists", "This device already exists.", 409)
            limit = await self._device_limit(account.subscription_id)
            subscription_device_count = await self._repository.active_device_count_for_subscription(
                account.subscription_id
            )
            if subscription_device_count >= limit:
                raise ApplicationError(
                    "device_limit_reached",
                    "The shared subscription device limit has been reached.",
                    409,
                )
            used_slots = {device.slot_number for device in devices}
            slot = next(number for number in range(1, limit + 1) if number not in used_slots)
            device = Device(
                user_id=user_id,
                vpn_account_id=account.id,
                slot_number=slot,
                label=label,
                external_hwid=hwid,
                platform=platform,
                status=DeviceStatus.RESERVED.value,
            )
            self._repository.add_device(device)
            await self._session.flush()
            command = self._new_command(
                account.id,
                CommandType.CREATE_DEVICE,
                scoped_key,
                {
                    "device_id": str(device.id),
                    "hwid": hwid,
                    "platform": platform,
                    "os_version": os_version,
                    "device_model": device_model,
                    "user_agent": client.user_agent,
                    "request_ip": client.ip_address,
                },
                now,
            )
            self._repository.add_command(command)
            self._audit(
                user_id=user_id,
                action="vpn.device.create_requested",
                entity_type="device",
                entity_id=device.id,
                client=client,
                after_state={"slot_number": slot},
            )
            return device, command

    async def remove_device(
        self,
        *,
        user_id: UUID,
        device_id: UUID,
        idempotency_key: str,
        client: VpnClientContext,
    ) -> VpnSyncCommand:
        now = datetime.now(UTC)
        scoped_key = f"vpn:device:remove:{user_id}:{idempotency_key}"
        async with self._session.begin():
            await self._repository.serialize_idempotency_key(scoped_key)
            existing = await self._repository.command_by_idempotency_key(scoped_key)
            if existing is not None:
                if str(existing.payload.get("device_id")) != str(device_id):
                    raise self._idempotency_conflict()
                return existing
            device = await self._repository.get_device_for_update(device_id, user_id)
            if device is None or device.status == DeviceStatus.REVOKED.value:
                raise ApplicationError("device_not_found", "Device not found.", 404)
            account = await self._repository.get_account(device.vpn_account_id)
            if account.remnawave_user_id is None or device.external_hwid is None:
                raise ApplicationError(
                    "device_not_provisioned",
                    "Device has not been provisioned in Remnawave.",
                    409,
                )
            device.status = DeviceStatus.REVOKED.value
            device.revoked_at = now
            command = self._new_command(
                account.id,
                CommandType.REMOVE_DEVICE,
                scoped_key,
                {
                    "device_id": str(device.id),
                    "hwid": device.external_hwid,
                },
                now,
            )
            self._repository.add_command(command)
            self._audit(
                user_id=user_id,
                action="vpn.device.remove_requested",
                entity_type="device",
                entity_id=device.id,
                client=client,
                after_state={"revoked": True},
            )
            return command

    async def disable_user(self, user_id: UUID, *, reason: str) -> VpnSyncCommand:
        now = datetime.now(UTC)
        async with self._session.begin():
            account = await self._require_provisioned_account(user_id, for_update=True)
            account.desired_status = DesiredVpnStatus.DISABLED.value
            key = f"vpn:disable:{account.id}:{uuid7()}"
            command = self._new_command(
                account.id,
                CommandType.DISABLE,
                key,
                {"reason": reason},
                now,
            )
            self._repository.add_command(command)
            return command

    async def enable_user(self, user_id: UUID, *, source_id: UUID) -> VpnSyncCommand:
        now = datetime.now(UTC)
        async with self._session.begin():
            account = await self._require_provisioned_account(user_id, for_update=True)
            account.desired_status = DesiredVpnStatus.ACTIVE.value
            key = f"vpn:enable:{account.id}:{source_id}"
            existing = await self._repository.command_by_idempotency_key(key)
            if existing:
                return existing
            command = self._new_command(
                account.id,
                CommandType.ENABLE,
                key,
                {"source_id": str(source_id)},
                now,
            )
            self._repository.add_command(command)
            return command

    async def request_sync(self, user_id: UUID, *, cycle_id: UUID) -> VpnSyncCommand:
        now = datetime.now(UTC)
        async with self._session.begin():
            account = await self._require_provisioned_account(user_id, for_update=True)
            key = f"vpn:sync:{account.id}:{cycle_id}"
            existing = await self._repository.command_by_idempotency_key(key)
            if existing:
                return existing
            command = self._new_command(
                account.id,
                CommandType.SYNC,
                key,
                {},
                now,
            )
            self._repository.add_command(command)
            return command

    async def extend_subscription(
        self, user_id: UUID, *, expires_at: datetime, source_id: UUID
    ) -> VpnSyncCommand:
        now = datetime.now(UTC)
        async with self._session.begin():
            account = await self._require_provisioned_account(user_id, for_update=True)
            account.desired_expires_at = expires_at
            key = f"vpn:extend:{account.id}:{source_id}"
            existing = await self._repository.command_by_idempotency_key(key)
            if existing:
                return existing
            command = self._new_command(
                account.id,
                CommandType.EXTEND,
                key,
                {"expires_at": expires_at.isoformat()},
                now,
            )
            self._repository.add_command(command)
            return command

    async def _require_provisioned_account(self, user_id: UUID, *, for_update: bool) -> VpnAccount:
        account = await self._repository.get_account_for_user(user_id, for_update=for_update)
        if account is None:
            raise ApplicationError("vpn_account_not_found", "VPN account not found.", 404)
        if account.remnawave_user_id is None:
            raise ApplicationError(
                "vpn_provisioning_pending",
                "VPN account provisioning is still pending.",
                409,
            )
        return account

    async def _device_limit(self, subscription_id: UUID) -> int:
        limit = await self._repository.device_limit_for_subscription(subscription_id)
        if limit is None:
            raise RuntimeError("VPN account references no subscription plan")
        return limit

    @staticmethod
    def _squad_ids(policy: dict[str, Any]) -> list[str]:
        values = policy.get("internal_squad_ids", [])
        if not isinstance(values, list):
            raise ApplicationError(
                "invalid_remnawave_policy",
                "Plan Remnawave policy is invalid.",
                500,
            )
        try:
            return [str(UUID(str(value))) for value in values]
        except ValueError as exc:
            raise ApplicationError(
                "invalid_remnawave_policy",
                "Plan Remnawave policy is invalid.",
                500,
            ) from exc

    @staticmethod
    def _new_command(
        account_id: UUID,
        command_type: CommandType,
        idempotency_key: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> VpnSyncCommand:
        return VpnSyncCommand(
            vpn_account_id=account_id,
            command_type=command_type.value,
            idempotency_key=idempotency_key,
            payload=payload,
            status=CommandStatus.PENDING.value,
            attempt_count=0,
            next_attempt_at=now,
        )

    def _audit(
        self,
        *,
        user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        client: VpnClientContext,
        after_state: dict[str, Any],
    ) -> None:
        self._session.add(
            AuditLog(
                actor_user_id=user_id,
                actor_type="user",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                ip_address=client.ip_address,
                user_agent=client.user_agent,
                request_id=client.request_id,
                after_state=after_state,
            )
        )

    @staticmethod
    def _account_response(account: VpnAccount) -> VpnAccountResponse:
        return VpnAccountResponse(
            id=account.id,
            username=account.username,
            desired_status=account.desired_status,
            observed_status=account.observed_status,
            expires_at=account.desired_expires_at,
            last_synced_at=account.last_synced_at,
            provisioning=account.remnawave_user_id is None,
        )

    @staticmethod
    def device_response(device: Device) -> DeviceResponse:
        return DeviceResponse(
            id=device.id,
            slot_number=device.slot_number,
            label=device.label,
            hwid=device.external_hwid,
            platform=device.platform,
            status=device.status,
            first_seen_at=device.first_seen_at,
            last_seen_at=device.last_seen_at,
        )

    @staticmethod
    def _idempotency_conflict() -> ApplicationError:
        return ApplicationError(
            "idempotency_key_conflict",
            "Idempotency-Key was already used for a different request.",
            409,
        )
