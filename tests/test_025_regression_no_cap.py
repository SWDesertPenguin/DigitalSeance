"""Spec 025 SC-001 regression canary (T023 of tasks.md).

Architectural assertion: when `length_cap_kind='none'` (the FR-001 default),
no spec 025 code path fires. Pre-feature loop behavior is preserved.

This canary lands BEFORE the US1 conclude-phase code so any subsequent
"additive when unset" leak surfaces immediately. Tests grow as US1+
implementation lands; the file's CURRENT job is the architectural shape:

- The `SessionLengthCap` dataclass round-trips with `kind='none'`,
  `seconds=None`, `turns=None`.
- `is_active` returns False on a default-constructed cap.
- A future per-dispatch cap-check (US1 T032) MUST short-circuit on
  `cap.is_active is False` — once that helper lands, this test file
  gains the corresponding architectural assertion. Until then the
  shape is the canary.
"""

from __future__ import annotations

from src.orchestrator.length_cap import SessionLengthCap


def test_default_cap_is_inactive() -> None:
    """SC-001: default-constructed cap matches FR-001 'none' default and short-circuits."""
    cap = SessionLengthCap()
    assert cap.kind == "none"
    assert cap.seconds is None
    assert cap.turns is None
    assert cap.is_active is False


def test_explicit_kind_none_is_inactive() -> None:
    """An explicit kind='none' (e.g., from a session row) also short-circuits."""
    cap = SessionLengthCap(kind="none", seconds=None, turns=None)
    assert cap.is_active is False


def test_kind_time_is_active() -> None:
    """A configured cap activates the evaluator path."""
    cap = SessionLengthCap(kind="time", seconds=1800)
    assert cap.is_active is True


def test_kind_turns_is_active() -> None:
    cap = SessionLengthCap(kind="turns", turns=20)
    assert cap.is_active is True


def test_kind_both_is_active() -> None:
    cap = SessionLengthCap(kind="both", seconds=1800, turns=20)
    assert cap.is_active is True
