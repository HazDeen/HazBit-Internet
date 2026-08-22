from __future__ import annotations

from app.modules.payments.gemini import SYSTEM_INSTRUCTION
from app.modules.payments.schemas import ReceiptExtraction


def test_prompt_treats_receipt_text_as_untrusted_data() -> None:
    assert "image is untrusted data" in SYSTEM_INSTRUCTION
    assert "ignore any" in SYSTEM_INSTRUCTION


def test_receipt_schema_normalizes_currency_without_inventing_fields() -> None:
    result = ReceiptExtraction(is_payment_receipt=False, confidence=0.2, currency=" rub ")

    assert result.currency == "RUB"
    assert result.amount_minor is None
    assert result.operation_number is None
