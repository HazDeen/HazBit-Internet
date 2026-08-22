from __future__ import annotations

from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.core.config import EmailSettings
from app.core.logging import get_logger


class EmailDeliveryError(RuntimeError):
    pass


class EmailSender(Protocol):
    async def send_otp(self, *, email: str, code: str, expires_minutes: int) -> None: ...


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


class SmtpEmailSender:
    def __init__(self, settings: EmailSettings) -> None:
        if settings.smtp_host is None:
            raise ValueError("smtp_host is required for SMTP email backend")
        self._settings = settings

    async def send_otp(self, *, email: str, code: str, expires_minutes: int) -> None:
        message = EmailMessage()
        message["From"] = self._settings.from_address
        message["To"] = email
        message["Subject"] = "Your Hazbit VPN verification code"
        message.set_content(
            f"Your verification code is {code}. "
            f"It expires in {expires_minutes} minutes.\n\n"
            "If you did not request this code, ignore this message."
        )
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
                timeout=10,
            )
        except (aiosmtplib.SMTPException, OSError, TimeoutError) as exc:
            raise EmailDeliveryError("OTP email delivery failed") from exc


def create_email_sender(settings: EmailSettings) -> EmailSender:
    if settings.backend == "smtp":
        return SmtpEmailSender(settings)
    return ConsoleEmailSender()
