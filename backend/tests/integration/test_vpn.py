from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import DatabaseSettings, Settings
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.database.session import DatabaseManager
from app.integrations.remnawave_adapter import (
    AdapterDeviceList,
    AdapterDeviceState,
    AdapterError,
    AdapterUserState,
)
from app.modules.vpn.crypto import SubscriptionUrlCipher
from app.modules.vpn.processor import VpnCommandProcessor
from app.modules.vpn.service import VpnClientContext, VpnService
from sqlalchemy import text
from sqlalchemy.engine import make_url


class FakeAdapter:
    def __init__(self, now: datetime, external_user_id: int) -> None:
        self.now = now
        self.external_user_id = external_user_id
        self.user: AdapterUserState | None = None
        self.devices: list[AdapterDeviceState] = []
        self.failure: AdapterError | None = None

    async def get_user_by_username(self, username: str) -> AdapterUserState:
        if self.user is None:
            raise AdapterError("panel_not_found_a025", "not found", 404, False)
        return self.user

    async def create_user(self, **payload: Any) -> AdapterUserState:
        self.user = AdapterUserState(
            id=self.external_user_id,
            username=payload["username"],
            status="ACTIVE",
            expire_at=payload["expire_at"],
            traffic_limit_bytes=payload["traffic_limit_bytes"],
            device_limit=payload["device_limit"],
            subscription_url="https://subscription.example/secret-token",
        )
        return self.user

    async def get_user(self, user_id: int) -> AdapterUserState:
        if self.failure is not None:
            raise self.failure
        assert user_id == self.external_user_id and self.user is not None
        return self.user

    async def update_user(self, user_id: int, **payload: Any) -> AdapterUserState:
        assert user_id == self.external_user_id and self.user is not None
        if payload.get("expire_at") is not None:
            self.user.expire_at = payload["expire_at"]
        return self.user

    async def disable_user(self, user_id: int) -> AdapterUserState:
        assert self.user is not None
        self.user.status = "DISABLED"
        return self.user

    async def enable_user(self, user_id: int) -> AdapterUserState:
        assert self.user is not None
        self.user.status = "ACTIVE"
        return self.user

    async def list_devices(self, user_id: int) -> AdapterDeviceList:
        return AdapterDeviceList(total=len(self.devices), devices=self.devices)

    async def create_device(self, user_id: int, payload: dict[str, Any]) -> AdapterDeviceState:
        device = AdapterDeviceState(
            hwid=payload["hwid"],
            user_id=user_id,
            platform=payload.get("platform"),
            os_version=payload.get("os_version"),
            device_model=payload.get("device_model"),
            created_at=self.now,
            updated_at=self.now,
        )
        self.devices.append(device)
        return device

    async def remove_device(self, user_id: int, hwid: str) -> AdapterDeviceList:
        self.devices = [device for device in self.devices if device.hwid != hwid]
        return AdapterDeviceList(total=len(self.devices), devices=self.devices)


def _database_url() -> str:
    value = os.getenv("HAZBIT_TEST_DATABASE_URL")
    if not value:
        pytest.skip("HAZBIT_TEST_DATABASE_URL is not configured")
    return (
        make_url(value).set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)
    )


def _migrate(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAZBIT_DATABASE__URL", url)
    root = Path(__file__).resolve().parents[2]
    command.upgrade(Config(str(root / "alembic.ini")), "head")


async def _claim_and_process(
    database: DatabaseManager,
    settings: Settings,
    adapter: FakeAdapter,
    cipher: SubscriptionUrlCipher,
) -> None:
    async with database.session() as session:
        ids = await VpnCommandProcessor(
            session=session,
            settings=settings.vpn,
            adapter=adapter,  # type: ignore[arg-type]
            cipher=cipher,
        ).claim()
    assert len(ids) == 1
    async with database.session() as session:
        await VpnCommandProcessor(
            session=session,
            settings=settings.vpn,
            adapter=adapter,  # type: ignore[arg-type]
            cipher=cipher,
        ).process(ids[0])


@pytest.mark.integration
async def test_vpn_provision_device_and_remove_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = _database_url()
    _migrate(url, monkeypatch)
    settings = Settings(
        _env_file=None,
        environment="test",
        database=DatabaseSettings(url=url, pool_size=1, max_overflow=0),
    )
    database = DatabaseManager(settings.database)
    cipher = SubscriptionUrlCipher(settings.vpn)
    now = datetime.now(UTC)
    adapter = FakeAdapter(now, uuid7().int % 2_000_000_000 + 1)
    user_id, plan_id, plan_version_id, subscription_id = (uuid7() for _ in range(4))
    context = VpnClientContext("203.0.113.20", "pytest", uuid7())

    try:
        async with database.session() as session, session.begin():
            await session.execute(
                text("INSERT INTO app.users (id) VALUES (:user_id)"),
                {"user_id": user_id},
            )
            await session.execute(
                text(
                    "INSERT INTO app.user_emails "
                    "(id, user_id, email, is_primary, verified_at) "
                    "VALUES (:email_id, :user_id, :email, true, now())"
                ),
                {"email_id": uuid7(), "user_id": user_id, "email": f"vpn-{user_id}@example.com"},
            )
            await session.execute(
                text("INSERT INTO app.plans (id, slug, name) VALUES (:id, :slug, :name)"),
                {"id": plan_id, "slug": f"vpn-{plan_id}", "name": "VPN Integration Test"},
            )
            await session.execute(
                text(
                    "INSERT INTO app.plan_versions "
                    "(id, plan_id, version, device_limit, remnawave_policy) "
                    "VALUES (:id, :plan_id, 1, 1, CAST(:policy AS jsonb))"
                ),
                {
                    "id": plan_version_id,
                    "plan_id": plan_id,
                    "policy": json.dumps({"internal_squad_ids": []}),
                },
            )
            await session.execute(
                text(
                    "INSERT INTO app.subscriptions "
                    "(id, owner_user_id, plan_version_id, status, source, starts_at, "
                    "current_period_ends_at) VALUES "
                    "(:id, :user_id, :version_id, 'active', 'purchase', :starts_at, :ends_at)"
                ),
                {
                    "id": subscription_id,
                    "user_id": user_id,
                    "version_id": plan_version_id,
                    "starts_at": now,
                    "ends_at": now + timedelta(days=30),
                },
            )

        async with database.session() as session:
            account, ensure_command = await VpnService(
                session=session,
                settings=settings.vpn,
                cipher=cipher,
            ).ensure_account(user_id=user_id, subscription_id=subscription_id)
        assert ensure_command.command_type == "ensure_account"
        assert account.remnawave_user_id is None

        await _claim_and_process(database, settings, adapter, cipher)

        async with database.session() as session:
            service = VpnService(session=session, settings=settings.vpn, cipher=cipher)
            account_state = await service.get_account(user_id)
            subscription_url = await service.get_subscription_url(user_id)
        assert account_state.observed_status == "active"
        assert subscription_url == "https://subscription.example/secret-token"

        async with database.session() as session:
            device, device_command = await VpnService(
                session=session,
                settings=settings.vpn,
                cipher=cipher,
            ).create_device(
                user_id=user_id,
                idempotency_key="create-device-1",
                hwid="abcdefghij",
                label="MacBook",
                platform="macOS",
                os_version="15",
                device_model="MacBookPro",
                client=context,
            )
        assert device.status == "reserved"
        assert device_command.command_type == "create_device"

        await _claim_and_process(database, settings, adapter, cipher)

        async with database.session() as session:
            devices = await VpnService(
                session=session,
                settings=settings.vpn,
                cipher=cipher,
            ).list_devices(user_id)
        assert len(devices) == 1
        assert devices[0].status == "observed"

        async with database.session() as session:
            with pytest.raises(ApplicationError) as exc_info:
                await VpnService(
                    session=session,
                    settings=settings.vpn,
                    cipher=cipher,
                ).create_device(
                    user_id=user_id,
                    idempotency_key="create-device-2",
                    hwid="klmnopqrst",
                    label=None,
                    platform=None,
                    os_version=None,
                    device_model=None,
                    client=context,
                )
            assert exc_info.value.code == "device_limit_reached"

        async with database.session() as session:
            remove_command = await VpnService(
                session=session,
                settings=settings.vpn,
                cipher=cipher,
            ).remove_device(
                user_id=user_id,
                device_id=devices[0].id,
                idempotency_key="remove-device-1",
                client=context,
            )
        assert remove_command.command_type == "remove_device"

        await _claim_and_process(database, settings, adapter, cipher)
        assert adapter.devices == []

        async with database.session() as session:
            ciphertext = await session.scalar(
                text(
                    "SELECT subscription_url_ciphertext FROM app.vpn_accounts "
                    "WHERE user_id = :user_id"
                ),
                {"user_id": user_id},
            )
            audit_count = await session.scalar(
                text(
                    "SELECT count(*) FROM app.audit_logs WHERE actor_user_id = :user_id "
                    "AND action LIKE 'vpn.device.%'"
                ),
                {"user_id": user_id},
            )
        assert b"secret-token" not in bytes(ciphertext)
        assert audit_count == 2

        retry_command_id = uuid7()
        async with database.session() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO app.vpn_sync_commands "
                    "(id, vpn_account_id, command_type, idempotency_key, payload) "
                    "VALUES (:id, :account_id, 'sync', :key, '{}'::jsonb)"
                ),
                {
                    "id": retry_command_id,
                    "account_id": account.id,
                    "key": f"vpn:sync:retry-test:{retry_command_id}",
                },
            )
        adapter.failure = AdapterError(
            "adapter_unavailable",
            "Remnawave adapter is unavailable.",
            503,
            True,
        )
        await _claim_and_process(database, settings, adapter, cipher)
        async with database.session() as session:
            retry_state = (
                await session.execute(
                    text(
                        "SELECT status, attempt_count, next_attempt_at > now() "
                        "FROM app.vpn_sync_commands WHERE id = :id"
                    ),
                    {"id": retry_command_id},
                )
            ).one()
        assert retry_state == ("retry_scheduled", 1, True)
    finally:
        await database.dispose()
