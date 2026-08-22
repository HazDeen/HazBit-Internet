from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import DatabaseSettings, Settings
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.database.session import DatabaseManager
from app.modules.auth.rate_limit import RateLimit
from app.modules.support.schemas import (
    AdminReplyRequest,
    CreateTicketRequest,
    UpdateTicketRequest,
)
from app.modules.support.service import SupportClientContext, SupportService
from sqlalchemy import text
from sqlalchemy.engine import make_url


class FakeRateLimiter:
    async def enforce(self, policy: RateLimit, identity: str) -> None:
        assert policy.limit > 0
        assert identity


def _database_url() -> str:
    value = os.getenv("HAZBIT_TEST_DATABASE_URL")
    if not value:
        pytest.skip("HAZBIT_TEST_DATABASE_URL is not configured")
    return (
        make_url(value).set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)
    )


def _migrate(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAZBIT_DATABASE__URL", url)
    root = Path(__file__).resolve().parents[2]
    command.upgrade(Config(str(root / "alembic.ini")), "head")


def _service(session: object, settings: Settings) -> SupportService:
    return SupportService(
        session=session,  # type: ignore[arg-type]
        settings=settings.support,
        rate_limiter=FakeRateLimiter(),  # type: ignore[arg-type]
    )


def _context() -> SupportClientContext:
    return SupportClientContext("203.0.113.80", "pytest", uuid7())


async def _insert_user(
    database: DatabaseManager, user_id: UUID, *, role: str | None = None
) -> None:
    async with database.session() as session, session.begin():
        await session.execute(text("INSERT INTO app.users (id) VALUES (:id)"), {"id": user_id})
        if role is not None:
            await session.execute(
                text("INSERT INTO app.user_roles (user_id, role) VALUES (:user_id, :role)"),
                {"user_id": user_id, "role": role},
            )


@pytest.mark.integration
async def test_support_conversation_rbac_status_and_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = _database_url()
    _migrate(url, monkeypatch)
    settings = Settings(
        _env_file=None,
        environment="test",
        database=DatabaseSettings(url=url, pool_size=2, max_overflow=0),
    )
    database = DatabaseManager(settings.database)
    user_id, other_user_id, support_id = (uuid7() for _ in range(3))

    try:
        await _insert_user(database, user_id)
        await _insert_user(database, other_user_id)
        await _insert_user(database, support_id, role="support")

        create_payload = CreateTicketRequest(
            subject="Cannot connect from iPhone",
            category="connection",
            message="The VPN disconnects after a few seconds.",
        )
        async with database.session() as session:
            created = await _service(session, settings).create_ticket(
                user_id=user_id,
                payload=create_payload,
                idempotency_key="ticket-create-001",
                client=_context(),
            )
        ticket_id = created.ticket.id
        assert created.ticket.public_number > 0
        assert created.ticket.status == "open"
        assert created.ticket.version == 1
        assert len(created.messages) == 1

        async with database.session() as session:
            repeated = await _service(session, settings).create_ticket(
                user_id=user_id,
                payload=create_payload,
                idempotency_key="ticket-create-001",
                client=_context(),
            )
        assert repeated.ticket.id == ticket_id
        assert repeated.messages[0].id == created.messages[0].id

        async with database.session() as session:
            with pytest.raises(ApplicationError) as conflict:
                await _service(session, settings).create_ticket(
                    user_id=user_id,
                    payload=CreateTicketRequest(
                        subject="Different problem",
                        message="This must not reuse the same key.",
                    ),
                    idempotency_key="ticket-create-001",
                    client=_context(),
                )
        assert conflict.value.code == "idempotency_key_conflict"

        async with database.session() as session:
            with pytest.raises(ApplicationError) as hidden:
                await _service(session, settings).user_ticket(
                    user_id=other_user_id, ticket_id=ticket_id
                )
        assert hidden.value.code == "ticket_not_found"

        async with database.session() as session:
            queue = await _service(session, settings).admin_queue(
                status=None,
                assigned_to_user_id=None,
                unassigned_only=True,
                limit=100,
            )
        assert [item.id for item in queue] == [ticket_id]

        reply_payload = AdminReplyRequest(body="Please reinstall the VPN profile.")
        async with database.session() as session:
            reply = await _service(session, settings).admin_reply(
                staff_user_id=support_id,
                actor_type="support",
                ticket_id=ticket_id,
                payload=reply_payload,
                idempotency_key="ticket-reply-001",
                client=_context(),
            )
        async with database.session() as session:
            repeated_reply = await _service(session, settings).admin_reply(
                staff_user_id=support_id,
                actor_type="support",
                ticket_id=ticket_id,
                payload=reply_payload,
                idempotency_key="ticket-reply-001",
                client=_context(),
            )
            waiting = await _service(session, settings).admin_ticket(ticket_id)
        assert repeated_reply.id == reply.id
        assert waiting.ticket.status == "waiting_user"
        assert waiting.ticket.assigned_to_user_id == support_id
        assert waiting.ticket.version == 2

        async with database.session() as session:
            note = await _service(session, settings).admin_reply(
                staff_user_id=support_id,
                actor_type="support",
                ticket_id=ticket_id,
                payload=AdminReplyRequest(
                    body="Likely an expired local profile.", message_type="internal_note"
                ),
                idempotency_key="ticket-note-001",
                client=_context(),
            )
        assert note.message_type == "internal_note"

        async with database.session() as session:
            user_view = await _service(session, settings).user_ticket(
                user_id=user_id, ticket_id=ticket_id
            )
            admin_view = await _service(session, settings).admin_ticket(ticket_id)
        assert all(message.message_type != "internal_note" for message in user_view.messages)
        assert any(message.message_type == "internal_note" for message in admin_view.messages)

        async with database.session() as session:
            user_reply = await _service(session, settings).send_user_message(
                user_id=user_id,
                ticket_id=ticket_id,
                body="Reinstalled. It still disconnects.",
                idempotency_key="ticket-user-reply-001",
                client=_context(),
            )
        assert user_reply.sender_user_id == user_id

        async with database.session() as session:
            reopened_by_reply = await _service(session, settings).admin_ticket(ticket_id)
        assert reopened_by_reply.ticket.status == "open"
        assert reopened_by_reply.ticket.version == 4

        async with database.session() as session:
            with pytest.raises(ApplicationError) as invalid_assignee:
                await _service(session, settings).update_ticket(
                    ticket_id=ticket_id,
                    staff_user_id=support_id,
                    actor_type="support",
                    payload=UpdateTicketRequest(
                        assigned_to_user_id=other_user_id,
                        expected_version=4,
                        reason="Invalid assignment check",
                    ),
                    client=_context(),
                )
        assert invalid_assignee.value.code == "ticket_assignee_invalid"

        async with database.session() as session:
            progressed = await _service(session, settings).update_ticket(
                ticket_id=ticket_id,
                staff_user_id=support_id,
                actor_type="support",
                payload=UpdateTicketRequest(
                    status="in_progress",
                    priority="urgent",
                    expected_version=4,
                    reason="Investigation started",
                ),
                client=_context(),
            )
        assert progressed.status == "in_progress"
        assert progressed.priority == "urgent"
        assert progressed.version == 5

        async with database.session() as session:
            with pytest.raises(ApplicationError) as stale:
                await _service(session, settings).update_ticket(
                    ticket_id=ticket_id,
                    staff_user_id=support_id,
                    actor_type="support",
                    payload=UpdateTicketRequest(
                        status="closed",
                        expected_version=4,
                        reason="Stale operator view",
                    ),
                    client=_context(),
                )
        assert stale.value.code == "ticket_version_conflict"

        async with database.session() as session:
            closed = await _service(session, settings).update_ticket(
                ticket_id=ticket_id,
                staff_user_id=support_id,
                actor_type="support",
                payload=UpdateTicketRequest(
                    status="closed",
                    expected_version=5,
                    reason="Issue resolved",
                ),
                client=_context(),
            )
        assert closed.status == "closed"
        assert closed.closed_at is not None
        assert closed.version == 6

        async with database.session() as session:
            with pytest.raises(ApplicationError) as closed_message:
                await _service(session, settings).send_user_message(
                    user_id=user_id,
                    ticket_id=ticket_id,
                    body="One more question",
                    idempotency_key="ticket-after-close-001",
                    client=_context(),
                )
        assert closed_message.value.code == "ticket_closed"

        async with database.session() as session:
            opened = await _service(session, settings).update_ticket(
                ticket_id=ticket_id,
                staff_user_id=support_id,
                actor_type="support",
                payload=UpdateTicketRequest(
                    status="open",
                    expected_version=6,
                    reason="Customer requested follow-up",
                ),
                client=_context(),
            )
        assert opened.status == "open"
        assert opened.closed_at is None
        assert opened.version == 7

        async with database.session() as session:
            first_page = await _service(session, settings).user_messages(
                user_id=user_id,
                ticket_id=ticket_id,
                after_message_id=None,
                limit=2,
            )
        assert len(first_page.items) == 2
        assert first_page.next_cursor is not None
        assert all(item.message_type != "internal_note" for item in first_page.items)

        async with database.session() as session:
            counts = (
                await session.execute(
                    text(
                        "SELECT "
                        "(SELECT count(*) FROM app.tickets WHERE id = :ticket_id), "
                        "(SELECT count(*) FROM app.ticket_messages WHERE ticket_id = :ticket_id), "
                        "(SELECT count(*) FROM app.audit_logs "
                        " WHERE entity_type = 'ticket' AND entity_id = :ticket_id), "
                        "(SELECT count(*) FROM app.outbox_events "
                        " WHERE aggregate_type = 'support_ticket' "
                        " AND aggregate_id = :ticket_id)"
                    ),
                    {"ticket_id": ticket_id},
                )
            ).one()
        assert counts == (1, 7, 7, 6)
    finally:
        await database.dispose()
