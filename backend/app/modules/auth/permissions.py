from __future__ import annotations

from app.modules.auth.enums import Permission, Role

ALL_STAFF_PERMISSIONS = frozenset(Permission)

ROLE_PERMISSION_PRESETS: dict[Role, frozenset[Permission]] = {
    Role.SUPER_ADMIN: ALL_STAFF_PERMISSIONS,
    Role.ADMIN: ALL_STAFF_PERMISSIONS - {Permission.STAFF_MANAGE},
    Role.SUPPORT: frozenset(
        {
            Permission.DASHBOARD_READ,
            Permission.USERS_READ,
            Permission.TICKETS_READ,
            Permission.TICKETS_REPLY,
            Permission.TICKETS_MANAGE,
        }
    ),
    Role.NETWORK: frozenset(
        {
            Permission.DASHBOARD_READ,
            Permission.USERS_READ,
            Permission.SUBSCRIPTIONS_READ,
            Permission.VPN_READ,
            Permission.VPN_NODES_MANAGE,
        }
    ),
    Role.FINANCE: frozenset(
        {
            Permission.DASHBOARD_READ,
            Permission.USERS_READ,
            Permission.SUBSCRIPTIONS_READ,
            Permission.PAYMENTS_READ,
            Permission.PAYMENTS_REVIEW,
        }
    ),
    Role.CONTENT: frozenset(
        {
            Permission.DASHBOARD_READ,
            Permission.PROMOTIONS_MANAGE,
            Permission.PLANS_MANAGE,
        }
    ),
    Role.USER: frozenset(),
}


def permissions_for_roles(roles: set[Role] | frozenset[Role]) -> set[Permission]:
    permissions: set[Permission] = set()
    for role in roles:
        permissions.update(ROLE_PERMISSION_PRESETS[role])
    return permissions
