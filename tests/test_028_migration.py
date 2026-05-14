# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 alembic 024 migration tests (T010 of tasks.md).

Static analysis of `alembic/versions/024_capcom_routing_scope.py`. DB-free —
imports the migration module and inspects its source against the spec 028
data-model contract. The DB-backed upgrade exercise is covered by the
per-test FastAPI fixture in conftest.py (which builds the schema from the
raw DDL mirror updated alongside this migration per
`feedback_test_schema_mirror`).
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_MIGRATION_PATH = REPO_ROOT / "alembic" / "versions" / "024_capcom_routing_scope.py"


def _load() -> object:
    spec = importlib.util.spec_from_file_location("alembic_024", _MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _upgrade_source() -> str:
    return inspect.getsource(_load().upgrade)


def test_revision_metadata():
    mod = _load()
    assert mod.revision == "024"
    assert mod.down_revision == "023"
    assert mod.branch_labels is None
    assert mod.depends_on is None


def test_forward_only_downgrade():
    """Per Constitution §6 + 001 §FR-017 the downgrade body is pass."""
    mod = _load()
    src = inspect.getsource(mod.downgrade)
    assert "    pass" in src


def test_adds_messages_kind_with_check_constraint():
    src = _upgrade_source()
    assert "ALTER TABLE messages ADD COLUMN kind" in src
    assert "DEFAULT 'utterance'" in src
    assert "'capcom_relay'" in src
    assert "'capcom_query'" in src


def test_adds_messages_visibility_with_check_constraint():
    src = _upgrade_source()
    assert "ALTER TABLE messages ADD COLUMN visibility" in src
    assert "DEFAULT 'public'" in src
    assert "'capcom_only'" in src


def test_adds_sessions_capcom_participant_id_fk():
    src = _upgrade_source()
    assert "ALTER TABLE sessions ADD COLUMN capcom_participant_id" in src
    assert "REFERENCES participants(id)" in src


def test_creates_partial_unique_index():
    src = _upgrade_source()
    assert "CREATE UNIQUE INDEX ux_participants_session_capcom" in src
    assert "WHERE routing_preference = 'capcom'" in src


def test_creates_visibility_covering_index():
    src = _upgrade_source()
    assert "CREATE INDEX idx_messages_visibility" in src
    assert "session_id, visibility, turn_number DESC" in src
