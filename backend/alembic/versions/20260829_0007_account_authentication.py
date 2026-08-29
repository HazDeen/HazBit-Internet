"""Add password, Google and verified Telegram authentication.

Revision ID: 20260829_0007
Revises: 20260829_0006
Create Date: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260829_0007"
down_revision: str | None = "20260829_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE app.password_credentials (
            user_id uuid PRIMARY KEY REFERENCES app.users(id) ON DELETE CASCADE,
            password_hash text NOT NULL,
            changed_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE app.google_accounts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL UNIQUE REFERENCES app.users(id) ON DELETE CASCADE,
            google_subject varchar(255) NOT NULL UNIQUE,
            email citext NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE app.registration_challenges (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            token_hash bytea NOT NULL UNIQUE,
            email citext NOT NULL,
            public_name varchar(120) NOT NULL,
            password_hash text NOT NULL,
            telegram_user_id bigint,
            telegram_username citext,
            telegram_first_name varchar(255),
            telegram_last_name varchar(255),
            telegram_language_code varchar(16),
            requested_ip inet,
            device_fingerprint_hash bytea,
            email_verified_at timestamptz,
            telegram_verified_at timestamptz,
            consumed_at timestamptz,
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (expires_at > created_at)
        );
        CREATE INDEX ix_registration_challenges_email_active
            ON app.registration_challenges (email, expires_at)
            WHERE consumed_at IS NULL;

        CREATE TABLE app.telegram_login_challenges (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            token_hash bytea NOT NULL UNIQUE,
            telegram_user_id bigint NOT NULL,
            requested_ip inet,
            device_fingerprint_hash bytea,
            approved_at timestamptz,
            consumed_at timestamptz,
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (expires_at > created_at)
        );
        CREATE INDEX ix_telegram_login_challenges_active
            ON app.telegram_login_challenges (telegram_user_id, expires_at)
            WHERE consumed_at IS NULL;

        CREATE TRIGGER trg_google_accounts_updated_at
        BEFORE UPDATE ON app.google_accounts
        FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.telegram_login_challenges")
    op.execute("DROP TABLE IF EXISTS app.registration_challenges")
    op.execute("DROP TABLE IF EXISTS app.google_accounts")
    op.execute("DROP TABLE IF EXISTS app.password_credentials")
