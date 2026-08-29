from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TelegramUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    is_bot: bool = False
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


class TelegramChat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    type: str


class TelegramSuccessfulPayment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    currency: str
    total_amount: int = Field(ge=0)
    invoice_payload: str
    telegram_payment_charge_id: str
    provider_payment_charge_id: str


class TelegramMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: int
    from_user: TelegramUser | None = Field(default=None, alias="from")
    chat: TelegramChat
    text: str | None = None
    successful_payment: TelegramSuccessfulPayment | None = None


class TelegramCallbackQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    from_user: TelegramUser = Field(alias="from")
    message: TelegramMessage | None = None
    data: str | None = None


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: TelegramMessage | None = None
    callback_query: TelegramCallbackQuery | None = None

    @property
    def actor_id(self) -> int | None:
        if self.callback_query is not None:
            return self.callback_query.from_user.id
        if self.message is not None and self.message.from_user is not None:
            return self.message.from_user.id
        return None
