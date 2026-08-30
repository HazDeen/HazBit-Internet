from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.core.logging import configure_logging, redact_telegram_tokens
from app.modules.bots.health import wait_for_public_webhooks, webhook_urls
from app.modules.bots.runtime import create_telegram_bots_runtime
from app.modules.bots.telegram_api import TelegramBotClient


async def verify_delivery(
    clients: Mapping[str, TelegramBotClient],
    expected: Mapping[str, str],
    *,
    verification_started_at: int,
    attempts: int = 7,
    retry_seconds: float = 5,
) -> None:
    """Call only after public route checks. Never discard or consume pending updates."""
    failures = ["Telegram verification did not complete"]
    try:
        async with asyncio.timeout(60):
            for label, client in clients.items():
                identity = await client.call("getMe", {})
                if not isinstance(identity, dict) or identity.get("is_bot") is not True:
                    raise RuntimeError(f"{label}: getMe did not return a bot identity")
                print(f"{label}: @{identity.get('username', '?')}", flush=True)
            for attempt in range(attempts):
                failures = []
                for label, client in clients.items():
                    webhook = await client.call("getWebhookInfo", {})
                    data: dict[str, Any] = webhook if isinstance(webhook, dict) else {}
                    pending = data.get("pending_update_count")
                    error = data.get("last_error_message")
                    error_date = data.get("last_error_date")
                    timestamp = error_date if isinstance(error_date, int) else 0
                    date_valid = type(error_date) is int and timestamp > 0
                    error_time = str(error_date)
                    if date_valid:
                        try:
                            error_time = datetime.fromtimestamp(timestamp, UTC).isoformat()
                        except (ValueError, OverflowError, OSError):
                            date_valid = False
                    print(
                        redact_telegram_tokens(
                            f"{label}: {data.get('url') or '(webhook missing)'}; "
                            f"pending={pending}; "
                            f"last_error_date={error_time}; last_error={error or 'none'}"
                        ),
                        flush=True,
                    )
                    if data.get("url") != expected[label]:
                        failures.append(f"{label}: webhook URL does not match {expected[label]}")
                    if type(pending) is not int or pending < 0:
                        failures.append(f"{label}: invalid pending_update_count")
                    elif pending:
                        failures.append(f"{label}: pending={pending}, delivery not yet confirmed")
                    if error and (not date_valid or timestamp >= verification_started_at):
                        failures.append(
                            f"{label}: new or undated Telegram error: {error} ({error_time})"
                        )
                    elif error and pending == 0:
                        print(
                            f"{label}: historical error; queue empty, public route checked",
                            flush=True,
                        )
                if not failures:
                    print("Telegram webhook checks passed. Send /start to verify bot replies.")
                    return
                if attempt + 1 < attempts:
                    print(f"Waiting for Telegram delivery ({attempt + 1}/{attempts})…", flush=True)
                    await asyncio.sleep(retry_seconds)
    except TimeoutError:
        failures.append("Telegram verification exceeded 60 seconds")
    raise RuntimeError(
        redact_telegram_tokens(
            "; ".join(failures) + ". Keep the stack running; inspect platform/Caddy logs and rerun "
            "python -m app.workers.check_telegram_bots. Pending updates were not deleted."
        )
    )


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    if not settings.features.telegram_bots:
        print("Telegram bots are disabled by HAZBIT_FEATURES__TELEGRAM_BOTS=false")
        return
    verification_started_at = int(time.time())
    await wait_for_public_webhooks(settings)
    runtime = create_telegram_bots_runtime(settings)
    try:
        await verify_delivery(
            {"customer": runtime.customer, "operations": runtime.operations},
            webhook_urls(settings),
            verification_started_at=verification_started_at,
        )
    finally:
        await runtime.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
