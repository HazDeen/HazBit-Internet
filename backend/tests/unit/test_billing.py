from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from app.core.config import PlategaSettings
from app.core.errors import ApplicationError
from app.modules.billing.platega import PlategaClient
from app.modules.billing.schemas import PlategaCallbackPayload
from app.modules.billing.service import BillingService


def provider_settings() -> PlategaSettings:
    return PlategaSettings(
        enabled=True,
        merchant_id="merchant-123",
        secret="provider-secret",
        success_url="https://hazbit.example/#billing/success",
        failed_url="https://hazbit.example/#billing/failed",
    )


@pytest.mark.asyncio
async def test_platega_checkout_uses_documented_headers_and_payload() -> None:
    transaction_id = uuid4()
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["headers"] = dict(request.headers)
        observed["payload"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "transactionId": str(transaction_id),
                "redirect": "https://app.platega.io/pay/demo",
                "status": "PENDING",
                "expiresIn": "00:15:00",
            },
        )

    client = PlategaClient(provider_settings(), transport=httpx.MockTransport(handler))
    top_up_id = uuid4()
    result = await client.create_checkout(
        top_up_id=top_up_id,
        user_id=uuid4(),
        amount_minor=100_000,
        currency="RUB",
        payment_method=2,
        client_ip="203.0.113.7",
    )
    await client.close()

    headers = observed["headers"]
    assert isinstance(headers, dict)
    assert headers["x-merchantid"] == "merchant-123"
    assert headers["x-secret"] == "provider-secret"
    assert result.transaction_id == transaction_id
    assert result.redirect_url.startswith("https://")
    assert f'"payload":"{top_up_id}"' in str(observed["payload"])
    assert '"amount":1000' in str(observed["payload"])


@pytest.mark.asyncio
async def test_platega_rejects_insecure_redirect() -> None:
    client = PlategaClient(
        provider_settings(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"transactionId": str(uuid4()), "redirect": "http://attacker.example"},
            )
        ),
    )

    with pytest.raises(ApplicationError, match="temporarily unavailable"):
        await client.create_checkout(
            top_up_id=uuid4(),
            user_id=uuid4(),
            amount_minor=10_000,
            currency="RUB",
            payment_method=2,
            client_ip="203.0.113.8",
        )
    await client.close()


def test_platega_callback_accepts_documented_mixed_case_fields() -> None:
    transaction_id = uuid4()
    payload = PlategaCallbackPayload.model_validate(
        {
            "Id": str(transaction_id),
            "Amount": "499.00",
            "Currency": "rub",
            "Status": "confirmed",
            "PaymentMethod": 10,
            "Payload": str(uuid4()),
        }
    )

    assert payload.id == transaction_id
    assert payload.currency == "RUB"
    assert payload.status == "CONFIRMED"
    assert BillingService._provider_amount_minor(Decimal("499.00")) == 49_900


def test_platega_callback_rejects_sub_minor_precision() -> None:
    with pytest.raises(ApplicationError, match="invalid precision"):
        BillingService._provider_amount_minor(Decimal("1.001"))
