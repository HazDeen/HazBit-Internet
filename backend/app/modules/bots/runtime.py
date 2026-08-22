from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.modules.bots.callbacks import CallbackCodec
from app.modules.bots.telegram_api import TelegramBotClient


@dataclass(frozen=True, slots=True)
class TelegramBotsRuntime:
    customer: TelegramBotClient
    operations: TelegramBotClient
    callbacks: CallbackCodec

    async def close(self) -> None:
        await self.customer.close()
        await self.operations.close()


def create_telegram_bots_runtime(settings: Settings) -> TelegramBotsRuntime:
    return TelegramBotsRuntime(
        customer=TelegramBotClient(settings.auth.telegram.bot_token.get_secret_value()),
        operations=TelegramBotClient(
            settings.telegram_bots.operations_bot_token.get_secret_value()
        ),
        callbacks=CallbackCodec(
            settings.telegram_bots.callback_secret.get_secret_value(),
            default_ttl_seconds=settings.telegram_bots.callback_ttl_seconds,
        ),
    )
