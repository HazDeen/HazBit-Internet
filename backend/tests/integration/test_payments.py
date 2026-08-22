from __future__ import annotations

import io
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import DatabaseSettings, Settings
from app.core.ids import uuid7
from app.database.session import DatabaseManager
from app.modules.auth.rate_limit import RateLimit
from app.modules.payments.enums import ReviewDecision
from app.modules.payments.processor import PaymentAnalysisProcessor
from app.modules.payments.schemas import ReceiptExtraction
from app.modules.payments.service import PaymentClientContext, PaymentService
from fastapi import UploadFile
from PIL import Image
from sqlalchemy import text
from sqlalchemy.engine import make_url


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        assert content_type == "image/jpeg"
        self.objects[key] = data

    async def get(self, key: str) -> bytes:
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def close(self) -> None:
        return None


class FakeExtractor:
    def __init__(self, extraction: ReceiptExtraction) -> None:
        self.extraction = extraction

    async def extract(self, image: bytes, content_type: str) -> ReceiptExtraction:
        assert image.startswith(b"\xff\xd8")
        assert content_type == "image/jpeg"
        return self.extraction

    async def close(self) -> None:
        return None


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


def _receipt_image() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (120, 80), "white").save(output, "PNG")
    return output.getvalue()


async def _create_and_upload(
    *,
    database: DatabaseManager,
    settings: Settings,
    storage: FakeStorage,
    user_id: Any,
    price_id: Any,
    intent_key: str,
) -> Any:
    context = PaymentClientContext("203.0.113.30", "pytest", uuid7())
    async with database.session() as session:
        service = PaymentService(
            session=session,
            settings=settings.payments,
            storage=storage,
            rate_limiter=FakeRateLimiter(),  # type: ignore[arg-type]
        )
        payment = await service.create_intent(
            user_id=user_id,
            plan_price_id=price_id,
            idempotency_key=intent_key,
            client=context,
        )
    async with database.session() as session:
        uploaded = await PaymentService(
            session=session,
            settings=settings.payments,
            storage=storage,
            rate_limiter=FakeRateLimiter(),  # type: ignore[arg-type]
        ).upload_evidence(
            user_id=user_id,
            payment_id=payment.id,
            idempotency_key=f"upload-{intent_key}",
            upload=UploadFile(file=io.BytesIO(_receipt_image()), filename="receipt.png"),
            client=context,
        )
    assert uploaded.payment.status == "uploaded"
    return uploaded.payment


@pytest.mark.integration
async def test_payment_auto_approval_duplicate_guard_and_manual_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = _database_url()
    _migrate(url, monkeypatch)
    settings = Settings(
        _env_file=None,
        environment="test",
        database=DatabaseSettings(url=url, pool_size=2, max_overflow=0),
        payments={"expected_recipient": "HAZBIT VPN"},
    )
    database = DatabaseManager(settings.database)
    storage = FakeStorage()
    now = datetime.now(UTC)
    user_id, plan_id, plan_version_id, price_id = (uuid7() for _ in range(4))
    extraction = ReceiptExtraction(
        is_payment_receipt=True,
        amount_minor=49900,
        currency="RUB",
        operation_date=now.date(),
        operation_number="BANK-OP-123456",
        bank_name="Test Bank",
        recipient="HAZBIT VPN",
        confidence=0.99,
    )
    extractor = FakeExtractor(extraction)

    try:
        async with database.session() as session, session.begin():
            await session.execute(text("INSERT INTO app.users (id) VALUES (:id)"), {"id": user_id})
            await session.execute(
                text("INSERT INTO app.plans (id, slug, name) VALUES (:id, :slug, 'Payments')"),
                {"id": plan_id, "slug": f"payments-{plan_id}"},
            )
            await session.execute(
                text(
                    "INSERT INTO app.plan_versions "
                    "(id, plan_id, version, device_limit, remnawave_policy) "
                    "VALUES (:id, :plan_id, 1, 1, CAST(:policy AS jsonb))"
                ),
                {"id": plan_version_id, "plan_id": plan_id, "policy": json.dumps({})},
            )
            await session.execute(
                text(
                    "INSERT INTO app.plan_prices "
                    "(id, plan_version_id, term_months, duration_days, currency, amount_minor) "
                    "VALUES (:id, :version_id, 1, 30, 'RUB', 49900)"
                ),
                {"id": price_id, "version_id": plan_version_id},
            )

        first = await _create_and_upload(
            database=database,
            settings=settings,
            storage=storage,
            user_id=user_id,
            price_id=price_id,
            intent_key="payment-first",
        )
        async with database.session() as session:
            claims = await PaymentAnalysisProcessor(
                session=session,
                settings=settings.payments,
                storage=storage,
                extractor=extractor,
            ).claim()
        assert [claim.payment_id for claim in claims] == [first.id]
        async with database.session() as session:
            await PaymentAnalysisProcessor(
                session=session,
                settings=settings.payments,
                storage=storage,
                extractor=extractor,
            ).process(claims[0])

        async with database.session() as session:
            first_status = await session.scalar(
                text("SELECT status FROM app.payments WHERE id = :id"), {"id": first.id}
            )
            ledger = (
                await session.execute(
                    text(
                        "SELECT t.status, count(te.id), sum(te.amount_minor) "
                        "FROM app.transactions t JOIN app.transaction_entries te "
                        "ON te.transaction_id = t.id WHERE t.payment_id = :id GROUP BY t.status"
                    ),
                    {"id": first.id},
                )
            ).one()
            outbox_count = await session.scalar(
                text("SELECT count(*) FROM app.outbox_events WHERE aggregate_id = :id"),
                {"id": first.id},
            )
        assert first_status == "approved"
        assert ledger == ("posted", 2, 0)
        assert outbox_count == 1

        async with database.session() as session:
            repeated_upload = await PaymentService(
                session=session,
                settings=settings.payments,
                storage=storage,
                rate_limiter=FakeRateLimiter(),  # type: ignore[arg-type]
            ).upload_evidence(
                user_id=user_id,
                payment_id=first.id,
                idempotency_key="upload-payment-first",
                upload=UploadFile(file=io.BytesIO(_receipt_image()), filename="receipt.png"),
                client=PaymentClientContext("203.0.113.30", "pytest", uuid7()),
            )
        assert repeated_upload.payment.status == "approved"

        second = await _create_and_upload(
            database=database,
            settings=settings,
            storage=storage,
            user_id=user_id,
            price_id=price_id,
            intent_key="payment-second",
        )
        async with database.session() as session:
            claims = await PaymentAnalysisProcessor(
                session=session,
                settings=settings.payments,
                storage=storage,
                extractor=extractor,
            ).claim()
        assert [claim.payment_id for claim in claims] == [second.id]
        async with database.session() as session:
            await PaymentAnalysisProcessor(
                session=session,
                settings=settings.payments,
                storage=storage,
                extractor=extractor,
            ).process(claims[0])

        async with database.session() as session:
            service = PaymentService(
                session=session,
                settings=settings.payments,
                storage=storage,
                rate_limiter=FakeRateLimiter(),  # type: ignore[arg-type]
            )
            pending = await service.get_payment(user_id=user_id, payment_id=second.id)
        assert pending.status == "manual_review"
        assert pending.latest_analysis is not None
        assert pending.latest_analysis.rule_results["checks"]["operation_not_duplicate"] is False

        async with database.session() as session:
            rejected = await PaymentService(
                session=session,
                settings=settings.payments,
                storage=storage,
                rate_limiter=FakeRateLimiter(),  # type: ignore[arg-type]
            ).review_payment(
                payment_id=second.id,
                reviewer_user_id=user_id,
                decision=ReviewDecision.REJECTED,
                reason="Duplicate operation confirmed by reviewer",
                expected_version=pending.version,
            )
        assert rejected.status == "rejected"
    finally:
        await database.dispose()
