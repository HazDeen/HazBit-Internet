"""Add staff roles, granular permissions and secure invitations.

Revision ID: 20260829_0006
Revises: 20260828_0005
Create Date: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260829_0006"
down_revision: str | None = "20260828_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE app.user_roles DROP CONSTRAINT user_roles_role_check;
        ALTER TABLE app.user_roles ADD CONSTRAINT user_roles_role_check
            CHECK (role IN (
                'super_admin', 'admin', 'support', 'network', 'finance', 'content', 'user'
            ));

        CREATE TABLE app.user_permissions (
            user_id uuid NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
            permission varchar(120) NOT NULL,
            granted_by uuid REFERENCES app.users(id) ON DELETE SET NULL,
            granted_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, permission),
            CHECK (permission IN (
                'dashboard.read', 'users.read', 'users.manage',
                'subscriptions.read', 'subscriptions.manage',
                'payments.read', 'payments.review',
                'tickets.read', 'tickets.reply', 'tickets.manage',
                'promotions.manage', 'plans.manage', 'families.manage',
                'vpn.read', 'vpn.nodes.manage', 'settings.read', 'staff.manage'
            ))
        );

        CREATE INDEX ix_user_permissions_permission
            ON app.user_permissions (permission, user_id);

        CREATE TABLE app.staff_invitations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email citext NOT NULL,
            token_hash bytea NOT NULL UNIQUE,
            roles jsonb NOT NULL CHECK (jsonb_typeof(roles) = 'array'),
            permissions jsonb NOT NULL DEFAULT '[]'::jsonb
                CHECK (jsonb_typeof(permissions) = 'array'),
            invited_by_user_id uuid NOT NULL REFERENCES app.users(id) ON DELETE RESTRICT,
            accepted_by_user_id uuid REFERENCES app.users(id) ON DELETE SET NULL,
            expires_at timestamptz NOT NULL,
            accepted_at timestamptz,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (expires_at > created_at),
            CHECK (accepted_at IS NULL OR revoked_at IS NULL)
        );

        CREATE INDEX ix_staff_invitations_pending_email
            ON app.staff_invitations (email, expires_at)
            WHERE accepted_at IS NULL AND revoked_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS app.staff_invitations;
        DROP TABLE IF EXISTS app.user_permissions;
        ALTER TABLE app.user_roles DROP CONSTRAINT user_roles_role_check;
        ALTER TABLE app.user_roles ADD CONSTRAINT user_roles_role_check
            CHECK (role IN ('super_admin', 'admin', 'support', 'user'));
        """
    )
