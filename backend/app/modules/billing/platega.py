from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx

from app.core.config import PlategaSettings
from app.core.errors import ApplicationError


@dataclass(frozen=True, slots=True)
class PlategaCheckout:
    transaction_id: UUID
    status: str
    redirect_url: str
    expires_at: datetime | None


class PlategaClient:
    def __init__(
        self,
        settings: PlategaSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=str(settings.base_url).rstrip("/") + "/",
            timeout=settings.timeout_seconds,
            transport=transport,
            headers={
                "X-MerchantId": settings.merchant_id.get_secret_value(),
                "X-Secret": settings.secret.get_secret_value(),
                "Accept": "application/json",
            },
        )

    async def create_checkout(
        self,
        *,
        top_up_id: UUID,
        user_id: UUID,
        amount_minor: int,
        currency: str,
        payment_method: int,
        client_ip: str,
    ) -> PlategaCheckout:
        if amount_minor % 100 != 0:
            raise ApplicationError(
                "wallet_top_up_fraction_not_supported",
                "Platega wallet top-ups must use whole currency units.",
                422,
            )
        payload = {
            "paymentMethod": payment_method,
            "paymentDetails": {
                "amount": amount_minor // 100,
                "currency": currency,
            },
            "description": f"Пополнение баланса Hazbit #{str(top_up_id)[:8]}",
            "return": str(self._settings.success_url),
            "failedUrl": str(self._settings.failed_url),
            "payload": str(top_up_id),
            "metadata": {
                "userId": str(user_id),
                "clientIp": client_ip,
            },
        }
        try:
            response = await self._client.post("transaction/process", json=payload)
            response.raise_for_status()
            value: dict[str, Any] = response.json()
            transaction_id = UUID(str(value["transactionId"]))
            redirect_url = str(value.get("redirect") or value.get("url") or "")
            if not redirect_url.startswith("https://"):
                raise ValueError("Platega response has no secure redirect URL")
            return PlategaCheckout(
                transaction_id=transaction_id,
                status=str(value.get("status", "PENDING")).upper(),
                redirect_url=redirect_url,
                expires_at=self._expires_at(value.get("expiresIn")),
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ApplicationError(
                "platega_unavailable",
                "Payment provider is temporarily unavailable.",
                503,
            ) from exc

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _expires_at(raw: object) -> datetime | None:
        if not isinstance(raw, str):
            return None
        try:
            hours, minutes, seconds = (int(part) for part in raw.split(":"))
        except (TypeError, ValueError):
            return None
        return datetime.now(UTC) + timedelta(hours=hours, minutes=minutes, seconds=seconds)


class DisabledPlategaClient(PlategaClient):
    def __init__(self) -> None:
        self._client = None  # type: ignore[assignment]

    async def create_checkout(self, **_: object) -> PlategaCheckout:
        raise ApplicationError(
            "platega_not_configured",
            "Real payments are not configured in this environment.",
            503,
        )

    async def close(self) -> None:
        return None
