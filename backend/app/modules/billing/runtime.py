from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.modules.billing.platega import DisabledPlategaClient, PlategaClient


@dataclass(frozen=True, slots=True)
class BillingRuntime:
    platega: PlategaClient


def create_billing_runtime(settings: Settings) -> BillingRuntime:
    provider = settings.billing.platega
    return BillingRuntime(
        platega=PlategaClient(provider) if provider.enabled else DisabledPlategaClient()
    )
