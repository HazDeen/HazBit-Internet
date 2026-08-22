from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import SupportSettings
from app.core.errors import ApplicationError
from app.modules.auth.models import AuditLog
from app.modules.auth.rate_limit import RateLimit, RateLimiter
from app.modules.payments.models import OutboxEvent
from app.modules.support.enums import TicketMessageType, TicketStatus
from app.modules.support.models import IdempotencyRecord, Ticket, TicketMessage
from app.modules.support.repository import SupportRepository
from app.modules.support.schemas import (
    AdminReplyRequest,
    CreateTicketRequest,
    TicketDetailResponse,
    TicketMessagePage,
    TicketMessageResponse,
    TicketResponse,
    UpdateTicketRequest,
)


@dataclass(frozen=True, slots=True)
class SupportClientContext:
    ip_address: str
    user_agent: str | None
    request_id: UUID | None


class SupportService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: SupportSettings,
        rate_limiter: RateLimiter,
    ) -> None:
        self._session = session
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._repository = SupportRepository(session)

    async def create_ticket(
        self,
        *,
        user_id: UUID,
        payload: CreateTicketRequest,
        idempotency_key: str,
        client: SupportClientContext,
    ) -> TicketDetailResponse:
        await self._rate_limiter.enforce(
            RateLimit("support_ticket_create", self._settings.create_rate_limit_per_day, 86400),
            str(user_id),
        )
        now = datetime.now(UTC)
        scope = f"support:create:{user_id}"
        request_hash = self._request_hash(payload.model_dump(mode="json"))
        async with self._session.begin():
            await self._repository.serialize_key(f"idempotency:{scope}:{idempotency_key}")
            existing = await self._idempotent_resource(
                scope=scope,
                key=idempotency_key,
                request_hash=request_hash,
                resource_type="ticket",
                now=now,
            )
            if existing is not None:
                ticket = await self._repository.ticket_by_resource(existing)
                if ticket is None:
                    raise RuntimeError("idempotency record references no ticket")
                messages = await self._repository.messages(
                    ticket.id,
                    include_internal=False,
                    after_message_id=None,
                    limit=self._settings.initial_message_limit,
                )
                return self._detail(ticket, messages)

            ticket = Ticket(
                user_id=user_id,
                assigned_to_user_id=None,
                subject=payload.subject,
                category=payload.category,
                priority="normal",
                status=TicketStatus.OPEN.value,
                last_message_at=now,
                closed_at=None,
                version=1,
                created_at=now,
                updated_at=now,
            )
            self._session.add(ticket)
            await self._session.flush()
            message = TicketMessage(
                ticket_id=ticket.id,
                sender_user_id=user_id,
                message_type=TicketMessageType.MESSAGE.value,
                body=payload.message,
                created_at=now,
            )
            self._session.add(message)
            await self._session.flush()
            self._session.add(
                IdempotencyRecord(
                    scope=scope,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_status=201,
                    resource_type="ticket",
                    resource_id=ticket.id,
                    expires_at=now + timedelta(hours=self._settings.idempotency_ttl_hours),
                )
            )
            self._event(
                ticket=ticket,
                event_type="support.ticket.created",
                key=f"support-ticket-created:{ticket.id}",
                payload={
                    "ticket_id": str(ticket.id),
                    "public_number": ticket.public_number,
                    "user_id": str(user_id),
                    "category": ticket.category,
                    "priority": ticket.priority,
                },
            )
            self._audit(
                actor_user_id=user_id,
                actor_type="user",
                action="support.ticket_created",
                ticket=ticket,
                client=client,
                after={"status": ticket.status, "message_id": str(message.id)},
            )
            return self._detail(ticket, [message])

    async def list_user_tickets(
        self, *, user_id: UUID, status: str | None, limit: int
    ) -> list[TicketResponse]:
        return [
            self._ticket_response(ticket)
            for ticket in await self._repository.user_tickets(user_id, status=status, limit=limit)
        ]

    async def user_ticket(self, *, user_id: UUID, ticket_id: UUID) -> TicketDetailResponse:
        ticket = await self._repository.ticket_for_user(ticket_id, user_id)
        if ticket is None:
            raise ApplicationError("ticket_not_found", "Ticket not found.", 404)
        messages = await self._repository.messages(
            ticket.id,
            include_internal=False,
            after_message_id=None,
            limit=self._settings.initial_message_limit,
        )
        return self._detail(ticket, messages)

    async def user_messages(
        self,
        *,
        user_id: UUID,
        ticket_id: UUID,
        after_message_id: UUID | None,
        limit: int,
    ) -> TicketMessagePage:
        ticket = await self._repository.ticket_for_user(ticket_id, user_id)
        if ticket is None:
            raise ApplicationError("ticket_not_found", "Ticket not found.", 404)
        return await self._message_page(
            ticket_id=ticket.id,
            include_internal=False,
            after_message_id=after_message_id,
            limit=limit,
        )

    async def send_user_message(
        self,
        *,
        user_id: UUID,
        ticket_id: UUID,
        body: str,
        idempotency_key: str,
        client: SupportClientContext,
    ) -> TicketMessageResponse:
        await self._rate_limiter.enforce(
            RateLimit("support_ticket_message", self._settings.message_rate_limit_per_hour, 3600),
            str(user_id),
        )
        return await self._send_message(
            actor_user_id=user_id,
            actor_type="user",
            ticket_id=ticket_id,
            body=body,
            message_type=TicketMessageType.MESSAGE.value,
            status_after=None,
            idempotency_key=idempotency_key,
            client=client,
            require_owner=True,
        )

    async def admin_queue(
        self,
        *,
        status: str | None,
        assigned_to_user_id: UUID | None,
        unassigned_only: bool,
        limit: int,
    ) -> list[TicketResponse]:
        return [
            self._ticket_response(ticket)
            for ticket in await self._repository.admin_queue(
                status=status,
                assigned_to_user_id=assigned_to_user_id,
                unassigned_only=unassigned_only,
                limit=limit,
            )
        ]

    async def admin_ticket(self, ticket_id: UUID) -> TicketDetailResponse:
        ticket = await self._repository.ticket(ticket_id)
        if ticket is None:
            raise ApplicationError("ticket_not_found", "Ticket not found.", 404)
        messages = await self._repository.messages(
            ticket.id,
            include_internal=True,
            after_message_id=None,
            limit=self._settings.initial_message_limit,
        )
        return self._detail(ticket, messages)

    async def admin_messages(
        self,
        *,
        ticket_id: UUID,
        after_message_id: UUID | None,
        limit: int,
    ) -> TicketMessagePage:
        if await self._repository.ticket(ticket_id) is None:
            raise ApplicationError("ticket_not_found", "Ticket not found.", 404)
        return await self._message_page(
            ticket_id=ticket_id,
            include_internal=True,
            after_message_id=after_message_id,
            limit=limit,
        )

    async def admin_reply(
        self,
        *,
        staff_user_id: UUID,
        actor_type: str,
        ticket_id: UUID,
        payload: AdminReplyRequest,
        idempotency_key: str,
        client: SupportClientContext,
    ) -> TicketMessageResponse:
        status_after = payload.status_after
        if payload.message_type == TicketMessageType.MESSAGE.value and status_after is None:
            status_after = TicketStatus.WAITING_USER.value
        return await self._send_message(
            actor_user_id=staff_user_id,
            actor_type=actor_type,
            ticket_id=ticket_id,
            body=payload.body,
            message_type=payload.message_type,
            status_after=status_after,
            idempotency_key=idempotency_key,
            client=client,
            require_owner=False,
        )

    async def update_ticket(
        self,
        *,
        ticket_id: UUID,
        staff_user_id: UUID,
        actor_type: str,
        payload: UpdateTicketRequest,
        client: SupportClientContext,
    ) -> TicketResponse:
        now = datetime.now(UTC)
        async with self._session.begin():
            ticket = await self._repository.ticket(ticket_id, for_update=True)
            if ticket is None:
                raise ApplicationError("ticket_not_found", "Ticket not found.", 404)
            if ticket.version != payload.expected_version:
                raise ApplicationError(
                    "ticket_version_conflict",
                    "Ticket was changed by another operator. Refresh and try again.",
                    409,
                )
            before = self._mutable_state(ticket)
            if "status" in payload.model_fields_set and payload.status is not None:
                self._set_status(ticket, payload.status, now)
            if "priority" in payload.model_fields_set and payload.priority is not None:
                ticket.priority = payload.priority
            if "assigned_to_user_id" in payload.model_fields_set:
                if payload.assigned_to_user_id is not None:
                    await self._require_staff_assignee(payload.assigned_to_user_id)
                ticket.assigned_to_user_id = payload.assigned_to_user_id
            after = self._mutable_state(ticket)
            if after == before:
                return self._ticket_response(ticket)
            ticket.version += 1
            ticket.updated_at = now
            if before["status"] != after["status"]:
                self._session.add(
                    TicketMessage(
                        ticket_id=ticket.id,
                        sender_user_id=None,
                        message_type=TicketMessageType.SYSTEM.value,
                        body=f"Ticket status changed: {before['status']} → {after['status']}.",
                        created_at=now,
                    )
                )
            self._event(
                ticket=ticket,
                event_type="support.ticket.updated",
                key=f"support-ticket-updated:{ticket.id}:{ticket.version}",
                payload={
                    "ticket_id": str(ticket.id),
                    "user_id": str(ticket.user_id),
                    "before": before,
                    "after": after,
                },
            )
            self._audit(
                actor_user_id=staff_user_id,
                actor_type=actor_type,
                action="support.ticket_updated",
                ticket=ticket,
                client=client,
                before=before,
                after=after,
                reason=payload.reason,
            )
            await self._session.flush()
            return self._ticket_response(ticket)

    async def _send_message(
        self,
        *,
        actor_user_id: UUID,
        actor_type: str,
        ticket_id: UUID,
        body: str,
        message_type: str,
        status_after: str | None,
        idempotency_key: str,
        client: SupportClientContext,
        require_owner: bool,
    ) -> TicketMessageResponse:
        now = datetime.now(UTC)
        scope = f"support:message:{ticket_id}:{actor_user_id}"
        request_hash = self._request_hash(
            {"body": body, "message_type": message_type, "status_after": status_after}
        )
        async with self._session.begin():
            await self._repository.serialize_key(f"idempotency:{scope}:{idempotency_key}")
            existing = await self._idempotent_resource(
                scope=scope,
                key=idempotency_key,
                request_hash=request_hash,
                resource_type="ticket_message",
                now=now,
            )
            if existing is not None:
                message = await self._repository.message_by_resource(existing)
                if message is None:
                    raise RuntimeError("idempotency record references no ticket message")
                return self._message_response(message)

            ticket = (
                await self._repository.ticket_for_user(ticket_id, actor_user_id, for_update=True)
                if require_owner
                else await self._repository.ticket(ticket_id, for_update=True)
            )
            if ticket is None:
                raise ApplicationError("ticket_not_found", "Ticket not found.", 404)
            if ticket.status == TicketStatus.CLOSED.value and message_type != "internal_note":
                raise ApplicationError(
                    "ticket_closed", "Closed tickets do not accept new messages.", 409
                )
            before_status = ticket.status
            if require_owner and ticket.status == TicketStatus.WAITING_USER.value:
                self._set_status(ticket, TicketStatus.OPEN.value, now)
            elif status_after is not None:
                self._set_status(ticket, status_after, now)
            if not require_owner and ticket.assigned_to_user_id is None:
                ticket.assigned_to_user_id = actor_user_id
            message = TicketMessage(
                ticket_id=ticket.id,
                sender_user_id=actor_user_id,
                message_type=message_type,
                body=body,
                created_at=now,
            )
            self._session.add(message)
            if message_type != TicketMessageType.INTERNAL_NOTE.value:
                ticket.last_message_at = now
            ticket.version += 1
            ticket.updated_at = now
            await self._session.flush()
            self._session.add(
                IdempotencyRecord(
                    scope=scope,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_status=201,
                    resource_type="ticket_message",
                    resource_id=message.id,
                    expires_at=now + timedelta(hours=self._settings.idempotency_ttl_hours),
                )
            )
            if message_type != TicketMessageType.INTERNAL_NOTE.value:
                event_type = (
                    "support.ticket.user_replied"
                    if require_owner
                    else "support.ticket.admin_replied"
                )
                self._event(
                    ticket=ticket,
                    event_type=event_type,
                    key=f"support-message-created:{message.id}",
                    payload={
                        "ticket_id": str(ticket.id),
                        "message_id": str(message.id),
                        "user_id": str(ticket.user_id),
                        "sender_user_id": str(actor_user_id),
                        "status": ticket.status,
                    },
                )
            self._audit(
                actor_user_id=actor_user_id,
                actor_type=actor_type,
                action="support.message_created",
                ticket=ticket,
                client=client,
                before={"status": before_status},
                after={
                    "status": ticket.status,
                    "message_id": str(message.id),
                    "message_type": message.message_type,
                },
            )
            return self._message_response(message)

    async def _idempotent_resource(
        self,
        *,
        scope: str,
        key: str,
        request_hash: bytes,
        resource_type: str,
        now: datetime,
    ) -> UUID | None:
        record = await self._repository.idempotency_record(scope, key)
        if record is None:
            return None
        if record.expires_at <= now:
            await self._session.delete(record)
            await self._session.flush()
            return None
        if record.request_hash != request_hash or record.resource_type != resource_type:
            raise ApplicationError(
                "idempotency_key_conflict",
                "Idempotency-Key was already used for a different request.",
                409,
            )
        if record.resource_id is None:
            raise RuntimeError("completed idempotency record has no resource")
        return record.resource_id

    async def _message_page(
        self,
        *,
        ticket_id: UUID,
        include_internal: bool,
        after_message_id: UUID | None,
        limit: int,
    ) -> TicketMessagePage:
        messages = await self._repository.messages(
            ticket_id,
            include_internal=include_internal,
            after_message_id=after_message_id,
            limit=limit + 1,
        )
        has_more = len(messages) > limit
        visible = messages[:limit]
        return TicketMessagePage(
            items=[self._message_response(message) for message in visible],
            next_cursor=visible[-1].id if has_more and visible else None,
        )

    async def _require_staff_assignee(self, user_id: UUID) -> None:
        if await self._repository.active_staff_user(user_id) is None:
            raise ApplicationError(
                "ticket_assignee_invalid",
                "Assignee must be an active support or admin user.",
                422,
            )

    @staticmethod
    def _set_status(ticket: Ticket, new_status: str, now: datetime) -> None:
        if new_status == ticket.status:
            return
        allowed = {
            TicketStatus.OPEN.value: {
                TicketStatus.IN_PROGRESS.value,
                TicketStatus.WAITING_USER.value,
                TicketStatus.CLOSED.value,
            },
            TicketStatus.IN_PROGRESS.value: {
                TicketStatus.OPEN.value,
                TicketStatus.WAITING_USER.value,
                TicketStatus.CLOSED.value,
            },
            TicketStatus.WAITING_USER.value: {
                TicketStatus.OPEN.value,
                TicketStatus.IN_PROGRESS.value,
                TicketStatus.CLOSED.value,
            },
            TicketStatus.CLOSED.value: {TicketStatus.OPEN.value},
        }
        if new_status not in allowed[ticket.status]:
            raise ApplicationError(
                "ticket_status_transition_invalid",
                f"Ticket cannot transition from {ticket.status} to {new_status}.",
                409,
            )
        ticket.status = new_status
        ticket.closed_at = now if new_status == TicketStatus.CLOSED.value else None

    def _event(
        self,
        *,
        ticket: Ticket,
        event_type: str,
        key: str,
        payload: dict[str, Any],
    ) -> None:
        self._session.add(
            OutboxEvent(
                aggregate_type="support_ticket",
                aggregate_id=ticket.id,
                event_type=event_type,
                payload=payload,
                idempotency_key=key,
            )
        )

    def _audit(
        self,
        *,
        actor_user_id: UUID,
        actor_type: str,
        action: str,
        ticket: Ticket,
        client: SupportClientContext,
        after: dict[str, Any],
        before: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> None:
        audit = AuditLog(
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            action=action,
            entity_type="ticket",
            entity_id=ticket.id,
            reason=reason,
            after_state=after,
            ip_address=client.ip_address,
            user_agent=client.user_agent,
            request_id=client.request_id,
        )
        if before is not None:
            audit.before_state = before
        self._session.add(audit)

    @staticmethod
    def _request_hash(payload: dict[str, Any]) -> bytes:
        serialized = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
        return hashlib.sha256(serialized).digest()

    @staticmethod
    def _mutable_state(ticket: Ticket) -> dict[str, Any]:
        return {
            "status": ticket.status,
            "priority": ticket.priority,
            "assigned_to_user_id": str(ticket.assigned_to_user_id)
            if ticket.assigned_to_user_id
            else None,
        }

    @classmethod
    def _detail(cls, ticket: Ticket, messages: list[TicketMessage]) -> TicketDetailResponse:
        return TicketDetailResponse(
            ticket=cls._ticket_response(ticket),
            messages=[cls._message_response(message) for message in messages],
        )

    @staticmethod
    def _ticket_response(ticket: Ticket) -> TicketResponse:
        return TicketResponse(
            id=ticket.id,
            public_number=ticket.public_number,
            user_id=ticket.user_id,
            assigned_to_user_id=ticket.assigned_to_user_id,
            subject=ticket.subject,
            category=ticket.category,
            priority=ticket.priority,
            status=ticket.status,
            last_message_at=ticket.last_message_at,
            closed_at=ticket.closed_at,
            version=ticket.version,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )

    @staticmethod
    def _message_response(message: TicketMessage) -> TicketMessageResponse:
        return TicketMessageResponse(
            id=message.id,
            ticket_id=message.ticket_id,
            sender_user_id=message.sender_user_id,
            message_type=message.message_type,
            body=message.body,
            created_at=message.created_at,
        )
