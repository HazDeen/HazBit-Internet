from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import DatabaseSettings, Settings
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.database.session import DatabaseManager
from app.modules.admin.schemas import (
    AdminPlanPriceInput,
    ArchiveAdminPlanRequest,
    CreateAdminPlanRequest,
    CreateAdminPlanVersionRequest,
    UpdateAdminPlanRequest,
)
from app.modules.admin.service import AdminService
from sqlalchemy import text
from sqlalchemy.engine import make_url


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


@pytest.mark.integration
async def test_admin_dashboard_user_controls_and_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = _database_url()
    _migrate(url, monkeypatch)
    settings = Settings(
        _env_file=None,
        environment="test",
        database=DatabaseSettings(url=url, pool_size=2, max_overflow=0),
    )
    database = DatabaseManager(settings.database)
    now = datetime.now(UTC)
    admin_id, user_id = uuid7(), uuid7()
    plan_a_id, plan_b_id = uuid7(), uuid7()
    version_a_id, version_b_id, price_id = uuid7(), uuid7(), uuid7()
    subscription_id, account_id, device_id = uuid7(), uuid7(), uuid7()
    family_group_id, family_member_id = uuid7(), uuid7()
    payment_id, pending_payment_id, session_id = uuid7(), uuid7(), uuid7()
    slug_suffix = user_id.hex[:10]
    original_expiry = now + timedelta(days=5)

    try:
        async with database.session() as session, session.begin():
            for current_id in (admin_id, user_id):
                await session.execute(
                    text("INSERT INTO app.users (id) VALUES (:id)"), {"id": current_id}
                )
            await session.execute(
                text("INSERT INTO app.user_roles (user_id, role) VALUES (:user_id, 'admin')"),
                {"user_id": admin_id},
            )
            await session.execute(
                text(
                    "INSERT INTO app.user_emails (user_id, email, is_primary, verified_at) "
                    "VALUES (:user_id, :email, true, :now)"
                ),
                {"user_id": user_id, "email": f"ops-{slug_suffix}@hazbit.test", "now": now},
            )
            await session.execute(
                text(
                    "INSERT INTO app.telegram_accounts "
                    "(user_id, telegram_user_id, username) "
                    "VALUES (:user_id, :telegram_id, :username)"
                ),
                {
                    "user_id": user_id,
                    "telegram_id": int(user_id.hex[:10], 16),
                    "username": f"hazbit_{slug_suffix}",
                },
            )
            await session.execute(
                text(
                    "INSERT INTO app.plans (id, slug, name, description, sort_order) VALUES "
                    "(:a, :slug_a, 'Admin Basic', 'Base test plan', 100), "
                    "(:b, :slug_b, 'Admin Pro', 'Target test plan', 101)"
                ),
                {
                    "a": plan_a_id,
                    "b": plan_b_id,
                    "slug_a": f"admin-basic-{slug_suffix}",
                    "slug_b": f"admin-pro-{slug_suffix}",
                },
            )
            await session.execute(
                text(
                    "INSERT INTO app.plan_versions "
                    "(id, plan_id, version, device_limit, family_member_limit, "
                    " remnawave_policy, valid_from) VALUES "
                    "(:a, :plan_a, 1, 2, 0, '{}'::jsonb, :valid_from), "
                    "(:b, :plan_b, 1, 5, 1, '{}'::jsonb, :valid_from)"
                ),
                {
                    "a": version_a_id,
                    "b": version_b_id,
                    "plan_a": plan_a_id,
                    "plan_b": plan_b_id,
                    "valid_from": now - timedelta(days=30),
                },
            )
            await session.execute(
                text(
                    "INSERT INTO app.plan_prices "
                    "(id, plan_version_id, term_months, duration_days, currency, "
                    " amount_minor, valid_from) "
                    "VALUES (:id, :version_id, 1, 30, 'RUB', 99900, :valid_from)"
                ),
                {"id": price_id, "version_id": version_a_id, "valid_from": now},
            )
            await session.execute(
                text(
                    "INSERT INTO app.subscriptions "
                    "(id, owner_user_id, plan_version_id, status, source, starts_at, "
                    " current_period_ends_at) "
                    "VALUES (:id, :user_id, :version_id, 'active', 'trial', :starts, :ends)"
                ),
                {
                    "id": subscription_id,
                    "user_id": user_id,
                    "version_id": version_a_id,
                    "starts": now - timedelta(days=5),
                    "ends": original_expiry,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO app.subscription_periods "
                    "(subscription_id, source_type, starts_at, ends_at, plan_snapshot) "
                    "VALUES (:id, 'trial', :starts, :ends, '{}'::jsonb)"
                ),
                {
                    "id": subscription_id,
                    "starts": now - timedelta(days=5),
                    "ends": original_expiry,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO app.family_groups "
                    "(id, owner_user_id, subscription_id, name, member_limit) "
                    "VALUES (:id, :user_id, :subscription_id, 'Admin test family', 3)"
                ),
                {
                    "id": family_group_id,
                    "user_id": user_id,
                    "subscription_id": subscription_id,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO app.family_members (id, family_group_id, user_id) "
                    "VALUES (:id, :group_id, :user_id)"
                ),
                {"id": family_member_id, "group_id": family_group_id, "user_id": user_id},
            )
            await session.execute(
                text(
                    "INSERT INTO app.trial_grants "
                    "(user_id, subscription_id, duration_days, decision, granted_at) "
                    "VALUES (:user_id, :subscription_id, 10, 'granted', :now)"
                ),
                {"user_id": user_id, "subscription_id": subscription_id, "now": now},
            )
            await session.execute(
                text(
                    "INSERT INTO app.vpn_accounts "
                    "(id, user_id, subscription_id, remnawave_user_id, username, "
                    " desired_status, desired_expires_at) "
                    "VALUES (:id, :user_id, :subscription_id, :remote_id, :username, "
                    " 'active', :expires)"
                ),
                {
                    "id": account_id,
                    "user_id": user_id,
                    "subscription_id": subscription_id,
                    "remote_id": int(user_id.hex[:12], 16),
                    "username": f"admin_{slug_suffix}",
                    "expires": original_expiry,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO app.devices "
                    "(id, user_id, vpn_account_id, slot_number, label, external_hwid, "
                    " platform, status, first_seen_at, last_seen_at) "
                    "VALUES (:id, :user_id, :account_id, 1, 'MacBook', :hwid, "
                    " 'macOS', 'observed', :now, :now)"
                ),
                {
                    "id": device_id,
                    "user_id": user_id,
                    "account_id": account_id,
                    "hwid": f"hwid-{slug_suffix}",
                    "now": now,
                },
            )
            for current_id, status, approved_at in (
                (payment_id, "approved", now),
                (pending_payment_id, "manual_review", None),
            ):
                await session.execute(
                    text(
                        "INSERT INTO app.payments "
                        "(id, user_id, plan_price_id, status, expected_amount_minor, "
                        " currency, expected_recipient, idempotency_key, expires_at, "
                        " uploaded_at, approved_at) "
                        "VALUES (:id, :user_id, :price_id, :status, 99900, 'RUB', "
                        " 'HAZBIT VPN', :key, :expires_at, :uploaded_at, :approved_at)"
                    ),
                    {
                        "id": current_id,
                        "user_id": user_id,
                        "price_id": price_id,
                        "status": status,
                        "key": f"admin-{status}-{current_id}",
                        "expires_at": now + timedelta(days=1),
                        "uploaded_at": now,
                        "approved_at": approved_at,
                    },
                )
            await session.execute(
                text(
                    "INSERT INTO app.auth_sessions "
                    "(id, user_id, token_family_id, refresh_token_hash, expires_at) "
                    "VALUES (:id, :user_id, :family_id, :token_hash, :expires_at)"
                ),
                {
                    "id": session_id,
                    "user_id": user_id,
                    "family_id": uuid7(),
                    "token_hash": user_id.bytes,
                    "expires_at": now + timedelta(days=30),
                },
            )

        async with database.session() as session:
            service = AdminService(session=session, settings=settings)
            dashboard = await service.dashboard()
            users = await service.users(
                search=f"ops-{slug_suffix}", status="active", limit=10, offset=0
            )
            detail = await service.user(user_id)
            plans = await service.plans()
        assert dashboard.total_users >= 2
        assert dashboard.active_subscriptions >= 1
        assert dashboard.monthly_revenue_minor >= 99900
        assert dashboard.pending_payments >= 1
        assert users.total == 1
        assert users.items[0].id == user_id
        assert users.items[0].devices == 1
        assert users.items[0].trial is True
        assert users.items[0].approved_payments == 1
        assert detail.telegram_username == f"hazbit_{slug_suffix}"
        assert detail.payments[0].version == 1
        assert any(plan.id == plan_a_id and plan.versions[0].prices for plan in plans)

        async with database.session() as session:
            with pytest.raises(ApplicationError) as self_block:
                await AdminService(session=session, settings=settings).block_user(
                    user_id=admin_id, actor_user_id=admin_id, reason="Safety check"
                )
        assert self_block.value.code == "admin_self_block_forbidden"

        async with database.session() as session:
            blocked = await AdminService(session=session, settings=settings).block_user(
                user_id=user_id, actor_user_id=admin_id, reason="Abuse investigation"
            )
        assert blocked.status == "blocked"

        async with database.session() as session:
            state = (
                await session.execute(
                    text(
                        "SELECT u.status, s.revoked_at, v.desired_status "
                        "FROM app.users u "
                        "JOIN app.auth_sessions s ON s.user_id = u.id "
                        "JOIN app.vpn_accounts v ON v.user_id = u.id "
                        "WHERE u.id = :id"
                    ),
                    {"id": user_id},
                )
            ).one()
            disable_commands = await session.scalar(
                text(
                    "SELECT count(*) FROM app.vpn_sync_commands "
                    "WHERE vpn_account_id = :id AND command_type = 'disable'"
                ),
                {"id": account_id},
            )
        assert state[0] == "blocked"
        assert state[1] is not None
        assert state[2] == "disabled"
        assert disable_commands == 1

        async with database.session() as session:
            unblocked = await AdminService(session=session, settings=settings).unblock_user(
                user_id=user_id, actor_user_id=admin_id, reason="Investigation cleared"
            )
        assert unblocked.status == "active"

        async with database.session() as session:
            extended = await AdminService(session=session, settings=settings).extend_subscription(
                user_id=user_id,
                actor_user_id=admin_id,
                days=7,
                reason="Customer care adjustment",
            )
        assert extended.current_period_ends_at == original_expiry + timedelta(days=7)
        assert extended.version == 2

        async with database.session() as session:
            changed = await AdminService(session=session, settings=settings).change_plan(
                user_id=user_id,
                actor_user_id=admin_id,
                plan_version_id=version_b_id,
                reason="Upgrade requested by customer",
            )
        assert changed.plan_version_id == version_b_id
        assert changed.plan_name == "Admin Pro"
        assert changed.device_limit == 5
        assert changed.version == 3

        async with database.session() as session:
            service = AdminService(session=session, settings=settings)
            subscriptions = await service.subscriptions(status="active", limit=100, offset=0)
            payments = await service.payments(status="manual_review", limit=100, offset=0)
            devices = await service.devices(user_id=user_id, limit=100, offset=0)
            families = await service.family_groups(limit=100, offset=0)
            family = await service.family_group(family_group_id)
            safe_settings = await service.settings()
        assert any(item.id == subscription_id for item in subscriptions.items)
        assert any(item.id == pending_payment_id for item in payments.items)
        assert [item.id for item in devices.items] == [device_id]
        assert any(item.id == family_group_id for item in families.items)
        assert [member.id for member in family.members] == [family_member_id]
        assert family.owner_email == f"ops-{slug_suffix}@hazbit.test"
        assert safe_settings.environment == "test"
        assert "secret" not in safe_settings.model_dump_json().lower()

        create_plan_payload = CreateAdminPlanRequest(
            slug=f"managed-{slug_suffix}",
            name="Managed plan",
            description="Created through the admin catalog",
            sort_order=500,
            device_limit=3,
            family_member_limit=1,
            prices=[
                AdminPlanPriceInput(
                    term_months=1,
                    duration_days=30,
                    currency="RUB",
                    amount_minor=59900,
                )
            ],
            reason="Integration test catalog create",
        )
        async with database.session() as session:
            created_plan = await AdminService(session=session, settings=settings).create_plan(
                payload=create_plan_payload, actor_user_id=admin_id
            )
        assert created_plan.versions[0].version == 1

        async with database.session() as session:
            updated_plan = await AdminService(session=session, settings=settings).update_plan(
                plan_id=created_plan.id,
                payload=UpdateAdminPlanRequest(
                    name="Managed Pro",
                    reason="Integration test metadata update",
                ),
                actor_user_id=admin_id,
            )
        assert updated_plan.name == "Managed Pro"

        async with database.session() as session:
            versioned_plan = await AdminService(
                session=session, settings=settings
            ).create_plan_version(
                plan_id=created_plan.id,
                payload=CreateAdminPlanVersionRequest(
                    device_limit=6,
                    family_member_limit=3,
                    prices=[
                        AdminPlanPriceInput(
                            term_months=3,
                            duration_days=90,
                            currency="RUB",
                            amount_minor=149900,
                        )
                    ],
                    reason="Integration test new catalog version",
                ),
                actor_user_id=admin_id,
            )
        assert versioned_plan.versions[0].version == 2
        assert versioned_plan.versions[0].device_limit == 6

        async with database.session() as session:
            archived_plan = await AdminService(session=session, settings=settings).archive_plan(
                plan_id=created_plan.id,
                payload=ArchiveAdminPlanRequest(reason="Integration test catalog archive"),
                actor_user_id=admin_id,
            )
        assert archived_plan.is_active is False

        async with database.session() as session, session.begin():
            audit_actions = set(
                await session.scalars(
                    text(
                        "SELECT action FROM app.audit_logs "
                        "WHERE actor_user_id = :admin_id AND entity_id IN (:user_id, :sub_id)"
                    ),
                    {"admin_id": admin_id, "user_id": user_id, "sub_id": subscription_id},
                )
            )
            await session.execute(
                text(
                    "UPDATE app.vpn_sync_commands SET status = 'succeeded', "
                    "completed_at = now() WHERE vpn_account_id = :id"
                ),
                {"id": account_id},
            )
        assert {
            "admin.user_blocked",
            "admin.user_unblocked",
            "admin.subscription_extended",
            "admin.subscription_plan_changed",
        }.issubset(audit_actions)
    finally:
        await database.dispose()
