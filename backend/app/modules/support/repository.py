from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import and_, case, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User, UserRole
from app.modules.support.models import IdempotencyRecord, Ticket, TicketMessage


class SupportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def serialize_key(self, key: str) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )

    async def idempotency_record(self, scope: str, key: str) -> IdempotencyRecord | None:
        return cast(
            IdempotencyRecord | None,
            await self.session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.idempotency_key == key,
                )
            ),
        )

    async def ticket_for_user(
        self, ticket_id: UUID, user_id: UUID, *, for_update: bool = False
    ) -> Ticket | None:
        statement = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(Ticket | None, await self.session.scalar(statement))

    async def ticket(self, ticket_id: UUID, *, for_update: bool = False) -> Ticket | None:
        statement = select(Ticket).where(Ticket.id == ticket_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(Ticket | None, await self.session.scalar(statement))

    async def ticket_by_resource(self, resource_id: UUID) -> Ticket | None:
        return cast(
            Ticket | None,
            await self.session.scalar(select(Ticket).where(Ticket.id == resource_id)),
        )

    async def message_by_resource(self, resource_id: UUID) -> TicketMessage | None:
        return cast(
            TicketMessage | None,
            await self.session.scalar(select(TicketMessage).where(TicketMessage.id == resource_id)),
        )

    async def user_tickets(self, user_id: UUID, *, status: str | None, limit: int) -> list[Ticket]:
        statement = select(Ticket).where(Ticket.user_id == user_id)
        if status is not None:
            statement = statement.where(Ticket.status == status)
        return list(
            (
                await self.session.scalars(
                    statement.order_by(Ticket.last_message_at.desc()).limit(limit)
                )
            ).all()
        )

    async def admin_queue(
        self,
        *,
        status: str | None,
        assigned_to_user_id: UUID | None,
        unassigned_only: bool,
        limit: int,
    ) -> list[Ticket]:
        statement = select(Ticket)
        if status is not None:
            statement = statement.where(Ticket.status == status)
        else:
            statement = statement.where(Ticket.status != "closed")
        if unassigned_only:
            statement = statement.where(Ticket.assigned_to_user_id.is_(None))
        elif assigned_to_user_id is not None:
            statement = statement.where(Ticket.assigned_to_user_id == assigned_to_user_id)
        priority_order = case(
            (Ticket.priority == "urgent", 0),
            (Ticket.priority == "high", 1),
            (Ticket.priority == "normal", 2),
            else_=3,
        )
        return list(
            (
                await self.session.scalars(
                    statement.order_by(priority_order, Ticket.last_message_at).limit(limit)
                )
            ).all()
        )

    async def messages(
        self,
        ticket_id: UUID,
        *,
        include_internal: bool,
        after_message_id: UUID | None,
        limit: int,
    ) -> list[TicketMessage]:
        statement = select(TicketMessage).where(TicketMessage.ticket_id == ticket_id)
        if not include_internal:
            statement = statement.where(TicketMessage.message_type != "internal_note")
        if after_message_id is not None:
            cursor = await self.session.scalar(
                select(TicketMessage).where(
                    TicketMessage.id == after_message_id,
                    TicketMessage.ticket_id == ticket_id,
                )
            )
            if cursor is None:
                return []
            statement = statement.where(
                or_(
                    TicketMessage.created_at > cursor.created_at,
                    and_(
                        TicketMessage.created_at == cursor.created_at,
                        TicketMessage.id > cursor.id,
                    ),
                )
            )
        return list(
            (
                await self.session.scalars(
                    statement.order_by(TicketMessage.created_at, TicketMessage.id).limit(limit)
                )
            ).all()
        )

    async def active_staff_user(self, user_id: UUID) -> User | None:
        return cast(
            User | None,
            await self.session.scalar(
                select(User)
                .join(UserRole, UserRole.user_id == User.id)
                .where(
                    User.id == user_id,
                    User.status == "active",
                    UserRole.revoked_at.is_(None),
                    UserRole.role.in_(["support", "admin", "super_admin"]),
                )
                .limit(1)
            ),
        )
