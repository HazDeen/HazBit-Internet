from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import VpnSettings
from app.integrations.remnawave_adapter import (
    AdapterDeviceList,
    AdapterDeviceState,
    AdapterError,
    AdapterUserState,
    RemnawaveAdapterClient,
)
from app.modules.vpn.crypto import SubscriptionUrlCipher
from app.modules.vpn.enums import CommandStatus, CommandType, DeviceStatus, ObservedVpnStatus
from app.modules.vpn.models import Device, VpnAccount, VpnSyncCommand
from app.modules.vpn.repository import VpnRepository


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    user: AdapterUserState | None = None
    device: AdapterDeviceState | None = None
    devices: AdapterDeviceList | None = None


class VpnCommandProcessor:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: VpnSettings,
        adapter: RemnawaveAdapterClient,
        cipher: SubscriptionUrlCipher,
    ) -> None:
        self._session = session
        self._settings = settings
        self._adapter = adapter
        self._cipher = cipher
        self._repository = VpnRepository(session)

    async def claim(self, *, limit: int = 25) -> list[UUID]:
        now = datetime.now(UTC)
        async with self._session.begin():
            commands = await self._repository.claim_commands(
                now=now,
                stale_before=now - timedelta(seconds=self._settings.command_lock_timeout_seconds),
                limit=limit,
            )
            return [command.id for command in commands]

    async def process(self, command_id: UUID) -> None:
        async with self._session.begin():
            command = await self._repository.get_processing_command_for_update(command_id)
            account = await self._repository.get_account(command.vpn_account_id)
            command_type = CommandType(command.command_type)
            payload = dict(command.payload)

        try:
            outcome = await self._execute(command_type, account, payload)
        except AdapterError as exc:
            await self._record_failure(command_id, exc)
            return
        except (KeyError, TypeError, ValueError):
            await self._record_failure(
                command_id,
                AdapterError(
                    "invalid_command_payload",
                    "VPN synchronization command payload is invalid.",
                    500,
                    False,
                ),
            )
            return

        async with self._session.begin():
            command = await self._repository.get_processing_command_for_update(command_id)
            account = await self._repository.get_account(command.vpn_account_id, for_update=True)
            await self._apply_outcome(command_type, account, command, payload, outcome)

    async def _execute(
        self,
        command_type: CommandType,
        account: VpnAccount,
        payload: dict[str, Any],
    ) -> CommandOutcome:
        if command_type == CommandType.ENSURE_ACCOUNT:
            try:
                user = await self._adapter.get_user_by_username(account.username)
            except AdapterError as exc:
                if not exc.code.startswith("panel_not_found"):
                    raise
                user = await self._adapter.create_user(
                    username=str(payload["username"]),
                    expire_at=datetime.fromisoformat(str(payload["expire_at"])),
                    traffic_limit_bytes=int(payload["traffic_limit_bytes"]),
                    device_limit=int(payload["device_limit"]),
                    email=str(payload["email"]) if payload.get("email") else None,
                    telegram_id=(
                        int(payload["telegram_id"]) if payload.get("telegram_id") else None
                    ),
                    internal_squad_ids=[
                        UUID(str(value)) for value in payload.get("internal_squad_ids", [])
                    ],
                )
            else:
                if user.status.casefold() != "active":
                    user = await self._adapter.enable_user(user.id)
                user = await self._adapter.update_user(
                    user.id,
                    expire_at=datetime.fromisoformat(str(payload["expire_at"])),
                    traffic_limit_bytes=int(payload["traffic_limit_bytes"]),
                    device_limit=int(payload["device_limit"]),
                    internal_squad_ids=[
                        UUID(str(value)) for value in payload.get("internal_squad_ids", [])
                    ],
                )
            return CommandOutcome(user=user)

        user_id = self._external_user_id(account)
        if command_type == CommandType.DISABLE or command_type == CommandType.REVOKE:
            current = await self._adapter.get_user(user_id)
            user = (
                current
                if current.status == "DISABLED"
                else await self._adapter.disable_user(user_id)
            )
            return CommandOutcome(user=user)
        if command_type == CommandType.ENABLE:
            current = await self._adapter.get_user(user_id)
            user = (
                current if current.status == "ACTIVE" else await self._adapter.enable_user(user_id)
            )
            return CommandOutcome(user=user)
        if command_type == CommandType.EXTEND:
            return CommandOutcome(
                user=await self._adapter.update_user(
                    user_id,
                    expire_at=datetime.fromisoformat(str(payload["expires_at"])),
                )
            )
        if command_type == CommandType.CREATE_DEVICE:
            devices = await self._adapter.list_devices(user_id)
            hwid = str(payload["hwid"])
            for device in devices.devices:
                if device.hwid == hwid:
                    return CommandOutcome(device=device)
            return CommandOutcome(
                device=await self._adapter.create_device(
                    user_id,
                    {
                        "hwid": hwid,
                        "platform": payload.get("platform"),
                        "os_version": payload.get("os_version"),
                        "device_model": payload.get("device_model"),
                        "user_agent": payload.get("user_agent"),
                        "request_ip": payload.get("request_ip"),
                    },
                )
            )
        if command_type == CommandType.REMOVE_DEVICE:
            devices = await self._adapter.list_devices(user_id)
            hwid = str(payload["hwid"])
            if not any(device.hwid == hwid for device in devices.devices):
                return CommandOutcome(devices=devices)
            return CommandOutcome(devices=await self._adapter.remove_device(user_id, hwid))
        if command_type == CommandType.SYNC:
            return CommandOutcome(
                user=await self._adapter.get_user(user_id),
                devices=await self._adapter.list_devices(user_id),
            )
        raise AdapterError(
            "unsupported_vpn_command",
            "VPN synchronization command is unsupported.",
            500,
            False,
        )

    async def _apply_outcome(
        self,
        command_type: CommandType,
        account: VpnAccount,
        command: VpnSyncCommand,
        payload: dict[str, Any],
        outcome: CommandOutcome,
    ) -> None:
        now = datetime.now(UTC)
        if outcome.user is not None:
            self._apply_user(account, outcome.user, now)
        if command_type == CommandType.CREATE_DEVICE and outcome.device is not None:
            device_id = UUID(str(payload["device_id"]))
            device = await self._repository.get_device_for_update(device_id, account.user_id)
            if device is None:
                raise RuntimeError("create-device command references no local device")
            device.external_hwid = outcome.device.hwid
            device.platform = outcome.device.platform or device.platform
            device.status = DeviceStatus.OBSERVED.value
            device.first_seen_at = outcome.device.created_at
            device.last_seen_at = outcome.device.updated_at
        if command_type == CommandType.SYNC and outcome.devices is not None:
            await self._apply_devices(account, outcome.devices, now)
        command.status = CommandStatus.SUCCEEDED.value
        command.completed_at = now
        command.locked_at = None
        command.last_error_code = None
        command.last_error_detail = None
        account.last_sync_error_code = None
        account.last_synced_at = now

    def _apply_user(self, account: VpnAccount, user: AdapterUserState, now: datetime) -> None:
        status = user.status.casefold()
        allowed = {value.value for value in ObservedVpnStatus}
        account.remnawave_user_id = user.id
        account.observed_status = status if status in allowed else ObservedVpnStatus.UNKNOWN.value
        account.observed_expires_at = user.expire_at
        account.last_synced_at = now
        if user.subscription_url:
            account.subscription_url_ciphertext = self._cipher.encrypt(user.subscription_url)

    async def _apply_devices(
        self,
        account: VpnAccount,
        remote: AdapterDeviceList,
        now: datetime,
    ) -> None:
        local_devices = await self._repository.list_devices(account.id)
        by_hwid = {
            device.external_hwid: device
            for device in local_devices
            if device.external_hwid is not None
        }
        used_slots = {device.slot_number for device in local_devices}
        remote_hwids: set[str] = set()
        for remote_device in remote.devices:
            remote_hwids.add(remote_device.hwid)
            device = by_hwid.get(remote_device.hwid)
            if device is None:
                slot = 1
                while slot in used_slots:
                    slot += 1
                used_slots.add(slot)
                device = Device(
                    user_id=account.user_id,
                    vpn_account_id=account.id,
                    slot_number=slot,
                    external_hwid=remote_device.hwid,
                    platform=remote_device.platform,
                    status=DeviceStatus.OBSERVED.value,
                    first_seen_at=remote_device.created_at,
                    last_seen_at=remote_device.updated_at,
                )
                self._repository.add_device(device)
                continue
            device.platform = remote_device.platform or device.platform
            device.status = DeviceStatus.OBSERVED.value
            device.first_seen_at = device.first_seen_at or remote_device.created_at
            device.last_seen_at = remote_device.updated_at

        for device in local_devices:
            if (
                device.status == DeviceStatus.OBSERVED.value
                and device.external_hwid not in remote_hwids
            ):
                device.status = DeviceStatus.RESERVED.value

    async def _record_failure(self, command_id: UUID, error: AdapterError) -> None:
        now = datetime.now(UTC)
        async with self._session.begin():
            command = await self._repository.get_processing_command_for_update(command_id)
            account = await self._repository.get_account(command.vpn_account_id, for_update=True)
            terminal = (
                not error.retryable or command.attempt_count >= self._settings.command_max_attempts
            )
            command.status = (
                CommandStatus.DEAD_LETTER.value if terminal else CommandStatus.RETRY_SCHEDULED.value
            )
            command.locked_at = None
            command.last_error_code = error.code[:80]
            command.last_error_detail = error.detail[:1000]
            account.last_sync_error_code = error.code[:80]
            if not terminal:
                delay = min(
                    self._settings.retry_max_seconds,
                    self._settings.retry_base_seconds * 2 ** max(0, command.attempt_count - 1),
                )
                command.next_attempt_at = now + timedelta(seconds=delay)

    @staticmethod
    def _external_user_id(account: VpnAccount) -> int:
        if account.remnawave_user_id is None:
            raise AdapterError(
                "vpn_account_not_provisioned",
                "VPN account has no Remnawave identity.",
                409,
                True,
            )
        return account.remnawave_user_id
