from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VpnAccountResponse(BaseModel):
    id: UUID
    username: str
    desired_status: str
    observed_status: str | None
    expires_at: datetime | None
    last_synced_at: datetime | None
    provisioning: bool


class VpnConfigResponse(BaseModel):
    subscription_url: str


class CreateDeviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    hwid: str = Field(min_length=10, max_length=64, pattern=r"^[a-zA-Z0-9=-]+$")
    label: str | None = Field(default=None, min_length=1, max_length=120)
    platform: str | None = Field(default=None, min_length=1, max_length=60)
    os_version: str | None = Field(default=None, min_length=1, max_length=120)
    device_model: str | None = Field(default=None, min_length=1, max_length=160)


class DeviceResponse(BaseModel):
    id: UUID
    slot_number: int
    label: str | None
    hwid: str | None
    platform: str | None
    status: str
    first_seen_at: datetime | None
    last_seen_at: datetime | None


class CommandAcceptedResponse(BaseModel):
    command_id: UUID
    status: str = "pending"
    device: DeviceResponse | None = None
