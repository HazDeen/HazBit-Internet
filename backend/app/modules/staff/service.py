from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.modules.auth.email import EmailDeliveryError, EmailSender
from app.modules.auth.enums import Permission, Role
from app.modules.auth.models import (
    AuditLog,
    StaffInvitation,
    TelegramAccount,
    User,
    UserEmail,
    UserPermission,
    UserRole,
)
from app.modules.auth.permissions import ROLE_PERMISSION_PRESETS
from app.modules.staff.schemas import (
    AcceptStaffInvitationRequest,
    CreateStaffInvitationRequest,
    StaffDirectoryResponse,
    StaffInvitationResponse,
    StaffMemberResponse,
    UpdateStaffAccessRequest,
)

STAFF_ROLES = frozenset(role for role in Role if role is not Role.USER)


class StaffService:
    def __init__(
        self, *, session: AsyncSession, settings: Settings, email_sender: EmailSender
    ) -> None:
        self._session = session
        self._settings = settings
        self._email = email_sender

    async def directory(self) -> StaffDirectoryResponse:
        role_rows = (
            await self._session.execute(
                select(User, UserEmail.email)
                .join(UserEmail, (UserEmail.user_id == User.id) & UserEmail.is_primary.is_(True))
                .where(
                    User.id.in_(
                        select(UserRole.user_id).where(
                            UserRole.role.in_([role.value for role in STAFF_ROLES]),
                            UserRole.revoked_at.is_(None),
                        )
                    )
                )
                .order_by(User.created_at)
            )
        ).all()
        members = [await self._member(user, str(email)) for user, email in role_rows]
        now = datetime.now(UTC)
        invitations = list(
            (
                await self._session.scalars(
                    select(StaffInvitation)
                    .where(
                        StaffInvitation.accepted_at.is_(None),
                        StaffInvitation.revoked_at.is_(None),
                        StaffInvitation.expires_at > now,
                    )
                    .order_by(StaffInvitation.created_at.desc())
                )
            ).all()
        )
        return StaffDirectoryResponse(
            members=members,
            invitations=[self._invitation(item) for item in invitations],
            role_presets={
                role: sorted(values, key=str)
                for role, values in ROLE_PERMISSION_PRESETS.items()
                if role in STAFF_ROLES
            },
            available_permissions=sorted(Permission, key=str),
        )

    async def invite(
        self, *, payload: CreateStaffInvitationRequest, actor_user_id: UUID
    ) -> StaffInvitationResponse:
        now = datetime.now(UTC)
        email = str(payload.email).casefold()
        if Role.SUPER_ADMIN in payload.roles:
            raise ApplicationError(
                "super_admin_invite_forbidden",
                "Super admin access can only be transferred through an explicit owner operation.",
                422,
            )
        raw_token = secrets.token_urlsafe(48)
        invitation = StaffInvitation(
            email=email,
            token_hash=self._token_digest(raw_token),
            roles=[role.value for role in payload.roles],
            permissions=[permission.value for permission in payload.permissions],
            invited_by_user_id=actor_user_id,
            expires_at=now + timedelta(hours=self._settings.auth.email.invitation_ttl_hours),
        )
        async with self._session.begin():
            since = now - timedelta(days=1)
            sent_today = await self._session.scalar(
                select(func.count(StaffInvitation.id)).where(
                    StaffInvitation.invited_by_user_id == actor_user_id,
                    StaffInvitation.created_at >= since,
                )
            )
            if int(sent_today or 0) >= self._settings.auth.email.invite_limit_per_day:
                raise ApplicationError(
                    "staff_invite_rate_limited", "Daily invitation limit reached.", 429
                )
            existing = list(
                (
                    await self._session.scalars(
                        select(StaffInvitation)
                        .where(
                            StaffInvitation.email == email,
                            StaffInvitation.accepted_at.is_(None),
                            StaffInvitation.revoked_at.is_(None),
                        )
                        .with_for_update()
                    )
                ).all()
            )
            for item in existing:
                item.revoked_at = now
            self._session.add(invitation)
            self._audit(
                actor_user_id=actor_user_id,
                action="staff.invitation_created",
                entity_id=invitation.id,
                after={
                    "email": email,
                    "roles": invitation.roles,
                    "permissions": invitation.permissions,
                },
            )

        separator = "&" if "?" in str(self._settings.auth.email.invitation_url) else "?"
        invitation_url = f"{self._settings.auth.email.invitation_url}{separator}token={raw_token}"
        try:
            await self._email.send_staff_invitation(
                email=email,
                invitation_url=invitation_url,
                roles=invitation.roles,
                expires_hours=self._settings.auth.email.invitation_ttl_hours,
            )
        except EmailDeliveryError as exc:
            async with self._session.begin():
                invitation.revoked_at = datetime.now(UTC)
            raise ApplicationError(
                "staff_invitation_delivery_failed",
                "Invitation email could not be delivered.",
                503,
            ) from exc
        return self._invitation(invitation)

    async def accept(
        self, *, payload: AcceptStaffInvitationRequest, actor_user_id: UUID
    ) -> StaffMemberResponse:
        now = datetime.now(UTC)
        async with self._session.begin():
            invitation = await self._session.scalar(
                select(StaffInvitation)
                .where(StaffInvitation.token_hash == self._token_digest(payload.token))
                .with_for_update()
            )
            if (
                invitation is None
                or invitation.accepted_at is not None
                or invitation.revoked_at is not None
                or invitation.expires_at <= now
            ):
                raise ApplicationError(
                    "staff_invitation_invalid", "Invitation is invalid or expired.", 400
                )
            user = await self._session.get(User, actor_user_id, with_for_update=True)
            email = await self._session.scalar(
                select(UserEmail.email).where(
                    UserEmail.user_id == actor_user_id,
                    UserEmail.is_primary.is_(True),
                    UserEmail.verified_at.is_not(None),
                )
            )
            if (
                user is None
                or email is None
                or str(email).casefold() != invitation.email.casefold()
            ):
                raise ApplicationError(
                    "staff_invitation_email_mismatch",
                    "Sign in with the verified email address that received the invitation.",
                    403,
                )
            await self._replace_access(
                user_id=actor_user_id,
                roles=[Role(value) for value in invitation.roles],
                permissions=[Permission(value) for value in invitation.permissions],
                granted_by=invitation.invited_by_user_id,
            )
            invitation.accepted_at = now
            invitation.accepted_by_user_id = actor_user_id
            self._audit(
                actor_user_id=actor_user_id,
                action="staff.invitation_accepted",
                entity_id=invitation.id,
                after={"roles": invitation.roles, "permissions": invitation.permissions},
            )
        try:
            await self._email.send_staff_welcome(email=str(email), roles=invitation.roles)
        except EmailDeliveryError:
            # Access is already committed. A confirmation email must not turn a
            # successful one-time invitation into a misleading client error.
            pass
        return await self._member(user, str(email))

    async def update(
        self,
        *,
        user_id: UUID,
        payload: UpdateStaffAccessRequest,
        actor_user_id: UUID,
    ) -> StaffMemberResponse:
        if user_id == actor_user_id:
            raise ApplicationError(
                "staff_self_update_forbidden",
                "You cannot change your own administrative access.",
                409,
            )
        if Role.SUPER_ADMIN in payload.roles:
            raise ApplicationError(
                "super_admin_assignment_forbidden",
                "Use the owner transfer procedure for super admin.",
                422,
            )
        async with self._session.begin():
            user = await self._session.get(User, user_id, with_for_update=True)
            email = await self._session.scalar(
                select(UserEmail.email).where(
                    UserEmail.user_id == user_id, UserEmail.is_primary.is_(True)
                )
            )
            if user is None or email is None:
                raise ApplicationError("staff_member_not_found", "Staff member not found.", 404)
            before_roles = await self._active_roles(user_id)
            if Role.SUPER_ADMIN in before_roles:
                raise ApplicationError(
                    "super_admin_update_forbidden", "Super admin access cannot be edited here.", 409
                )
            await self._replace_access(
                user_id=user_id,
                roles=payload.roles,
                permissions=payload.permissions,
                granted_by=actor_user_id,
            )
            self._audit(
                actor_user_id=actor_user_id,
                action="staff.access_updated",
                entity_id=user_id,
                before={"roles": sorted(role.value for role in before_roles)},
                after={
                    "roles": [role.value for role in payload.roles],
                    "permissions": [permission.value for permission in payload.permissions],
                },
                reason=payload.reason,
            )
        return await self._member(user, str(email))

    async def revoke_invitation(self, invitation_id: UUID, *, actor_user_id: UUID) -> None:
        async with self._session.begin():
            invitation = await self._session.get(
                StaffInvitation, invitation_id, with_for_update=True
            )
            if invitation is None or invitation.accepted_at is not None:
                raise ApplicationError(
                    "staff_invitation_not_found", "Pending invitation not found.", 404
                )
            invitation.revoked_at = datetime.now(UTC)
            self._audit(
                actor_user_id=actor_user_id,
                action="staff.invitation_revoked",
                entity_id=invitation.id,
                after={"email": invitation.email},
            )

    async def _replace_access(
        self,
        *,
        user_id: UUID,
        roles: list[Role],
        permissions: list[Permission],
        granted_by: UUID,
    ) -> None:
        await self._session.execute(
            delete(UserRole).where(UserRole.user_id == user_id, UserRole.role != Role.USER.value)
        )
        await self._session.execute(delete(UserPermission).where(UserPermission.user_id == user_id))
        self._session.add_all(
            [UserRole(user_id=user_id, role=role.value, granted_by=granted_by) for role in roles]
            + [
                UserPermission(user_id=user_id, permission=permission.value, granted_by=granted_by)
                for permission in permissions
            ]
        )
        await self._session.flush()

    async def _member(self, user: User, email: str) -> StaffMemberResponse:
        roles = await self._active_roles(user.id)
        explicit_permissions = set(
            Permission(value)
            for value in (
                await self._session.scalars(
                    select(UserPermission.permission).where(UserPermission.user_id == user.id)
                )
            ).all()
        )
        telegram_linked = bool(
            await self._session.scalar(
                select(func.count(TelegramAccount.id)).where(TelegramAccount.user_id == user.id)
            )
        )
        return StaffMemberResponse(
            user_id=user.id,
            email=email,
            public_name=user.public_name,
            status=user.status,
            roles=sorted(roles, key=str),
            permissions=sorted(explicit_permissions, key=str),
            telegram_linked=telegram_linked,
            created_at=user.created_at,
        )

    async def _active_roles(self, user_id: UUID) -> set[Role]:
        rows = await self._session.scalars(
            select(UserRole.role).where(UserRole.user_id == user_id, UserRole.revoked_at.is_(None))
        )
        return {Role(value) for value in rows.all() if Role(value) in STAFF_ROLES}

    def _token_digest(self, token: str) -> bytes:
        return hmac.new(
            self._settings.auth.email.invitation_secret.get_secret_value().encode(),
            token.encode(),
            hashlib.sha256,
        ).digest()

    @staticmethod
    def _invitation(invitation: StaffInvitation) -> StaffInvitationResponse:
        return StaffInvitationResponse(
            id=invitation.id,
            email=invitation.email,
            roles=[Role(value) for value in invitation.roles],
            permissions=[Permission(value) for value in invitation.permissions],
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        )

    def _audit(
        self,
        *,
        actor_user_id: UUID,
        action: str,
        entity_id: UUID,
        after: dict[str, object],
        before: dict[str, object] | None = None,
        reason: str | None = None,
    ) -> None:
        self._session.add(
            AuditLog(
                actor_user_id=actor_user_id,
                actor_type="super_admin",
                action=action,
                entity_type="staff_access",
                entity_id=entity_id,
                reason=reason,
                before_state=before,
                after_state=after,
            )
        )
