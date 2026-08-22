"""Secure ledger trigger function search paths.

Revision ID: 20260822_0003
Revises: 20260822_0002
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260822_0003"
down_revision: str | None = "20260822_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEDGER_FUNCTIONS = (
    "app.assert_transaction_postable()",
    "app.reject_posted_transaction_change()",
    "app.reject_posted_entry_change()",
)


def upgrade() -> None:
    for function in LEDGER_FUNCTIONS:
        op.execute(f"ALTER FUNCTION {function} SET search_path TO pg_catalog, app")


def downgrade() -> None:
    for function in LEDGER_FUNCTIONS:
        op.execute(f"ALTER FUNCTION {function} RESET search_path")
