from __future__ import annotations

import hmac
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
    SignalHasher,
)
from app.modules.auth.email import EmailDeliveryError, EmailSender
from app.modules.auth.enums import OtpPurpose, Permission, Role, UserStatus
from app.modules.auth.models import AuthSession, OtpChallenge, User
from app.modules.auth.rate_limit import RateLimit, RateLimiter
from app.modules.auth.repository import AuthRepository
from app.modules.auth.risk import AntiAbuseService, RiskAssessment
from app.modules.auth.schemas import AuthenticatedUser
from app.modules.auth.telegram import TelegramInitDataValidator, TelegramValidationError

EMAIL_START_IP = RateLimit("email_start_ip", 5, 600)
EMAIL_START_IDENTITY = RateLimit("email_start_identity", 3, 600)
EMAIL_VERIFY_IP = RateLimit("email_verify_ip", 10, 600)
EMAIL_VERIFY_IDENTITY = RateLimit("email_verify_identity", 8, 600)
TELEGRAM_IP = RateLimit("telegram_ip", 20, 300)
TELEGRAM_IDENTITY = RateLimit("telegram_identity", 10, 300)
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
        self._rate_limiter = rate_limiter
        self._email_sender = email_sender

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
