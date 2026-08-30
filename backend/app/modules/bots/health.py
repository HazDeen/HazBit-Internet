from __future__ import annotations

import asyncio

import httpx

from app.core.config import Settings
from app.core.logging import get_logger


def webhook_urls(settings: Settings) -> dict[str, str]:
    base = str(settings.telegram_bots.webhook_base_url).rstrip("/")
    return {
        kind: f"{base}{settings.api_v1_prefix}/bots/{kind}/webhook"
        for kind in ("customer", "operations")
    }


async def wait_for_public_webhooks(
    settings: Settings,
    *,
    attempts: int = 7,
    retry_seconds: float = 5,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Probe the public proxy without credentials or processing a Telegram update."""
    base = str(settings.telegram_bots.webhook_base_url).rstrip("/")
    probes = [(f"{base}/health/ready", 200, "status", "ok")]
    probes.extend(
        (url, 403, "code", "telegram_webhook_forbidden") for url in webhook_urls(settings).values()
    )
    failures = ["Public webhook probe did not complete"]
    logger = get_logger(component="telegram_webhook_probe")
    try:
        async with (
            asyncio.timeout(45),
            httpx.AsyncClient(
                timeout=5,
                follow_redirects=False,
                transport=transport,
            ) as client,
        ):
            for attempt in range(attempts):
                failures = []
                for url, status, field, expected in probes:
                    try:
                        if status == 200:
                            response = await client.get(url)
                        else:
                            # No secret: the API must reject BEFORE update deduplication/dispatch.
                            response = await client.post(url, json={"update_id": 0})
                        if response.status_code != status:
                            failures.append(
                                f"{url}: HTTP {response.status_code}, expected {status}"
                            )
                            continue
                        body = response.json()
                        if not isinstance(body, dict) or body.get(field) != expected:
                            failures.append(f"{url}: unexpected response (wrong upstream?)")
                    except (httpx.HTTPError, ValueError) as exc:
                        failures.append(f"{url}: {type(exc).__name__}")
                if not failures:
                    logger.info("public_webhooks_ready")
                    return
                logger.warning("public_webhooks_not_ready", attempt=attempt + 1, failures=failures)
                if attempt + 1 < attempts:
                    await asyncio.sleep(retry_seconds)
    except TimeoutError:
        failures.append("Public webhook probe exceeded 45 seconds")
    raise RuntimeError("Public API/Caddy route is not ready: " + "; ".join(failures))
