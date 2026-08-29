from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RemnawaveStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    LIMITED = "LIMITED"
    EXPIRED = "EXPIRED"


class ProvisionUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=36, pattern=r"^[a-zA-Z0-9_-]+$")
    expire_at: datetime
    traffic_limit_bytes: int = Field(default=0, ge=0)
    device_limit: int = Field(ge=1, le=100)
    email: EmailStr | None = None
    telegram_id: int | None = Field(default=None, gt=0)
    internal_squad_ids: list[UUID] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expire_at: datetime | None = None
    traffic_limit_bytes: int | None = Field(default=None, ge=0)
    device_limit: int | None = Field(default=None, ge=1, le=100)
    internal_squad_ids: list[UUID] | None = None


class ExtendUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(ge=1, le=3660)


class CreateDeviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hwid: str = Field(min_length=10, max_length=64, pattern=r"^[a-zA-Z0-9=-]+$")
    platform: str | None = Field(default=None, max_length=120)
    os_version: str | None = Field(default=None, max_length=120)
    device_model: str | None = Field(default=None, max_length=160)
    user_agent: str | None = Field(default=None, max_length=1024)
    request_ip: str | None = Field(default=None, max_length=64)


class UserState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    username: str
    status: RemnawaveStatus
    expire_at: datetime
    traffic_limit_bytes: int
    device_limit: int | None
    subscription_url: str | None = None


class DeviceState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hwid: str
    user_id: int
    platform: str | None = None
    os_version: str | None = None
    device_model: str | None = None
    created_at: datetime
    updated_at: datetime


class DeviceList(BaseModel):
    total: int
    devices: list[DeviceState]


class NodeState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    uuid: UUID
    name: str
    address: str
    country_code: str
    is_connected: bool
    is_disabled: bool
    is_connecting: bool
    last_status_change: datetime | None = None
    last_status_message: str | None = None
    users_online: int = 0
    traffic_used_bytes: int | None = None
    traffic_limit_bytes: int | None = None
    xray_uptime: int = 0
    cpu_count: int | None = None
    memory_total_bytes: int | None = None
    memory_used_bytes: int | None = None
    load_average: list[float] = Field(default_factory=list)
    rx_bytes_per_second: int | None = None
    tx_bytes_per_second: int | None = None
    xray_version: str | None = None
    node_version: str | None = None


class NodeList(BaseModel):
    nodes: list[NodeState]


class HealthResponse(BaseModel):
    status: str
