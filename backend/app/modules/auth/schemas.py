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


class PasswordLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    device_fingerprint: str | None = Field(default=None, min_length=16, max_length=512)


class RegistrationStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    public_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    telegram_user_id: int | None = Field(default=None, gt=0)
    device_fingerprint: str | None = Field(default=None, min_length=16, max_length=512)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        groups = sum(
            (
                any(character.islower() for character in value),
                any(character.isupper() for character in value),
                any(character.isdigit() for character in value),
                any(not character.isalnum() for character in value),
            )
        )
        if groups < 3:
            raise ValueError("password must include at least three character groups")
        return value


class RegistrationStartResponse(BaseModel):
    message: str
    registration_token: str
    telegram_confirmation_url: str | None = None


class RegistrationVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    registration_token: str = Field(min_length=24, max_length=128)
    code: str = Field(pattern=r"^\d{6,8}$")
    device_fingerprint: str | None = Field(default=None, min_length=16, max_length=512)


class RegistrationCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    registration_token: str = Field(min_length=24, max_length=128)
    device_fingerprint: str | None = Field(default=None, min_length=16, max_length=512)


class TelegramPendingResponse(BaseModel):
    status: str = "telegram_confirmation_required"
    telegram_confirmation_url: str


class GoogleAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    credential: str = Field(min_length=100, max_length=8192)
    device_fingerprint: str | None = Field(default=None, min_length=16, max_length=512)


class TelegramWidgetAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int = Field(gt=0)
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    photo_url: str | None = Field(default=None, max_length=2048)
    auth_date: int = Field(gt=0)
    hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    device_fingerprint: str | None = Field(default=None, min_length=16, max_length=512)


class TelegramIdStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_user_id: int = Field(gt=0)
    device_fingerprint: str | None = Field(default=None, min_length=16, max_length=512)


class TelegramIdStartResponse(BaseModel):
    challenge_token: str
    confirmation_url: str
    expires_in: int


class TelegramIdVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    challenge_token: str = Field(min_length=24, max_length=128)
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
