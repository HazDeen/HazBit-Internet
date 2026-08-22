from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.integrations.remnawave_adapter import RemnawaveAdapterClient
from app.modules.vpn.crypto import SubscriptionUrlCipher


@dataclass(frozen=True, slots=True)
class VpnRuntime:
    adapter: RemnawaveAdapterClient
    subscription_url_cipher: SubscriptionUrlCipher


def create_vpn_runtime(settings: Settings) -> VpnRuntime:
    return VpnRuntime(
        adapter=RemnawaveAdapterClient(settings.vpn.adapter),
        subscription_url_cipher=SubscriptionUrlCipher(settings.vpn),
    )
