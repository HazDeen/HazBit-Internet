from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import RemnawaveAdapterSettings


class AdapterUserState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    username: str
    status: str
    expire_at: datetime
    traffic_limit_bytes: int
    device_limit: int | None
    subscription_url: str | None = None


class AdapterDeviceState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hwid: str
    user_id: int
    platform: str | None = None
    os_version: str | None = None
    device_model: str | None = None
    created_at: datetime
    updated_at: datetime


class AdapterDeviceList(BaseModel):
    total: int
    devices: list[AdapterDeviceState]


class AdapterNodeState(BaseModel):
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


class AdapterNodeList(BaseModel):
    nodes: list[AdapterNodeState]


@dataclass(slots=True)
class AdapterError(Exception):
    code: str
    detail: str
    status_code: int
    retryable: bool


class RemnawaveAdapterClient:
    def __init__(
        self,
        settings: RemnawaveAdapterSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=str(settings.base_url).rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.internal_token.get_secret_value()}",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(
                settings.read_timeout_seconds,
                connect=settings.connect_timeout_seconds,
            ),
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def create_user(
        self,
        *,
        username: str,
        expire_at: datetime,
        traffic_limit_bytes: int,
        device_limit: int,
        email: str | None,
        telegram_id: int | None,
        internal_squad_ids: list[UUID],
    ) -> AdapterUserState:
        return await self._user(
            "POST",
            "/internal/v1/users",
            json={
                "username": username,
                "expire_at": expire_at.isoformat(),
                "traffic_limit_bytes": traffic_limit_bytes,
                "device_limit": device_limit,
                "email": email,
                "telegram_id": telegram_id,
                "internal_squad_ids": [str(value) for value in internal_squad_ids],
            },
        )

    async def get_user_by_username(self, username: str) -> AdapterUserState:
        return await self._user("GET", f"/internal/v1/users/by-username/{username}")

    async def get_user(self, user_id: int) -> AdapterUserState:
        return await self._user("GET", f"/internal/v1/users/{user_id}")

    async def update_user(
        self,
        user_id: int,
        *,
        expire_at: datetime | None = None,
        traffic_limit_bytes: int | None = None,
        device_limit: int | None = None,
        internal_squad_ids: list[UUID] | None = None,
    ) -> AdapterUserState:
        return await self._user(
            "PATCH",
            f"/internal/v1/users/{user_id}",
            json={
                "expire_at": expire_at.isoformat() if expire_at else None,
                "traffic_limit_bytes": traffic_limit_bytes,
                "device_limit": device_limit,
                "internal_squad_ids": (
                    [str(value) for value in internal_squad_ids]
                    if internal_squad_ids is not None
                    else None
                ),
            },
        )

    async def disable_user(self, user_id: int) -> AdapterUserState:
        return await self._user("POST", f"/internal/v1/users/{user_id}/disable")

    async def enable_user(self, user_id: int) -> AdapterUserState:
        return await self._user("POST", f"/internal/v1/users/{user_id}/enable")

    async def create_device(self, user_id: int, payload: dict[str, Any]) -> AdapterDeviceState:
        data = await self._request("POST", f"/internal/v1/users/{user_id}/devices", json=payload)
        try:
            return AdapterDeviceState.model_validate(data)
        except ValidationError as exc:
            raise self._contract_error() from exc

    async def list_devices(self, user_id: int) -> AdapterDeviceList:
        data = await self._request("GET", f"/internal/v1/users/{user_id}/devices")
        try:
            return AdapterDeviceList.model_validate(data)
        except ValidationError as exc:
            raise self._contract_error() from exc

    async def remove_device(self, user_id: int, hwid: str) -> AdapterDeviceList:
        data = await self._request("DELETE", f"/internal/v1/users/{user_id}/devices/{hwid}")
        try:
            return AdapterDeviceList.model_validate(data)
        except ValidationError as exc:
            raise self._contract_error() from exc

    async def list_nodes(self) -> AdapterNodeList:
        data = await self._request("GET", "/internal/v1/nodes")
        try:
            return AdapterNodeList.model_validate(data)
        except ValidationError as exc:
            raise self._contract_error() from exc

    async def disable_node(self, node_uuid: UUID) -> AdapterNodeState:
        return await self._node("POST", f"/internal/v1/nodes/{node_uuid}/disable")

    async def enable_node(self, node_uuid: UUID) -> AdapterNodeState:
        return await self._node("POST", f"/internal/v1/nodes/{node_uuid}/enable")

    async def _node(self, method: str, path: str) -> AdapterNodeState:
        data = await self._request(method, path)
        try:
            return AdapterNodeState.model_validate(data)
        except ValidationError as exc:
            raise self._contract_error() from exc

    async def _user(self, method: str, path: str, **kwargs: Any) -> AdapterUserState:
        data = await self._request(method, path, **kwargs)
        try:
            return AdapterUserState.model_validate(data)
        except ValidationError as exc:
            raise self._contract_error() from exc

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AdapterError(
                "adapter_unavailable",
                "Remnawave adapter is unavailable.",
                503,
                True,
            ) from exc
        if response.is_error:
            try:
                body = response.json()
            except ValueError:
                body = {}
            code = body.get("code", "adapter_error") if isinstance(body, dict) else "adapter_error"
            retryable = (
                bool(body.get("retryable", response.status_code >= 500))
                if isinstance(body, dict)
                else True
            )
            raise AdapterError(
                code=str(code),
                detail="Remnawave adapter rejected the operation.",
                status_code=response.status_code,
                retryable=retryable,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise self._contract_error() from exc
        if not isinstance(body, dict):
            raise self._contract_error()
        return body

    @staticmethod
    def _contract_error() -> AdapterError:
        return AdapterError(
            "adapter_contract_mismatch",
            "Remnawave adapter returned an invalid response.",
            502,
            False,
        )
