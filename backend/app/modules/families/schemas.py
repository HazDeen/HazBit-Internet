from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator


class CreateFamilyGroupRequest(BaseModel):
    subscription_id: UUID
    name: str = Field(default="Family", min_length=2, max_length=120)


class RenameFamilyGroupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class CreateFamilyInvitationRequest(BaseModel):
    invited_user_id: UUID | None = None
    invited_email: EmailStr | None = None

    @model_validator(mode="after")
    def exactly_one_target(self) -> CreateFamilyInvitationRequest:
        if (self.invited_user_id is None) == (self.invited_email is None):
            raise ValueError("exactly one invitation target is required")
        return self


class AcceptFamilyInvitationRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class RemoveFamilyMemberRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class FamilyMemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: str | None
    role: Literal["owner", "member"]
    joined_at: datetime


class FamilyInvitationResponse(BaseModel):
    id: UUID
    family_group_id: UUID
    invited_user_id: UUID | None
    invited_email: str | None
    status: str
    expires_at: datetime
    created_at: datetime
    invite_token: str | None = None


class FamilyGroupResponse(BaseModel):
    id: UUID
    owner_user_id: UUID
    subscription_id: UUID
    name: str
    status: str
    member_limit: int
    active_member_count: int
    pending_invitation_count: int
    device_limit: int
    active_device_count: int
    members: list[FamilyMemberResponse] = Field(default_factory=list)
    invitations: list[FamilyInvitationResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class FamilyInvitationInboxResponse(BaseModel):
    invitations: list[FamilyInvitationResponse]
