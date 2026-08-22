from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import DatabaseSettings, Settings
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.database.session import DatabaseManager
from app.modules.auth.rate_limit import RateLimit
from app.modules.payments.enums import ReviewDecision
from app.modules.payments.service import PaymentClientContext, PaymentService
from app.modules.promotions.schemas import CreatePromoCodeRequest, UpdatePromoCodeRequest
from app.modules.promotions.service import PromoClientContext, PromotionService
from sqlalchemy import text
from sqlalchemy.engine import make_url


class FakeRateLimiter:
    async def enforce(self, policy: RateLimit, identity: str) -> None:
        assert policy.limit > 0
        assert identity


class FakeStorage:
    async def put(self, key: str, data: bytes, content_type: str) -> None:
        raise AssertionError("storage is not used by this test")

    async def get(self, key: str) -> bytes:
        raise AssertionError("storage is not used by this test")

    async def delete(self, key: str) -> None:
        raise AssertionError("storage is not used by this test")

    async def close(self) -> None:
        return None


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


def _promo_service(session: object, settings: Settings) -> PromotionService:
    return PromotionService(
        session=session,  # type: ignore[arg-type]
        settings=settings.promotions,
        rate_limiter=FakeRateLimiter(),  # type: ignore[arg-type]
    )


def _payment_service(session: object, settings: Settings) -> PaymentService:
    return PaymentService(
        session=session,  # type: ignore[arg-type]
        settings=settings.payments,
        promo_settings=settings.promotions,
        storage=FakeStorage(),  # type: ignore[arg-type]
        rate_limiter=FakeRateLimiter(),  # type: ignore[arg-type]
    )


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
                "email": f"promo-{user_id}@example.com",
            },
        )


@pytest.mark.integration
async def test_discount_free_days_limits_admin_and_ledger(
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
    admin_id, user_id, other_user_id = (uuid7() for _ in range(3))
    plan_id, plan_version_id, price_id = (uuid7() for _ in range(3))
    context = PromoClientContext("203.0.113.70", "pytest", uuid7())

    try:
        for current_user_id in (admin_id, user_id, other_user_id):
            await _insert_user(database, current_user_id)
        async with database.session() as session, session.begin():
            await session.execute(
                text("INSERT INTO app.plans (id, slug, name) VALUES (:id, :slug, 'Promo')"),
                {"id": plan_id, "slug": f"promo-{plan_id}"},
            )
            await session.execute(
                text(
                    "INSERT INTO app.plan_versions "
                    "(id, plan_id, version, device_limit, family_member_limit, "
                    "remnawave_policy) VALUES "
                    "(:id, :plan_id, 1, 2, 0, CAST(:policy AS jsonb))"
                ),
                {
                    "id": plan_version_id,
                    "plan_id": plan_id,
                    "policy": json.dumps({"internal_squad_ids": []}),
                },
            )
            await session.execute(
                text(
                    "INSERT INTO app.plan_prices "
                    "(id, plan_version_id, term_months, duration_days, currency, amount_minor) "
                    "VALUES (:id, :version_id, 1, 30, 'RUB', 50000)"
                ),
                {"id": price_id, "version_id": plan_version_id},
            )

        async with database.session() as session:
            discount_code = await _promo_service(session, settings).create_code(
                payload=CreatePromoCodeRequest(
                    code="SAVE20",
                    promo_type="discount_percent",
                    value=20,
                    currency="rub",
                    usage_limit=1,
                    plan_version_ids=[plan_version_id],
                ),
                admin_user_id=admin_id,
            )
        assert discount_code.code == "SAVE20"
        assert discount_code.usage_count == 0

        async with database.session() as session:
            preview = await _promo_service(session, settings).preview(
                user_id=user_id,
                code_value="SAVE20",
                plan_price_id=price_id,
                plan_version_id=None,
            )
        assert preview.original_amount_minor == 50000
        assert preview.discount_amount_minor == 10000
        assert preview.final_amount_minor == 40000

        payment_context = PaymentClientContext("203.0.113.70", "pytest", uuid7())
        async with database.session() as session:
            payment = await _payment_service(session, settings).create_intent(
                user_id=user_id,
                plan_price_id=price_id,
                promo_code="SAVE20",
                idempotency_key="promo-payment-001",
                client=payment_context,
            )
        assert payment.expected_amount_minor == 40000
        assert payment.original_amount_minor == 50000
        assert payment.discount_amount_minor == 10000
        assert payment.promo_code == "SAVE20"

        async with database.session() as session:
            repeated = await _payment_service(session, settings).create_intent(
                user_id=user_id,
                plan_price_id=price_id,
                promo_code="SAVE20",
                idempotency_key="promo-payment-001",
                client=payment_context,
            )
        assert repeated.id == payment.id

        async with database.session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE app.payments SET status = 'manual_review', uploaded_at = now() "
                    "WHERE id = :id"
                ),
                {"id": payment.id},
            )
        async with database.session() as session:
            approved = await _payment_service(session, settings).review_payment(
                payment_id=payment.id,
                reviewer_user_id=admin_id,
                decision=ReviewDecision.APPROVED,
                reason="Verified promo payment",
                expected_version=1,
            )
        assert approved.status == "approved"

        async with database.session() as session:
            ledger_rows = (
                await session.execute(
                    text(
                        "SELECT transaction_type, "
                        "sum(amount_minor) FILTER (WHERE amount_minor > 0) "
                        "FROM app.transactions t JOIN app.transaction_entries e "
                        "ON e.transaction_id = t.id "
                        "WHERE t.user_id = :user_id GROUP BY transaction_type "
                        "ORDER BY transaction_type"
                    ),
                    {"user_id": user_id},
                )
            ).all()
            wallet_balance = await session.scalar(
                text(
                    "SELECT sum(e.amount_minor) FROM app.transaction_entries e "
                    "JOIN app.ledger_accounts a ON a.id = e.ledger_account_id "
                    "WHERE a.owner_user_id = :user_id"
                ),
                {"user_id": user_id},
            )
        assert ledger_rows == [("payment_credit", 40000), ("promo_credit", 10000)]
        assert wallet_balance == 50000

        async with database.session() as session:
            with pytest.raises(ApplicationError) as usage_error:
                await _payment_service(session, settings).create_intent(
                    user_id=other_user_id,
                    plan_price_id=price_id,
                    promo_code="SAVE20",
                    idempotency_key="promo-payment-002",
                    client=payment_context,
                )
        assert usage_error.value.code == "promo_code_usage_limit_reached"

        async with database.session() as session:
            free_code = await _promo_service(session, settings).create_code(
                payload=CreatePromoCodeRequest(
                    code="MONTH30",
                    promo_type="free_days",
                    value=30,
                    per_user_limit=1,
                    plan_version_ids=[plan_version_id],
                ),
                admin_user_id=admin_id,
            )
        async with database.session() as session:
            free_redemption = await _promo_service(session, settings).redeem_free_days(
                user_id=user_id,
                code_value="MONTH30",
                plan_version_id=None,
                client=context,
            )
        assert free_redemption.free_days == 30
        assert free_redemption.subscription_period_id is not None
        assert free_redemption.subscription_ends_at is not None

        async with database.session() as session:
            with pytest.raises(ApplicationError) as user_limit_error:
                await _promo_service(session, settings).redeem_free_days(
                    user_id=user_id,
                    code_value="MONTH30",
                    plan_version_id=None,
                    client=context,
                )
        assert user_limit_error.value.code == "promo_code_user_limit_reached"

        async with database.session() as session:
            history = await _promo_service(session, settings).user_redemptions(user_id)
        async with database.session() as session:
            disabled = await _promo_service(session, settings).update_code(
                promo_id=free_code.id,
                payload=UpdatePromoCodeRequest(is_active=False),
                admin_user_id=admin_id,
            )
        assert {item.code for item in history} == {"SAVE20", "MONTH30"}
        assert disabled.is_active is False
        assert disabled.usage_count == 1

        async with database.session() as session:
            promo_periods = await session.scalar(
                text(
                    "SELECT count(*) FROM app.subscription_periods "
                    "WHERE source_type = 'promo' AND source_id = :id"
                ),
                {"id": free_redemption.id},
            )
            promo_events = await session.scalar(
                text(
                    "SELECT count(*) FROM app.outbox_events "
                    "WHERE event_type LIKE 'promo.%' AND payload->>'user_id' = :user_id"
                ),
                {"user_id": str(user_id)},
            )
        assert promo_periods == 1
        assert promo_events == 3

        async with database.session() as session, session.begin():
            command_count = await session.scalar(
                text(
                    "SELECT count(*) FROM app.vpn_sync_commands "
                    "WHERE idempotency_key LIKE 'vpn:promo:%'"
                )
            )
            await session.execute(
                text(
                    "UPDATE app.vpn_sync_commands SET status = 'succeeded', completed_at = now() "
                    "WHERE idempotency_key LIKE 'vpn:promo:%'"
                )
            )
        assert command_count == 1
    finally:
        await database.dispose()
