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
    CapEvaluation,
    SessionLengthCap,
    cap_from_session,
    evaluate_per_dispatch_cap,
    evaluate_trigger_fraction,
    is_at_or_past_cap,
    is_in_conclude_phase,
    should_exit_conclude_on_extension,
    should_finalize_conclude_phase,
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


# ---------------------------------------------------------------------------
# evaluate_per_dispatch_cap (loop call-site contract)
# ---------------------------------------------------------------------------


def test_per_dispatch_no_op_when_inactive() -> None:
    cap = SessionLengthCap()
    out = evaluate_per_dispatch_cap(
        cap, elapsed_turns=0, elapsed_seconds=0, already_in_conclude=False
    )
    assert out == CapEvaluation(enter_conclude=False, trigger_dimension=None)


def test_per_dispatch_no_op_when_already_in_conclude() -> None:
    """Once in conclude phase, the trigger transition is recorded only once."""
    cap = SessionLengthCap(kind="turns", turns=20)
    out = evaluate_per_dispatch_cap(
        cap, elapsed_turns=18, elapsed_seconds=0, already_in_conclude=True
    )
    assert out.enter_conclude is False


def test_per_dispatch_enter_on_threshold_cross() -> None:
    cap = SessionLengthCap(kind="turns", turns=20)
    out = evaluate_per_dispatch_cap(
        cap, elapsed_turns=16, elapsed_seconds=0, already_in_conclude=False
    )
    assert out.enter_conclude is True
    assert out.trigger_dimension == "turns"


def test_per_dispatch_below_threshold() -> None:
    cap = SessionLengthCap(kind="turns", turns=20)
    out = evaluate_per_dispatch_cap(
        cap, elapsed_turns=10, elapsed_seconds=0, already_in_conclude=False
    )
    assert out.enter_conclude is False


# ---------------------------------------------------------------------------
# cap_from_session and is_in_conclude_phase (T038 plumbing)
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self, **fields: object) -> None:
        for name, value in fields.items():
            setattr(self, name, value)


def test_cap_from_session_default_inactive() -> None:
    session = _FakeSession(
        length_cap_kind="none",
        length_cap_seconds=None,
        length_cap_turns=None,
        conclude_phase_started_at=None,
        active_seconds_accumulator=None,
    )
    cap = cap_from_session(session)
    assert cap.is_active is False


def test_cap_from_session_active_turns() -> None:
    session = _FakeSession(
        length_cap_kind="turns",
        length_cap_seconds=None,
        length_cap_turns=20,
        conclude_phase_started_at=None,
        active_seconds_accumulator=None,
    )
    cap = cap_from_session(session)
    assert cap.kind == "turns"
    assert cap.turns == 20
    assert cap.is_active is True


def test_is_in_conclude_phase_false_when_null() -> None:
    session = _FakeSession(conclude_phase_started_at=None)
    assert is_in_conclude_phase(session) is False


def test_is_in_conclude_phase_true_when_set() -> None:
    from datetime import datetime

    session = _FakeSession(conclude_phase_started_at=datetime.now())
    assert is_in_conclude_phase(session) is True


# ---------------------------------------------------------------------------
# should_finalize_conclude_phase (FR-011)
# ---------------------------------------------------------------------------


def test_finalize_zero_active_ai_immediately() -> None:
    """No active participants -> finalize on first check (edge case from spec)."""
    assert (
        should_finalize_conclude_phase(current_turn=20, conclude_started_turn=16, active_ai_count=0)
        is True
    )


def test_finalize_below_quota() -> None:
    """At turn 17 with 3 active AIs needing conclude turns, NOT yet finalize."""
    assert (
        should_finalize_conclude_phase(current_turn=17, conclude_started_turn=16, active_ai_count=3)
        is False
    )


def test_finalize_at_quota() -> None:
    """At turn 19 (16 + 3), every active AI has had its conclude turn."""
    assert (
        should_finalize_conclude_phase(current_turn=19, conclude_started_turn=16, active_ai_count=3)
        is True
    )


def test_finalize_past_quota() -> None:
    """Cap-decrease scenario can leave us past the quota (still finalize)."""
    assert (
        should_finalize_conclude_phase(current_turn=25, conclude_started_turn=16, active_ai_count=3)
        is True
    )


# ---------------------------------------------------------------------------
# should_exit_conclude_on_extension (US3 / FR-013)
# ---------------------------------------------------------------------------


def test_extension_lifts_trigger_past_elapsed_exits_conclude() -> None:
    """At turn 19 with cap extended 20 -> 30: 19/30 (63%) is below the 0.80 trigger."""
    new_cap = SessionLengthCap(kind="turns", turns=30)
    assert should_exit_conclude_on_extension(new_cap, elapsed_turns=19, elapsed_seconds=0) is True


def test_small_extension_still_in_conclude() -> None:
    """At turn 19 with cap extended 20 -> 22: 19/22 (86%) still past the 0.80 trigger."""
    new_cap = SessionLengthCap(kind="turns", turns=22)
    assert should_exit_conclude_on_extension(new_cap, elapsed_turns=19, elapsed_seconds=0) is False


def test_extension_clearing_cap_exits_conclude() -> None:
    """Setting kind='none' lifts the cap entirely; loop returns to running."""
    new_cap = SessionLengthCap(kind="none")
    assert should_exit_conclude_on_extension(new_cap, elapsed_turns=999, elapsed_seconds=0) is True


def test_extension_both_dimensions_one_still_past_trigger_stays() -> None:
    """Both caps, time still past trigger -> stay in conclude (OR semantics)."""
    new_cap = SessionLengthCap(kind="both", seconds=600, turns=200)
    # turns 19/200 below trigger, time 600/600 at cap
    out = should_exit_conclude_on_extension(new_cap, elapsed_turns=19, elapsed_seconds=600)
    assert out is False
