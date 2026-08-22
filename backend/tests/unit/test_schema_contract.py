from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPOSITORY_ROOT / "database" / "schema.sql"
MIGRATION_PATH = (
    REPOSITORY_ROOT / "backend" / "alembic" / "versions" / "20260822_0001_initial_schema.py"
)


def test_reference_schema_is_frozen_into_initial_migration() -> None:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    expected_hash = re.search(r'SCHEMA_SHA256 = "([a-f0-9]{64})"', migration)

    assert expected_hash is not None
    assert sha256(SCHEMA_PATH.read_bytes()).hexdigest() == expected_hash.group(1)


def test_reference_schema_has_expected_table_count() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    assert len(re.findall(r"^CREATE TABLE ", schema, flags=re.MULTILINE)) == 39
