"""Add wallet top-ups and subscription billing settings.

Revision ID: 20260828_0005
Revises: 20260822_0004
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260828_0005"
down_revision: str | None = "20260822_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE app.wallet_top_ups (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES app.users(id) ON DELETE RESTRICT,
            provider text NOT NULL CHECK (provider IN ('platega')),
            provider_transaction_id uuid,
            payment_method smallint NOT NULL CHECK (payment_method IN (2, 10, 13)),
            status text NOT NULL DEFAULT 'creating'
                CHECK (status IN (
                    'creating', 'pending', 'confirmed', 'cancelled',
                    'failed', 'expired', 'chargebacked'
                )),
            amount_minor bigint NOT NULL CHECK (amount_minor > 0),
            currency char(3) NOT NULL CHECK (currency = upper(currency)),
            checkout_url text,
            idempotency_key varchar(255) NOT NULL,
            expires_at timestamptz,
            confirmed_at timestamptz,
            cancelled_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (user_id, idempotency_key),
            UNIQUE (provider, provider_transaction_id),
            CHECK ((status = 'confirmed') = (confirmed_at IS NOT NULL)),
            CHECK ((status IN ('cancelled', 'chargebacked')) = (cancelled_at IS NOT NULL))
        );

        CREATE INDEX ix_wallet_top_ups_user_created_at
            ON app.wallet_top_ups (user_id, created_at DESC);
        CREATE INDEX ix_wallet_top_ups_pending
            ON app.wallet_top_ups (expires_at) WHERE status IN ('creating', 'pending');

        CREATE TABLE app.subscription_billing_settings (
            subscription_id uuid PRIMARY KEY
                REFERENCES app.subscriptions(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES app.users(id) ON DELETE RESTRICT,
            plan_price_id uuid NOT NULL REFERENCES app.plan_prices(id) ON DELETE RESTRICT,
            auto_renew_enabled boolean NOT NULL DEFAULT false,
            next_renewal_at timestamptz,
            last_attempt_at timestamptz,
            last_failure_code varchar(80),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (user_id)
        );

        CREATE INDEX ix_subscription_billing_due
            ON app.subscription_billing_settings (next_renewal_at)
            WHERE auto_renew_enabled;

        CREATE TRIGGER trg_wallet_top_ups_updated_at
        BEFORE UPDATE ON app.wallet_top_ups
        FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();

        CREATE TRIGGER trg_subscription_billing_settings_updated_at
        BEFORE UPDATE ON app.subscription_billing_settings
        FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.subscription_billing_settings")
    op.execute("DROP TABLE IF EXISTS app.wallet_top_ups")
