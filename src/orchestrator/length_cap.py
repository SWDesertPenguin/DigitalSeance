"""Spec 025 session-length cap evaluator and active-time accumulator.

Per spec 025 plan.md and data-model.md, this module owns:

- The `SessionLengthCap` dataclass (mirrors the five `sessions.length_cap_*`
  + `conclude_phase_started_at` + `active_seconds_accumulator` columns).
- The cap evaluator (`evaluate_trigger_fraction`) called per dispatch from
  `src/orchestrator/loop.py`.
- The `active_seconds_accumulator` update path called at every FSM
  transition that exits the running OR conclude state.
- The cap-decrease disambiguation helper (`detect_decrease_intent`) used
  by the cap-set HTTP endpoint and the MCP tool variant.
- The `CapInterpretation` audit-log discriminator and `CapSetEvent`
  dataclass for `routing_log.cap_set` rows.

This module is added by tasks T019/T020 and grows additional helpers in
US1 (T032), US2 (T051, T053), and US3 (T063) per tasks.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

CapKind = Literal["none", "time", "turns", "both"]
CapInterpretation = Literal["absolute", "relative"]


@dataclass(frozen=True, slots=True)
class SessionLengthCap:
    """Per-session cap state — mirrors the five sessions.length_cap_* columns.

    Defaults reflect the FR-001 default `length_cap_kind='none'`; an
    unconfigured session round-trips through this dataclass with the same
    pre-feature behavior (SC-001).
    """

    kind: CapKind = "none"
    seconds: int | None = None
    turns: int | None = None
    conclude_phase_started_at: datetime | None = None
    active_seconds_accumulator: int | None = None

    @property
    def is_active(self) -> bool:
        """True when at least one dimension is set; cap-evaluation runs only when True."""
        return self.kind != "none"


@dataclass(frozen=True, slots=True)
class CapSetEvent:
    """`routing_log.cap_set` row payload per contracts/routing-log-reasons.md.

    `interpretation` is non-null only when the cap-set involved a cap-decrease
    that triggered the FR-026 disambiguation flow.
    """

    session_id: str
    old_cap: SessionLengthCap
    new_cap: SessionLengthCap
    interpretation: CapInterpretation | None
    actor_id: str
    at: datetime


# Default trigger fraction (overridable via SACP_CONCLUDE_PHASE_TRIGGER_FRACTION).
DEFAULT_TRIGGER_FRACTION = 0.80


def evaluate_trigger_fraction(
    cap: SessionLengthCap,
    *,
    elapsed_turns: int,
    elapsed_seconds: int,
    trigger_fraction: float = DEFAULT_TRIGGER_FRACTION,
) -> str | None:
    """Return the dimension that crossed its trigger fraction, or None.

    Per FR-005 / FR-006 OR semantics: when both dimensions are set,
    whichever crosses first triggers the conclude phase. Returns:

    - ``"turns"`` if the turn cap's trigger fraction was crossed first.
    - ``"time"`` if the time cap's trigger fraction was crossed first.
    - ``"both"`` if both were already past trigger at evaluation time
      (rare; the same-dispatch edge case noted in
      ``contracts/routing-log-reasons.md`` for ``conclude_phase_entered``).
    - ``None`` if no dimension has crossed (or the cap is inactive).

    Returns ``None`` immediately when ``cap.is_active`` is False so the
    SC-001 short-circuit holds and no spec 025 evaluation runs on
    default-cap sessions.
    """
    if not cap.is_active:
        return None
    turns_crossed = _dimension_crossed(cap.turns, elapsed_turns, trigger_fraction)
    time_crossed = _dimension_crossed(cap.seconds, elapsed_seconds, trigger_fraction)
    if turns_crossed and time_crossed:
        return "both"
    if turns_crossed:
        return "turns"
    if time_crossed:
        return "time"
    return None


def _dimension_crossed(cap_value: int | None, elapsed: int, fraction: float) -> bool:
    """True when this dimension's elapsed counter crosses fraction * cap."""
    if cap_value is None:
        return False
    return elapsed >= cap_value * fraction


def is_at_or_past_cap(
    cap: SessionLengthCap,
    *,
    elapsed_turns: int,
    elapsed_seconds: int,
) -> bool:
    """True when elapsed is at or past 100% on any set dimension.

    Used to drive the FR-012 auto-pause path: once the last conclude turn
    completes AND elapsed is at or past 100%, the loop transitions to
    paused with `routing_log.reason='auto_pause_on_cap'`.
    """
    if not cap.is_active:
        return False
    if cap.turns is not None and elapsed_turns >= cap.turns:
        return True
    return cap.seconds is not None and elapsed_seconds >= cap.seconds


def cap_from_session(session: object) -> SessionLengthCap:
    """Build a SessionLengthCap from a Session row.

    Loop call sites pass in the live session row; this helper isolates
    the field-reading so future schema renames touch one place.
    """
    return SessionLengthCap(
        kind=getattr(session, "length_cap_kind", "none") or "none",
        seconds=getattr(session, "length_cap_seconds", None),
        turns=getattr(session, "length_cap_turns", None),
        conclude_phase_started_at=getattr(session, "conclude_phase_started_at", None),
        active_seconds_accumulator=getattr(session, "active_seconds_accumulator", None),
    )


def is_in_conclude_phase(session: object) -> bool:
    """True when the session row's `conclude_phase_started_at` is non-null.

    The persistence-layer marker for conclude-phase membership; once set,
    every dispatch injects the Tier 4 delta and the cadence falls to floor.
    Cleared on US3's `conclude_phase_exited` transition.
    """
    return getattr(session, "conclude_phase_started_at", None) is not None


def should_finalize_conclude_phase(
    *,
    current_turn: int,
    conclude_started_turn: int,
    active_ai_count: int,
) -> bool:
    """True when every active AI has had its one conclude turn (FR-011).

    Counts turns dispatched since the conclude phase started. When that
    count meets or exceeds the number of active AIs at conclude start,
    the next iteration triggers the final summarizer + auto-pause.
    """
    if active_ai_count <= 0:
        return True
    return (current_turn - conclude_started_turn) >= active_ai_count


@dataclass(frozen=True, slots=True)
class CapEvaluation:
    """Outcome of one per-dispatch cap-check (T032 / T033 plumbing).

    `enter_conclude` is True when the loop should transition running -> conclude
    on this iteration. `trigger_dimension` names which cap dimension crossed
    (`'turns'` / `'time'` / `'both'`) for the routing-log row. Both fields
    are None on no-op evaluations (cap inactive OR threshold not crossed OR
    already in conclude phase).
    """

    enter_conclude: bool
    trigger_dimension: str | None


def evaluate_per_dispatch_cap(
    cap: SessionLengthCap,
    *,
    elapsed_turns: int,
    elapsed_seconds: int,
    already_in_conclude: bool,
    trigger_fraction: float = DEFAULT_TRIGGER_FRACTION,
) -> CapEvaluation:
    """Compute the per-dispatch FSM decision for `running -> conclude`.

    Pure function so the loop call site is a single conditional and the
    decision is unit-testable without DB or routing_log fakes. Returns
    a no-op evaluation when ``already_in_conclude`` is True so the
    transition is recorded exactly once per phase entry.
    """
    if already_in_conclude or not cap.is_active:
        return CapEvaluation(enter_conclude=False, trigger_dimension=None)
    dim = evaluate_trigger_fraction(
        cap,
        elapsed_turns=elapsed_turns,
        elapsed_seconds=elapsed_seconds,
        trigger_fraction=trigger_fraction,
    )
    if dim is None:
        return CapEvaluation(enter_conclude=False, trigger_dimension=None)
    return CapEvaluation(enter_conclude=True, trigger_dimension=dim)
