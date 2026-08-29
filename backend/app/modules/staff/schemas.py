from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.modules.auth.enums import Permission, Role

STAFF_ROLES = frozenset(
    {Role.SUPER_ADMIN, Role.ADMIN, Role.SUPPORT, Role.NETWORK, Role.FINANCE, Role.CONTENT}
)


class StaffAccessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles: list[Role] = Field(min_length=1, max_length=6)
    permissions: list[Permission] = Field(default_factory=list, max_length=30)

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, roles: list[Role]) -> list[Role]:
        unique = list(dict.fromkeys(roles))
        if any(role not in STAFF_ROLES for role in unique):
            raise ValueError("only staff roles can be assigned")
        return unique

    @field_validator("permissions")
    @classmethod
    def unique_permissions(cls, permissions: list[Permission]) -> list[Permission]:
        return list(dict.fromkeys(permissions))


class CreateStaffInvitationRequest(StaffAccessInput):
    email: EmailStr


class UpdateStaffAccessRequest(StaffAccessInput):
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def protect_super_admin_shape(self) -> UpdateStaffAccessRequest:
        if Role.SUPER_ADMIN in self.roles and len(self.roles) > 1:
            raise ValueError("super admin must be assigned as a standalone role")
        return self


class AcceptStaffInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token: str = Field(min_length=32, max_length=512)


class StaffMemberResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    public_name: str | None
    status: str
    roles: list[Role]
    permissions: list[Permission]
    telegram_linked: bool
    created_at: datetime


class StaffInvitationResponse(BaseModel):
    id: UUID
    email: EmailStr
    roles: list[Role]
    permissions: list[Permission]
    expires_at: datetime
    created_at: datetime


class StaffDirectoryResponse(BaseModel):
    members: list[StaffMemberResponse]
    invitations: list[StaffInvitationResponse]
    role_presets: dict[Role, list[Permission]]
    available_permissions: list[Permission]
