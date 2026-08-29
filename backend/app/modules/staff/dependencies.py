from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencies import SessionDependency
from app.core.config import Settings
from app.modules.auth.runtime import AuthRuntime
from app.modules.staff.service import StaffService


def get_staff_service(request: Request, session: SessionDependency) -> StaffService:
    settings = cast(Settings, request.app.state.settings)
    runtime = cast(AuthRuntime, request.app.state.auth_runtime)
    return StaffService(session=session, settings=settings, email_sender=runtime.email_sender)


StaffServiceDependency = Annotated[StaffService, Depends(get_staff_service)]
