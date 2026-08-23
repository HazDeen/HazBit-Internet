from __future__ import annotations

from email.message import EmailMessage
from typing import Any

import pytest
from app.core.config import EmailSettings
from app.modules.auth.email import SmtpEmailSender


@pytest.mark.asyncio
async def test_smtp_sender_builds_branded_multipart_otp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_send(message: EmailMessage, **kwargs: Any) -> None:
        captured["message"] = message
        captured["kwargs"] = kwargs

    monkeypatch.setattr("app.modules.auth.email.aiosmtplib.send", fake_send)
    sender = SmtpEmailSender(
        EmailSettings(
            backend="smtp",
            from_address="no-reply@hazbit.example.com",
            from_name="Hazbit",
            smtp_host="smtp.hazbit.example.com",
            smtp_port=587,
            smtp_username="smtp-user",
            smtp_password="smtp-secret",
        )
    )

    await sender.send_otp(email="person@example.com", code="123456", expires_minutes=10)

    message = captured["message"]
    assert isinstance(message, EmailMessage)
    assert message["From"] == "Hazbit <no-reply@hazbit.example.com>"
    assert message["To"] == "person@example.com"
    assert message.is_multipart()
    assert "123456" in message.get_body(preferencelist=("plain",)).get_content()
    assert "HAZBIT ACCESS" in message.get_body(preferencelist=("html",)).get_content()
    assert captured["kwargs"]["start_tls"] is True
    assert captured["kwargs"]["use_tls"] is False
    assert captured["kwargs"]["password"] == "smtp-secret"


def test_smtp_tls_modes_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="cannot both be enabled"):
        EmailSettings(smtp_start_tls=True, smtp_use_tls=True)


def test_smtp_credentials_must_be_configured_together() -> None:
    with pytest.raises(ValueError, match="configured together"):
        EmailSettings(smtp_username="smtp-user")
