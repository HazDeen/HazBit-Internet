from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.modules.bots.runtime import create_telegram_bots_runtime


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    if not settings.features.telegram_bots:
        print("Telegram bots are disabled by HAZBIT_FEATURES__TELEGRAM_BOTS=false")
        return
    runtime = create_telegram_bots_runtime(settings)
    base = str(settings.telegram_bots.webhook_base_url).rstrip("/")
    expected = {
        "customer": f"{base}{settings.api_v1_prefix}/bots/customer/webhook",
        "operations": f"{base}{settings.api_v1_prefix}/bots/operations/webhook",
    }
    failures: list[str] = []
    try:
        for label, client in (("customer", runtime.customer), ("operations", runtime.operations)):
            identity = await client.call("getMe", {})
            webhook = await client.call("getWebhookInfo", {})
            identity_data = identity if isinstance(identity, dict) else {}
            webhook_data: dict[str, Any] = webhook if isinstance(webhook, dict) else {}
            print(
                f"{label}: @{identity_data.get('username', '?')} -> "
                f"{webhook_data.get('url') or '(webhook missing)'}; "
                f"pending={webhook_data.get('pending_update_count', 0)}"
            )
            if webhook_data.get("url") != expected[label]:
                failures.append(f"{label} webhook URL does not match {expected[label]}")
            if webhook_data.get("last_error_message"):
                failures.append(f"{label} Telegram error: {webhook_data['last_error_message']}")
        if failures:
            raise RuntimeError("; ".join(failures))
    finally:
        await runtime.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
