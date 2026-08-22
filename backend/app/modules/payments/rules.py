from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.core.config import PaymentSettings
from app.modules.payments.models import Payment
from app.modules.payments.schemas import ReceiptExtraction


def normalize_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).casefold()
    compact = re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)
    return compact or None


@dataclass(frozen=True, slots=True)
class PaymentRuleDecision:
    auto_approve: bool
    results: dict[str, Any]
    operation_number_normalized: str | None
    recipient_normalized: str | None


def evaluate_payment_rules(
    *,
    payment: Payment,
    extraction: ReceiptExtraction,
    settings: PaymentSettings,
    duplicate_operation: bool,
) -> PaymentRuleDecision:
    operation_number = normalize_identifier(extraction.operation_number)
    recipient = normalize_identifier(extraction.recipient)
    expected_recipient = normalize_identifier(payment.expected_recipient)
    earliest_date = payment.created_at.date() - timedelta(days=settings.operation_max_age_days)
    latest_date = payment.created_at.date() + timedelta(
        days=settings.operation_future_tolerance_days
    )

    checks: dict[str, bool] = {
        "is_payment_receipt": extraction.is_payment_receipt,
        "amount_exact": extraction.amount_minor == payment.expected_amount_minor,
        "currency_exact": extraction.currency == payment.currency,
        "recipient_exact": recipient is not None and recipient == expected_recipient,
        "operation_number_present": operation_number is not None,
        "operation_date_valid": (
            extraction.operation_date is not None
            and earliest_date <= extraction.operation_date <= latest_date
        ),
        "confidence_sufficient": extraction.confidence >= settings.auto_approve_confidence,
        "operation_not_duplicate": not duplicate_operation,
    }
    return PaymentRuleDecision(
        auto_approve=all(checks.values()),
        results={
            "decision": "auto_approved" if all(checks.values()) else "manual_review",
            "checks": checks,
            "policy": {
                "minimum_confidence": settings.auto_approve_confidence,
                "operation_max_age_days": settings.operation_max_age_days,
                "operation_future_tolerance_days": settings.operation_future_tolerance_days,
            },
        },
        operation_number_normalized=operation_number,
        recipient_normalized=recipient,
    )
