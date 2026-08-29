from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status

from app.core.errors import ApplicationError
from app.modules.auth.dependencies import PrincipalDependency, require_permissions
from app.modules.auth.enums import Permission, Role
from app.modules.auth.service import Principal
from app.modules.support.dependencies import SupportServiceDependency
from app.modules.support.schemas import (
    AdminReplyRequest,
    CreateTicketRequest,
    SendTicketMessageRequest,
    TicketDetailResponse,
    TicketMessagePage,
    TicketMessageResponse,
    TicketResponse,
    UpdateTicketRequest,
)
from app.modules.support.service import SupportClientContext

StaffPrincipal = Annotated[
    Principal,
    Depends(require_permissions(Permission.TICKETS_READ)),
]
ReplyPrincipal = Annotated[Principal, Depends(require_permissions(Permission.TICKETS_REPLY))]
ManagePrincipal = Annotated[Principal, Depends(require_permissions(Permission.TICKETS_MANAGE))]
TicketStatusFilter = Literal["open", "in_progress", "waiting_user", "closed"]


def create_support_router() -> APIRouter:
    router = APIRouter(tags=["support"])

    @router.post(
        "/tickets",
        response_model=TicketDetailResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_ticket(
        payload: CreateTicketRequest,
        request: Request,
        principal: PrincipalDependency,
        service: SupportServiceDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
        ],
    ) -> TicketDetailResponse:
        return await service.create_ticket(
            user_id=principal.user_id,
            payload=payload,
            idempotency_key=idempotency_key,
            client=_client_context(request),
        )

    @router.get("/tickets", response_model=list[TicketResponse])
    async def list_tickets(
        principal: PrincipalDependency,
        service: SupportServiceDependency,
        ticket_status: Annotated[TicketStatusFilter | None, Query(alias="status")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> list[TicketResponse]:
        return await service.list_user_tickets(
            user_id=principal.user_id, status=ticket_status, limit=limit
        )

    @router.get("/tickets/{ticket_id}", response_model=TicketDetailResponse)
    async def get_ticket(
        ticket_id: UUID,
        principal: PrincipalDependency,
        service: SupportServiceDependency,
    ) -> TicketDetailResponse:
        return await service.user_ticket(user_id=principal.user_id, ticket_id=ticket_id)

    @router.get("/tickets/{ticket_id}/messages", response_model=TicketMessagePage)
    async def get_messages(
        ticket_id: UUID,
        principal: PrincipalDependency,
        service: SupportServiceDependency,
        after: Annotated[UUID | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> TicketMessagePage:
        return await service.user_messages(
            user_id=principal.user_id,
            ticket_id=ticket_id,
            after_message_id=after,
            limit=limit,
        )

    @router.post(
        "/tickets/{ticket_id}/messages",
        response_model=TicketMessageResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def send_message(
        ticket_id: UUID,
        payload: SendTicketMessageRequest,
        request: Request,
        principal: PrincipalDependency,
        service: SupportServiceDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
        ],
    ) -> TicketMessageResponse:
        return await service.send_user_message(
            user_id=principal.user_id,
            ticket_id=ticket_id,
            body=payload.body,
            idempotency_key=idempotency_key,
            client=_client_context(request),
        )

    @router.get("/admin/tickets", response_model=list[TicketResponse])
    async def admin_queue(
        principal: StaffPrincipal,
        service: SupportServiceDependency,
        ticket_status: Annotated[TicketStatusFilter | None, Query(alias="status")] = None,
        assigned_to_me: Annotated[bool, Query()] = False,
        unassigned_only: Annotated[bool, Query()] = False,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> list[TicketResponse]:
        if assigned_to_me and unassigned_only:
            raise ApplicationError(
                "ticket_queue_filter_conflict",
                "assigned_to_me and unassigned_only cannot be combined.",
                422,
            )
        return await service.admin_queue(
            status=ticket_status,
            assigned_to_user_id=principal.user_id if assigned_to_me else None,
            unassigned_only=unassigned_only,
            limit=limit,
        )

    @router.get("/admin/tickets/{ticket_id}", response_model=TicketDetailResponse)
    async def admin_ticket(
        ticket_id: UUID,
        principal: StaffPrincipal,
        service: SupportServiceDependency,
    ) -> TicketDetailResponse:
        del principal
        return await service.admin_ticket(ticket_id)

    @router.get("/admin/tickets/{ticket_id}/messages", response_model=TicketMessagePage)
    async def admin_messages(
        ticket_id: UUID,
        principal: StaffPrincipal,
        service: SupportServiceDependency,
        after: Annotated[UUID | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> TicketMessagePage:
        del principal
        return await service.admin_messages(
            ticket_id=ticket_id, after_message_id=after, limit=limit
        )

    @router.post(
        "/admin/tickets/{ticket_id}/messages",
        response_model=TicketMessageResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def admin_reply(
        ticket_id: UUID,
        payload: AdminReplyRequest,
        request: Request,
        principal: ReplyPrincipal,
        service: SupportServiceDependency,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
        ],
    ) -> TicketMessageResponse:
        return await service.admin_reply(
            staff_user_id=principal.user_id,
            actor_type=_staff_actor_type(principal),
            ticket_id=ticket_id,
            payload=payload,
            idempotency_key=idempotency_key,
            client=_client_context(request),
        )

    @router.patch("/admin/tickets/{ticket_id}", response_model=TicketResponse)
    async def update_ticket(
        ticket_id: UUID,
        payload: UpdateTicketRequest,
        request: Request,
        principal: ManagePrincipal,
        service: SupportServiceDependency,
    ) -> TicketResponse:
        return await service.update_ticket(
            ticket_id=ticket_id,
            staff_user_id=principal.user_id,
            actor_type=_staff_actor_type(principal),
            payload=payload,
            client=_client_context(request),
        )

    return router


def _staff_actor_type(principal: Principal) -> str:
    return "support" if Role.SUPPORT in principal.roles else "admin"


def _client_context(request: Request) -> SupportClientContext:
    ip_address = request.client.host if request.client is not None else "0.0.0.0"  # noqa: S104
    user_agent = request.headers.get("user-agent")
    return SupportClientContext(
        ip_address=ip_address,
        user_agent=user_agent[:1024] if user_agent else None,
        request_id=getattr(request.state, "request_id", None),
    )
