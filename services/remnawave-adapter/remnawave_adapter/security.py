from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from remnawave_adapter.config import Settings

bearer = HTTPBearer(auto_error=False)


def settings_dependency(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


async def require_internal_token(
    settings: Annotated[Settings, Depends(settings_dependency)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = settings.internal_token.get_secret_value()
    if (
        credentials is None
        or credentials.scheme.casefold() != "bearer"
        or not hmac.compare_digest(credentials.credentials, expected)
    ):
        raise HTTPException(
            status_code=401,
            detail="Internal service authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
