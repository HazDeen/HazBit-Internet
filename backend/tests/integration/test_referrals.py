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
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.database.session import DatabaseManager
from app.modules.auth.crypto import SignalHasher
from app.modules.auth.rate_limit import RateLimit
from app.modules.referrals.processor import ReferralRewardProcessor
from app.modules.referrals.service import ReferralClientContext, ReferralService
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


def _service(session: object, settings: Settings) -> ReferralService:
    return ReferralService(
        session=session,  # type: ignore[arg-type]
        settings=settings.referrals,
        rate_limiter=FakeRateLimiter(),  # type: ignore[arg-type]
        signal_hasher=SignalHasher(settings.auth),
    )


def _context(ip: str, fingerprint: str | None) -> ReferralClientContext:
    return ReferralClientContext(ip, fingerprint, "pytest", uuid7())


async def _insert_user(database: DatabaseManager, user_id: UUID) -> None:
    async with database.session() as session, session.begin():
        await session.execute(text("INSERT INTO app.users (id) VALUES (:id)"), {"id": user_id})
        await session.execute(
            text(
                "INSERT INTO app.user_emails "
                "(id, user_id, email, is_primary, verified_at) "
                "VALUES (:id, :user_id, :email, true, now())"
            ),
            {
                "id": uuid7(),
                "user_id": user_id,
                "email": f"referral-{user_id}@example.com",
            },
        )


@pytest.mark.integration
async def test_referral_rewards_review_statistics_and_idempotency(
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
    referrer_id, referred_id, reviewed_user_id = (uuid7() for _ in range(3))
    plan_id, plan_version_id = uuid7(), uuid7()

    try:
        for user_id in (referrer_id, referred_id, reviewed_user_id):
            await _insert_user(database, user_id)
        async with database.session() as session, session.begin():
            await session.execute(
                text("INSERT INTO app.plans (id, slug, name) VALUES (:id, 'basic', 'Basic')"),
                {"id": plan_id},
            )
            await session.execute(
                text(
                    "INSERT INTO app.plan_versions "
                    "(id, plan_id, version, device_limit, family_member_limit, "
                    "remnawave_policy) VALUES "
                    "(:id, :plan_id, 1, 3, 0, CAST(:policy AS jsonb))"
                ),
                {
                    "id": plan_version_id,
                    "plan_id": plan_id,
                    "policy": json.dumps({"internal_squad_ids": []}),
                },
            )

        async with database.session() as session:
            code = await _service(session, settings).get_or_create_code(referrer_id)
        assert len(code.code) == settings.referrals.code_length
        assert code.share_url.endswith(code.code)

        async with database.session() as session:
            claim = await _service(session, settings).claim(
                user_id=referred_id,
                code_value=code.code,
                client=_context("203.0.113.40", "device-referred-001"),
            )
        assert claim.status == "qualified"
        assert claim.risk_decision == "allow"
        assert sorted(reward.days for reward in claim.rewards) == [3, 5]

        async with database.session() as session:
            repeated = await _service(session, settings).claim(
                user_id=referred_id,
                code_value=code.code,
                client=_context("203.0.113.40", "device-referred-001"),
            )
        assert repeated.id == claim.id

        async with database.session() as session:
            processed = await ReferralRewardProcessor(
                session=session, settings=settings.referrals
            ).process_batch()
        assert processed == 1
        async with database.session() as session:
            assert (
                await ReferralRewardProcessor(
                    session=session, settings=settings.referrals
                ).process_batch()
                == 0
            )

        async with database.session() as session:
            referral_status = await session.scalar(
                text("SELECT status FROM app.referrals WHERE id = :id"), {"id": claim.id}
            )
            rewards = (
                await session.execute(
                    text(
                        "SELECT reward_side, days, status FROM app.referral_rewards "
                        "WHERE referral_id = :id ORDER BY reward_side"
                    ),
                    {"id": claim.id},
                )
            ).all()
            trial = (
                await session.execute(
                    text(
                        "SELECT duration_days, decision FROM app.trial_grants "
                        "WHERE user_id = :user_id"
                    ),
                    {"user_id": referred_id},
                )
            ).one()
            periods = await session.scalar(
                text("SELECT count(*) FROM app.subscription_periods WHERE source_type = 'referral'")
            )
            commands = await session.scalar(
                text(
                    "SELECT count(*) FROM app.vpn_sync_commands "
                    "WHERE command_type = 'ensure_account' "
                    "AND idempotency_key LIKE 'vpn:referral:%'"
                )
            )
            outbox = await session.scalar(
                text("SELECT count(*) FROM app.outbox_events WHERE event_type LIKE 'referral.%'")
            )
        assert referral_status == "rewarded"
        assert rewards == [("referred", 3, "granted"), ("referrer", 5, "granted")]
        assert trial == (3, "granted")
        assert periods == 2
        assert commands == 2
        assert outbox == 3

        async with database.session() as session:
            stats = await _service(session, settings).statistics(referrer_id)
        assert stats.total == 1
        assert stats.rewarded == 1
        assert stats.granted_referrer_days == 5
        async with database.session() as session:
            referred_stats = await _service(session, settings).statistics(referred_id)
        assert referred_stats.referred_by_status == "rewarded"
        assert referred_stats.referred_reward_days == 3

        review_ip = "203.0.113.99"
        ip_hash = SignalHasher(settings.auth).digest("ip", review_ip)
        async with database.session() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO app.risk_signals "
                    "(id, user_id, signal_type, signal_hash, score, decision, context, expires_at) "
                    "VALUES (:id, :user_id, 'ip', :hash, 0, 'allow', '{}'::jsonb, :expires)"
                ),
                {
                    "id": uuid7(),
                    "user_id": referrer_id,
                    "hash": ip_hash,
                    "expires": datetime.now(UTC) + timedelta(days=30),
                },
            )
        async with database.session() as session:
            review_claim = await _service(session, settings).claim(
                user_id=reviewed_user_id,
                code_value=code.code,
                client=_context(review_ip, None),
            )
        assert review_claim.status == "attributed"
        assert review_claim.risk_decision == "review"

        async with database.session() as session:
            queue = await _service(session, settings).review_queue(50)
        assert [item.referral_id for item in queue] == [review_claim.id]

        async with database.session() as session:
            approved = await _service(session, settings).review(
                referral_id=review_claim.id,
                reviewer_user_id=referrer_id,
                decision="approved",
                reason="Household members verified manually",
            )
        assert approved.status == "qualified"
        async with database.session() as session:
            assert (
                await ReferralRewardProcessor(
                    session=session, settings=settings.referrals
                ).process_batch()
                == 1
            )

        async with database.session() as session:
            updated_stats = await _service(session, settings).statistics(referrer_id)
            referrer_period_days = await session.scalar(
                text(
                    "SELECT extract(epoch FROM "
                    "(max(current_period_ends_at) - min(starts_at))) / 86400 "
                    "FROM app.subscriptions WHERE owner_user_id = :user_id"
                ),
                {"user_id": referrer_id},
            )
        assert updated_stats.rewarded == 2
        assert updated_stats.granted_referrer_days == 10
        assert float(referrer_period_days) >= 9.99

        async with database.session() as session:
            with pytest.raises(ApplicationError) as exc_info:
                await _service(session, settings).claim(
                    user_id=referrer_id,
                    code_value=code.code,
                    client=_context("203.0.113.50", "device-referrer-001"),
                )
        assert exc_info.value.code == "referral_self_claim_forbidden"

        # Keep the shared integration database queue-neutral for later VPN tests.
        async with database.session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE app.vpn_sync_commands SET status = 'succeeded', "
                    "completed_at = now() WHERE idempotency_key LIKE 'vpn:referral:%'"
                )
            )
    finally:
        await database.dispose()
