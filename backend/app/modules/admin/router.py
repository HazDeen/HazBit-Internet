from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.features import FeatureKey
from app.modules.admin.dependencies import AdminServiceDependency
from app.modules.admin.schemas import (
    AdminDashboardResponse,
    AdminDevicePage,
    AdminFamilyActionRequest,
    AdminFamilyGroupPage,
    AdminFamilyGroupResponse,
    AdminFeatureResponse,
    AdminNodeActionRequest,
    AdminPaymentPage,
    AdminPlanResponse,
    AdminRemnawaveNodeResponse,
    AdminSettingsResponse,
    AdminSubscriptionPage,
    AdminSubscriptionSummary,
    AdminUserDetail,
    AdminUserPage,
    ArchiveAdminPlanRequest,
    BlockUserRequest,
    ChangePlanRequest,
    CreateAdminPlanRequest,
    CreateAdminPlanVersionRequest,
    ExtendSubscriptionRequest,
    UpdateAdminFeatureRequest,
    UpdateAdminPlanRequest,
)
from app.modules.auth.dependencies import require_permissions, require_roles
from app.modules.auth.enums import Permission, Role
from app.modules.auth.service import Principal

AdminPrincipal = Annotated[
    Principal,
    Depends(require_roles(Role.ADMIN, Role.SUPER_ADMIN)),
]
SuperAdminPrincipal = Annotated[Principal, Depends(require_roles(Role.SUPER_ADMIN))]
DashboardPrincipal = Annotated[Principal, Depends(require_permissions(Permission.DASHBOARD_READ))]
UsersReadPrincipal = Annotated[Principal, Depends(require_permissions(Permission.USERS_READ))]
UsersManagePrincipal = Annotated[Principal, Depends(require_permissions(Permission.USERS_MANAGE))]
SubscriptionsReadPrincipal = Annotated[
    Principal, Depends(require_permissions(Permission.SUBSCRIPTIONS_READ))
]
SubscriptionsManagePrincipal = Annotated[
    Principal, Depends(require_permissions(Permission.SUBSCRIPTIONS_MANAGE))
]
PaymentsReadPrincipal = Annotated[Principal, Depends(require_permissions(Permission.PAYMENTS_READ))]
PlansPrincipal = Annotated[Principal, Depends(require_permissions(Permission.PLANS_MANAGE))]
FamiliesPrincipal = Annotated[Principal, Depends(require_permissions(Permission.FAMILIES_MANAGE))]
VpnReadPrincipal = Annotated[Principal, Depends(require_permissions(Permission.VPN_READ))]
NodeManagePrincipal = Annotated[
    Principal, Depends(require_permissions(Permission.VPN_NODES_MANAGE))
]
SettingsReadPrincipal = Annotated[
    Principal, Depends(require_permissions(Permission.SETTINGS_READ))
]
UserStatusFilter = Literal["active", "blocked", "pending_deletion", "deleted"]
SubscriptionStatusFilter = Literal[
    "pending", "active", "grace_period", "suspended", "expired", "cancelled"
]


def create_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])

    @router.get("/dashboard", response_model=AdminDashboardResponse)
    async def dashboard(
        principal: DashboardPrincipal, service: AdminServiceDependency
    ) -> AdminDashboardResponse:
        del principal
        return await service.dashboard()

    @router.get("/users", response_model=AdminUserPage)
    async def users(
        principal: UsersReadPrincipal,
        service: AdminServiceDependency,
        search: Annotated[str | None, Query(max_length=200)] = None,
        user_status: Annotated[UserStatusFilter | None, Query(alias="status")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> AdminUserPage:
        del principal
        return await service.users(search=search, status=user_status, limit=limit, offset=offset)

    @router.get("/users/{user_id}", response_model=AdminUserDetail)
    async def user(
        user_id: UUID,
        principal: UsersReadPrincipal,
        service: AdminServiceDependency,
    ) -> AdminUserDetail:
        del principal
        return await service.user(user_id)

    @router.post("/users/{user_id}/block", response_model=AdminUserDetail)
    async def block_user(
        user_id: UUID,
        payload: BlockUserRequest,
        principal: UsersManagePrincipal,
        service: AdminServiceDependency,
    ) -> AdminUserDetail:
        return await service.block_user(
            user_id=user_id, actor_user_id=principal.user_id, reason=payload.reason
        )

    @router.post("/users/{user_id}/unblock", response_model=AdminUserDetail)
    async def unblock_user(
        user_id: UUID,
        payload: BlockUserRequest,
        principal: UsersManagePrincipal,
        service: AdminServiceDependency,
    ) -> AdminUserDetail:
        return await service.unblock_user(
            user_id=user_id, actor_user_id=principal.user_id, reason=payload.reason
        )

    @router.post(
        "/users/{user_id}/subscription/extend",
        response_model=AdminSubscriptionSummary,
    )
    async def extend_subscription(
        user_id: UUID,
        payload: ExtendSubscriptionRequest,
        principal: SubscriptionsManagePrincipal,
        service: AdminServiceDependency,
    ) -> AdminSubscriptionSummary:
        return await service.extend_subscription(
            user_id=user_id,
            actor_user_id=principal.user_id,
            days=payload.days,
            reason=payload.reason,
        )

    @router.patch(
        "/users/{user_id}/subscription/plan",
        response_model=AdminSubscriptionSummary,
    )
    async def change_plan(
        user_id: UUID,
        payload: ChangePlanRequest,
        principal: SubscriptionsManagePrincipal,
        service: AdminServiceDependency,
    ) -> AdminSubscriptionSummary:
        return await service.change_plan(
            user_id=user_id,
            actor_user_id=principal.user_id,
            plan_version_id=payload.plan_version_id,
            reason=payload.reason,
        )

    @router.get("/users/{user_id}/devices", response_model=AdminDevicePage)
    async def user_devices(
        user_id: UUID,
        principal: VpnReadPrincipal,
        service: AdminServiceDependency,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> AdminDevicePage:
        del principal
        return await service.devices(user_id=user_id, limit=limit, offset=offset)

    @router.get("/subscriptions", response_model=AdminSubscriptionPage)
    async def subscriptions(
        principal: SubscriptionsReadPrincipal,
        service: AdminServiceDependency,
        subscription_status: Annotated[
            SubscriptionStatusFilter | None, Query(alias="status")
        ] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> AdminSubscriptionPage:
        del principal
        return await service.subscriptions(status=subscription_status, limit=limit, offset=offset)

    @router.get("/payments", response_model=AdminPaymentPage)
    async def payments(
        principal: PaymentsReadPrincipal,
        service: AdminServiceDependency,
        payment_status: Annotated[str | None, Query(alias="status", max_length=40)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> AdminPaymentPage:
        del principal
        return await service.payments(status=payment_status, limit=limit, offset=offset)

    @router.get("/plans", response_model=list[AdminPlanResponse])
    async def plans(
        principal: PlansPrincipal, service: AdminServiceDependency
    ) -> list[AdminPlanResponse]:
        del principal
        return await service.plans()

    @router.post("/plans", response_model=AdminPlanResponse, status_code=201)
    async def create_plan(
        payload: CreateAdminPlanRequest,
        principal: PlansPrincipal,
        service: AdminServiceDependency,
    ) -> AdminPlanResponse:
        return await service.create_plan(payload=payload, actor_user_id=principal.user_id)

    @router.patch("/plans/{plan_id}", response_model=AdminPlanResponse)
    async def update_plan(
        plan_id: UUID,
        payload: UpdateAdminPlanRequest,
        principal: PlansPrincipal,
        service: AdminServiceDependency,
    ) -> AdminPlanResponse:
        return await service.update_plan(
            plan_id=plan_id, payload=payload, actor_user_id=principal.user_id
        )

    @router.post("/plans/{plan_id}/versions", response_model=AdminPlanResponse, status_code=201)
    async def create_plan_version(
        plan_id: UUID,
        payload: CreateAdminPlanVersionRequest,
        principal: PlansPrincipal,
        service: AdminServiceDependency,
    ) -> AdminPlanResponse:
        return await service.create_plan_version(
            plan_id=plan_id, payload=payload, actor_user_id=principal.user_id
        )

    @router.delete("/plans/{plan_id}", response_model=AdminPlanResponse)
    async def archive_plan(
        plan_id: UUID,
        payload: ArchiveAdminPlanRequest,
        principal: PlansPrincipal,
        service: AdminServiceDependency,
    ) -> AdminPlanResponse:
        return await service.archive_plan(
            plan_id=plan_id, payload=payload, actor_user_id=principal.user_id
        )

    @router.get("/family-groups", response_model=AdminFamilyGroupPage)
    async def family_groups(
        principal: FamiliesPrincipal,
        service: AdminServiceDependency,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> AdminFamilyGroupPage:
        del principal
        return await service.family_groups(limit=limit, offset=offset)

    @router.get("/family-groups/{group_id}", response_model=AdminFamilyGroupResponse)
    async def family_group(
        group_id: UUID,
        principal: FamiliesPrincipal,
        service: AdminServiceDependency,
    ) -> AdminFamilyGroupResponse:
        del principal
        return await service.family_group(group_id)

    @router.delete(
        "/family-groups/{group_id}/members/{member_user_id}",
        response_model=AdminFamilyGroupResponse,
    )
    async def remove_family_member(
        group_id: UUID,
        member_user_id: UUID,
        payload: AdminFamilyActionRequest,
        principal: FamiliesPrincipal,
        service: AdminServiceDependency,
    ) -> AdminFamilyGroupResponse:
        return await service.remove_family_member(
            group_id=group_id,
            member_user_id=member_user_id,
            actor_user_id=principal.user_id,
            payload=payload,
        )

    @router.delete(
        "/family-groups/{group_id}/invitations/{invitation_id}",
        response_model=AdminFamilyGroupResponse,
    )
    async def revoke_family_invitation(
        group_id: UUID,
        invitation_id: UUID,
        payload: AdminFamilyActionRequest,
        principal: FamiliesPrincipal,
        service: AdminServiceDependency,
    ) -> AdminFamilyGroupResponse:
        return await service.revoke_family_invitation(
            group_id=group_id,
            invitation_id=invitation_id,
            actor_user_id=principal.user_id,
            payload=payload,
        )

    @router.get("/vpn-devices", response_model=AdminDevicePage)
    async def vpn_devices(
        principal: VpnReadPrincipal,
        service: AdminServiceDependency,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> AdminDevicePage:
        del principal
        return await service.devices(user_id=None, limit=limit, offset=offset)

    @router.get("/settings", response_model=AdminSettingsResponse)
    async def settings(
        principal: SettingsReadPrincipal, service: AdminServiceDependency
    ) -> AdminSettingsResponse:
        del principal
        return await service.settings()

    @router.patch("/settings/features/{feature}", response_model=AdminFeatureResponse)
    async def update_feature(
        feature: FeatureKey,
        payload: UpdateAdminFeatureRequest,
        principal: SuperAdminPrincipal,
        service: AdminServiceDependency,
    ) -> AdminFeatureResponse:
        return await service.update_feature(
            feature=feature,
            enabled=payload.enabled,
            actor_user_id=principal.user_id,
            reason=payload.reason,
        )

    @router.get("/remnawave/nodes", response_model=list[AdminRemnawaveNodeResponse])
    async def remnawave_nodes(
        principal: VpnReadPrincipal,
        service: AdminServiceDependency,
    ) -> list[AdminRemnawaveNodeResponse]:
        del principal
        return await service.remnawave_nodes()

    @router.post(
        "/remnawave/nodes/{node_uuid}/disable",
        response_model=AdminRemnawaveNodeResponse,
    )
    async def disable_remnawave_node(
        node_uuid: UUID,
        payload: AdminNodeActionRequest,
        principal: NodeManagePrincipal,
        service: AdminServiceDependency,
    ) -> AdminRemnawaveNodeResponse:
        return await service.set_remnawave_node_state(
            node_uuid=node_uuid,
            enabled=False,
            actor_user_id=principal.user_id,
            reason=payload.reason,
        )

    @router.post(
        "/remnawave/nodes/{node_uuid}/enable",
        response_model=AdminRemnawaveNodeResponse,
    )
    async def enable_remnawave_node(
        node_uuid: UUID,
        payload: AdminNodeActionRequest,
        principal: NodeManagePrincipal,
        service: AdminServiceDependency,
    ) -> AdminRemnawaveNodeResponse:
        return await service.set_remnawave_node_state(
            node_uuid=node_uuid,
            enabled=True,
            actor_user_id=principal.user_id,
            reason=payload.reason,
        )

    return router
