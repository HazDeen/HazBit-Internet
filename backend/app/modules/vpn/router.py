from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response, status

from app.modules.auth.dependencies import PrincipalDependency
from app.modules.vpn.dependencies import VpnServiceDependency
from app.modules.vpn.schemas import (
    CommandAcceptedResponse,
    CreateDeviceRequest,
    DeviceResponse,
    VpnAccountResponse,
    VpnConfigResponse,
)
from app.modules.vpn.service import VpnClientContext, VpnService


def create_vpn_router() -> APIRouter:
    router = APIRouter(tags=["vpn"])

    @router.get("/vpn/account", response_model=VpnAccountResponse)
    async def get_account(
        principal: PrincipalDependency,
        service: VpnServiceDependency,
    ) -> VpnAccountResponse:
        return await service.get_user_status(principal.user_id)

    @router.get("/vpn/config", response_model=VpnConfigResponse)
    async def get_config(
        response: Response,
        principal: PrincipalDependency,
        service: VpnServiceDependency,
    ) -> VpnConfigResponse:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return VpnConfigResponse(
            subscription_url=await service.get_subscription_url(principal.user_id)
        )

    @router.get("/devices", response_model=list[DeviceResponse])
    async def list_devices(
        principal: PrincipalDependency,
        service: VpnServiceDependency,
    ) -> list[DeviceResponse]:
        return await service.list_devices(principal.user_id)

    @router.post(
        "/devices",
        response_model=CommandAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_device(
        payload: CreateDeviceRequest,
        request: Request,
        response: Response,
        principal: PrincipalDependency,
        service: VpnServiceDependency,
        idempotency_key: Annotated[
            str,
            Header(alias="Idempotency-Key", min_length=8, max_length=128),
        ],
    ) -> CommandAcceptedResponse:
        device, command = await service.create_device(
            user_id=principal.user_id,
            idempotency_key=idempotency_key,
            hwid=payload.hwid,
            label=payload.label,
            platform=payload.platform,
            os_version=payload.os_version,
            device_model=payload.device_model,
            client=_client_context(request),
        )
        response.headers["Location"] = f"/api/v1/devices/{device.id}"
        return CommandAcceptedResponse(
            command_id=command.id,
            device=VpnService.device_response(device),
        )

    @router.delete(
        "/devices/{device_id}",
        response_model=CommandAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def remove_device(
        device_id: UUID,
        request: Request,
        principal: PrincipalDependency,
        service: VpnServiceDependency,
        idempotency_key: Annotated[
            str,
            Header(alias="Idempotency-Key", min_length=8, max_length=128),
        ],
    ) -> CommandAcceptedResponse:
        command = await service.remove_device(
            user_id=principal.user_id,
            device_id=device_id,
            idempotency_key=idempotency_key,
            client=_client_context(request),
        )
        return CommandAcceptedResponse(command_id=command.id)

    return router


def _client_context(request: Request) -> VpnClientContext:
    ip_address = request.client.host if request.client is not None else "0.0.0.0"  # noqa: S104
    user_agent = request.headers.get("user-agent")
    return VpnClientContext(
        ip_address=ip_address,
        user_agent=user_agent[:1024] if user_agent else None,
        request_id=getattr(request.state, "request_id", None),
    )
