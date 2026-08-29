from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.features import FEATURE_LABELS, FeatureControlStore, FeatureKey, FeatureState
from app.core.ids import uuid7
from app.integrations.redis import RedisManager
from app.integrations.remnawave_adapter import AdapterError, AdapterNodeState
from app.modules.admin.repository import AdminRepository
from app.modules.admin.schemas import (
    AdminDashboardResponse,
    AdminDevicePage,
    AdminDeviceResponse,
    AdminFamilyActionRequest,
    AdminFamilyGroupPage,
    AdminFamilyGroupResponse,
    AdminFamilyInvitationResponse,
    AdminFamilyMemberResponse,
    AdminFeatureResponse,
    AdminPaymentPage,
    AdminPaymentSummary,
    AdminPlanPriceInput,
    AdminPlanPriceResponse,
    AdminPlanResponse,
    AdminPlanVersionResponse,
    AdminRemnawaveNodeResponse,
    AdminSettingsResponse,
    AdminSubscriptionListItem,
    AdminSubscriptionPage,
    AdminSubscriptionSummary,
    AdminUserDetail,
    AdminUserListItem,
    AdminUserPage,
    ArchiveAdminPlanRequest,
    CreateAdminPlanRequest,
    CreateAdminPlanVersionRequest,
    DashboardTrendPoint,
    UpdateAdminPlanRequest,
)
from app.modules.auth.models import AuditLog, AuthSession, User
from app.modules.families.models import FamilyGroup
from app.modules.payments.models import OutboxEvent, Payment, PlanPrice
from app.modules.referrals.models import Plan, SubscriptionPeriod
from app.modules.vpn.enums import CommandStatus, CommandType, DesiredVpnStatus
from app.modules.vpn.models import Device, PlanVersion, Subscription, VpnAccount, VpnSyncCommand
from app.modules.vpn.runtime import VpnRuntime


class AdminService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        redis: RedisManager | None = None,
        vpn_runtime: VpnRuntime | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._feature_store = (
            FeatureControlStore(redis.client, redis_settings=settings.redis) if redis else None
        )
        self._adapter = vpn_runtime.adapter if vpn_runtime else None
        self._repository = AdminRepository(session)

    async def dashboard(self) -> AdminDashboardResponse:
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        trend_start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        currency = "RUB"
        users_by_day = await self._repository.daily_user_counts(trend_start)
        payments_by_day = await self._repository.daily_payment_totals(
            since=trend_start, currency=currency
        )
        trend = []
        for index in range(7):
            day = (trend_start + timedelta(days=index)).date().isoformat()
            trend.append(
                DashboardTrendPoint(
                    date=day,
                    users=users_by_day.get(day, 0),
                    payments_minor=payments_by_day.get(day, 0),
                )
            )
        return AdminDashboardResponse(
            total_users=await self._repository.count_users(),
            active_users=await self._repository.count_users(status="active"),
            active_subscriptions=await self._repository.count_active_subscriptions(),
            monthly_revenue_minor=await self._repository.monthly_revenue(
                since=month_start, currency=currency
            ),
            revenue_currency=currency,
            open_tickets=await self._repository.count_open_tickets(),
            pending_payments=await self._repository.count_pending_payments(),
            active_vpn_accounts=await self._repository.count_active_vpn_accounts(),
            active_promo_codes=await self._repository.count_active_promos(now),
            trend=trend,
        )

    async def users(
        self,
        *,
        search: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> AdminUserPage:
        rows, total = await self._repository.user_page(
            search=search, status=status, limit=limit, offset=offset
        )
        return AdminUserPage(
            items=[await self._user_list_item(*row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def user(self, user_id: UUID) -> AdminUserDetail:
        identity = await self._repository.user_identity(user_id)
        if identity is None:
            raise ApplicationError("admin_user_not_found", "User not found.", 404)
        base = await self._user_list_item(*identity)
        user = identity[0]
        devices, _ = await self._repository.devices(user_id=user_id, limit=200)
        payments = await self._repository.user_payments(user_id)
        return AdminUserDetail(
            **base.model_dump(),
            public_name=user.public_name,
            locale=user.locale,
            timezone=user.timezone,
            blocked_at=user.blocked_at,
            blocked_reason=user.blocked_reason,
            devices_detail=[self._device_response(device) for device in devices],
            payments=[self._payment_response(payment) for payment in payments],
        )

    async def block_user(
        self, *, user_id: UUID, actor_user_id: UUID, reason: str
    ) -> AdminUserDetail:
        if user_id == actor_user_id:
            raise ApplicationError(
                "admin_self_block_forbidden", "Administrators cannot block themselves.", 409
            )
        now = datetime.now(UTC)
        async with self._session.begin():
            user = await self._require_user_for_update(user_id)
            if user.status == "blocked":
                return await self.user(user_id)
            if user.status != "active":
                raise ApplicationError(
                    "admin_user_not_blockable", "Only active users can be blocked.", 409
                )
            before = self._user_state(user)
            user.status = "blocked"
            user.blocked_at = now
            user.blocked_reason = reason
            user.updated_at = now
            await self._session.execute(
                update(AuthSession)
                .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=now, revoke_reason="admin_user_blocked")
            )
            account = await self._repository.vpn_account_for_update(user_id)
            if account is not None:
                account.desired_status = DesiredVpnStatus.DISABLED.value
                if account.remnawave_user_id is not None:
                    self._enqueue_command(
                        account=account,
                        command_type=CommandType.DISABLE.value,
                        key=f"vpn:admin:block:{account.id}:{uuid7()}",
                        payload={"reason": reason},
                        now=now,
                    )
            self._record_user_action(
                user=user,
                actor_user_id=actor_user_id,
                action="admin.user_blocked",
                reason=reason,
                before=before,
            )
            await self._session.flush()
            return await self.user(user_id)

    async def unblock_user(
        self, *, user_id: UUID, actor_user_id: UUID, reason: str
    ) -> AdminUserDetail:
        now = datetime.now(UTC)
        async with self._session.begin():
            user = await self._require_user_for_update(user_id)
            if user.status == "active":
                return await self.user(user_id)
            if user.status != "blocked":
                raise ApplicationError(
                    "admin_user_not_unblockable", "Only blocked users can be unblocked.", 409
                )
            before = self._user_state(user)
            user.status = "active"
            user.blocked_at = None
            user.blocked_reason = None
            user.updated_at = now
            account = await self._repository.vpn_account_for_update(user_id)
            subscription_row = await self._repository.live_subscription(user_id)
            if account is not None and subscription_row is not None:
                subscription, plan, _ = subscription_row
                if (
                    subscription.status in {"active", "grace_period"}
                    and subscription.current_period_ends_at is not None
                    and subscription.current_period_ends_at > now
                ):
                    account.desired_status = DesiredVpnStatus.ACTIVE.value
                    await self._enqueue_entitlement_sync(
                        account=account,
                        subscription=subscription,
                        plan=plan,
                        key=f"vpn:admin:unblock:{account.id}:{uuid7()}",
                        now=now,
                    )
            self._record_user_action(
                user=user,
                actor_user_id=actor_user_id,
                action="admin.user_unblocked",
                reason=reason,
                before=before,
            )
            await self._session.flush()
            return await self.user(user_id)

    async def extend_subscription(
        self, *, user_id: UUID, actor_user_id: UUID, days: int, reason: str
    ) -> AdminSubscriptionSummary:
        now = datetime.now(UTC)
        operation_id = uuid7()
        async with self._session.begin():
            await self._require_user_for_update(user_id)
            row = await self._repository.live_subscription(user_id, for_update=True)
            if row is None:
                raise ApplicationError(
                    "admin_subscription_not_found", "User has no extendable subscription.", 404
                )
            subscription, plan, product = row
            if subscription.status == "cancelled":
                raise ApplicationError(
                    "admin_subscription_not_extendable",
                    "Cancelled subscriptions cannot be extended.",
                    409,
                )
            starts_at = max(subscription.current_period_ends_at or now, now)
            ends_at = starts_at + timedelta(days=days)
            before = self._subscription_state(subscription)
            subscription.starts_at = subscription.starts_at or now
            subscription.current_period_ends_at = ends_at
            if subscription.status in {"pending", "expired", "grace_period"}:
                subscription.status = "active"
            subscription.version += 1
            self._repository.add_period(
                SubscriptionPeriod(
                    subscription_id=subscription.id,
                    source_type="admin",
                    source_id=operation_id,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    plan_snapshot=self._plan_snapshot(plan),
                    price_minor=None,
                    currency=None,
                )
            )
            await self._session.flush()
            account = await self._ensure_vpn_account(
                user_id=user_id, subscription=subscription, plan=plan, now=now
            )
            if subscription.status != "suspended":
                await self._enqueue_entitlement_sync(
                    account=account,
                    subscription=subscription,
                    plan=plan,
                    key=f"vpn:admin:extend:{account.id}:{operation_id}",
                    now=now,
                )
            self._record_subscription_action(
                subscription=subscription,
                actor_user_id=actor_user_id,
                action="admin.subscription_extended",
                reason=reason,
                before=before,
                extra={"days": days, "operation_id": str(operation_id)},
            )
            await self._session.flush()
            return self._subscription_response(subscription, plan, product)

    async def change_plan(
        self,
        *,
        user_id: UUID,
        actor_user_id: UUID,
        plan_version_id: UUID,
        reason: str,
    ) -> AdminSubscriptionSummary:
        now = datetime.now(UTC)
        async with self._session.begin():
            await self._require_user_for_update(user_id)
            row = await self._repository.live_subscription(user_id, for_update=True)
            if row is None:
                raise ApplicationError(
                    "admin_subscription_not_found", "User has no subscription.", 404
                )
            subscription, _, _ = row
            target = await self._repository.active_plan_version(plan_version_id, now)
            if target is None:
                raise ApplicationError(
                    "admin_plan_version_not_found", "Active plan version not found.", 404
                )
            if subscription.plan_version_id == target.id:
                refreshed = await self._repository.live_subscription(user_id)
                assert refreshed is not None
                return self._subscription_response(*refreshed)
            products = {plan.id: plan for plan in await self._repository.plans()}
            product = products.get(target.plan_id)
            if product is None or not product.is_active:
                raise ApplicationError("admin_plan_inactive", "Plan is inactive.", 409)
            before = self._subscription_state(subscription)
            subscription.plan_version_id = target.id
            subscription.version += 1
            account = await self._ensure_vpn_account(
                user_id=user_id, subscription=subscription, plan=target, now=now
            )
            if subscription.status != "suspended":
                await self._enqueue_entitlement_sync(
                    account=account,
                    subscription=subscription,
                    plan=target,
                    key=f"vpn:admin:plan:{account.id}:{uuid7()}",
                    now=now,
                )
            self._record_subscription_action(
                subscription=subscription,
                actor_user_id=actor_user_id,
                action="admin.subscription_plan_changed",
                reason=reason,
                before=before,
                extra={"plan_version_id": str(target.id)},
            )
            await self._session.flush()
            return self._subscription_response(subscription, target, product)

    async def subscriptions(
        self, *, status: str | None, limit: int, offset: int
    ) -> AdminSubscriptionPage:
        rows, total = await self._repository.subscription_page(
            status=status, limit=limit, offset=offset
        )
        return AdminSubscriptionPage(
            items=[
                AdminSubscriptionListItem(
                    **self._subscription_response(sub, version, plan).model_dump(),
                    owner_user_id=sub.owner_user_id,
                    owner_email=email,
                    vpn_status=vpn_status,
                )
                for sub, version, plan, email, vpn_status in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def plans(self) -> list[AdminPlanResponse]:
        return [await self._plan_response(plan) for plan in await self._repository.plans()]

    async def create_plan(
        self, *, payload: CreateAdminPlanRequest, actor_user_id: UUID
    ) -> AdminPlanResponse:
        now = datetime.now(UTC)
        async with self._session.begin():
            if await self._repository.plan_by_slug(payload.slug) is not None:
                raise ApplicationError("admin_plan_slug_exists", "Plan slug already exists.", 409)
            plan = Plan(
                id=uuid7(),
                slug=payload.slug,
                name=payload.name,
                description=payload.description,
                is_active=True,
                sort_order=payload.sort_order,
            )
            self._repository.add(plan)
            await self._session.flush()
            await self._create_plan_version(
                plan=plan,
                version_number=1,
                device_limit=payload.device_limit,
                family_member_limit=payload.family_member_limit,
                traffic_limit_bytes=payload.traffic_limit_bytes,
                prices=payload.prices,
                now=now,
            )
            self._record_plan_action(
                plan=plan,
                actor_user_id=actor_user_id,
                action="admin.plan_created",
                reason=payload.reason,
                before=None,
                after={"slug": plan.slug, "name": plan.name, "version": 1},
            )
            await self._session.flush()
            return await self._plan_response(plan)

    async def update_plan(
        self,
        *,
        plan_id: UUID,
        payload: UpdateAdminPlanRequest,
        actor_user_id: UUID,
    ) -> AdminPlanResponse:
        async with self._session.begin():
            plan = await self._require_plan_for_update(plan_id)
            before = self._plan_state(plan)
            for field in ("name", "description", "sort_order", "is_active"):
                if field in payload.model_fields_set:
                    setattr(plan, field, getattr(payload, field))
            plan.updated_at = datetime.now(UTC)
            self._record_plan_action(
                plan=plan,
                actor_user_id=actor_user_id,
                action="admin.plan_updated",
                reason=payload.reason,
                before=before,
                after=self._plan_state(plan),
            )
            await self._session.flush()
            return await self._plan_response(plan)

    async def create_plan_version(
        self,
        *,
        plan_id: UUID,
        payload: CreateAdminPlanVersionRequest,
        actor_user_id: UUID,
    ) -> AdminPlanResponse:
        now = datetime.now(UTC)
        async with self._session.begin():
            plan = await self._require_plan_for_update(plan_id)
            if not plan.is_active:
                raise ApplicationError(
                    "admin_plan_inactive", "Inactive plan cannot be versioned.", 409
                )
            for current in await self._repository.current_plan_versions_for_update(plan.id):
                if current.valid_from < now:
                    current.valid_until = now
            version_number = await self._repository.next_plan_version(plan.id)
            await self._create_plan_version(
                plan=plan,
                version_number=version_number,
                device_limit=payload.device_limit,
                family_member_limit=payload.family_member_limit,
                traffic_limit_bytes=payload.traffic_limit_bytes,
                prices=payload.prices,
                now=now,
            )
            self._record_plan_action(
                plan=plan,
                actor_user_id=actor_user_id,
                action="admin.plan_version_created",
                reason=payload.reason,
                before=None,
                after={"version": version_number},
            )
            await self._session.flush()
            return await self._plan_response(plan)

    async def archive_plan(
        self,
        *,
        plan_id: UUID,
        payload: ArchiveAdminPlanRequest,
        actor_user_id: UUID,
    ) -> AdminPlanResponse:
        async with self._session.begin():
            plan = await self._require_plan_for_update(plan_id)
            before = self._plan_state(plan)
            plan.is_active = False
            plan.updated_at = datetime.now(UTC)
            self._record_plan_action(
                plan=plan,
                actor_user_id=actor_user_id,
                action="admin.plan_archived",
                reason=payload.reason,
                before=before,
                after=self._plan_state(plan),
            )
            await self._session.flush()
            return await self._plan_response(plan)

    async def family_groups(self, *, limit: int, offset: int) -> AdminFamilyGroupPage:
        rows, total = await self._repository.family_group_page(limit=limit, offset=offset)
        return AdminFamilyGroupPage(
            items=[self._family_group_response(*row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def family_group(self, group_id: UUID) -> AdminFamilyGroupResponse:
        row = await self._repository.family_group(group_id)
        if row is None:
            raise ApplicationError("admin_family_group_not_found", "Family group not found.", 404)
        response = self._family_group_response(*row)
        response.members = [
            AdminFamilyMemberResponse(
                id=member.id,
                user_id=member.user_id,
                email=email,
                joined_at=member.joined_at,
            )
            for member, email in await self._repository.family_members(group_id)
        ]
        invitations = await self._repository.family_invitations(group_id)
        response.invitations = [
            AdminFamilyInvitationResponse(
                id=invitation.id,
                invited_user_id=invitation.invited_user_id,
                invited_email=invitation.invited_email,
                status=(
                    "expired"
                    if invitation.status == "pending" and invitation.expires_at <= datetime.now(UTC)
                    else invitation.status
                ),
                expires_at=invitation.expires_at,
                created_at=invitation.created_at,
            )
            for invitation in invitations
        ]
        response.pending_invitation_count = sum(
            invitation.status == "pending" and invitation.expires_at > datetime.now(UTC)
            for invitation in invitations
        )
        (
            response.active_device_count,
            response.device_limit,
        ) = await self._repository.family_device_summary(response.subscription_id)
        return response

    async def remove_family_member(
        self,
        *,
        group_id: UUID,
        member_user_id: UUID,
        actor_user_id: UUID,
        payload: AdminFamilyActionRequest,
    ) -> AdminFamilyGroupResponse:
        now = datetime.now(UTC)
        async with self._session.begin():
            group = await self._repository.family_group_for_update(group_id)
            if group is None:
                raise ApplicationError(
                    "admin_family_group_not_found", "Family group not found.", 404
                )
            if member_user_id == group.owner_user_id:
                raise ApplicationError(
                    "admin_family_owner_remove_forbidden",
                    "The family owner cannot be removed.",
                    409,
                )
            member = await self._repository.family_member_for_update(group_id, member_user_id)
            if member is None:
                raise ApplicationError(
                    "admin_family_member_not_found", "Family member not found.", 404
                )
            member.left_at = now
            member.removed_by_user_id = actor_user_id
            member.remove_reason = payload.reason
            account = await self._repository.vpn_account_for_update(member_user_id)
            if account is not None and account.subscription_id == group.subscription_id:
                account.desired_status = DesiredVpnStatus.DISABLED.value
                self._enqueue_command(
                    account=account,
                    command_type=CommandType.DISABLE.value,
                    key=f"vpn:family:admin-disable:{account.id}:{member.id}",
                    payload={"reason": payload.reason},
                    now=now,
                )
            self._record_family_action(
                group=group,
                actor_user_id=actor_user_id,
                action="admin.family_member.removed",
                reason=payload.reason,
                payload={"member_user_id": str(member_user_id)},
            )
        return await self.family_group(group_id)

    async def revoke_family_invitation(
        self,
        *,
        group_id: UUID,
        invitation_id: UUID,
        actor_user_id: UUID,
        payload: AdminFamilyActionRequest,
    ) -> AdminFamilyGroupResponse:
        async with self._session.begin():
            group = await self._repository.family_group_for_update(group_id)
            if group is None:
                raise ApplicationError(
                    "admin_family_group_not_found", "Family group not found.", 404
                )
            invitation = await self._repository.family_invitation_for_update(
                group_id, invitation_id
            )
            if invitation is None:
                raise ApplicationError(
                    "admin_family_invitation_not_found", "Invitation not found.", 404
                )
            if invitation.status != "pending":
                raise ApplicationError(
                    "admin_family_invitation_not_pending",
                    "Invitation is no longer pending.",
                    409,
                )
            invitation.status = "revoked"
            self._record_family_action(
                group=group,
                actor_user_id=actor_user_id,
                action="admin.family_invitation.revoked",
                reason=payload.reason,
                payload={"invitation_id": str(invitation_id)},
            )
        return await self.family_group(group_id)

    async def payments(self, *, status: str | None, limit: int, offset: int) -> AdminPaymentPage:
        values, total = await self._repository.payment_page(
            status=status, limit=limit, offset=offset
        )
        return AdminPaymentPage(
            items=[self._payment_response(payment) for payment in values],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def devices(self, *, user_id: UUID | None, limit: int, offset: int) -> AdminDevicePage:
        values, total = await self._repository.devices(user_id=user_id, limit=limit, offset=offset)
        return AdminDevicePage(
            items=[self._device_response(device) for device in values],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def settings(self) -> AdminSettingsResponse:
        features = (
            await self._feature_store.states(self._settings.features)
            if self._feature_store
            else [
                FeatureState(
                    key=key,
                    configured=bool(getattr(self._settings.features, key.value)),
                    runtime_enabled=True,
                )
                for key in FeatureKey
            ]
        )
        return AdminSettingsResponse(
            environment=self._settings.environment,
            app_version=self._settings.app_version,
            log_level=self._settings.log_level,
            payment_ai_model=self._settings.payments.gemini.model,
            payment_prompt_version=self._settings.payments.gemini.prompt_version,
            remnawave_adapter_url=str(self._settings.vpn.adapter.base_url),
            referral_days=self._settings.referrals.referred_days,
            referrer_days=self._settings.referrals.referrer_days,
            default_promo_plan=self._settings.promotions.default_plan_slug,
            support_create_limit_per_day=self._settings.support.create_rate_limit_per_day,
            support_message_limit_per_hour=self._settings.support.message_rate_limit_per_hour,
            features=[
                AdminFeatureResponse(
                    key=state.key,
                    label=FEATURE_LABELS[state.key][0],
                    description=FEATURE_LABELS[state.key][1],
                    configured=state.configured,
                    runtime_enabled=state.runtime_enabled,
                    enabled=state.enabled,
                )
                for state in features
            ],
        )

    async def update_feature(
        self,
        *,
        feature: FeatureKey,
        enabled: bool,
        actor_user_id: UUID,
        reason: str,
    ) -> AdminFeatureResponse:
        if self._feature_store is None:
            raise ApplicationError(
                "feature_control_unavailable", "Feature control is unavailable.", 503
            )
        configured = bool(getattr(self._settings.features, feature.value))
        if enabled and not configured:
            raise ApplicationError(
                "feature_disabled_by_environment",
                "The deployment configuration disables this feature.",
                409,
            )
        previous = next(
            state
            for state in await self._feature_store.states(self._settings.features)
            if state.key == feature
        )
        try:
            async with self._session.begin():
                self._session.add(
                    AuditLog(
                        actor_user_id=actor_user_id,
                        actor_type="user",
                        action="admin.feature_control_updated",
                        entity_type="feature_control",
                        entity_id=None,
                        reason=reason,
                        before_state={"key": feature.value, "enabled": previous.enabled},
                        after_state={"key": feature.value, "enabled": configured and enabled},
                    )
                )
                await self._session.flush()
                await self._feature_store.set_runtime(feature, enabled)
        except Exception:
            try:
                await self._feature_store.set_runtime(feature, previous.runtime_enabled)
            except RedisError:
                pass
            raise
        label, description = FEATURE_LABELS[feature]
        return AdminFeatureResponse(
            key=feature,
            label=label,
            description=description,
            configured=configured,
            runtime_enabled=enabled,
            enabled=configured and enabled,
        )

    async def remnawave_nodes(self) -> list[AdminRemnawaveNodeResponse]:
        if self._adapter is None:
            raise ApplicationError("adapter_unavailable", "Remnawave adapter is unavailable.", 503)
        try:
            result = await self._adapter.list_nodes()
        except AdapterError as exc:
            raise ApplicationError(exc.code, exc.detail, exc.status_code) from exc
        return [self._node_response(node) for node in result.nodes]

    async def set_remnawave_node_state(
        self,
        *,
        node_uuid: UUID,
        enabled: bool,
        actor_user_id: UUID,
        reason: str,
    ) -> AdminRemnawaveNodeResponse:
        if self._adapter is None:
            raise ApplicationError("adapter_unavailable", "Remnawave adapter is unavailable.", 503)
        async with self._session.begin():
            self._session.add(
                AuditLog(
                    actor_user_id=actor_user_id,
                    actor_type="user",
                    action="admin.remnawave_node_state_requested",
                    entity_type="remnawave_node",
                    entity_id=node_uuid,
                    reason=reason,
                    before_state=None,
                    after_state={"enabled": enabled},
                )
            )
        try:
            node = (
                await self._adapter.enable_node(node_uuid)
                if enabled
                else await self._adapter.disable_node(node_uuid)
            )
        except AdapterError as exc:
            raise ApplicationError(exc.code, exc.detail, exc.status_code) from exc
        async with self._session.begin():
            self._session.add(
                AuditLog(
                    actor_user_id=actor_user_id,
                    actor_type="user",
                    action="admin.remnawave_node_state_completed",
                    entity_type="remnawave_node",
                    entity_id=node_uuid,
                    reason=reason,
                    before_state=None,
                    after_state={"enabled": enabled, "name": node.name},
                )
            )
        return self._node_response(node)

    @staticmethod
    def _node_response(node: AdapterNodeState) -> AdminRemnawaveNodeResponse:
        return AdminRemnawaveNodeResponse(**node.model_dump())

    async def _user_list_item(
        self,
        user: User,
        email: str | None,
        telegram_id: int | None,
        telegram_username: str | None,
    ) -> AdminUserListItem:
        subscription_row = await self._repository.live_subscription(user.id)
        subscription = self._subscription_response(*subscription_row) if subscription_row else None
        payment_count, payment_total = await self._repository.payment_stats(user.id)
        return AdminUserListItem(
            id=user.id,
            email=email,
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            status=user.status,
            created_at=user.created_at,
            subscription=subscription,
            devices=await self._repository.device_count(user.id),
            trial=await self._repository.trial_exists(user.id),
            approved_payments=payment_count,
            paid_total_minor=payment_total,
        )

    async def _require_user_for_update(self, user_id: UUID) -> User:
        user = await self._repository.user_for_update(user_id)
        if user is None:
            raise ApplicationError("admin_user_not_found", "User not found.", 404)
        return user

    async def _ensure_vpn_account(
        self,
        *,
        user_id: UUID,
        subscription: Subscription,
        plan: PlanVersion,
        now: datetime,
    ) -> VpnAccount:
        if subscription.current_period_ends_at is None:
            raise ApplicationError(
                "admin_subscription_has_no_expiry", "Subscription has no expiry.", 409
            )
        account = await self._repository.vpn_account_for_update(user_id)
        if account is None:
            account = VpnAccount(
                user_id=user_id,
                subscription_id=subscription.id,
                username=f"hz_{user_id.hex[:24]}",
                desired_status=DesiredVpnStatus.ACTIVE.value,
                desired_expires_at=subscription.current_period_ends_at,
            )
            self._session.add(account)
            await self._session.flush()
        else:
            account.subscription_id = subscription.id
            account.desired_expires_at = subscription.current_period_ends_at
            if subscription.status != "suspended":
                account.desired_status = DesiredVpnStatus.ACTIVE.value
        return account

    async def _enqueue_entitlement_sync(
        self,
        *,
        account: VpnAccount,
        subscription: Subscription,
        plan: PlanVersion,
        key: str,
        now: datetime,
    ) -> None:
        if subscription.current_period_ends_at is None:
            raise RuntimeError("subscription has no expiry")
        email, telegram_id = await self._repository.identity_contacts(account.user_id)
        self._enqueue_command(
            account=account,
            command_type=CommandType.ENSURE_ACCOUNT.value,
            key=key,
            payload={
                "username": account.username,
                "expire_at": subscription.current_period_ends_at.isoformat(),
                "traffic_limit_bytes": plan.traffic_limit_bytes or 0,
                "device_limit": plan.device_limit,
                "email": email,
                "telegram_id": telegram_id,
                "internal_squad_ids": self._squad_ids(plan.remnawave_policy),
            },
            now=now,
        )

    def _enqueue_command(
        self,
        *,
        account: VpnAccount,
        command_type: str,
        key: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        self._session.add(
            VpnSyncCommand(
                vpn_account_id=account.id,
                command_type=command_type,
                idempotency_key=key,
                payload=payload,
                status=CommandStatus.PENDING.value,
                attempt_count=0,
                next_attempt_at=now,
            )
        )

    def _record_user_action(
        self,
        *,
        user: User,
        actor_user_id: UUID,
        action: str,
        reason: str,
        before: dict[str, Any],
    ) -> None:
        after = self._user_state(user)
        self._session.add(
            AuditLog(
                actor_user_id=actor_user_id,
                actor_type="admin",
                action=action,
                entity_type="user",
                entity_id=user.id,
                reason=reason,
                before_state=before or {},
                after_state=after,
            )
        )
        self._session.add(
            OutboxEvent(
                aggregate_type="user",
                aggregate_id=user.id,
                event_type=action,
                payload={"user_id": str(user.id), "before": before, "after": after},
                idempotency_key=f"{action}:{user.id}:{uuid7()}",
            )
        )

    def _record_family_action(
        self,
        *,
        group: FamilyGroup,
        actor_user_id: UUID,
        action: str,
        reason: str,
        payload: dict[str, Any],
    ) -> None:
        self._session.add(
            AuditLog(
                actor_user_id=actor_user_id,
                actor_type="admin",
                action=action,
                entity_type="family_group",
                entity_id=group.id,
                reason=reason,
                after_state=payload,
            )
        )
        self._session.add(
            OutboxEvent(
                aggregate_type="family_group",
                aggregate_id=group.id,
                event_type=action,
                payload={"family_group_id": str(group.id), **payload},
                idempotency_key=f"{action}:{group.id}:{uuid7()}",
            )
        )

    def _record_subscription_action(
        self,
        *,
        subscription: Subscription,
        actor_user_id: UUID,
        action: str,
        reason: str,
        before: dict[str, Any],
        extra: dict[str, Any],
    ) -> None:
        after = self._subscription_state(subscription) | extra
        self._session.add(
            AuditLog(
                actor_user_id=actor_user_id,
                actor_type="admin",
                action=action,
                entity_type="subscription",
                entity_id=subscription.id,
                reason=reason,
                before_state=before,
                after_state=after,
            )
        )
        self._session.add(
            OutboxEvent(
                aggregate_type="subscription",
                aggregate_id=subscription.id,
                event_type=action,
                payload={
                    "subscription_id": str(subscription.id),
                    "owner_user_id": str(subscription.owner_user_id),
                    **after,
                },
                idempotency_key=f"{action}:{subscription.id}:{subscription.version}",
            )
        )

    @staticmethod
    def _subscription_response(
        subscription: Subscription, plan: PlanVersion, product: Plan
    ) -> AdminSubscriptionSummary:
        return AdminSubscriptionSummary(
            id=subscription.id,
            plan_version_id=plan.id,
            plan_slug=product.slug,
            plan_name=product.name,
            status=subscription.status,
            source=subscription.source,
            starts_at=subscription.starts_at,
            current_period_ends_at=subscription.current_period_ends_at,
            device_limit=plan.device_limit,
            version=subscription.version,
        )

    @staticmethod
    def _payment_response(payment: Payment) -> AdminPaymentSummary:
        return AdminPaymentSummary(
            id=payment.id,
            user_id=payment.user_id,
            status=payment.status,
            amount_minor=payment.expected_amount_minor,
            currency=payment.currency,
            plan_price_id=payment.plan_price_id,
            created_at=payment.created_at,
            approved_at=payment.approved_at,
            version=payment.version,
        )

    async def _require_plan_for_update(self, plan_id: UUID) -> Plan:
        plan = await self._repository.plan_for_update(plan_id)
        if plan is None:
            raise ApplicationError("admin_plan_not_found", "Plan not found.", 404)
        return plan

    async def _create_plan_version(
        self,
        *,
        plan: Plan,
        version_number: int,
        device_limit: int,
        family_member_limit: int,
        traffic_limit_bytes: int | None,
        prices: list[AdminPlanPriceInput],
        now: datetime,
    ) -> PlanVersion:
        version = PlanVersion(
            id=uuid7(),
            plan_id=plan.id,
            version=version_number,
            device_limit=device_limit,
            family_member_limit=family_member_limit,
            traffic_limit_bytes=traffic_limit_bytes,
            remnawave_policy={},
            valid_from=now,
            valid_until=None,
        )
        self._repository.add(version)
        await self._session.flush()
        for price in prices:
            self._repository.add(
                PlanPrice(
                    id=uuid7(),
                    plan_version_id=version.id,
                    term_months=price.term_months,
                    duration_days=price.duration_days,
                    currency=price.currency,
                    amount_minor=price.amount_minor,
                    is_active=True,
                    valid_from=now,
                    valid_until=None,
                )
            )
        return version

    async def _plan_response(self, plan: Plan) -> AdminPlanResponse:
        versions = []
        for version in await self._repository.plan_versions(plan.id):
            prices = await self._repository.plan_prices(version.id)
            versions.append(
                AdminPlanVersionResponse(
                    id=version.id,
                    version=version.version,
                    device_limit=version.device_limit,
                    family_member_limit=version.family_member_limit,
                    traffic_limit_bytes=version.traffic_limit_bytes,
                    valid_from=version.valid_from,
                    valid_until=version.valid_until,
                    prices=[
                        AdminPlanPriceResponse(
                            id=price.id,
                            term_months=price.term_months,
                            duration_days=price.duration_days,
                            currency=price.currency,
                            amount_minor=price.amount_minor,
                            is_active=price.is_active,
                        )
                        for price in prices
                    ],
                )
            )
        return AdminPlanResponse(
            id=plan.id,
            slug=plan.slug,
            name=plan.name,
            description=plan.description,
            is_active=plan.is_active,
            sort_order=plan.sort_order,
            versions=versions,
        )

    @staticmethod
    def _family_group_response(
        group: FamilyGroup,
        owner_email: str | None,
        subscription_status: str,
        plan_name: str,
        member_count: int,
    ) -> AdminFamilyGroupResponse:
        return AdminFamilyGroupResponse(
            id=group.id,
            owner_user_id=group.owner_user_id,
            owner_email=owner_email,
            subscription_id=group.subscription_id,
            plan_name=plan_name,
            subscription_status=subscription_status,
            name=group.name,
            status=group.status,
            member_limit=group.member_limit,
            active_member_count=member_count,
            created_at=group.created_at,
        )

    def _record_plan_action(
        self,
        *,
        plan: Plan,
        actor_user_id: UUID,
        action: str,
        reason: str,
        before: dict[str, Any] | None,
        after: dict[str, Any],
    ) -> None:
        self._session.add(
            AuditLog(
                actor_user_id=actor_user_id,
                actor_type="admin",
                action=action,
                entity_type="plan",
                entity_id=plan.id,
                reason=reason,
                before_state=before or {},
                after_state=after,
            )
        )
        self._session.add(
            OutboxEvent(
                aggregate_type="plan",
                aggregate_id=plan.id,
                event_type=action,
                payload={"plan_id": str(plan.id), **after},
                idempotency_key=f"{action}:{plan.id}:{uuid7()}",
            )
        )

    @staticmethod
    def _plan_state(plan: Plan) -> dict[str, Any]:
        return {
            "name": plan.name,
            "description": plan.description,
            "sort_order": plan.sort_order,
            "is_active": plan.is_active,
        }

    @staticmethod
    def _device_response(device: Device) -> AdminDeviceResponse:
        return AdminDeviceResponse(
            id=device.id,
            user_id=device.user_id,
            vpn_account_id=device.vpn_account_id,
            slot_number=device.slot_number,
            label=device.label,
            external_hwid=device.external_hwid,
            platform=device.platform,
            status=device.status,
            first_seen_at=device.first_seen_at,
            last_seen_at=device.last_seen_at,
            created_at=device.created_at,
        )

    @staticmethod
    def _user_state(user: User) -> dict[str, Any]:
        return {
            "status": user.status,
            "blocked_at": user.blocked_at.isoformat() if user.blocked_at else None,
            "blocked_reason": user.blocked_reason,
        }

    @staticmethod
    def _subscription_state(subscription: Subscription) -> dict[str, Any]:
        return {
            "status": subscription.status,
            "plan_version_id": str(subscription.plan_version_id),
            "current_period_ends_at": subscription.current_period_ends_at.isoformat()
            if subscription.current_period_ends_at
            else None,
            "version": subscription.version,
        }

    @staticmethod
    def _plan_snapshot(plan: PlanVersion) -> dict[str, Any]:
        return {
            "plan_version_id": str(plan.id),
            "version": plan.version,
            "device_limit": plan.device_limit,
            "family_member_limit": plan.family_member_limit,
            "traffic_limit_bytes": plan.traffic_limit_bytes,
            "remnawave_policy": plan.remnawave_policy,
        }

    @staticmethod
    def _squad_ids(policy: dict[str, Any]) -> list[str]:
        values = policy.get("internal_squad_ids", [])
        if not isinstance(values, list):
            raise ApplicationError(
                "admin_plan_policy_invalid", "Plan Remnawave policy is invalid.", 409
            )
        try:
            return [str(UUID(str(value))) for value in values]
        except ValueError as exc:
            raise ApplicationError(
                "admin_plan_policy_invalid", "Plan squad ID is invalid.", 409
            ) from exc
