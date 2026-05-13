# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 alembic 018 migration tests (T013 of tasks.md).

Static analysis of `alembic/versions/018_compression_log.py`. DB-free --
imports the migration module and inspects its source / metadata against
the spec 026 data-model contract. The DB-backed upgrade exercise is
covered by the existing test_schema_mirror.py + the per-test migration
fixture in conftest.py (which builds the schema from the raw DDL mirror,
NOT alembic -- per memory `feedback_test_schema_mirror`).

Asserts:

  - Revision metadata: revision='018', down_revision='017',
    branch_labels=None, depends_on=None.
  - Forward-only invariant per Constitution SS6 + 001 SSF-R017:
    downgrade() body is `pass`.
  - upgrade() creates the `compression_log` table with the columns
    documented in data-model.md: id, session_id, turn_id,
    participant_id, source_tokens, output_tokens, compressor_id,
    compressor_version, trust_tier, layer, duration_ms, created_at.
  - Two indexes exist: compression_log_session_created_idx and
    compression_log_compressor_created_idx.
  - CHECK constraints fire on negative source_tokens, output_tokens,
    and duration_ms (nonneg constraints present in source).
  - compressor_id and trust_tier CHECK constraints reference the
    registered enum sets.
  - upgrade() adds sessions.compression_mode column with DEFAULT 'auto'
    and a seven-value CHECK constraint.
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_MIGRATION_PATH = REPO_ROOT / "alembic" / "versions" / "018_compression_log.py"


def _load() -> object:
    spec = importlib.util.spec_from_file_location("alembic_018", _MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _upgrade_source() -> str:
    return inspect.getsource(_load().upgrade)


def _all_source() -> str:
    """Concatenated source of every helper called by upgrade()."""
    mod = _load()
    parts: list[str] = []
    for name in dir(mod):
        obj = getattr(mod, name)
        if callable(obj) and not name.startswith("__"):
            with contextlib.suppress(OSError, TypeError):
                parts.append(inspect.getsource(obj))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Revision metadata
# ---------------------------------------------------------------------------


def test_revision_is_018() -> None:
    mod = _load()
    assert mod.revision == "018"


def test_down_revision_is_017() -> None:
    """Slot 017 is taken by spec 022's detection_events migration."""
    mod = _load()
    assert mod.down_revision == "017"


def test_branch_labels_and_depends_on_are_none() -> None:
    mod = _load()
    assert mod.branch_labels is None
    assert mod.depends_on is None


# ---------------------------------------------------------------------------
# Forward-only invariant (Constitution SS6 + 001 SSFR-017)
# ---------------------------------------------------------------------------


def test_downgrade_is_no_op() -> None:
    """Forward-only per Constitution SS6 + 001 SSFR-017."""
    src = inspect.getsource(_load().downgrade)
    body_lines = [
        line.strip()
        for line in src.splitlines()[1:]
        if line.strip() and not line.strip().startswith("#")
    ]
    body_lines = [line for line in body_lines if not line.startswith(('"""', "'''"))]
    assert "pass" in body_lines


# ---------------------------------------------------------------------------
# compression_log table columns
# ---------------------------------------------------------------------------


def test_creates_compression_log_table() -> None:
    src = _all_source().upper()
    assert "COMPRESSION_LOG" in src


def test_compression_log_has_bigserial_id() -> None:
    src = _all_source()
    assert "id" in src.lower()
    assert "BigInteger" in src or "BIGSERIAL" in src.upper() or "biginteger" in src.lower()


def test_compression_log_has_session_id_column() -> None:
    src = _all_source()
    assert "session_id" in src


def test_compression_log_has_turn_id_column() -> None:
    src = _all_source()
    assert "turn_id" in src


def test_compression_log_has_participant_id_column() -> None:
    src = _all_source()
    assert "participant_id" in src


def test_compression_log_has_source_tokens_column() -> None:
    src = _all_source()
    assert "source_tokens" in src


def test_compression_log_has_output_tokens_column() -> None:
    src = _all_source()
    assert "output_tokens" in src


def test_compression_log_has_compressor_id_column() -> None:
    src = _all_source()
    assert "compressor_id" in src


def test_compression_log_has_compressor_version_column() -> None:
    src = _all_source()
    assert "compressor_version" in src


def test_compression_log_has_trust_tier_column() -> None:
    src = _all_source()
    assert "trust_tier" in src


def test_compression_log_has_layer_column() -> None:
    src = _all_source()
    assert '"layer"' in src or 'Column("layer"' in src or "'layer'" in src


def test_compression_log_has_duration_ms_column() -> None:
    src = _all_source()
    assert "duration_ms" in src


def test_compression_log_has_created_at_column() -> None:
    src = _all_source()
    assert "created_at" in src


# ---------------------------------------------------------------------------
# compression_log indexes
# ---------------------------------------------------------------------------


def test_session_created_index_exists() -> None:
    """(session_id, created_at DESC) index for the primary cross-spec read pattern."""
    src = _all_source()
    assert "compression_log_session_created_idx" in src


def test_compressor_created_index_exists() -> None:
    """(compressor_id, created_at DESC) index for spec 016 metrics group-by."""
    src = _all_source()
    assert "compression_log_compressor_created_idx" in src


# ---------------------------------------------------------------------------
# CHECK constraints -- nonneg + enum
# ---------------------------------------------------------------------------


def test_source_tokens_nonneg_check_present() -> None:
    src = _all_source()
    assert "source_tokens >= 0" in src


def test_output_tokens_nonneg_check_present() -> None:
    src = _all_source()
    assert "output_tokens >= 0" in src


def test_duration_ms_nonneg_check_present() -> None:
    src = _all_source()
    assert "duration_ms >= 0" in src


def test_trust_tier_enum_check_present() -> None:
    """trust_tier constrained to system/facilitator/participant_supplied."""
    src = _all_source()
    assert "system" in src
    assert "facilitator" in src
    assert "participant_supplied" in src


def test_compressor_id_enum_check_present() -> None:
    """compressor_id constrained to the five registered compressors."""
    src = _all_source()
    assert "noop" in src
    assert "llmlingua2_mbert" in src
    assert "selective_context" in src
    assert "provence" in src
    assert "layer6" in src


# ---------------------------------------------------------------------------
# sessions.compression_mode column
# ---------------------------------------------------------------------------


def test_adds_sessions_compression_mode_column() -> None:
    src = _all_source()
    assert "compression_mode" in src


def test_compression_mode_has_auto_default() -> None:
    src = _all_source()
    assert "'auto'" in src or "auto" in src


def test_compression_mode_enum_check_covers_seven_values() -> None:
    """Seven-value enum per FR-026: auto, off, noop, llmlingua2_mbert,
    selective_context, provence, layer6."""
    src = _all_source()
    for expected in (
        "auto",
        "off",
        "noop",
        "llmlingua2_mbert",
        "selective_context",
        "provence",
        "layer6",
    ):
        assert expected in src, f"Missing compression_mode enum value: {expected}"


# ---------------------------------------------------------------------------
# upgrade() composes the three helpers
# ---------------------------------------------------------------------------


def test_upgrade_calls_all_three_helpers() -> None:
    """upgrade() composes _create_compression_log_table,
    _create_compression_log_indexes, _add_compression_mode_column."""
    src = _upgrade_source()
    assert "_create_compression_log_table" in src
    assert "_create_compression_log_indexes" in src
    assert "_add_compression_mode_column" in src
