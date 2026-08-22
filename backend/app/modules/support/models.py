from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.database.base import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    public_number: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id"), nullable=False)
    assigned_to_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.users.id"))
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("app.tickets.id"), nullable=False)
    sender_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.users.id"))
    message_type: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"

    ticket_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.ticket_messages.id"), primary_key=True
    )
    storage_object_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.storage_objects.id"), primary_key=True
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    scope: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[bytes] = mapped_column(nullable=False)
    response_status: Mapped[int | None] = mapped_column(SmallInteger)
    response_body: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB)
    resource_type: Mapped[str | None] = mapped_column(String(120))
    resource_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
