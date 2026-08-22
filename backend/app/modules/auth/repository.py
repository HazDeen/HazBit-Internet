from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import distinct, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import Role
from app.modules.auth.models import (
    AuditLog,
    AuthSession,
    OtpChallenge,
    RiskSignal,
    TelegramAccount,
    User,
    UserEmail,
    UserRole,
)


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def invalidate_otp_challenges(
        self,
        *,
        email: str,
        purpose: str,
        consumed_at: datetime,
    ) -> None:
        await self.session.execute(
            update(OtpChallenge)
            .where(
                OtpChallenge.email == email,
                OtpChallenge.purpose == purpose,
                OtpChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=consumed_at)
        )

    def add_otp_challenge(self, challenge: OtpChallenge) -> None:
        self.session.add(challenge)

    async def get_latest_otp_for_update(
        self,
        *,
        email: str,
        purpose: str,
    ) -> OtpChallenge | None:
        result = await self.session.execute(
            select(OtpChallenge)
            .where(
                OtpChallenge.email == email,
                OtpChallenge.purpose == purpose,
                OtpChallenge.consumed_at.is_(None),
            )
            .order_by(OtpChallenge.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> tuple[User, UserEmail] | None:
        result = await self.session.execute(
            select(User, UserEmail)
            .join(UserEmail, UserEmail.user_id == User.id)
            .where(UserEmail.email == email)
        )
        row = result.one_or_none()
        return (row[0], row[1]) if row is not None else None

    async def create_user_with_email(self, *, email: str, verified_at: datetime) -> User:
        user = User()
        self.session.add(user)
        await self.session.flush()
        self.session.add(
            UserEmail(
                user_id=user.id,
                email=email,
                is_primary=True,
                verified_at=verified_at,
            )
        )
        self.session.add(UserRole(user_id=user.id, role=Role.USER.value))
        await self.session.flush()
        return user

    async def serialize_telegram_login(self, telegram_user_id: int) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": telegram_user_id},
        )

    async def get_telegram_account(self, telegram_user_id: int) -> TelegramAccount | None:
        result = await self.session.execute(
            select(TelegramAccount).where(TelegramAccount.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def create_user_with_telegram(
        self,
        *,
        telegram_user_id: int,
        username: str | None,
        first_name: str,
        last_name: str | None,
        language_code: str | None,
    ) -> tuple[User, TelegramAccount]:
        display_name = " ".join(value for value in (first_name, last_name) if value)
        user = User(public_name=display_name or None, locale=language_code or "ru")
        self.session.add(user)
        await self.session.flush()
        account = TelegramAccount(
            user_id=user.id,
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
        )
        self.session.add_all([account, UserRole(user_id=user.id, role=Role.USER.value)])
        await self.session.flush()
        return user, account

    async def update_telegram_account(
        self,
        account: TelegramAccount,
        *,
        username: str | None,
        first_name: str,
        last_name: str | None,
        language_code: str | None,
        updated_at: datetime,
    ) -> User:
        account.username = username
        account.first_name = first_name
        account.last_name = last_name
        account.language_code = language_code
        account.updated_at = updated_at
        return await self.get_user(account.user_id)

    async def get_user(self, user_id: UUID) -> User:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one()

    async def get_roles(self, user_id: UUID) -> set[Role]:
        result = await self.session.scalars(
            select(UserRole.role).where(
                UserRole.user_id == user_id,
                UserRole.revoked_at.is_(None),
            )
        )
        return {Role(value) for value in result.all()}

    async def get_primary_email(self, user_id: UUID) -> str | None:
        result = await self.session.scalar(
            select(UserEmail.email).where(
                UserEmail.user_id == user_id,
                UserEmail.is_primary.is_(True),
            )
        )
        return str(result) if result is not None else None

    async def get_telegram_user_id(self, user_id: UUID) -> int | None:
        value = await self.session.scalar(
            select(TelegramAccount.telegram_user_id).where(TelegramAccount.user_id == user_id)
        )
        return int(value) if value is not None else None

    def add_session(self, session: AuthSession) -> None:
        self.session.add(session)

    async def get_session_by_digest_for_update(self, digest: bytes) -> AuthSession | None:
        result = await self.session.execute(
            select(AuthSession).where(AuthSession.refresh_token_hash == digest).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_active_session(self, session_id: UUID, *, now: datetime) -> AuthSession | None:
        result = await self.session.execute(
            select(AuthSession).where(
                AuthSession.id == session_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def revoke_token_family(
        self,
        token_family_id: UUID,
        *,
        revoked_at: datetime,
        reason: str,
    ) -> None:
        await self.session.execute(
            update(AuthSession)
            .where(
                AuthSession.token_family_id == token_family_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at, revoke_reason=reason)
        )

    async def count_signal_users_since(
        self,
        *,
        signal_type: str,
        signal_hash: bytes,
        since: datetime,
    ) -> int:
        value = await self.session.scalar(
            select(func.count(distinct(RiskSignal.user_id))).where(
                RiskSignal.signal_type == signal_type,
                RiskSignal.signal_hash == signal_hash,
                RiskSignal.created_at >= since,
                RiskSignal.user_id.is_not(None),
            )
        )
        return int(value or 0)

    def add_risk_signal(self, signal: RiskSignal) -> None:
        self.session.add(signal)

    def add_auth_audit(
        self,
        *,
        user_id: UUID,
        action: str,
        session_id: UUID,
        ip_address: str,
        user_agent: str | None,
        request_id: UUID | None,
        after_state: dict[str, object],
    ) -> None:
        self.session.add(
            AuditLog(
                actor_user_id=user_id,
                actor_type="user",
                action=action,
                entity_type="auth_session",
                entity_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                after_state=after_state,
            )
        )
