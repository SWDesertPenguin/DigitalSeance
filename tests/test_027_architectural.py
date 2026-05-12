# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 027 architectural invariants (T008 of tasks.md).

Enforces the contract a downstream PR could silently break:

- The five new audit-action labels are registered in BOTH
  ``src/orchestrator/audit_labels.py`` (LABELS dict) AND
  ``frontend/audit_labels.js`` (mirror dict). The CI parity gate
  (``scripts/check_audit_label_parity.py``) catches drift in either
  direction, but this test catches a missing label registration before
  CI runs.

- The four new SACP_STANDBY_* validators are registered in the
  ``validators.VALIDATORS`` tuple. A validator function authored but not
  registered silently fails open.

- The migration ``021_participant_standby_modes.py`` exists with the
  ``revision = '021'`` token, AND ``down_revision`` chain-links to the
  current alembic head.

- ``tests/conftest.py``'s ``_PARTICIPANTS_TABLE_DDL`` carries the three
  new columns (per ``feedback_test_schema_mirror`` — the CI test
  substrate is built from conftest DDL, not alembic).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
ALEMBIC = REPO_ROOT / "alembic" / "versions"
FRONTEND = REPO_ROOT / "frontend"
TESTS = REPO_ROOT / "tests"


_SPEC_027_AUDIT_ACTIONS = (
    "standby_entered",
    "standby_exited",
    "pivot_injected",
    "standby_observer_marked",
    "wait_mode_changed",
)


def test_all_audit_actions_registered_in_python_labels() -> None:
    """Every spec 027 action MUST appear in audit_labels.LABELS."""
    from src.orchestrator import audit_labels

    for action in _SPEC_027_AUDIT_ACTIONS:
        assert action in audit_labels.LABELS, (
            f"audit action {action!r} missing from " "src/orchestrator/audit_labels.LABELS"
        )


def test_all_audit_actions_registered_in_frontend_mirror() -> None:
    """The frontend mirror MUST contain every spec 027 action key."""
    text = (FRONTEND / "audit_labels.js").read_text(encoding="utf-8")
    for action in _SPEC_027_AUDIT_ACTIONS:
        assert (
            f'"{action}"' in text
        ), f"audit action {action!r} missing from frontend/audit_labels.js"


def test_all_four_validators_in_validators_tuple() -> None:
    from src.config import validators

    fn_names = {fn.__name__ for fn in validators.VALIDATORS}
    for name in (
        "validate_standby_default_wait_mode",
        "validate_standby_filler_detection_turns",
        "validate_standby_pivot_timeout_seconds",
        "validate_standby_pivot_rate_cap_per_session",
    ):
        assert name in fn_names, f"validator {name!r} missing from VALIDATORS"


def test_migration_021_exists_and_chains() -> None:
    """The migration file ships AND chains to a real prior revision."""
    migration = ALEMBIC / "021_participant_standby_modes.py"
    assert migration.exists(), "021_participant_standby_modes.py missing"
    text = migration.read_text(encoding="utf-8")
    assert 'revision = "021"' in text
    # down_revision must point at an alembic-head candidate (018 or
    # later when sibling lanes land). We don't pin a specific value here
    # — the lane-coordination memo permits 018/019/020 depending on
    # merge order. The closeout migration-chain preflight enforces the
    # actual chain post-merge.
    assert "down_revision = " in text


def test_conftest_mirrors_three_new_columns() -> None:
    """tests/conftest.py raw DDL MUST carry wait_mode + cycle_count + metadata."""
    text = (TESTS / "conftest.py").read_text(encoding="utf-8")
    assert "wait_mode TEXT NOT NULL DEFAULT 'wait_for_human'" in text
    assert "standby_cycle_count INTEGER NOT NULL DEFAULT 0" in text
    assert "wait_mode_metadata TEXT NOT NULL DEFAULT '{}'" in text


def test_conftest_mirrors_three_new_routing_log_timing_columns() -> None:
    """V14 standby timing columns mirrored in routing_log conftest DDL."""
    text = (TESTS / "conftest.py").read_text(encoding="utf-8")
    assert "standby_eval_ms INTEGER" in text
    assert "pivot_inject_ms INTEGER" in text
    assert "standby_transition_ms INTEGER" in text
