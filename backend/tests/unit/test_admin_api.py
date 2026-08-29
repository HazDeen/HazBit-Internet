from __future__ import annotations

from app.core.config import Settings
from app.main import create_app


def test_admin_panel_routes_are_registered(test_settings: Settings) -> None:
    paths = set(create_app(test_settings).openapi()["paths"])

    assert {
        "/api/v1/admin/dashboard",
        "/api/v1/admin/users",
        "/api/v1/admin/users/{user_id}",
        "/api/v1/admin/users/{user_id}/block",
        "/api/v1/admin/users/{user_id}/unblock",
        "/api/v1/admin/users/{user_id}/subscription/extend",
        "/api/v1/admin/users/{user_id}/subscription/plan",
        "/api/v1/admin/users/{user_id}/devices",
        "/api/v1/admin/subscriptions",
        "/api/v1/admin/payments",
        "/api/v1/admin/plans",
        "/api/v1/admin/plans/{plan_id}",
        "/api/v1/admin/plans/{plan_id}/versions",
        "/api/v1/admin/family-groups",
        "/api/v1/admin/family-groups/{group_id}",
        "/api/v1/admin/vpn-devices",
        "/api/v1/admin/settings",
        "/api/v1/admin/staff",
        "/api/v1/admin/staff/invitations",
        "/api/v1/admin/staff/invitations/accept",
        "/api/v1/admin/staff/{user_id}",
    }.issubset(paths)


def test_admin_mutations_require_a_reason(test_settings: Settings) -> None:
    schemas = create_app(test_settings).openapi()["components"]["schemas"]

    block_reason = schemas["BlockUserRequest"]["properties"]["reason"]
    extend = schemas["ExtendSubscriptionRequest"]["properties"]
    change_reason = schemas["ChangePlanRequest"]["properties"]["reason"]

    assert block_reason["minLength"] == 3
    assert change_reason["minLength"] == 3
    assert extend["reason"]["minLength"] == 3
    assert extend["days"]["minimum"] == 1
    assert extend["days"]["maximum"] == 365
