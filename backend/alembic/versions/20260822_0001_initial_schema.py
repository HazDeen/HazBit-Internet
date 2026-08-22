"""Create the STEP 2 business schema.

Revision ID: 20260822_0001
Revises: None
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path

from alembic import op

revision: str = "20260822_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_SHA256 = "6aeb940b7a0631005cb171acd969d1e94987c810bc78eab4c2b637007e4d91e5"


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[3] / "database" / "schema.sql"


def _load_schema() -> str:
    path = _schema_path()
    content = path.read_bytes()
    actual_hash = sha256(content).hexdigest()
    if actual_hash != SCHEMA_SHA256:
        raise RuntimeError(
            "database/schema.sql changed after the initial migration was frozen; "
            "create a new Alembic revision instead"
        )

    lines = content.decode("utf-8").splitlines()
    try:
        begin_index = lines.index("BEGIN;")
        commit_index = len(lines) - 1 - lines[::-1].index("COMMIT;")
    except ValueError as exc:
        raise RuntimeError("reference schema must be wrapped in BEGIN/COMMIT") from exc
    if begin_index >= commit_index:
        raise RuntimeError("reference schema must be wrapped in BEGIN/COMMIT")
    return "\n".join(lines[begin_index + 1 : commit_index]).strip()


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        _load_schema(),
        execution_options={"no_parameters": True},
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS app CASCADE")
