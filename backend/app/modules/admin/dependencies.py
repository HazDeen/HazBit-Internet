from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencies import SessionDependency
from app.core.config import Settings
from app.integrations.redis import RedisManager
from app.modules.admin.service import AdminService
from app.modules.vpn.runtime import VpnRuntime


def get_admin_service(request: Request, session: SessionDependency) -> AdminService:
    return AdminService(
        session=session,
        settings=cast(Settings, request.app.state.settings),
        redis=cast(RedisManager, request.app.state.redis),
        vpn_runtime=cast(VpnRuntime, request.app.state.vpn_runtime),
    )


AdminServiceDependency = Annotated[AdminService, Depends(get_admin_service)]
