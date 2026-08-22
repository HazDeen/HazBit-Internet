from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from remnawave_adapter.client import RemnawaveClient
from remnawave_adapter.schemas import (
    CreateDeviceRequest,
    DeviceList,
    DeviceState,
    ExtendUserRequest,
    ProvisionUserRequest,
    UpdateUserRequest,
    UserState,
)
from remnawave_adapter.security import require_internal_token


def client_dependency(request: Request) -> RemnawaveClient:
    return request.app.state.remnawave_client  # type: ignore[no-any-return]


ClientDependency = Annotated[RemnawaveClient, Depends(client_dependency)]


def create_router() -> APIRouter:
    router = APIRouter(prefix="/internal/v1", dependencies=[Depends(require_internal_token)])

    @router.post("/users", response_model=UserState, status_code=201)
    async def create_user(body: ProvisionUserRequest, client: ClientDependency) -> UserState:
        return await client.create_user(body)

    @router.get("/users/{user_id}", response_model=UserState)
    async def get_user(user_id: int, client: ClientDependency) -> UserState:
        return await client.get_user(user_id)

    @router.get("/users/by-username/{username}", response_model=UserState)
    async def get_user_by_username(username: str, client: ClientDependency) -> UserState:
        return await client.get_user_by_username(username)

    @router.patch("/users/{user_id}", response_model=UserState)
    async def update_user(
        user_id: int,
        body: UpdateUserRequest,
        client: ClientDependency,
    ) -> UserState:
        changes: dict[str, Any] = {}
        if body.expire_at is not None:
            changes["expireAt"] = body.expire_at.isoformat().replace("+00:00", "Z")
        if body.traffic_limit_bytes is not None:
            changes["trafficLimitBytes"] = body.traffic_limit_bytes
        if body.device_limit is not None:
            changes["hwidDeviceLimit"] = body.device_limit
        if body.internal_squad_ids is not None:
            changes["activeInternalSquads"] = [str(value) for value in body.internal_squad_ids]
        return await client.update_user(user_id, **changes)

    @router.post("/users/{user_id}/disable", response_model=UserState)
    async def disable_user(user_id: int, client: ClientDependency) -> UserState:
        return await client.disable_user(user_id)

    @router.post("/users/{user_id}/enable", response_model=UserState)
    async def enable_user(user_id: int, client: ClientDependency) -> UserState:
        return await client.enable_user(user_id)

    @router.post("/users/{user_id}/extend", response_model=UserState)
    async def extend_user(
        user_id: int,
        body: ExtendUserRequest,
        client: ClientDependency,
    ) -> UserState:
        return await client.extend_user(user_id, body.days)

    @router.post("/users/{user_id}/devices", response_model=DeviceState)
    async def create_device(
        user_id: int,
        body: CreateDeviceRequest,
        client: ClientDependency,
    ) -> DeviceState:
        return await client.create_device(user_id, **body.model_dump())

    @router.get("/users/{user_id}/devices", response_model=DeviceList)
    async def list_devices(user_id: int, client: ClientDependency) -> DeviceList:
        return await client.list_devices(user_id)

    @router.delete("/users/{user_id}/devices/{hwid}", response_model=DeviceList)
    async def remove_device(user_id: int, hwid: str, client: ClientDependency) -> DeviceList:
        return await client.remove_device(user_id, hwid)

    return router
