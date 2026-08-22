from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class CreateTicketRequest(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    category: Literal["general", "connection", "payment", "subscription", "account", "other"] = (
        "general"
    )
    message: str = Field(min_length=1, max_length=5000)

    @field_validator("subject", "message")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class SendTicketMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


class AdminReplyRequest(SendTicketMessageRequest):
    message_type: Literal["message", "internal_note"] = "message"
    status_after: Literal["in_progress", "waiting_user", "closed"] | None = None

    @model_validator(mode="after")
    def validate_internal_note(self) -> Self:
        if self.message_type == "internal_note" and self.status_after is not None:
            raise ValueError("internal notes cannot change customer-visible status")
        return self


class UpdateTicketRequest(BaseModel):
    status: Literal["open", "in_progress", "waiting_user", "closed"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    assigned_to_user_id: UUID | None = None
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_change(self) -> Self:
        mutable = {"status", "priority", "assigned_to_user_id"}
        if not self.model_fields_set.intersection(mutable):
            raise ValueError("at least one ticket change must be provided")
        return self


class TicketMessageResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    sender_user_id: UUID | None
    message_type: str
    body: str
    created_at: datetime


class TicketResponse(BaseModel):
    id: UUID
    public_number: int
    user_id: UUID
    assigned_to_user_id: UUID | None
    subject: str
    category: str
    priority: str
    status: str
    last_message_at: datetime
    closed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class TicketDetailResponse(BaseModel):
    ticket: TicketResponse
    messages: list[TicketMessageResponse]


class TicketMessagePage(BaseModel):
    items: list[TicketMessageResponse]
    next_cursor: UUID | None
