from __future__ import annotations

import pytest
from app.modules.promotions.schemas import CreatePromoCodeRequest, PromoCodeValue
from pydantic import ValidationError


def test_promo_code_is_normalized() -> None:
    assert PromoCodeValue(code=" summer-20 ").code == "SUMMER-20"


def test_discount_percent_cannot_make_payment_free() -> None:
    with pytest.raises(ValidationError, match="between 1 and 99"):
        CreatePromoCodeRequest(code="FREE", promo_type="discount_percent", value=100)


def test_free_days_rejects_currency() -> None:
    with pytest.raises(ValidationError, match="currency"):
        CreatePromoCodeRequest(code="MONTH", promo_type="free_days", value=30, currency="rub")
