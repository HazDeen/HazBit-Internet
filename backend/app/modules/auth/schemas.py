from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.auth.enums import Permission, Role


class EmailStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    device_fingerprint: str | None = Field(default=None, min_length=16, max_length=512)


class EmailVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    code: str = Field(pattern=r"^\d{6,8}$")
    device_fingerprint: str | None = Field(default=None, min_length=16, max_length=512)


class TelegramAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    init_data: str = Field(min_length=20, max_length=8192)
    device_fingerprint: str | None = Field(default=None, min_length=16, max_length=512)


class MessageResponse(BaseModel):
    message: str


class AuthenticatedUser(BaseModel):
    id: UUID
    display_name: str | None
    email: EmailStr | None
    telegram_user_id: int | None
    roles: list[Role]
    permissions: list[Permission]

    @field_validator("roles")
    @classmethod
    def sort_roles(cls, value: list[Role]) -> list[Role]:
        return sorted(value, key=str)

    @field_validator("permissions")
    @classmethod
    def sort_permissions(cls, value: list[Permission]) -> list[Permission]:
        return sorted(value, key=str)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"  # noqa: S105 - OAuth token type, not a credential
    expires_in: int
    user: AuthenticatedUser


class SessionResponse(BaseModel):
    session_id: UUID
    expires_at: str
