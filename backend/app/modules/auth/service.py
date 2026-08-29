from __future__ import annotations

import asyncio
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AuthSettings
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.modules.auth.crypto import (
    AccessTokenCodec,
    OpaqueTokenCodec,
    OtpCodec,
    PasswordCodec,
    SignalHasher,
)
from app.modules.auth.email import EmailDeliveryError, EmailSender
from app.modules.auth.enums import OtpPurpose, Permission, Role, UserStatus
from app.modules.auth.google import GoogleIdTokenValidator, GoogleTokenValidationError
from app.modules.auth.models import (
    AuthSession,
    GoogleAccount,
    OtpChallenge,
    RegistrationChallenge,
    TelegramLoginChallenge,
    User,
)
from app.modules.auth.rate_limit import RateLimit, RateLimiter
from app.modules.auth.repository import AuthRepository
from app.modules.auth.risk import AntiAbuseService, RiskAssessment
from app.modules.auth.schemas import AuthenticatedUser
from app.modules.auth.telegram import (
    TelegramInitDataValidator,
    TelegramUserData,
    TelegramValidationError,
    TelegramWidgetValidator,
)

EMAIL_START_IP = RateLimit("email_start_ip", 5, 600)
EMAIL_START_IDENTITY = RateLimit("email_start_identity", 3, 600)
EMAIL_VERIFY_IP = RateLimit("email_verify_ip", 10, 600)
EMAIL_VERIFY_IDENTITY = RateLimit("email_verify_identity", 8, 600)
TELEGRAM_IP = RateLimit("telegram_ip", 20, 300)
TELEGRAM_IDENTITY = RateLimit("telegram_identity", 10, 300)
PASSWORD_IP = RateLimit("password_ip", 12, 600)
PASSWORD_IDENTITY = RateLimit("password_identity", 8, 600)
REGISTRATION_IP = RateLimit("registration_ip", 5, 3600)
REGISTRATION_IDENTITY = RateLimit("registration_identity", 3, 3600)
REFRESH_IP = RateLimit("refresh_ip", 30, 300)
REFRESH_TOKEN = RateLimit("refresh_token", 10, 300)


@dataclass(frozen=True, slots=True)
class ClientContext:
    ip_address: str
    user_agent: str | None
    device_fingerprint: str | None
    request_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AuthResult:
    access_token: str
    access_expires_in: int
    refresh_token: str
    csrf_token: str
    refresh_expires_at: datetime
    user: AuthenticatedUser
    risk: RiskAssessment | None


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    session_id: UUID
    roles: frozenset[Role]
    permissions: frozenset[Permission] = frozenset()


@dataclass(frozen=True, slots=True)
class RegistrationStart:
    token: str
    telegram_confirmation_url: str | None


@dataclass(frozen=True, slots=True)
class TelegramChallengeStart:
    token: str
    confirmation_url: str
    expires_in: int


class AuthService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: AuthSettings,
        otp_codec: OtpCodec,
        opaque_token_codec: OpaqueTokenCodec,
        access_token_codec: AccessTokenCodec,
        signal_hasher: SignalHasher,
        telegram_validator: TelegramInitDataValidator,
        telegram_widget_validator: TelegramWidgetValidator,
        google_validator: GoogleIdTokenValidator,
        password_codec: PasswordCodec,
        rate_limiter: RateLimiter,
        email_sender: EmailSender,
    ) -> None:
        self._session = session
        self._settings = settings
        self._repository = AuthRepository(session)
        self._otp = otp_codec
        self._opaque_tokens = opaque_token_codec
        self._access_tokens = access_token_codec
        self._signals = signal_hasher
        self._telegram = telegram_validator
        self._telegram_widget = telegram_widget_validator
        self._google = google_validator
        self._passwords = password_codec
        self._rate_limiter = rate_limiter
        self._email_sender = email_sender

    async def start_registration(
        self,
        *,
        public_name: str,
        email: str,
        password: str,
        telegram_user_id: int | None,
        client: ClientContext,
    ) -> RegistrationStart:
        normalized_email = email.strip().casefold()
        confirmation_url: str | None = None
        await self._rate_limiter.enforce(
            REGISTRATION_IP, self._signals.digest("ip", client.ip_address).hex()
        )
        await self._rate_limiter.enforce(
            REGISTRATION_IDENTITY, self._signals.digest("email", normalized_email).hex()
        )
        now = datetime.now(UTC)
        raw_token = secrets.token_urlsafe(24)
        if telegram_user_id is not None:
            confirmation_url = self._telegram_confirmation_url("reg", raw_token)
        challenge_id = uuid7()
        code = self._otp.generate()
        registration = RegistrationChallenge(
            id=uuid7(),
            token_hash=self._opaque_tokens.digest(raw_token),
            email=normalized_email,
            public_name=public_name.strip(),
            password_hash=await asyncio.to_thread(self._passwords.hash, password),
            telegram_user_id=telegram_user_id,
            requested_ip=client.ip_address,
            device_fingerprint_hash=self._fingerprint(client.device_fingerprint),
            expires_at=now + timedelta(minutes=30),
        )
        otp = OtpChallenge(
            id=challenge_id,
            email=normalized_email,
            purpose=OtpPurpose.REGISTER.value,
            code_hash=self._otp.digest(challenge_id, code),
            attempts=0,
            max_attempts=self._settings.otp.max_attempts,
            requested_ip=client.ip_address,
            device_fingerprint_hash=self._fingerprint(client.device_fingerprint),
            expires_at=now + timedelta(minutes=self._settings.otp.ttl_minutes),
        )
        async with self._session.begin():
            identity = await self._repository.get_user_by_email(normalized_email)
            if identity is not None:
                credential = await self._repository.get_password_credential(identity[0].id)
                if credential is not None:
                    raise ApplicationError(
                        "account_already_exists",
                        "An account with this email already exists. Sign in instead.",
                        409,
                    )
            await self._repository.invalidate_registration_challenges(
                email=normalized_email, consumed_at=now
            )
            await self._repository.invalidate_otp_challenges(
                email=normalized_email,
                purpose=OtpPurpose.REGISTER.value,
                consumed_at=now,
            )
            self._repository.add_registration_challenge(registration)
            self._repository.add_otp_challenge(otp)
        try:
            await self._email_sender.send_otp(
                email=normalized_email,
                code=code,
                expires_minutes=self._settings.otp.ttl_minutes,
            )
        except EmailDeliveryError as exc:
            async with self._session.begin():
                registration.consumed_at = datetime.now(UTC)
                otp.consumed_at = registration.consumed_at
            raise ApplicationError(
                "otp_delivery_unavailable",
                "Verification email could not be delivered. Try again later.",
                503,
            ) from exc
        return RegistrationStart(
            token=raw_token,
            telegram_confirmation_url=confirmation_url,
        )

    async def verify_registration(
        self,
        *,
        registration_token: str,
        code: str,
        client: ClientContext,
    ) -> AuthResult | str:
        digest = self._opaque_tokens.digest(registration_token)
        await self._rate_limiter.enforce(
            EMAIL_VERIFY_IP, self._signals.digest("ip", client.ip_address).hex()
        )
        await self._rate_limiter.enforce(EMAIL_VERIFY_IDENTITY, digest.hex())
        now = datetime.now(UTC)
        result: AuthResult | None = None
        pending_url: str | None = None
        error: ApplicationError | None = None
        async with self._session.begin():
            registration = await self._repository.get_registration_for_update(digest)
            self._ensure_registration_active(registration, now, client)
            assert registration is not None
            otp = await self._repository.get_latest_otp_for_update(
                email=registration.email,
                purpose=OtpPurpose.REGISTER.value,
            )
            if otp is None or otp.expires_at <= now or otp.attempts >= otp.max_attempts:
                if otp is not None:
                    otp.consumed_at = now
                error = self._invalid_otp_error()
            elif not self._otp.verify(otp.id, code, otp.code_hash):
                otp.attempts += 1
                if otp.attempts >= otp.max_attempts:
                    otp.consumed_at = now
                error = self._invalid_otp_error()
            else:
                otp.consumed_at = now
                registration.email_verified_at = now
                if (
                    registration.telegram_user_id is not None
                    and registration.telegram_verified_at is None
                ):
                    pending_url = self._telegram_confirmation_url("reg", registration_token)
                else:
                    result = await self._finalize_registration(registration, client=client, now=now)
        if error is not None:
            raise error
        if pending_url is not None:
            return pending_url
        if result is not None:
            return result
        raise self._registration_invalid()

    async def complete_registration(
        self, *, registration_token: str, client: ClientContext
    ) -> AuthResult | str:
        digest = self._opaque_tokens.digest(registration_token)
        now = datetime.now(UTC)
        result: AuthResult | None = None
        pending_url: str | None = None
        async with self._session.begin():
            registration = await self._repository.get_registration_for_update(digest)
            self._ensure_registration_active(registration, now, client)
            assert registration is not None
            if registration.email_verified_at is None:
                raise self._registration_invalid()
            if (
                registration.telegram_user_id is not None
                and registration.telegram_verified_at is None
            ):
                pending_url = self._telegram_confirmation_url("reg", registration_token)
            else:
                result = await self._finalize_registration(registration, client=client, now=now)
        if pending_url is not None:
            return pending_url
        if result is not None:
            return result
        raise self._registration_invalid()

    async def authenticate_password(
        self, *, email: str, password: str, client: ClientContext
    ) -> AuthResult:
        normalized_email = email.strip().casefold()
        await self._rate_limiter.enforce(
            PASSWORD_IP, self._signals.digest("ip", client.ip_address).hex()
        )
        await self._rate_limiter.enforce(
            PASSWORD_IDENTITY, self._signals.digest("email", normalized_email).hex()
        )
        now = datetime.now(UTC)
        async with self._session.begin():
            identity = await self._repository.get_user_by_email(normalized_email)
            credential = (
                await self._repository.get_password_credential(identity[0].id)
                if identity is not None
                else None
            )
            if (
                identity is None
                or credential is None
                or not await asyncio.to_thread(
                    self._passwords.verify, credential.password_hash, password
                )
            ):
                raise ApplicationError(
                    "invalid_credentials", "The email or password is incorrect.", 401
                )
            user = identity[0]
            result = await self._issue_login(user, client=client, method="password", now=now)
        return result

    async def authenticate_google(self, *, credential: str, client: ClientContext) -> AuthResult:
        try:
            google = await self._google.validate(credential)
        except GoogleTokenValidationError as exc:
            raise ApplicationError(
                "invalid_google_credential", "Google authentication failed.", 401
            ) from exc
        now = datetime.now(UTC)
        async with self._session.begin():
            account = await self._repository.get_google_account(google.subject)
            if account is not None:
                user = await self._repository.get_user(account.user_id)
            else:
                identity = await self._repository.get_user_by_email(google.email)
                if identity is None:
                    user = await self._repository.create_user_with_email(
                        email=google.email, verified_at=now
                    )
                    user.public_name = google.name
                else:
                    user, user_email = identity
                    user_email.verified_at = user_email.verified_at or now
                    user.public_name = user.public_name or google.name
                self._repository.add_google_account(
                    GoogleAccount(
                        user_id=user.id,
                        google_subject=google.subject,
                        email=google.email,
                    )
                )
            result = await self._issue_login(user, client=client, method="google", now=now)
        return result

    async def authenticate_telegram_widget(
        self, *, fields: dict[str, str | int | None], client: ClientContext
    ) -> AuthResult:
        try:
            telegram = self._telegram_widget.validate(fields)
        except TelegramValidationError as exc:
            raise ApplicationError(
                "invalid_telegram_widget_data", "Telegram authentication failed.", 401
            ) from exc
        return await self._authenticate_telegram_user(
            telegram.user, client=client, method="telegram_widget"
        )

    async def start_telegram_id_login(
        self, *, telegram_user_id: int, client: ClientContext
    ) -> TelegramChallengeStart:
        await self._rate_limiter.enforce(
            TELEGRAM_IP, self._signals.digest("ip", client.ip_address).hex()
        )
        raw_token = secrets.token_urlsafe(24)
        ttl_seconds = 600
        now = datetime.now(UTC)
        challenge = TelegramLoginChallenge(
            id=uuid7(),
            token_hash=self._opaque_tokens.digest(raw_token),
            telegram_user_id=telegram_user_id,
            requested_ip=client.ip_address,
            device_fingerprint_hash=self._fingerprint(client.device_fingerprint),
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        async with self._session.begin():
            self._repository.add_telegram_login_challenge(challenge)
        return TelegramChallengeStart(
            token=raw_token,
            confirmation_url=self._telegram_confirmation_url("login", raw_token),
            expires_in=ttl_seconds,
        )

    async def verify_telegram_id_login(
        self, *, challenge_token: str, client: ClientContext
    ) -> AuthResult | None:
        now = datetime.now(UTC)
        async with self._session.begin():
            challenge = await self._repository.get_telegram_login_for_update(
                self._opaque_tokens.digest(challenge_token)
            )
            if (
                challenge is None
                or challenge.consumed_at is not None
                or challenge.expires_at <= now
            ):
                raise ApplicationError(
                    "telegram_challenge_invalid", "Telegram confirmation expired.", 400
                )
            self._ensure_fingerprint(challenge.device_fingerprint_hash, client)
            if challenge.approved_at is None:
                return None
            account = await self._repository.get_telegram_account(challenge.telegram_user_id)
            if account is None:
                raise ApplicationError(
                    "telegram_account_not_linked",
                    "This Telegram account is not linked to Hazbit yet.",
                    404,
                )
            challenge.consumed_at = now
            user = await self._repository.get_user(account.user_id)
            result = await self._issue_login(
                user, client=client, method="telegram_id_confirmation", now=now
            )
        return result

    async def start_email_auth(self, *, email: str, client: ClientContext) -> None:
        normalized_email = email.strip().casefold()
        await self._rate_limiter.enforce(
            EMAIL_START_IP, self._signals.digest("ip", client.ip_address).hex()
        )
        await self._rate_limiter.enforce(
            EMAIL_START_IDENTITY,
            self._signals.digest("email", normalized_email).hex(),
        )

        now = datetime.now(UTC)
        challenge_id = uuid7()
        code = self._otp.generate()
        challenge = OtpChallenge(
            id=challenge_id,
            email=normalized_email,
            purpose=OtpPurpose.LOGIN.value,
            code_hash=self._otp.digest(challenge_id, code),
            attempts=0,
            max_attempts=self._settings.otp.max_attempts,
            requested_ip=client.ip_address,
            device_fingerprint_hash=self._fingerprint(client.device_fingerprint),
            expires_at=now + timedelta(minutes=self._settings.otp.ttl_minutes),
        )
        async with self._session.begin():
            await self._repository.invalidate_otp_challenges(
                email=normalized_email,
                purpose=OtpPurpose.LOGIN.value,
                consumed_at=now,
            )
            self._repository.add_otp_challenge(challenge)

        try:
            await self._email_sender.send_otp(
                email=normalized_email,
                code=code,
                expires_minutes=self._settings.otp.ttl_minutes,
            )
        except EmailDeliveryError as exc:
            async with self._session.begin():
                challenge.consumed_at = datetime.now(UTC)
            raise ApplicationError(
                code="otp_delivery_unavailable",
                detail="Verification email could not be delivered. Try again later.",
                status_code=503,
            ) from exc

    async def verify_email(
        self,
        *,
        email: str,
        code: str,
        client: ClientContext,
    ) -> AuthResult:
        normalized_email = email.strip().casefold()
        await self._rate_limiter.enforce(
            EMAIL_VERIFY_IP, self._signals.digest("ip", client.ip_address).hex()
        )
        await self._rate_limiter.enforce(
            EMAIL_VERIFY_IDENTITY,
            self._signals.digest("email", normalized_email).hex(),
        )

        now = datetime.now(UTC)
        error: ApplicationError | None = None
        issued: tuple[User, set[Role], AuthSession, str, str, RiskAssessment] | None = None

        async with self._session.begin():
            challenge = await self._repository.get_latest_otp_for_update(
                email=normalized_email,
                purpose=OtpPurpose.LOGIN.value,
            )
            if challenge is None or challenge.expires_at <= now:
                if challenge is not None:
                    challenge.consumed_at = now
                error = self._invalid_otp_error()
            elif challenge.attempts >= challenge.max_attempts:
                challenge.consumed_at = now
                error = self._invalid_otp_error()
            elif not self._otp.verify(challenge.id, code, challenge.code_hash):
                challenge.attempts += 1
                if challenge.attempts >= challenge.max_attempts:
                    challenge.consumed_at = now
                error = self._invalid_otp_error()
            else:
                challenge.consumed_at = now
                identity = await self._repository.get_user_by_email(normalized_email)
                if identity is None:
                    user = await self._repository.create_user_with_email(
                        email=normalized_email,
                        verified_at=now,
                    )
                else:
                    user, user_email = identity
                    if user_email.verified_at is None:
                        user_email.verified_at = now
                self._ensure_active(user)
                roles = await self._repository.get_roles(user.id)
                risk = await AntiAbuseService(self._repository, self._signals).assess_and_record(
                    user_id=user.id,
                    ip_address=client.ip_address,
                    device_fingerprint=client.device_fingerprint,
                    method="email_otp",
                    now=now,
                )
                auth_session, refresh_token, csrf_token = self._new_session(
                    user_id=user.id,
                    client=client,
                    now=now,
                )
                self._repository.add_auth_audit(
                    user_id=user.id,
                    action="auth.email_otp.succeeded",
                    session_id=auth_session.id,
                    ip_address=client.ip_address,
                    user_agent=client.user_agent,
                    request_id=client.request_id,
                    after_state={"risk_decision": risk.decision.value},
                )
                issued = (user, roles, auth_session, refresh_token, csrf_token, risk)

        if error is not None:
            raise error
        if issued is None:
            raise RuntimeError("email authentication produced no result")
        user, roles, auth_session, refresh_token, csrf_token, risk = issued
        return await self._result(
            user=user,
            roles=roles,
            auth_session=auth_session,
            refresh_token=refresh_token,
            csrf_token=csrf_token,
            risk=risk,
        )

    async def authenticate_telegram(
        self,
        *,
        init_data: str,
        client: ClientContext,
    ) -> AuthResult:
        await self._rate_limiter.enforce(
            TELEGRAM_IP, self._signals.digest("ip", client.ip_address).hex()
        )
        try:
            telegram = self._telegram.validate(init_data)
        except TelegramValidationError as exc:
            raise ApplicationError(
                code="invalid_telegram_init_data",
                detail="Telegram authentication data is invalid or expired.",
                status_code=401,
                headers={"WWW-Authenticate": "TelegramInitData"},
            ) from exc
        await self._rate_limiter.enforce(
            TELEGRAM_IDENTITY,
            self._signals.digest("telegram", str(telegram.user.id)).hex(),
        )

        now = datetime.now(UTC)
        async with self._session.begin():
            await self._repository.serialize_telegram_login(telegram.user.id)
            account = await self._repository.get_telegram_account(telegram.user.id)
            if account is None:
                user, _ = await self._repository.create_user_with_telegram(
                    telegram_user_id=telegram.user.id,
                    username=telegram.user.username,
                    first_name=telegram.user.first_name,
                    last_name=telegram.user.last_name,
                    language_code=telegram.user.language_code,
                )
            else:
                user = await self._repository.update_telegram_account(
                    account,
                    username=telegram.user.username,
                    first_name=telegram.user.first_name,
                    last_name=telegram.user.last_name,
                    language_code=telegram.user.language_code,
                    updated_at=now,
                )
            self._ensure_active(user)
            roles = await self._repository.get_roles(user.id)
            risk = await AntiAbuseService(self._repository, self._signals).assess_and_record(
                user_id=user.id,
                ip_address=client.ip_address,
                device_fingerprint=client.device_fingerprint,
                method="telegram_mini_app",
                now=now,
            )
            auth_session, refresh_token, csrf_token = self._new_session(
                user_id=user.id,
                client=client,
                now=now,
            )
            self._repository.add_auth_audit(
                user_id=user.id,
                action="auth.telegram.succeeded",
                session_id=auth_session.id,
                ip_address=client.ip_address,
                user_agent=client.user_agent,
                request_id=client.request_id,
                after_state={"risk_decision": risk.decision.value},
            )

        return await self._result(
            user=user,
            roles=roles,
            auth_session=auth_session,
            refresh_token=refresh_token,
            csrf_token=csrf_token,
            risk=risk,
        )

    async def refresh(self, *, refresh_token: str, client: ClientContext) -> AuthResult:
        digest = self._opaque_tokens.digest(refresh_token)
        await self._rate_limiter.enforce(
            REFRESH_IP, self._signals.digest("ip", client.ip_address).hex()
        )
        await self._rate_limiter.enforce(REFRESH_TOKEN, digest.hex())

        now = datetime.now(UTC)
        error: ApplicationError | None = None
        issued: tuple[User, set[Role], AuthSession, str, str] | None = None
        async with self._session.begin():
            old_session = await self._repository.get_session_by_digest_for_update(digest)
            if old_session is None:
                error = self._invalid_refresh_error()
            elif old_session.revoked_at is not None:
                if old_session.replaced_by_session_id is not None:
                    await self._repository.revoke_token_family(
                        old_session.token_family_id,
                        revoked_at=now,
                        reason="refresh_token_reuse",
                    )
                    self._repository.add_auth_audit(
                        user_id=old_session.user_id,
                        action="auth.refresh.reuse_detected",
                        session_id=old_session.id,
                        ip_address=client.ip_address,
                        user_agent=client.user_agent,
                        request_id=client.request_id,
                        after_state={"token_family_revoked": True},
                    )
                    error = ApplicationError(
                        code="refresh_token_reuse",
                        detail="The session was revoked because token reuse was detected.",
                        status_code=401,
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                else:
                    error = self._invalid_refresh_error()
            elif old_session.expires_at <= now:
                old_session.revoked_at = now
                old_session.revoke_reason = "expired"
                error = self._invalid_refresh_error()
            else:
                user = await self._repository.get_user(old_session.user_id)
                self._ensure_active(user)
                roles = await self._repository.get_roles(user.id)
                new_session, new_refresh_token, csrf_token = self._new_session(
                    user_id=user.id,
                    client=client,
                    now=now,
                    token_family_id=old_session.token_family_id,
                )
                # The self-referencing FK is immediate. Persist the successor before
                # linking the predecessor to it so flush ordering is deterministic.
                await self._session.flush()
                old_session.revoked_at = now
                old_session.revoke_reason = "rotated"
                old_session.replaced_by_session_id = new_session.id
                old_session.last_used_at = now
                self._repository.add_auth_audit(
                    user_id=user.id,
                    action="auth.refresh.rotated",
                    session_id=new_session.id,
                    ip_address=client.ip_address,
                    user_agent=client.user_agent,
                    request_id=client.request_id,
                    after_state={"predecessor_session_id": str(old_session.id)},
                )
                issued = (user, roles, new_session, new_refresh_token, csrf_token)

        if error is not None:
            raise error
        if issued is None:
            raise RuntimeError("refresh produced no result")
        user, roles, auth_session, new_refresh_token, csrf_token = issued
        return await self._result(
            user=user,
            roles=roles,
            auth_session=auth_session,
            refresh_token=new_refresh_token,
            csrf_token=csrf_token,
            risk=None,
        )

    async def _finalize_registration(
        self,
        registration: RegistrationChallenge,
        *,
        client: ClientContext,
        now: datetime,
    ) -> AuthResult:
        email_identity = await self._repository.get_user_by_email(registration.email)
        telegram_account = (
            await self._repository.get_telegram_account(registration.telegram_user_id)
            if registration.telegram_user_id is not None
            else None
        )
        if (
            email_identity is not None
            and telegram_account is not None
            and email_identity[0].id != telegram_account.user_id
        ):
            raise ApplicationError(
                "identity_conflict",
                "Email and Telegram belong to different accounts. Contact support to merge them.",
                409,
            )
        user = (
            email_identity[0]
            if email_identity is not None
            else await self._repository.get_user(telegram_account.user_id)
            if telegram_account is not None
            else None
        )
        if user is None:
            user = await self._repository.create_registered_user(
                email=registration.email,
                public_name=registration.public_name,
                password_hash=registration.password_hash,
                verified_at=registration.email_verified_at or now,
            )
        else:
            existing_credential = await self._repository.get_password_credential(user.id)
            if existing_credential is not None:
                raise ApplicationError(
                    "account_already_exists",
                    "This account already has a password. Sign in instead.",
                    409,
                )
            if email_identity is None:
                await self._repository.attach_registered_identity(
                    user=user,
                    email=registration.email,
                    public_name=registration.public_name,
                    password_hash=registration.password_hash,
                    verified_at=registration.email_verified_at or now,
                )
            else:
                await self._repository.attach_password_credential(
                    user=user,
                    public_name=registration.public_name,
                    password_hash=registration.password_hash,
                )
                email_identity[1].verified_at = email_identity[1].verified_at or now
        if registration.telegram_user_id is not None and telegram_account is None:
            await self._repository.attach_telegram_account(
                user_id=user.id,
                telegram_user_id=registration.telegram_user_id,
                username=registration.telegram_username,
                first_name=registration.telegram_first_name or registration.public_name,
                last_name=registration.telegram_last_name,
                language_code=registration.telegram_language_code,
            )
        registration.consumed_at = now
        return await self._issue_login(user, client=client, method="registration", now=now)

    async def _authenticate_telegram_user(
        self,
        telegram: TelegramUserData,
        *,
        client: ClientContext,
        method: str,
    ) -> AuthResult:
        await self._rate_limiter.enforce(
            TELEGRAM_IDENTITY,
            self._signals.digest("telegram", str(telegram.id)).hex(),
        )
        now = datetime.now(UTC)
        async with self._session.begin():
            await self._repository.serialize_telegram_login(telegram.id)
            account = await self._repository.get_telegram_account(telegram.id)
            if account is None:
                user, _ = await self._repository.create_user_with_telegram(
                    telegram_user_id=telegram.id,
                    username=telegram.username,
                    first_name=telegram.first_name,
                    last_name=telegram.last_name,
                    language_code=telegram.language_code,
                )
            else:
                user = await self._repository.update_telegram_account(
                    account,
                    username=telegram.username,
                    first_name=telegram.first_name,
                    last_name=telegram.last_name,
                    language_code=telegram.language_code,
                    updated_at=now,
                )
            result = await self._issue_login(user, client=client, method=method, now=now)
        return result

    async def _issue_login(
        self, user: User, *, client: ClientContext, method: str, now: datetime
    ) -> AuthResult:
        self._ensure_active(user)
        roles = await self._repository.get_roles(user.id)
        risk = await AntiAbuseService(self._repository, self._signals).assess_and_record(
            user_id=user.id,
            ip_address=client.ip_address,
            device_fingerprint=client.device_fingerprint,
            method=method,
            now=now,
        )
        auth_session, refresh_token, csrf_token = self._new_session(
            user_id=user.id,
            client=client,
            now=now,
        )
        self._repository.add_auth_audit(
            user_id=user.id,
            action=f"auth.{method}.succeeded",
            session_id=auth_session.id,
            ip_address=client.ip_address,
            user_agent=client.user_agent,
            request_id=client.request_id,
            after_state={"risk_decision": risk.decision.value},
        )
        return await self._result(
            user=user,
            roles=roles,
            auth_session=auth_session,
            refresh_token=refresh_token,
            csrf_token=csrf_token,
            risk=risk,
        )

    def _telegram_confirmation_url(self, action: str, token: str) -> str:
        username = self._settings.telegram.bot_username
        if not username:
            raise ApplicationError(
                "telegram_login_unavailable",
                "Telegram confirmation is not configured yet.",
                503,
            )
        return f"https://t.me/{username}?start={action}_{token}"

    def _ensure_registration_active(
        self,
        registration: RegistrationChallenge | None,
        now: datetime,
        client: ClientContext,
    ) -> None:
        if (
            registration is None
            or registration.consumed_at is not None
            or registration.expires_at <= now
        ):
            raise self._registration_invalid()
        self._ensure_fingerprint(registration.device_fingerprint_hash, client)

    def _ensure_fingerprint(self, expected: bytes | None, client: ClientContext) -> None:
        actual = self._fingerprint(client.device_fingerprint)
        if expected is not None and (actual is None or not hmac.compare_digest(expected, actual)):
            raise ApplicationError(
                "authentication_context_changed",
                "Continue authentication in the same browser and device.",
                403,
            )

    @staticmethod
    def _registration_invalid() -> ApplicationError:
        return ApplicationError(
            "registration_challenge_invalid",
            "Registration confirmation is invalid or expired.",
            400,
        )

    async def logout(self, *, refresh_token: str, client: ClientContext) -> None:
        digest = self._opaque_tokens.digest(refresh_token)
        now = datetime.now(UTC)
        async with self._session.begin():
            session = await self._repository.get_session_by_digest_for_update(digest)
            if session is not None and session.revoked_at is None:
                session.revoked_at = now
                session.revoke_reason = "logout"
                self._repository.add_auth_audit(
                    user_id=session.user_id,
                    action="auth.logout",
                    session_id=session.id,
                    ip_address=client.ip_address,
                    user_agent=client.user_agent,
                    request_id=client.request_id,
                    after_state={"revoked": True},
                )

    async def authenticate_access_token(self, token: str) -> Principal:
        try:
            claims = self._access_tokens.decode(token)
        except jwt.PyJWTError as exc:
            raise self._invalid_access_error() from exc
        now = datetime.now(UTC)
        session = await self._repository.get_active_session(claims.session_id, now=now)
        if session is None or session.user_id != claims.user_id:
            raise self._invalid_access_error()
        user = await self._repository.get_user(claims.user_id)
        self._ensure_active(user)
        roles = await self._repository.get_roles(user.id)
        permissions = await self._repository.get_permissions(user.id, roles=roles)
        return Principal(
            user_id=user.id,
            session_id=session.id,
            roles=frozenset(roles),
            permissions=frozenset(permissions),
        )

    async def current_user(self, principal: Principal) -> AuthenticatedUser:
        user = await self._repository.get_user(principal.user_id)
        return await self._user_response(user, set(principal.roles))

    async def _result(
        self,
        *,
        user: User,
        roles: set[Role],
        auth_session: AuthSession,
        refresh_token: str,
        csrf_token: str,
        risk: RiskAssessment | None,
    ) -> AuthResult:
        return AuthResult(
            access_token=self._access_tokens.encode(
                user_id=user.id,
                session_id=auth_session.id,
                roles=roles,
            ),
            access_expires_in=self._access_tokens.expires_in_seconds,
            refresh_token=refresh_token,
            csrf_token=csrf_token,
            refresh_expires_at=auth_session.expires_at,
            user=await self._user_response(user, roles),
            risk=risk,
        )

    async def _user_response(self, user: User, roles: set[Role]) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=user.id,
            display_name=user.public_name,
            email=await self._repository.get_primary_email(user.id),
            telegram_user_id=await self._repository.get_telegram_user_id(user.id),
            roles=list(roles),
            permissions=list(await self._repository.get_permissions(user.id, roles=roles)),
        )

    def _new_session(
        self,
        *,
        user_id: UUID,
        client: ClientContext,
        now: datetime,
        token_family_id: UUID | None = None,
    ) -> tuple[AuthSession, str, str]:
        raw_token = self._opaque_tokens.generate()
        csrf_token = self._opaque_tokens.generate_csrf()
        session = AuthSession(
            id=uuid7(),
            user_id=user_id,
            token_family_id=token_family_id or uuid7(),
            refresh_token_hash=self._opaque_tokens.digest(raw_token),
            user_agent=client.user_agent,
            ip_address=client.ip_address,
            device_fingerprint_hash=self._fingerprint(client.device_fingerprint),
            last_used_at=now,
            expires_at=now + timedelta(days=self._settings.jwt.refresh_ttl_days),
        )
        self._repository.add_session(session)
        return session, raw_token, csrf_token

    def _fingerprint(self, value: str | None) -> bytes | None:
        return self._signals.digest("device", value) if value else None

    @staticmethod
    def verify_csrf(cookie_value: str | None, header_value: str | None) -> None:
        if (
            not cookie_value
            or not header_value
            or not hmac.compare_digest(cookie_value, header_value)
        ):
            raise ApplicationError(
                code="csrf_validation_failed",
                detail="CSRF validation failed.",
                status_code=403,
            )

    @staticmethod
    def _ensure_active(user: User) -> None:
        if user.status == UserStatus.BLOCKED.value:
            raise ApplicationError(
                code="user_blocked",
                detail="This account is blocked.",
                status_code=403,
            )
        if user.status != UserStatus.ACTIVE.value:
            raise ApplicationError(
                code="user_inactive",
                detail="This account is not active.",
                status_code=403,
            )

    @staticmethod
    def _invalid_otp_error() -> ApplicationError:
        return ApplicationError(
            code="invalid_otp",
            detail="The verification code is invalid or expired.",
            status_code=400,
        )

    @staticmethod
    def _invalid_refresh_error() -> ApplicationError:
        return ApplicationError(
            code="invalid_refresh_token",
            detail="The refresh token is invalid or expired.",
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @staticmethod
    def _invalid_access_error() -> ApplicationError:
        return ApplicationError(
            code="invalid_access_token",
            detail="The access token is invalid or expired.",
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
