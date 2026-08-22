from __future__ import annotations

from uuid import uuid4

import pytest
from app.modules.families.schemas import CreateFamilyInvitationRequest
from pydantic import ValidationError


def test_family_invitation_requires_exactly_one_target() -> None:
    with pytest.raises(ValidationError):
        CreateFamilyInvitationRequest()
    with pytest.raises(ValidationError):
        CreateFamilyInvitationRequest(invited_user_id=uuid4(), invited_email="member@example.com")


def test_family_invitation_accepts_user_or_email() -> None:
    user_id = uuid4()
    by_user = CreateFamilyInvitationRequest(invited_user_id=user_id)
    by_email = CreateFamilyInvitationRequest(invited_email="MEMBER@example.com")

    assert by_user.invited_user_id == user_id
    assert str(by_email.invited_email) == "MEMBER@example.com"
