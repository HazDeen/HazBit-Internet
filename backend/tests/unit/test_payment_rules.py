from __future__ import annotations

from datetime import UTC, date, datetime

from app.core.config import PaymentSettings
from app.core.ids import uuid7
from app.modules.payments.models import Payment
from app.modules.payments.rules import evaluate_payment_rules, normalize_identifier
from app.modules.payments.schemas import ReceiptExtraction


def _payment() -> Payment:
    now = datetime.now(UTC)
    return Payment(
        id=uuid7(),
        user_id=uuid7(),
        plan_price_id=uuid7(),
        status="analyzing",
        expected_amount_minor=49900,
        currency="RUB",
        expected_recipient="OOO Hazbit VPN",
        idempotency_key="payment-rule-test",
        expires_at=now,
        version=1,
        created_at=now,
        updated_at=now,
    )


def _extraction() -> ReceiptExtraction:
    return ReceiptExtraction(
        is_payment_receipt=True,
        amount_minor=49900,
        currency="rub",
        operation_date=date.today(),
        operation_number="AB-123 456",
        bank_name="Test Bank",
        recipient="ooo hazbit vpn",
        confidence=0.99,
    )


def test_all_deterministic_rules_must_pass_for_auto_approval() -> None:
    decision = evaluate_payment_rules(
        payment=_payment(),
        extraction=_extraction(),
        settings=PaymentSettings(expected_recipient="OOO Hazbit VPN"),
        duplicate_operation=False,
    )

    assert decision.auto_approve is True
    assert decision.results["decision"] == "auto_approved"
    assert decision.operation_number_normalized == "ab123456"


def test_duplicate_operation_forces_manual_review() -> None:
    decision = evaluate_payment_rules(
        payment=_payment(),
        extraction=_extraction(),
        settings=PaymentSettings(expected_recipient="OOO Hazbit VPN"),
        duplicate_operation=True,
    )

    assert decision.auto_approve is False
    assert decision.results["decision"] == "manual_review"
    assert decision.results["checks"]["operation_not_duplicate"] is False


def test_identifier_normalization_is_case_and_punctuation_stable() -> None:
    assert normalize_identifier("  OOO [Hazbit-VPN]  ") == "ooohazbitvpn"
