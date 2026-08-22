from __future__ import annotations

from enum import StrEnum


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_USER = "waiting_user"
    CLOSED = "closed"


class TicketPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TicketCategory(StrEnum):
    GENERAL = "general"
    CONNECTION = "connection"
    PAYMENT = "payment"
    SUBSCRIPTION = "subscription"
    ACCOUNT = "account"
    OTHER = "other"


class TicketMessageType(StrEnum):
    MESSAGE = "message"
    INTERNAL_NOTE = "internal_note"
    SYSTEM = "system"
