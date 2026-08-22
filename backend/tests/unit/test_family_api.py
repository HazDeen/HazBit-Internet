from __future__ import annotations

from app.core.config import Settings
from app.main import create_app


def test_family_routes_are_registered(test_settings: Settings) -> None:
    paths = set(create_app(test_settings).openapi()["paths"])

    assert {
        "/api/v1/family/groups",
        "/api/v1/family/group",
        "/api/v1/family/groups/{group_id}",
        "/api/v1/family/groups/{group_id}/invitations",
        "/api/v1/family/invitations",
        "/api/v1/family/invitations/accept",
        "/api/v1/family/invitations/decline",
        "/api/v1/family/groups/{group_id}/invitations/{invitation_id}",
        "/api/v1/family/members/me",
        "/api/v1/family/groups/{group_id}/members/{member_user_id}",
        "/api/v1/admin/family-groups/{group_id}/members/{member_user_id}",
        "/api/v1/admin/family-groups/{group_id}/invitations/{invitation_id}",
    }.issubset(paths)


def test_family_mutations_require_bearer_authentication(test_settings: Settings) -> None:
    schema = create_app(test_settings).openapi()
    operation = schema["paths"]["/api/v1/family/groups"]["post"]
    assert operation["security"] == [{"HTTPBearer": []}]
