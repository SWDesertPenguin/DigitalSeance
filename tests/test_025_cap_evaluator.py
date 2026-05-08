"""Spec 025 cap evaluator + helpers (T032 + parts of T024/T028 of tasks.md).

Pure-function unit tests for `evaluate_trigger_fraction` and
`is_at_or_past_cap` — these are the architectural contract tests
covered by US1 and US2 acceptance scenarios. Loop-integration tests
that drive a real session through to conclude phase + auto-pause are
deferred to the integration test file in Phase 8 (DB-gated, drives
the full `execute_turn` cycle).

Covers:

- US1 acceptance #1 (FSM trigger criterion via the cap evaluator).
- FR-005 trigger-fraction default of 0.80; per-call override.
- FR-006 OR semantics on the both-dimensions cap.
- SC-001 short-circuit when cap is inactive.
"""

from __future__ import annotations

import pytest

from src.orchestrator.length_cap import (
    DEFAULT_TRIGGER_FRACTION,
    SessionLengthCap,
    evaluate_trigger_fraction,
    is_at_or_past_cap,
)

# ---------------------------------------------------------------------------
# evaluate_trigger_fraction
# ---------------------------------------------------------------------------


def test_default_fraction_is_eighty_percent() -> None:
    """FR-005 default trigger fraction is 0.80."""
    assert DEFAULT_TRIGGER_FRACTION == 0.80


def test_inactive_cap_returns_none() -> None:
    """SC-001: kind='none' short-circuits before any evaluation."""
    cap = SessionLengthCap()  # default kind='none'
    assert evaluate_trigger_fraction(cap, elapsed_turns=10000, elapsed_seconds=1000000) is None


def test_turns_cap_below_trigger() -> None:
    """At 15/20 turns (75%), the 0.80 trigger has not yet crossed."""
    cap = SessionLengthCap(kind="turns", turns=20)
    assert evaluate_trigger_fraction(cap, elapsed_turns=15, elapsed_seconds=0) is None


def test_turns_cap_at_trigger() -> None:
    """At 16/20 turns (80%), the 0.80 trigger crosses; reason='turns'."""
    cap = SessionLengthCap(kind="turns", turns=20)
    assert evaluate_trigger_fraction(cap, elapsed_turns=16, elapsed_seconds=0) == "turns"


def test_turns_cap_past_trigger() -> None:
    """At 19/20 turns (95%), still 'turns' (cap-decrease scenarios use this path)."""
    cap = SessionLengthCap(kind="turns", turns=20)
    assert evaluate_trigger_fraction(cap, elapsed_turns=19, elapsed_seconds=0) == "turns"


def test_time_cap_below_trigger() -> None:
    """At 1400/1800s (~78%), under the 0.80 trigger."""
    cap = SessionLengthCap(kind="time", seconds=1800)
    assert evaluate_trigger_fraction(cap, elapsed_turns=0, elapsed_seconds=1400) is None


def test_time_cap_at_trigger() -> None:
    """At 1440/1800s (80%), the 0.80 trigger crosses; reason='time'."""
    cap = SessionLengthCap(kind="time", seconds=1800)
    assert evaluate_trigger_fraction(cap, elapsed_turns=0, elapsed_seconds=1440) == "time"


# ---------------------------------------------------------------------------
# FR-006 OR semantics for kind='both'
# ---------------------------------------------------------------------------


def test_both_neither_crossed_returns_none() -> None:
    cap = SessionLengthCap(kind="both", seconds=1800, turns=20)
    assert evaluate_trigger_fraction(cap, elapsed_turns=10, elapsed_seconds=600) is None


def test_both_only_turns_crossed_returns_turns() -> None:
    """Turn cap crosses first (16/20), time cap below (600/1800)."""
    cap = SessionLengthCap(kind="both", seconds=1800, turns=20)
    assert evaluate_trigger_fraction(cap, elapsed_turns=16, elapsed_seconds=600) == "turns"


def test_both_only_time_crossed_returns_time() -> None:
    """Time cap crosses first (1500/1800), turn cap below (10/20)."""
    cap = SessionLengthCap(kind="both", seconds=1800, turns=20)
    assert evaluate_trigger_fraction(cap, elapsed_turns=10, elapsed_seconds=1500) == "time"


def test_both_dimensions_simultaneously_returns_both() -> None:
    """Both already past trigger at same evaluation; reason='both'."""
    cap = SessionLengthCap(kind="both", seconds=1800, turns=20)
    assert evaluate_trigger_fraction(cap, elapsed_turns=18, elapsed_seconds=1500) == "both"


# ---------------------------------------------------------------------------
# Per-call trigger fraction override
# ---------------------------------------------------------------------------


def test_override_lower_fraction_triggers_earlier() -> None:
    """Operator drops trigger to 0.50; 11/20 (55%) crosses."""
    cap = SessionLengthCap(kind="turns", turns=20)
    assert (
        evaluate_trigger_fraction(cap, elapsed_turns=11, elapsed_seconds=0, trigger_fraction=0.50)
        == "turns"
    )


def test_override_higher_fraction_triggers_later() -> None:
    """Operator raises trigger to 0.95; 16/20 (80%) does NOT cross."""
    cap = SessionLengthCap(kind="turns", turns=20)
    assert (
        evaluate_trigger_fraction(cap, elapsed_turns=16, elapsed_seconds=0, trigger_fraction=0.95)
        is None
    )


# ---------------------------------------------------------------------------
# is_at_or_past_cap (FR-012 auto-pause feeder)
# ---------------------------------------------------------------------------


def test_inactive_cap_never_at_cap() -> None:
    cap = SessionLengthCap()
    assert is_at_or_past_cap(cap, elapsed_turns=999999, elapsed_seconds=999999) is False


def test_turns_below_cap() -> None:
    cap = SessionLengthCap(kind="turns", turns=20)
    assert is_at_or_past_cap(cap, elapsed_turns=19, elapsed_seconds=0) is False


def test_turns_at_cap() -> None:
    cap = SessionLengthCap(kind="turns", turns=20)
    assert is_at_or_past_cap(cap, elapsed_turns=20, elapsed_seconds=0) is True


def test_turns_past_cap() -> None:
    """Cap-decrease absolute interpretation can leave elapsed past 100%."""
    cap = SessionLengthCap(kind="turns", turns=20)
    assert is_at_or_past_cap(cap, elapsed_turns=30, elapsed_seconds=0) is True


def test_time_at_cap() -> None:
    cap = SessionLengthCap(kind="time", seconds=1800)
    assert is_at_or_past_cap(cap, elapsed_turns=0, elapsed_seconds=1800) is True


def test_both_either_dimension_triggers_at_cap() -> None:
    """OR semantics for the at-cap predicate as well."""
    cap = SessionLengthCap(kind="both", seconds=1800, turns=20)
    # turns at cap, time below
    assert is_at_or_past_cap(cap, elapsed_turns=20, elapsed_seconds=600) is True
    # time at cap, turns below
    assert is_at_or_past_cap(cap, elapsed_turns=10, elapsed_seconds=1800) is True
    # neither at cap
    assert is_at_or_past_cap(cap, elapsed_turns=10, elapsed_seconds=600) is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("turns", [0, 1, 5])
def test_negligible_elapsed_does_not_trigger(turns: int) -> None:
    cap = SessionLengthCap(kind="turns", turns=20)
    assert evaluate_trigger_fraction(cap, elapsed_turns=turns, elapsed_seconds=0) is None
