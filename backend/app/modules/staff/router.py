from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.modules.auth.dependencies import PrincipalDependency, require_permissions
from app.modules.auth.enums import Permission
from app.modules.auth.service import Principal
from app.modules.staff.dependencies import StaffServiceDependency
from app.modules.staff.schemas import (
    AcceptStaffInvitationRequest,
    CreateStaffInvitationRequest,
    StaffDirectoryResponse,
    StaffInvitationResponse,
    StaffMemberResponse,
    UpdateStaffAccessRequest,
)

StaffManager = Annotated[Principal, Depends(require_permissions(Permission.STAFF_MANAGE))]


def create_staff_router() -> APIRouter:
    router = APIRouter(prefix="/admin/staff", tags=["staff"])

    @router.get("", response_model=StaffDirectoryResponse)
    async def directory(
        principal: StaffManager, service: StaffServiceDependency
    ) -> StaffDirectoryResponse:
        del principal
        return await service.directory()

    @router.post("/invitations", response_model=StaffInvitationResponse, status_code=201)
    async def invite(
        payload: CreateStaffInvitationRequest,
        principal: StaffManager,
        service: StaffServiceDependency,
    ) -> StaffInvitationResponse:
        return await service.invite(payload=payload, actor_user_id=principal.user_id)

    @router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def revoke_invitation(
        invitation_id: UUID, principal: StaffManager, service: StaffServiceDependency
    ) -> Response:
        await service.revoke_invitation(invitation_id, actor_user_id=principal.user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.patch("/{user_id}", response_model=StaffMemberResponse)
    async def update(
        user_id: UUID,
        payload: UpdateStaffAccessRequest,
        principal: StaffManager,
        service: StaffServiceDependency,
    ) -> StaffMemberResponse:
        return await service.update(
            user_id=user_id, payload=payload, actor_user_id=principal.user_id
        )

    @router.post("/invitations/accept", response_model=StaffMemberResponse)
    async def accept(
        payload: AcceptStaffInvitationRequest,
        principal: PrincipalDependency,
        service: StaffServiceDependency,
    ) -> StaffMemberResponse:
        return await service.accept(payload=payload, actor_user_id=principal.user_id)

    return router
