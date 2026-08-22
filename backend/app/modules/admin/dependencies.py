from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencies import SessionDependency
from app.core.config import Settings
from app.modules.admin.service import AdminService


def get_admin_service(request: Request, session: SessionDependency) -> AdminService:
    return AdminService(
        session=session,
        settings=cast(Settings, request.app.state.settings),
    )


AdminServiceDependency = Annotated[AdminService, Depends(get_admin_service)]
