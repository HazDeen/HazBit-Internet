from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.dependencies import SessionDependency
from app.modules.portal.service import PortalService


def get_portal_service(session: SessionDependency) -> PortalService:
    return PortalService(session)


PortalServiceDependency = Annotated[PortalService, Depends(get_portal_service)]
