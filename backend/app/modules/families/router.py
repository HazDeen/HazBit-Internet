from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response, status

from app.modules.auth.dependencies import PrincipalDependency
from app.modules.families.dependencies import FamilyServiceDependency
from app.modules.families.schemas import (
    AcceptFamilyInvitationRequest,
    CreateFamilyGroupRequest,
    CreateFamilyInvitationRequest,
    FamilyGroupResponse,
    FamilyInvitationInboxResponse,
    FamilyInvitationResponse,
    RemoveFamilyMemberRequest,
    RenameFamilyGroupRequest,
)
from app.modules.families.service import FamilyClientContext


def create_family_router() -> APIRouter:
    router = APIRouter(prefix="/family", tags=["family"])

    @router.post("/groups", response_model=FamilyGroupResponse, status_code=201)
    async def create_group(
        payload: CreateFamilyGroupRequest,
        request: Request,
        principal: PrincipalDependency,
        service: FamilyServiceDependency,
        device_fingerprint: Annotated[
            str | None, Header(alias="X-Device-Fingerprint", min_length=8, max_length=512)
        ] = None,
    ) -> FamilyGroupResponse:
        return await service.create_group(
            owner_user_id=principal.user_id,
            subscription_id=payload.subscription_id,
            name=payload.name,
            client=_context(request, device_fingerprint),
        )

    @router.get("/group", response_model=FamilyGroupResponse)
    async def my_group(
        principal: PrincipalDependency, service: FamilyServiceDependency
    ) -> FamilyGroupResponse:
        return await service.my_group(principal.user_id)

    @router.patch("/groups/{group_id}", response_model=FamilyGroupResponse)
    async def rename_group(
        group_id: UUID,
        payload: RenameFamilyGroupRequest,
        request: Request,
        principal: PrincipalDependency,
        service: FamilyServiceDependency,
        device_fingerprint: Annotated[
            str | None, Header(alias="X-Device-Fingerprint", min_length=8, max_length=512)
        ] = None,
    ) -> FamilyGroupResponse:
        return await service.rename_group(
            group_id=group_id,
            owner_user_id=principal.user_id,
            name=payload.name,
            client=_context(request, device_fingerprint),
        )

    @router.post(
        "/groups/{group_id}/invitations",
        response_model=FamilyInvitationResponse,
        status_code=201,
    )
    async def invite(
        group_id: UUID,
        payload: CreateFamilyInvitationRequest,
        request: Request,
        principal: PrincipalDependency,
        service: FamilyServiceDependency,
        device_fingerprint: Annotated[
            str | None, Header(alias="X-Device-Fingerprint", min_length=8, max_length=512)
        ] = None,
    ) -> FamilyInvitationResponse:
        return await service.invite(
            group_id=group_id,
            owner_user_id=principal.user_id,
            invited_user_id=payload.invited_user_id,
            invited_email=str(payload.invited_email) if payload.invited_email else None,
            client=_context(request, device_fingerprint),
        )

    @router.get("/invitations", response_model=FamilyInvitationInboxResponse)
    async def invitation_inbox(
        principal: PrincipalDependency, service: FamilyServiceDependency
    ) -> FamilyInvitationInboxResponse:
        return await service.inbox(principal.user_id)

    @router.post("/invitations/accept", response_model=FamilyGroupResponse)
    async def accept_invitation(
        payload: AcceptFamilyInvitationRequest,
        request: Request,
        principal: PrincipalDependency,
        service: FamilyServiceDependency,
        device_fingerprint: Annotated[
            str | None, Header(alias="X-Device-Fingerprint", min_length=8, max_length=512)
        ] = None,
    ) -> FamilyGroupResponse:
        return await service.accept(
            user_id=principal.user_id,
            token=payload.token,
            client=_context(request, device_fingerprint),
        )

    @router.post("/invitations/decline", response_model=FamilyInvitationResponse)
    async def decline_invitation(
        payload: AcceptFamilyInvitationRequest,
        request: Request,
        principal: PrincipalDependency,
        service: FamilyServiceDependency,
        device_fingerprint: Annotated[
            str | None, Header(alias="X-Device-Fingerprint", min_length=8, max_length=512)
        ] = None,
    ) -> FamilyInvitationResponse:
        return await service.decline(
            user_id=principal.user_id,
            token=payload.token,
            client=_context(request, device_fingerprint),
        )

    @router.delete(
        "/groups/{group_id}/invitations/{invitation_id}",
        response_model=FamilyInvitationResponse,
    )
    async def revoke_invitation(
        group_id: UUID,
        invitation_id: UUID,
        request: Request,
        principal: PrincipalDependency,
        service: FamilyServiceDependency,
        device_fingerprint: Annotated[
            str | None, Header(alias="X-Device-Fingerprint", min_length=8, max_length=512)
        ] = None,
    ) -> FamilyInvitationResponse:
        return await service.revoke_invitation(
            group_id=group_id,
            invitation_id=invitation_id,
            owner_user_id=principal.user_id,
            client=_context(request, device_fingerprint),
        )

    @router.delete("/members/me", status_code=status.HTTP_204_NO_CONTENT)
    async def leave_group(
        request: Request,
        principal: PrincipalDependency,
        service: FamilyServiceDependency,
        device_fingerprint: Annotated[
            str | None, Header(alias="X-Device-Fingerprint", min_length=8, max_length=512)
        ] = None,
    ) -> Response:
        await service.leave(user_id=principal.user_id, client=_context(request, device_fingerprint))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.delete(
        "/groups/{group_id}/members/{member_user_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def remove_member(
        group_id: UUID,
        member_user_id: UUID,
        payload: RemoveFamilyMemberRequest,
        request: Request,
        principal: PrincipalDependency,
        service: FamilyServiceDependency,
        device_fingerprint: Annotated[
            str | None, Header(alias="X-Device-Fingerprint", min_length=8, max_length=512)
        ] = None,
    ) -> Response:
        await service.remove_member(
            group_id=group_id,
            member_user_id=member_user_id,
            owner_user_id=principal.user_id,
            reason=payload.reason,
            client=_context(request, device_fingerprint),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _context(request: Request, fingerprint: str | None) -> FamilyClientContext:
    user_agent = request.headers.get("user-agent")
    return FamilyClientContext(
        ip_address=request.client.host if request.client is not None else "0.0.0.0",  # noqa: S104
        device_fingerprint=fingerprint,
        user_agent=user_agent[:1024] if user_agent else None,
        request_id=getattr(request.state, "request_id", None),
    )
