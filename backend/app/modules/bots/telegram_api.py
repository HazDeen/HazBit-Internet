from __future__ import annotations

from typing import Any

import httpx


class TelegramApiError(RuntimeError):
    pass


class TelegramBotClient:
    def __init__(
        self,
        token: str,
        *,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{token}/",
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    @property
    def configured(self) -> bool:
        return bool(self._token)

    async def close(self) -> None:
        await self._client.aclose()

    async def call(self, method: str, payload: dict[str, Any]) -> Any:
        if not self.configured:
            raise TelegramApiError("Telegram bot token is not configured")
        try:
            response = await self._client.post(method, json=payload)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            # Raw httpx exception chains contain credentials in the request URL.
            raise TelegramApiError(
                f"Telegram API {method}: HTTP {exc.response.status_code}"
            ) from None
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramApiError(f"Telegram API {method}: {type(exc).__name__}") from None
        if not isinstance(body, dict):
            raise TelegramApiError(f"Telegram API {method}: invalid response")
        if not body.get("ok"):
            description = str(body.get("description") or "Telegram API rejected request")
            raise TelegramApiError(description.replace(self._token, "[REDACTED]"))
        return body.get("result")

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = await self.call("sendMessage", payload)
        return result if isinstance(result, dict) else {}

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        await self.call("editMessageText", payload)

    async def answer_callback(self, callback_id: str, text: str = "") -> None:
        await self.call(
            "answerCallbackQuery",
            {"callback_query_id": callback_id, "text": text, "show_alert": False},
        )

    async def get_chat_member(self, chat_id: str, user_id: int) -> str:
        result = await self.call("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        return str(result.get("status", "left")) if isinstance(result, dict) else "left"
