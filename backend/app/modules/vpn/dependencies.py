from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencies import SessionDependency
from app.core.config import Settings
from app.modules.vpn.runtime import VpnRuntime
from app.modules.vpn.service import VpnService


def get_vpn_service(request: Request, session: SessionDependency) -> VpnService:
    settings = cast(Settings, request.app.state.settings)
    runtime = cast(VpnRuntime, request.app.state.vpn_runtime)
    return VpnService(
        session=session,
        settings=settings.vpn,
        cipher=runtime.subscription_url_cipher,
    )


VpnServiceDependency = Annotated[VpnService, Depends(get_vpn_service)]
