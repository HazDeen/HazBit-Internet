from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import FamilySettings
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.modules.auth.crypto import OpaqueTokenCodec, SignalHasher
from app.modules.auth.models import AuditLog
from app.modules.auth.rate_limit import RateLimit, RateLimiter
from app.modules.families.enums import FamilyGroupStatus, FamilyInvitationStatus
from app.modules.families.models import FamilyGroup, FamilyInvitation, FamilyMember
from app.modules.families.repository import FamilyRepository
from app.modules.families.schemas import (
    FamilyGroupResponse,
    FamilyInvitationInboxResponse,
    FamilyInvitationResponse,
    FamilyMemberResponse,
)
from app.modules.payments.models import OutboxEvent
from app.modules.vpn.enums import CommandStatus, CommandType, DesiredVpnStatus
from app.modules.vpn.models import PlanVersion, Subscription, VpnAccount, VpnSyncCommand

LIVE_SUBSCRIPTION_STATUSES = {"active", "grace_period"}


@dataclass(frozen=True, slots=True)
class FamilyClientContext:
    ip_address: str
    device_fingerprint: str | None
    user_agent: str | None
    request_id: UUID | None


class FamilyService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: FamilySettings,
        rate_limiter: RateLimiter,
        token_codec: OpaqueTokenCodec,
        signal_hasher: SignalHasher,
    ) -> None:
        self._session = session
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._tokens = token_codec
        self._signals = signal_hasher
        self._repository = FamilyRepository(session)

    async def create_group(
        self,
        *,
        owner_user_id: UUID,
        subscription_id: UUID,
        name: str,
        client: FamilyClientContext,
    ) -> FamilyGroupResponse:
        await self._limit("family_group_create", owner_user_id, client, 5, 86400)
        now = datetime.now(UTC)
        async with self._session.begin():
            await self._repository.serialize(f"family:create:{owner_user_id}")
            if await self._repository.active_group_for_owner(owner_user_id):
                raise ApplicationError(
                    "family_group_already_exists", "You already own an active family group.", 409
                )
            if await self._repository.active_membership(owner_user_id):
                raise ApplicationError(
                    "family_membership_exists", "You already belong to a family group.", 409
                )
            subscription_plan = await self._repository.subscription_plan_for_owner(
                subscription_id, owner_user_id, for_update=True
            )
            if subscription_plan is None:
                raise ApplicationError("subscription_not_found", "Subscription not found.", 404)
            subscription, plan = subscription_plan
            self._require_family_subscription(subscription, plan, now)
            group = FamilyGroup(
                owner_user_id=owner_user_id,
                subscription_id=subscription_id,
                name=name.strip(),
                status=FamilyGroupStatus.ACTIVE.value,
                member_limit=plan.family_member_limit,
            )
            self._repository.add(group)
            await self._session.flush()
            self._repository.add(
                FamilyMember(family_group_id=group.id, user_id=owner_user_id, joined_at=now)
            )
            self._audit(
                actor_user_id=owner_user_id,
                action="family.group.created",
                entity_type="family_group",
                entity_id=group.id,
                client=client,
                after_state={
                    "subscription_id": str(subscription_id),
                    "member_limit": group.member_limit,
                },
            )
            self._event(group.id, "family.group.created", {"owner_user_id": str(owner_user_id)})
        return await self._response(group.id)

    async def my_group(self, user_id: UUID) -> FamilyGroupResponse:
        group = await self._repository.active_group_for_member(user_id)
        if group is None:
            raise ApplicationError("family_group_not_found", "Family group not found.", 404)
        return await self._response(group.id)

    async def rename_group(
        self,
        *,
        group_id: UUID,
        owner_user_id: UUID,
        name: str,
        client: FamilyClientContext,
    ) -> FamilyGroupResponse:
        async with self._session.begin():
            group = await self._owned_group(group_id, owner_user_id, for_update=True)
            before = group.name
            group.name = name.strip()
            self._audit(
                actor_user_id=owner_user_id,
                action="family.group.renamed",
                entity_type="family_group",
                entity_id=group.id,
                client=client,
                before_state={"name": before},
                after_state={"name": group.name},
            )
            self._event(group.id, "family.group.renamed", {"name": group.name})
        return await self._response(group_id)

    async def invite(
        self,
        *,
        group_id: UUID,
        owner_user_id: UUID,
        invited_user_id: UUID | None,
        invited_email: str | None,
        client: FamilyClientContext,
    ) -> FamilyInvitationResponse:
        await self._limit(
            "family_invite", owner_user_id, client, self._settings.invite_limit_per_day, 86400
        )
        now = datetime.now(UTC)
        normalized_email = invited_email.strip().casefold() if invited_email else None
        token = self._tokens.generate()
        async with self._session.begin():
            await self._repository.serialize(f"family:invite:{group_id}")
            group = await self._owned_group(group_id, owner_user_id, for_update=True)
            await self._repository.expire_pending_invitations(group.id, now)
            self._require_group_active(group)
            if invited_user_id == owner_user_id:
                raise ApplicationError("family_self_invite", "You cannot invite yourself.", 409)
            owner_email = await self._repository.primary_email(owner_user_id)
            if normalized_email and owner_email and normalized_email == owner_email.casefold():
                raise ApplicationError("family_self_invite", "You cannot invite yourself.", 409)
            target_user = None
            if invited_user_id is not None:
                target_user = await self._repository.user(invited_user_id)
                if target_user is None or target_user.status != "active":
                    raise ApplicationError("family_invitee_not_found", "Invitee not found.", 404)
            elif normalized_email:
                target_user = await self._repository.user_by_email(normalized_email)
            if target_user and await self._repository.active_membership(target_user.id):
                raise ApplicationError(
                    "family_membership_exists",
                    "The invited user already belongs to a family group.",
                    409,
                )
            member_count = await self._repository.active_member_count(group.id)
            pending_count = await self._repository.pending_invitation_count(group.id)
            if member_count + pending_count >= group.member_limit:
                raise ApplicationError(
                    "family_member_limit_reached", "Family member limit reached.", 409
                )
            if await self._repository.pending_invitation_for_target(
                group.id, user_id=invited_user_id, email=normalized_email
            ):
                raise ApplicationError(
                    "family_invitation_exists", "A pending invitation already exists.", 409
                )
            invitation = FamilyInvitation(
                family_group_id=group.id,
                invited_by_user_id=owner_user_id,
                invited_user_id=invited_user_id,
                invited_email=normalized_email,
                token_hash=self._tokens.digest(token),
                status=FamilyInvitationStatus.PENDING.value,
                expires_at=now + timedelta(hours=self._settings.invitation_ttl_hours),
            )
            self._repository.add(invitation)
            await self._session.flush()
            self._audit(
                actor_user_id=owner_user_id,
                action="family.invitation.created",
                entity_type="family_invitation",
                entity_id=invitation.id,
                client=client,
                after_state={
                    "family_group_id": str(group.id),
                    "invited_user_id": str(invited_user_id) if invited_user_id else None,
                    "invited_email": normalized_email,
                    "expires_at": invitation.expires_at.isoformat(),
                },
            )
            self._event(
                group.id,
                "family.invitation.created",
                {
                    "invitation_id": str(invitation.id),
                    "invited_user_id": str(invited_user_id) if invited_user_id else None,
                    "invited_email": normalized_email,
                },
                unique=str(invitation.id),
            )
            return self._invitation_response(invitation, token=token)

    async def inbox(self, user_id: UUID) -> FamilyInvitationInboxResponse:
        email = await self._repository.primary_email(user_id)
        invitations = await self._repository.invitation_inbox(user_id, email)
        return FamilyInvitationInboxResponse(
            invitations=[
                self._invitation_response(invitation)
                for invitation in invitations
                if invitation.expires_at > datetime.now(UTC)
            ]
        )

    async def accept(
        self, *, user_id: UUID, token: str, client: FamilyClientContext
    ) -> FamilyGroupResponse:
        await self._limit("family_accept", user_id, client, 10, 3600)
        now = datetime.now(UTC)
        async with self._session.begin():
            await self._repository.serialize(f"family:accept:{user_id}")
            invitation = await self._repository.invitation_by_token(
                self._tokens.digest(token), for_update=True
            )
            if invitation is None:
                raise ApplicationError("family_invitation_invalid", "Invitation is invalid.", 404)
            if invitation.status != FamilyInvitationStatus.PENDING.value:
                raise ApplicationError(
                    "family_invitation_not_pending", "Invitation is no longer pending.", 409
                )
            if invitation.expires_at <= now:
                raise ApplicationError("family_invitation_expired", "Invitation has expired.", 410)
            await self._verify_invitation_target(invitation, user_id)
            group = await self._repository.group(invitation.family_group_id, for_update=True)
            if group is None:
                raise ApplicationError("family_group_not_found", "Family group not found.", 404)
            self._require_group_active(group)
            if await self._repository.active_membership(user_id):
                raise ApplicationError(
                    "family_membership_exists", "You already belong to a family group.", 409
                )
            if await self._repository.active_member_count(group.id) >= group.member_limit:
                raise ApplicationError(
                    "family_member_limit_reached", "Family member limit reached.", 409
                )
            existing_account = await self._repository.live_vpn_account_for_user(
                user_id, for_update=True
            )
            if existing_account and existing_account.subscription_id != group.subscription_id:
                raise ApplicationError(
                    "family_entitlement_conflict",
                    "Your account already has a different active VPN entitlement.",
                    409,
                )
            invitation.status = FamilyInvitationStatus.ACCEPTED.value
            invitation.accepted_at = now
            member = FamilyMember(
                family_group_id=group.id,
                user_id=user_id,
                invitation_id=invitation.id,
                joined_at=now,
            )
            self._repository.add(member)
            await self._session.flush()
            await self._project_member_entitlement(
                group=group,
                user_id=user_id,
                source_id=invitation.id,
                existing_account=existing_account,
                now=now,
            )
            self._audit(
                actor_user_id=user_id,
                action="family.invitation.accepted",
                entity_type="family_member",
                entity_id=member.id,
                client=client,
                after_state={"family_group_id": str(group.id)},
            )
            self._event(
                group.id,
                "family.invitation.accepted",
                {"invitation_id": str(invitation.id), "user_id": str(user_id)},
                unique=str(invitation.id),
            )
        return await self._response(invitation.family_group_id)

    async def decline(
        self, *, user_id: UUID, token: str, client: FamilyClientContext
    ) -> FamilyInvitationResponse:
        async with self._session.begin():
            invitation = await self._repository.invitation_by_token(
                self._tokens.digest(token), for_update=True
            )
            if invitation is None or invitation.status != FamilyInvitationStatus.PENDING.value:
                raise ApplicationError("family_invitation_invalid", "Invitation is invalid.", 404)
            await self._verify_invitation_target(invitation, user_id)
            invitation.status = FamilyInvitationStatus.DECLINED.value
            self._audit(
                actor_user_id=user_id,
                action="family.invitation.declined",
                entity_type="family_invitation",
                entity_id=invitation.id,
                client=client,
                after_state={"status": invitation.status},
            )
            self._event(
                invitation.family_group_id,
                "family.invitation.declined",
                {"invitation_id": str(invitation.id), "user_id": str(user_id)},
                unique=str(invitation.id),
            )
            return self._invitation_response(invitation)

    async def revoke_invitation(
        self,
        *,
        group_id: UUID,
        invitation_id: UUID,
        owner_user_id: UUID,
        client: FamilyClientContext,
    ) -> FamilyInvitationResponse:
        async with self._session.begin():
            await self._owned_group(group_id, owner_user_id, for_update=True)
            invitation = await self._repository.invitation(invitation_id, for_update=True)
            if invitation is None or invitation.family_group_id != group_id:
                raise ApplicationError("family_invitation_not_found", "Invitation not found.", 404)
            if invitation.status != FamilyInvitationStatus.PENDING.value:
                raise ApplicationError(
                    "family_invitation_not_pending", "Invitation is no longer pending.", 409
                )
            invitation.status = FamilyInvitationStatus.REVOKED.value
            self._audit(
                actor_user_id=owner_user_id,
                action="family.invitation.revoked",
                entity_type="family_invitation",
                entity_id=invitation.id,
                client=client,
                after_state={"status": invitation.status},
            )
            self._event(
                group_id,
                "family.invitation.revoked",
                {"invitation_id": str(invitation.id)},
                unique=str(invitation.id),
            )
            return self._invitation_response(invitation)

    async def leave(self, *, user_id: UUID, client: FamilyClientContext) -> None:
        async with self._session.begin():
            await self._repository.serialize(f"family:member:{user_id}")
            membership = await self._repository.active_membership(user_id)
            if membership is None:
                raise ApplicationError("family_membership_not_found", "Membership not found.", 404)
            group = await self._repository.group(membership.family_group_id, for_update=True)
            if group is None:
                raise ApplicationError("family_group_not_found", "Family group not found.", 404)
            if group.owner_user_id == user_id:
                raise ApplicationError(
                    "family_owner_cannot_leave", "The family owner cannot leave the group.", 409
                )
            await self._deactivate_member(
                membership=membership,
                group=group,
                actor_user_id=user_id,
                reason="Member left the family group",
                action="family.member.left",
                client=client,
            )

    async def remove_member(
        self,
        *,
        group_id: UUID,
        member_user_id: UUID,
        owner_user_id: UUID,
        reason: str,
        client: FamilyClientContext,
    ) -> None:
        async with self._session.begin():
            await self._repository.serialize(f"family:member:{member_user_id}")
            group = await self._owned_group(group_id, owner_user_id, for_update=True)
            if member_user_id == owner_user_id:
                raise ApplicationError(
                    "family_owner_cannot_be_removed", "The family owner cannot be removed.", 409
                )
            membership = await self._repository.active_membership(member_user_id)
            if membership is None or membership.family_group_id != group.id:
                raise ApplicationError("family_member_not_found", "Family member not found.", 404)
            await self._deactivate_member(
                membership=membership,
                group=group,
                actor_user_id=owner_user_id,
                reason=reason,
                action="family.member.removed",
                client=client,
            )

    async def _response(self, group_id: UUID) -> FamilyGroupResponse:
        group = await self._repository.group(group_id)
        if group is None:
            raise ApplicationError("family_group_not_found", "Family group not found.", 404)
        plan = await self._repository.plan_for_group(group)
        members = await self._repository.members(group.id)
        invitations = await self._repository.invitations(group.id)
        now = datetime.now(UTC)
        return FamilyGroupResponse(
            id=group.id,
            owner_user_id=group.owner_user_id,
            subscription_id=group.subscription_id,
            name=group.name,
            status=group.status,
            member_limit=group.member_limit,
            active_member_count=len(members),
            pending_invitation_count=sum(
                1
                for invitation in invitations
                if invitation.status == "pending" and invitation.expires_at > now
            ),
            device_limit=plan.device_limit,
            active_device_count=await self._repository.active_device_count(group.subscription_id),
            members=[
                FamilyMemberResponse(
                    id=member.id,
                    user_id=member.user_id,
                    email=email,
                    role="owner" if member.user_id == group.owner_user_id else "member",
                    joined_at=member.joined_at,
                )
                for member, email in members
            ],
            invitations=[self._invitation_response(item, now=now) for item in invitations],
            created_at=group.created_at,
            updated_at=group.updated_at,
        )

    async def _owned_group(
        self, group_id: UUID, owner_user_id: UUID, *, for_update: bool
    ) -> FamilyGroup:
        group = await self._repository.group(group_id, for_update=for_update)
        if group is None or group.owner_user_id != owner_user_id:
            raise ApplicationError("family_group_not_found", "Family group not found.", 404)
        return group

    async def _verify_invitation_target(self, invitation: FamilyInvitation, user_id: UUID) -> None:
        if invitation.invited_user_id is not None:
            if invitation.invited_user_id != user_id:
                raise ApplicationError(
                    "family_invitation_forbidden", "Invitation is not yours.", 403
                )
            return
        email = await self._repository.primary_email(user_id)
        if email is None or email.casefold() != (invitation.invited_email or "").casefold():
            raise ApplicationError("family_invitation_forbidden", "Invitation is not yours.", 403)

    async def _project_member_entitlement(
        self,
        *,
        group: FamilyGroup,
        user_id: UUID,
        source_id: UUID,
        existing_account: VpnAccount | None,
        now: datetime,
    ) -> None:
        subscription_plan = await self._repository.subscription_plan_for_owner(
            group.subscription_id, group.owner_user_id
        )
        if subscription_plan is None:
            raise RuntimeError("family group subscription not found")
        subscription, plan = subscription_plan
        self._require_family_subscription(subscription, plan, now)
        account = existing_account
        if account is None:
            account = VpnAccount(
                user_id=user_id,
                subscription_id=subscription.id,
                username=f"hz_{user_id.hex[:24]}",
                desired_status=DesiredVpnStatus.ACTIVE.value,
                desired_expires_at=subscription.current_period_ends_at,
            )
            self._repository.add(account)
            await self._session.flush()
        else:
            account.desired_status = DesiredVpnStatus.ACTIVE.value
            account.desired_expires_at = subscription.current_period_ends_at
        email = await self._repository.primary_email(user_id)
        expires_at = subscription.current_period_ends_at
        if expires_at is None:
            raise RuntimeError("active family subscription has no expiration")
        command = VpnSyncCommand(
            vpn_account_id=account.id,
            command_type=CommandType.ENSURE_ACCOUNT.value,
            idempotency_key=f"vpn:family:ensure:{account.id}:{source_id}",
            payload={
                "username": account.username,
                "expire_at": expires_at.isoformat(),
                "traffic_limit_bytes": plan.traffic_limit_bytes or 0,
                "device_limit": plan.device_limit,
                "email": email,
                "telegram_id": None,
                "internal_squad_ids": self._squad_ids(plan.remnawave_policy),
            },
            status=CommandStatus.PENDING.value,
            attempt_count=0,
            next_attempt_at=now,
        )
        self._repository.add(command)

    async def _deactivate_member(
        self,
        *,
        membership: FamilyMember,
        group: FamilyGroup,
        actor_user_id: UUID,
        reason: str,
        action: str,
        client: FamilyClientContext,
    ) -> None:
        now = datetime.now(UTC)
        membership.left_at = now
        membership.removed_by_user_id = actor_user_id
        membership.remove_reason = reason
        account = await self._repository.vpn_account(
            membership.user_id, group.subscription_id, for_update=True
        )
        if account is not None:
            account.desired_status = DesiredVpnStatus.DISABLED.value
            self._repository.add(
                VpnSyncCommand(
                    vpn_account_id=account.id,
                    command_type=CommandType.DISABLE.value,
                    idempotency_key=f"vpn:family:disable:{account.id}:{membership.id}",
                    payload={"reason": reason},
                    status=CommandStatus.PENDING.value,
                    attempt_count=0,
                    next_attempt_at=now,
                )
            )
        self._audit(
            actor_user_id=actor_user_id,
            action=action,
            entity_type="family_member",
            entity_id=membership.id,
            client=client,
            after_state={"family_group_id": str(group.id), "reason": reason},
        )
        self._event(
            group.id,
            action,
            {"member_user_id": str(membership.user_id), "reason": reason},
            unique=str(membership.id),
        )

    async def _limit(
        self,
        name: str,
        user_id: UUID,
        client: FamilyClientContext,
        limit: int,
        window: int,
    ) -> None:
        await self._rate_limiter.enforce(RateLimit(f"{name}_user", limit, window), str(user_id))
        await self._rate_limiter.enforce(
            RateLimit(f"{name}_ip", limit * 3, window),
            self._signals.digest("ip", client.ip_address).hex(),
        )
        if client.device_fingerprint:
            await self._rate_limiter.enforce(
                RateLimit(f"{name}_device", limit * 2, window),
                self._signals.digest("device", client.device_fingerprint).hex(),
            )

    def _audit(
        self,
        *,
        actor_user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        client: FamilyClientContext,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
    ) -> None:
        self._repository.add(
            AuditLog(
                actor_user_id=actor_user_id,
                actor_type="user",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                before_state=before_state,
                after_state=after_state,
                ip_address=client.ip_address,
                user_agent=client.user_agent,
                request_id=client.request_id,
            )
        )

    def _event(
        self,
        group_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        *,
        unique: str | None = None,
    ) -> None:
        self._repository.add(
            OutboxEvent(
                aggregate_type="family_group",
                aggregate_id=group_id,
                event_type=event_type,
                payload=payload,
                idempotency_key=f"{event_type}:{unique or uuid7()}",
            )
        )

    @staticmethod
    def _require_group_active(group: FamilyGroup) -> None:
        if group.status != FamilyGroupStatus.ACTIVE.value:
            raise ApplicationError("family_group_inactive", "Family group is not active.", 409)

    @staticmethod
    def _require_family_subscription(
        subscription: Subscription, plan: PlanVersion, now: datetime
    ) -> None:
        if (
            subscription.status not in LIVE_SUBSCRIPTION_STATUSES
            or subscription.current_period_ends_at is None
            or subscription.current_period_ends_at <= now
        ):
            raise ApplicationError(
                "family_subscription_inactive", "An active family subscription is required.", 409
            )
        if plan.family_member_limit < 2:
            raise ApplicationError(
                "family_plan_required", "This subscription does not support a family group.", 409
            )

    @staticmethod
    def _squad_ids(policy: dict[str, Any]) -> list[str]:
        values = policy.get("internal_squad_ids", [])
        if not isinstance(values, list):
            raise ApplicationError("invalid_remnawave_policy", "Plan policy is invalid.", 500)
        try:
            return [str(UUID(str(value))) for value in values]
        except ValueError as exc:
            raise ApplicationError(
                "invalid_remnawave_policy", "Plan policy is invalid.", 500
            ) from exc

    @staticmethod
    def _invitation_response(
        invitation: FamilyInvitation,
        *,
        token: str | None = None,
        now: datetime | None = None,
    ) -> FamilyInvitationResponse:
        effective_status = invitation.status
        if effective_status == "pending" and invitation.expires_at <= (now or datetime.now(UTC)):
            effective_status = "expired"
        return FamilyInvitationResponse(
            id=invitation.id,
            family_group_id=invitation.family_group_id,
            invited_user_id=invitation.invited_user_id,
            invited_email=invitation.invited_email,
            status=effective_status,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
            invite_token=token,
        )
