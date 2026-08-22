"""Allow durable Remnawave HWID device creation commands.

Revision ID: 20260822_0002
Revises: 20260822_0001
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260822_0002"
down_revision: str | None = "20260822_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TYPES = "'ensure_account', 'enable', 'disable', 'extend', 'sync', 'remove_device', 'revoke'"
NEW_TYPES = (
    "'ensure_account', 'enable', 'disable', 'extend', 'sync', "
    "'create_device', 'remove_device', 'revoke'"
)


def upgrade() -> None:
    op.drop_constraint(
        op.f("vpn_sync_commands_command_type_check"),
        "vpn_sync_commands",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("vpn_sync_commands_command_type_check"),
        "vpn_sync_commands",
        f"command_type IN ({NEW_TYPES})",
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("vpn_sync_commands_command_type_check"),
        "vpn_sync_commands",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("vpn_sync_commands_command_type_check"),
        "vpn_sync_commands",
        f"command_type IN ({OLD_TYPES})",
        schema="app",
    )
