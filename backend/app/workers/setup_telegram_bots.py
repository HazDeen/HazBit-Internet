from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.modules.bots.runtime import create_telegram_bots_runtime


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(component="telegram_bot_setup")
    runtime = create_telegram_bots_runtime(settings)
    base = str(settings.telegram_bots.webhook_base_url).rstrip("/")
    try:
        await runtime.customer.call(
            "setWebhook",
            {
                "url": f"{base}{settings.api_v1_prefix}/bots/customer/webhook",
                "secret_token": settings.telegram_bots.customer_webhook_secret.get_secret_value(),
                "allowed_updates": ["message", "callback_query"],
                "drop_pending_updates": False,
            },
        )
        await runtime.customer.call(
            "setMyCommands",
            {
                "commands": [
                    {"command": "status", "description": "Статус подписки и VPN"},
                    {"command": "vpn", "description": "VPN и устройства"},
                    {"command": "pay", "description": "Тарифы и оплата"},
                    {"command": "support", "description": "Поддержка"},
                    {"command": "help", "description": "Главное меню"},
                ]
            },
        )
        await runtime.customer.call(
            "setChatMenuButton",
            {
                "menu_button": {
                    "type": "web_app",
                    "text": "Hazbit",
                    "web_app": {"url": str(settings.telegram_bots.mini_app_url)},
                }
            },
        )
        await runtime.operations.call(
            "setWebhook",
            {
                "url": f"{base}{settings.api_v1_prefix}/bots/operations/webhook",
                "secret_token": settings.telegram_bots.operations_webhook_secret.get_secret_value(),
                "allowed_updates": ["message", "callback_query"],
                "drop_pending_updates": False,
            },
        )
        await runtime.operations.call(
            "setMyCommands",
            {
                "commands": [
                    {"command": "queue", "description": "Операционная очередь"},
                    {"command": "help", "description": "Справка"},
                ]
            },
        )
        customer_identity = await runtime.customer.call("getMe", {})
        customer_webhook = await runtime.customer.call("getWebhookInfo", {})
        operations_identity = await runtime.operations.call("getMe", {})
        operations_webhook = await runtime.operations.call("getWebhookInfo", {})
        logger.info(
            "telegram_bots_configured",
            webhook_base_url=base,
            customer_bot=customer_identity.get("username"),
            customer_webhook=customer_webhook.get("url"),
            customer_webhook_error=customer_webhook.get("last_error_message"),
            operations_bot=operations_identity.get("username"),
            operations_webhook=operations_webhook.get("url"),
            operations_webhook_error=operations_webhook.get("last_error_message"),
        )
    finally:
        await runtime.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
