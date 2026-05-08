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


def effective_active_seconds(session: object) -> int:
    """Spec 025 FR-002 elapsed-time read for cap evaluation.

    Returns the durable `active_seconds_accumulator` when set, else
    falls back to `(now() - created_at)`. The fallback ignores pause
    time; the fully pause-aware accumulator lands in a follow-up
    commit under T051/T052. For the canonical "set time cap, watch
    it fire at trigger fraction" path the fallback is correct.
    """
    from datetime import UTC, datetime

    accumulator = getattr(session, "active_seconds_accumulator", None)
    if accumulator is not None:
        return int(accumulator)
    created = getattr(session, "created_at", None)
    if created is None:
        return 0
    if created.tzinfo is not None:
        now = datetime.now(UTC)
    else:
        # Naive datetime in fixture/legacy code; compare in naive UTC.
        now = datetime.now(UTC).replace(tzinfo=None)
    return int((now - created).total_seconds())


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
class CapUpdatePlan:
    """Resolved cap-set request — values are committed as-is.

    Returned by `detect_decrease_intent` when no disambiguation is needed
    (no decrease, or the caller supplied an explicit `interpretation`).
    """

    new_kind: CapKind
    new_seconds: int | None
    new_turns: int | None
    interpretation: CapInterpretation | None


@dataclass(frozen=True, slots=True)
class DisambiguationRequired:
    """Cap-set requires the facilitator to choose absolute vs relative.

    Per spec 025 FR-026 + contracts/cap-set-endpoint.md the endpoint
    returns 409 with both option payloads; the facilitator's re-POST
    sets `interpretation` explicitly.
    """

    submitted_kind: CapKind
    submitted_seconds: int | None
    submitted_turns: int | None
    current_turns: int
    current_seconds: int
    absolute_effective_turns: int | None
    absolute_effective_seconds: int | None
    relative_effective_turns: int | None
    relative_effective_seconds: int | None


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


def detect_decrease_intent(
    *,
    submitted_kind: CapKind,
    submitted_seconds: int | None,
    submitted_turns: int | None,
    current_turns: int,
    current_seconds: int,
    interpretation: CapInterpretation | None,
) -> CapUpdatePlan | DisambiguationRequired:
    """FR-026: classify a cap-set into commit-ready plan or 409 disambiguation.

    Returns ``CapUpdatePlan`` when no disambiguation is needed (no
    decrease, OR explicit ``interpretation``, OR ``kind='none'``).
    Returns ``DisambiguationRequired`` when any submitted dimension is
    below current elapsed AND no ``interpretation`` is supplied; the
    transport layer renders both options.
    """
    submitted = (submitted_kind, submitted_seconds, submitted_turns)
    current = (current_turns, current_seconds)
    if submitted_kind == "none" or interpretation is not None:
        return _build_plan(submitted, current, interpretation)
    if not _is_decrease(submitted_seconds, submitted_turns, current_turns, current_seconds):
        return _build_plan(submitted, current, None)
    return _build_disambiguation(submitted, current)


def _is_decrease(
    submitted_seconds: int | None,
    submitted_turns: int | None,
    current_turns: int,
    current_seconds: int,
) -> bool:
    """True when any submitted dimension is at or below current elapsed."""
    if submitted_turns is not None and submitted_turns <= current_turns:
        return True
    return submitted_seconds is not None and submitted_seconds <= current_seconds


def _build_plan(
    submitted: tuple[CapKind, int | None, int | None],
    current: tuple[int, int],
    interpretation: CapInterpretation | None,
) -> CapUpdatePlan:
    """Compute the effective cap values given the resolved interpretation."""
    submitted_kind, submitted_seconds, submitted_turns = submitted
    current_turns, current_seconds = current
    if interpretation == "relative":
        new_seconds = current_seconds + submitted_seconds if submitted_seconds is not None else None
        new_turns = current_turns + submitted_turns if submitted_turns is not None else None
        return CapUpdatePlan(
            new_kind=submitted_kind,
            new_seconds=new_seconds,
            new_turns=new_turns,
            interpretation="relative",
        )
    return CapUpdatePlan(
        new_kind=submitted_kind,
        new_seconds=submitted_seconds,
        new_turns=submitted_turns,
        interpretation=interpretation,
    )


def _build_disambiguation(
    submitted: tuple[CapKind, int | None, int | None],
    current: tuple[int, int],
) -> DisambiguationRequired:
    """Render the 409 payload object — both options + current elapsed."""
    submitted_kind, submitted_seconds, submitted_turns = submitted
    current_turns, current_seconds = current
    rel_turns = current_turns + submitted_turns if submitted_turns is not None else None
    rel_seconds = current_seconds + submitted_seconds if submitted_seconds is not None else None
    return DisambiguationRequired(
        submitted_kind=submitted_kind,
        submitted_seconds=submitted_seconds,
        submitted_turns=submitted_turns,
        current_turns=current_turns,
        current_seconds=current_seconds,
        absolute_effective_turns=submitted_turns,
        absolute_effective_seconds=submitted_seconds,
        relative_effective_turns=rel_turns,
        relative_effective_seconds=rel_seconds,
    )


def should_exit_conclude_on_extension(
    cap: SessionLengthCap,
    *,
    elapsed_turns: int,
    elapsed_seconds: int,
    trigger_fraction: float = DEFAULT_TRIGGER_FRACTION,
) -> bool:
    """Spec 025 FR-013: True when the new cap moves the trigger past current elapsed.

    Used by the cap-set endpoint to decide whether a cap update should
    transition the loop back to running phase. The check is the inverse
    of the entry trigger: the extension exits conclude phase only if
    NEITHER dimension is currently past its trigger fraction (the
    extension actually pulled both back below threshold).

    Pure function so the caller decides the transition; the helper
    just answers the geometric question.
    """
    if not cap.is_active:
        return True  # Cleared cap -> no longer in conclude
    return (
        evaluate_trigger_fraction(
            cap,
            elapsed_turns=elapsed_turns,
            elapsed_seconds=elapsed_seconds,
            trigger_fraction=trigger_fraction,
        )
        is None
    )


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
