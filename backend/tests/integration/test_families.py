from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import DatabaseSettings, Settings
from app.core.ids import uuid7
from app.database.session import DatabaseManager
from app.modules.auth.crypto import OpaqueTokenCodec, SignalHasher
from app.modules.auth.rate_limit import RateLimit
from app.modules.families.service import FamilyClientContext, FamilyService
from sqlalchemy import text
from sqlalchemy.engine import make_url


class FakeRateLimiter:
    async def enforce(self, policy: RateLimit, identity: str) -> None:
        assert policy.limit > 0
        assert identity


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


def _service(session: object, settings: Settings) -> FamilyService:
    return FamilyService(
        session=session,  # type: ignore[arg-type]
        settings=settings.families,
        rate_limiter=FakeRateLimiter(),  # type: ignore[arg-type]
        token_codec=OpaqueTokenCodec(settings.auth),
        signal_hasher=SignalHasher(settings.auth),
    )


def _context(user_id: UUID) -> FamilyClientContext:
    return FamilyClientContext(
        ip_address="203.0.113.51",
        device_fingerprint=f"family-test-{user_id}",
        user_agent="pytest",
        request_id=uuid7(),
    )


async def _insert_user(database: DatabaseManager, user_id: UUID, email: str) -> None:
    async with database.session() as session, session.begin():
        await session.execute(text("INSERT INTO app.users (id) VALUES (:id)"), {"id": user_id})
        await session.execute(
            text(
                "INSERT INTO app.user_emails "
                "(id, user_id, email, is_primary, verified_at) "
                "VALUES (:id, :user_id, :email, true, now())"
            ),
            {"id": uuid7(), "user_id": user_id, "email": email},
        )


@pytest.mark.integration
async def test_family_membership_projects_and_revokes_shared_entitlement(
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
    owner_id, member_id = uuid7(), uuid7()
    plan_id, plan_version_id, subscription_id = uuid7(), uuid7(), uuid7()
    now = datetime.now(UTC)

    try:
        await _insert_user(database, owner_id, f"owner-{owner_id}@example.com")
        await _insert_user(database, member_id, f"member-{member_id}@example.com")
        async with database.session() as session, session.begin():
            await session.execute(
                text("INSERT INTO app.plans (id, slug, name) VALUES (:id, :slug, 'Family')"),
                {"id": plan_id, "slug": f"family-{plan_id.hex}"},
            )
            await session.execute(
                text(
                    "INSERT INTO app.plan_versions "
                    "(id, plan_id, version, device_limit, family_member_limit, "
                    "traffic_limit_bytes, remnawave_policy, valid_from) VALUES "
                    "(:id, :plan_id, 1, 10, 3, NULL, CAST(:policy AS jsonb), :valid_from)"
                ),
                {
                    "id": plan_version_id,
                    "plan_id": plan_id,
                    "policy": json.dumps({"internal_squad_ids": []}),
                    "valid_from": now,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO app.subscriptions "
                    "(id, owner_user_id, plan_version_id, status, source, starts_at, "
                    "current_period_ends_at, cancel_at_period_end, version) VALUES "
                    "(:id, :owner, :plan_version, 'active', 'purchase', :starts_at, "
                    ":ends_at, false, 1)"
                ),
                {
                    "id": subscription_id,
                    "owner": owner_id,
                    "plan_version": plan_version_id,
                    "starts_at": now,
                    "ends_at": now + timedelta(days=30),
                },
            )

        async with database.session() as session:
            family = await _service(session, settings).create_group(
                owner_user_id=owner_id,
                subscription_id=subscription_id,
                name="Home",
                client=_context(owner_id),
            )
        assert family.active_member_count == 1
        assert family.member_limit == 3

        async with database.session() as session:
            invitation = await _service(session, settings).invite(
                group_id=family.id,
                owner_user_id=owner_id,
                invited_user_id=member_id,
                invited_email=None,
                client=_context(owner_id),
            )
        assert invitation.invite_token

        async with database.session() as session:
            accepted = await _service(session, settings).accept(
                user_id=member_id,
                token=invitation.invite_token,
                client=_context(member_id),
            )
        assert accepted.active_member_count == 2

        async with database.session() as session:
            account = (
                await session.execute(
                    text(
                        "SELECT desired_status, subscription_id FROM app.vpn_accounts "
                        "WHERE user_id = :user_id"
                    ),
                    {"user_id": member_id},
                )
            ).one()
            ensure_count = await session.scalar(
                text(
                    "SELECT count(*) FROM app.vpn_sync_commands "
                    "WHERE command_type = 'ensure_account' AND vpn_account_id IN "
                    "(SELECT id FROM app.vpn_accounts WHERE user_id = :user_id)"
                ),
                {"user_id": member_id},
            )
        assert account == ("active", subscription_id)
        assert ensure_count == 1

        async with database.session() as session:
            await _service(session, settings).remove_member(
                group_id=family.id,
                member_user_id=member_id,
                owner_user_id=owner_id,
                reason="Household access revoked",
                client=_context(owner_id),
            )

        async with database.session() as session:
            state = (
                await session.execute(
                    text(
                        "SELECT va.desired_status, fm.left_at IS NOT NULL "
                        "FROM app.vpn_accounts va JOIN app.family_members fm "
                        "ON fm.user_id = va.user_id WHERE va.user_id = :user_id"
                    ),
                    {"user_id": member_id},
                )
            ).one()
            disable_count = await session.scalar(
                text(
                    "SELECT count(*) FROM app.vpn_sync_commands "
                    "WHERE command_type = 'disable' AND vpn_account_id IN "
                    "(SELECT id FROM app.vpn_accounts WHERE user_id = :user_id)"
                ),
                {"user_id": member_id},
            )
            audits = await session.scalar(
                text("SELECT count(*) FROM app.audit_logs WHERE entity_type LIKE 'family%'")
            )
            events = await session.scalar(
                text("SELECT count(*) FROM app.outbox_events WHERE event_type LIKE 'family.%'")
            )
        assert state == ("disabled", True)
        assert disable_count == 1
        assert int(audits or 0) >= 4
        assert int(events or 0) >= 4
    finally:
        await database.dispose()
