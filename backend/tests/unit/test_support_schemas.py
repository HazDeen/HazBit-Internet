from __future__ import annotations

import pytest
from app.modules.support.schemas import (
    AdminReplyRequest,
    CreateTicketRequest,
    UpdateTicketRequest,
)
from pydantic import ValidationError


def test_ticket_text_is_trimmed() -> None:
    payload = CreateTicketRequest(subject="  Connection problem  ", message="  Help me  ")

    assert payload.subject == "Connection problem"
    assert payload.message == "Help me"


def test_internal_note_cannot_change_public_status() -> None:
    with pytest.raises(ValidationError, match="internal notes"):
        AdminReplyRequest(
            body="Internal investigation",
            message_type="internal_note",
            status_after="waiting_user",
        )


def test_ticket_update_requires_a_change() -> None:
    with pytest.raises(ValidationError, match="ticket change"):
        UpdateTicketRequest(expected_version=1, reason="No actual change")
