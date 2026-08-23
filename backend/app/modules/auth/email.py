from __future__ import annotations

from email.headerregistry import Address
from email.message import EmailMessage
from html import escape
from typing import Protocol

import aiosmtplib

from app.core.config import EmailSettings
from app.core.logging import get_logger


class EmailDeliveryError(RuntimeError):
    pass


class EmailSender(Protocol):
    async def send_otp(self, *, email: str, code: str, expires_minutes: int) -> None: ...

    async def send_test(self, *, email: str, reference: str) -> None: ...


class ConsoleEmailSender:
    def __init__(self) -> None:
        self._logger = get_logger(component="email")

    async def send_otp(self, *, email: str, code: str, expires_minutes: int) -> None:
        self._logger.warning(
            "development_otp",
            email=email,
            otp_code=code,
            expires_minutes=expires_minutes,
        )

    async def send_test(self, *, email: str, reference: str) -> None:
        self._logger.warning(
            "development_test_email",
            email=email,
            reference=reference,
        )


class SmtpEmailSender:
    def __init__(self, settings: EmailSettings) -> None:
        if settings.smtp_host is None:
            raise ValueError("smtp_host is required for SMTP email backend")
        self._settings = settings

    async def send_otp(self, *, email: str, code: str, expires_minutes: int) -> None:
        message = self._message(
            email=email,
            subject="Код входа в Hazbit",
            text=(
                f"Ваш код входа: {code}. Он действует {expires_minutes} минут.\n\n"
                "Если вы не запрашивали код, просто проигнорируйте это письмо."
            ),
            html=(
                "<p style=\"margin:0 0 18px;color:#aab3c5;font-size:16px\">"
                "Используйте этот код для входа в Hazbit:</p>"
                f"<div style=\"margin:0 0 18px;font-size:34px;font-weight:800;"
                f"letter-spacing:8px;color:#f7f9ff\">{escape(code)}</div>"
                f"<p style=\"margin:0;color:#7f899c;font-size:14px\">Код действует "
                f"{expires_minutes} минут. Никому его не сообщайте.</p>"  # noqa: RUF001
            ),
        )

        await self._send(message)

    async def send_test(self, *, email: str, reference: str) -> None:
        message = self._message(
            email=email,
            subject="Hazbit — SMTP настроен",
            text=f"Тестовое письмо доставлено. Проверочный номер: {reference}.",
            html=(
                "<p style=\"margin:0 0 16px;color:#aab3c5;font-size:16px\">"
                "SMTP подключён, и Hazbit может отправлять коды входа.</p>"
                f"<p style=\"margin:0;color:#f7f9ff\">Проверочный номер: "
                f"<strong>{escape(reference)}</strong></p>"
            ),
        )
        await self._send(message)

    def _message(self, *, email: str, subject: str, text: str, html: str) -> EmailMessage:
        message = EmailMessage()
        message["From"] = Address(
            display_name=self._settings.from_name,
            addr_spec=str(self._settings.from_address),
        )
        message["To"] = email
        message["Subject"] = subject
        message.set_content(text)
        message.add_alternative(
            "<!doctype html><html><body style=\"margin:0;background:#080b12;"
            "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif\">"
            "<div style=\"max-width:520px;margin:0 auto;padding:40px 20px\">"
            "<div style=\"padding:30px;border:1px solid #273047;border-radius:24px;"
            "background:linear-gradient(145deg,#111827,#0b1020)\">"
            "<div style=\"margin-bottom:24px;color:#8b7cff;font-size:13px;"
            "font-weight:800;letter-spacing:2px\">HAZBIT ACCESS</div>"
            f"{html}"
            "</div></div></body></html>",
            subtype="html",
        )
        return message

    async def _send(self, message: EmailMessage) -> None:
        password = (
            self._settings.smtp_password.get_secret_value()
            if self._settings.smtp_password is not None
            else None
        )
        try:
            await aiosmtplib.send(
                message,
                hostname=self._settings.smtp_host,
                port=self._settings.smtp_port,
                username=self._settings.smtp_username,
                password=password,
                start_tls=self._settings.smtp_start_tls,
                use_tls=self._settings.smtp_use_tls,
                timeout=10,
            )
        except (aiosmtplib.SMTPException, OSError, TimeoutError) as exc:
            raise EmailDeliveryError("Email delivery failed") from exc


def create_email_sender(settings: EmailSettings) -> EmailSender:
    if settings.backend == "smtp":
        return SmtpEmailSender(settings)
    return ConsoleEmailSender()
