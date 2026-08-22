from __future__ import annotations

import pytest
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.modules.auth.dependencies import require_roles
from app.modules.auth.enums import Role
from app.modules.auth.service import Principal


async def test_rbac_accepts_any_required_role() -> None:
    principal = Principal(uuid7(), uuid7(), frozenset({Role.USER, Role.SUPPORT}))
    checker = require_roles(Role.ADMIN, Role.SUPPORT)

    assert await checker(principal) is principal


async def test_rbac_denies_missing_role() -> None:
    principal = Principal(uuid7(), uuid7(), frozenset({Role.USER}))
    checker = require_roles(Role.ADMIN, Role.SUPER_ADMIN)

    with pytest.raises(ApplicationError) as exc_info:
        await checker(principal)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "insufficient_permissions"
