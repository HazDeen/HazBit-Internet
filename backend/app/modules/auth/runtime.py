from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.integrations.redis import RedisManager
from app.modules.auth.crypto import AccessTokenCodec, OpaqueTokenCodec, OtpCodec, SignalHasher
from app.modules.auth.email import EmailSender, create_email_sender
from app.modules.auth.rate_limit import RateLimiter
from app.modules.auth.telegram import TelegramInitDataValidator


@dataclass(frozen=True, slots=True)
class AuthRuntime:
    otp_codec: OtpCodec
    opaque_token_codec: OpaqueTokenCodec
    access_token_codec: AccessTokenCodec
    signal_hasher: SignalHasher
    telegram_validator: TelegramInitDataValidator
    rate_limiter: RateLimiter
    email_sender: EmailSender


def create_auth_runtime(settings: Settings, redis: RedisManager) -> AuthRuntime:
    return AuthRuntime(
        otp_codec=OtpCodec(settings.auth),
        opaque_token_codec=OpaqueTokenCodec(settings.auth),
        access_token_codec=AccessTokenCodec(settings.auth),
        signal_hasher=SignalHasher(settings.auth),
        telegram_validator=TelegramInitDataValidator(settings.auth.telegram),
        rate_limiter=RateLimiter(redis.client, key_prefix=settings.redis.key_prefix),
        email_sender=create_email_sender(settings.auth.email),
    )
