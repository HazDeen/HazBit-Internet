from __future__ import annotations

import pytest
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.modules.auth.dependencies import require_permissions, require_roles
from app.modules.auth.enums import Permission, Role
from app.modules.auth.permissions import permissions_for_roles
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


async def test_permission_guard_requires_every_declared_permission() -> None:
    principal = Principal(
        uuid7(),
        uuid7(),
        frozenset({Role.NETWORK}),
        frozenset({Permission.VPN_READ, Permission.VPN_NODES_MANAGE}),
    )
    checker = require_permissions(Permission.VPN_READ, Permission.VPN_NODES_MANAGE)

    assert await checker(principal) is principal


async def test_permission_guard_denies_partial_access() -> None:
    principal = Principal(
        uuid7(), uuid7(), frozenset({Role.NETWORK}), frozenset({Permission.VPN_READ})
    )

    with pytest.raises(ApplicationError) as exc_info:
        await require_permissions(Permission.VPN_NODES_MANAGE)(principal)

    assert exc_info.value.status_code == 403


def test_role_presets_keep_specialists_in_their_domain() -> None:
    network = permissions_for_roles({Role.NETWORK})
    finance = permissions_for_roles({Role.FINANCE})

    assert Permission.VPN_NODES_MANAGE in network
    assert Permission.PAYMENTS_REVIEW not in network
    assert Permission.PAYMENTS_REVIEW in finance
    assert Permission.VPN_NODES_MANAGE not in finance
