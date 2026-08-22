"""Harden promo redemption idempotency.

Revision ID: 20260822_0004
Revises: 20260822_0003
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260822_0004"
down_revision: str | None = "20260822_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX uq_promo_redemptions_active_payment "
        "ON app.promo_redemptions (payment_id) "
        "WHERE payment_id IS NOT NULL AND revoked_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_promo_redemptions_active_period "
        "ON app.promo_redemptions (subscription_period_id) "
        "WHERE subscription_period_id IS NOT NULL AND revoked_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS app.uq_promo_redemptions_active_period")
    op.execute("DROP INDEX IF EXISTS app.uq_promo_redemptions_active_payment")
