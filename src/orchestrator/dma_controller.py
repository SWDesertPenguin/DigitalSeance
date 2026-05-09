"""Dynamic mode assignment controller (spec 014).

Per-session signal-driven controller that observes a rolling 5-minute
window of session signals (turn rate, convergence derivative, queue
depth, density anomaly rate) and decides ENGAGE / DISENGAGE on top of
spec 013's high-traffic mechanisms.

See:
    - specs/014-dynamic-mode-assignment/spec.md (FR-001..FR-016)
    - specs/014-dynamic-mode-assignment/data-model.md (entities)
    - specs/014-dynamic-mode-assignment/research.md (decisions)
    - specs/014-dynamic-mode-assignment/contracts/audit-events.md
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from src.orchestrator.dma_signals import SignalSource
from src.orchestrator.high_traffic import HighTrafficRuntime, MechanismName
from src.orchestrator.timing import record_stage

log = logging.getLogger(__name__)

# Spec 014 plan.md §"Performance Goals": 12 decisions/minute (one tick / 5s).
DEFAULT_DECISIONS_PER_MINUTE = 12
# Spec 014 §FR-001: rolling 5-minute observation window.
DEFAULT_WINDOW_SECONDS = 300
# Default dwell when env var unset (advisory mode only — see FR-010).
DEFAULT_ADVISORY_DWELL_SECONDS = 120

# Action set per data-model.md §"ModeRecommendation".
Action = Literal["NORMAL", "ENGAGE", "DISENGAGE"]

# Health flags per data-model.md §"ControllerState".
SignalHealthFlag = Literal["AVAILABLE", "UNAVAILABLE", "RATE_LIMITED"]

# Spec-013 mechanism names (auto-apply targets).
ALL_MECHANISMS: tuple[MechanismName, ...] = (
    "batching",
    "convergence_override",
    "observer_downgrade",
)

# All four DMA signal threshold env vars (FR-004 absent-not-zero gate).
_DMA_THRESHOLD_ENV_VARS = (
    "SACP_DMA_TURN_RATE_THRESHOLD_TPM",
    "SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD",
    "SACP_DMA_QUEUE_DEPTH_THRESHOLD",
    "SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD",
)


def auto_mode_enabled() -> bool:
    """True iff ``SACP_AUTO_MODE_ENABLED=true``. Default false (advisory).

    The validator (``validate_auto_mode_enabled``) has already enforced
    well-formedness at startup; this read is a typed projection.
    """
    return os.environ.get("SACP_AUTO_MODE_ENABLED", "").strip() == "true"


def _topology_disables_controller() -> bool:
    """Research §7: SACP_TOPOLOGY=7 disables the controller.

    Forward-proof gate; topology 7 doesn't ship today, but the gate exists
    so deploying a topology-7 selector tomorrow won't surprise operators.
    """
    return os.environ.get("SACP_TOPOLOGY", "").strip() == "7"


def _any_threshold_configured() -> bool:
    """True iff at least one ``SACP_DMA_*_THRESHOLD`` env var is set."""
    for name in _DMA_THRESHOLD_ENV_VARS:
        raw = os.environ.get(name)
        if raw is not None and raw.strip() != "":
            return True
    return False


def _read_dwell_seconds() -> int:
    """Parse ``SACP_DMA_DWELL_TIME_S`` or fall back to advisory default."""
    raw = os.environ.get("SACP_DMA_DWELL_TIME_S")
    if raw is None or raw.strip() == "":
        return DEFAULT_ADVISORY_DWELL_SECONDS
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_ADVISORY_DWELL_SECONDS


# ---------------------------------------------------------------------------
# State containers (data-model.md)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SignalEntry:
    """Single timestamped observation in a signal's ring buffer."""

    timestamp: datetime
    value: float | int


@dataclass(slots=True)
class SessionSignals:
    """Bounded ring buffers — one per signal source — per data-model.md.

    Buffer depth = window_seconds / decision_interval_seconds = ~60 entries
    at the initial 12-dpm cap. Entries are evicted on append once full.
    """

    capacity: int = 60
    turn_rate: deque[SignalEntry] = field(default_factory=deque)
    convergence_derivative: deque[SignalEntry] = field(default_factory=deque)
    queue_depth: deque[SignalEntry] = field(default_factory=deque)
    density_anomaly_count: deque[SignalEntry] = field(default_factory=deque)

    def __post_init__(self) -> None:
        # ``deque(maxlen=...)`` evicts on overflow — exactly the bounded-
        # ring-buffer semantic data-model.md prescribes.
        self.turn_rate = deque(self.turn_rate, maxlen=self.capacity)
        self.convergence_derivative = deque(self.convergence_derivative, maxlen=self.capacity)
        self.queue_depth = deque(self.queue_depth, maxlen=self.capacity)
        self.density_anomaly_count = deque(self.density_anomaly_count, maxlen=self.capacity)

    def buffer_for(self, signal_name: str) -> deque[SignalEntry]:
        """Return the named ring buffer; raises KeyError on unknown name."""
        mapping = {
            "turn_rate": self.turn_rate,
            "convergence_derivative": self.convergence_derivative,
            "queue_depth": self.queue_depth,
            "density_anomaly": self.density_anomaly_count,
        }
        if signal_name not in mapping:
            msg = f"Unknown signal source: {signal_name!r}"
            raise KeyError(msg)
        return mapping[signal_name]

    def append(self, signal_name: str, value: float | int, *, now: datetime) -> None:
        """Append an observation to the named ring buffer."""
        self.buffer_for(signal_name).append(SignalEntry(now, value))

    def values(self, signal_name: str) -> list[float | int]:
        """Return the buffered values (oldest first) for ``evaluate()`` calls."""
        return [e.value for e in self.buffer_for(signal_name)]


@dataclass(slots=True)
class ControllerState:
    """Per-session controller state per data-model.md §"ControllerState".

    Drives dwell-floor calculation, recommendation deduplication, and the
    rate-limited unavailability emission in FR-013.
    """

    last_emitted_action: Action | None = None
    last_transition_at: datetime | None = None
    dwell_floor_at: datetime | None = None
    signal_health: dict[str, SignalHealthFlag] = field(default_factory=dict)
    # Snapshot of `signal_health` BEFORE the current cycle's poll updated it.
    # Audit reads this so `last_known_state` reflects the actual prior state
    # rather than the post-overwrite "UNAVAILABLE" value.
    prior_signal_health: dict[str, SignalHealthFlag] = field(default_factory=dict)
    unavailability_emitted_in_dwell: set[str] = field(default_factory=set)
    throttle_emitted_in_dwell: bool = False
    sustained_below_since: datetime | None = None

    def reset_dwell_emissions(self) -> None:
        """Clear per-dwell rate-limit gates after a transition or expiry."""
        self.unavailability_emitted_in_dwell.clear()
        self.throttle_emitted_in_dwell = False


# ---------------------------------------------------------------------------
# Decision-cycle throttle (research §5)
# ---------------------------------------------------------------------------


class DecisionCycleBudget:
    """Capacity-1 token bucket: 12 decisions/minute = one decision per 5s.

    Drops on overflow rather than queuing (FR-002). Time source is
    ``time.monotonic`` so the cap is robust to wall-clock changes.
    """

    def __init__(self, cap_per_minute: int = DEFAULT_DECISIONS_PER_MINUTE) -> None:
        if cap_per_minute <= 0:
            msg = f"cap_per_minute must be positive; got {cap_per_minute}"
            raise ValueError(msg)
        self._refill_interval_s = 60.0 / cap_per_minute
        self._cap_per_minute = cap_per_minute
        self._next_eligible_at = time.monotonic()
        self._last_acquired_at: float | None = None

    @property
    def cap_per_minute(self) -> int:
        return self._cap_per_minute

    @property
    def refill_interval_s(self) -> float:
        return self._refill_interval_s

    def try_acquire(self) -> bool:
        """True iff a token was available; False = drop (rate cap exceeded)."""
        now = time.monotonic()
        if now < self._next_eligible_at:
            return False
        self._last_acquired_at = now
        self._next_eligible_at = now + self._refill_interval_s
        return True

    def next_eligible_seconds_from_now(self) -> float:
        """Wall-clock seconds until the next acquire would succeed (>= 0)."""
        return max(0.0, self._next_eligible_at - time.monotonic())


# ---------------------------------------------------------------------------
# Decision result (in-memory shape consumed by the emission path)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SignalObservation:
    """Per-trigger observation entry — see data-model.md §"ModeRecommendation"."""

    signal_name: str
    observed_value: float | int
    configured_threshold: float | int


@dataclass(slots=True)
class DecisionOutcome:
    """In-memory result of one decision cycle.

    The controller's emission path translates this into ``mode_recommendation``
    / ``mode_transition`` / ``mode_transition_suppressed`` audit rows.
    """

    decision_at: datetime
    action: Action
    triggers: list[str]
    signal_observations: list[SignalObservation]
    dwell_floor_at: datetime | None
    unavailable_signals: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


class DmaController:
    """Per-session DMA controller — observes, decides, emits.

    Spawned per session in ``loop.py``'s init path; cancelled on teardown.
    The decision cycle wakes at ``decision_interval_seconds`` (= refill
    interval), polls configured signals, applies FR-009 asymmetry, and
    emits audit events on action change. Auto-apply mutates spec-013
    activation flags via ``HighTrafficRuntime`` per research §4.
    """

    def __init__(
        self,
        session_id: str,
        runtime: HighTrafficRuntime,
        signal_sources: Iterable[SignalSource],
        emitter: ModeEmitter | None = None,
        *,
        decisions_per_minute: int = DEFAULT_DECISIONS_PER_MINUTE,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session_id = session_id
        self._runtime = runtime
        self._sources: list[SignalSource] = list(signal_sources)
        self._emitter = emitter
        self._budget = DecisionCycleBudget(cap_per_minute=decisions_per_minute)
        capacity = max(1, window_seconds // max(1, int(self._budget.refill_interval_s)))
        self._signals = SessionSignals(capacity=capacity)
        self._state = ControllerState()
        self._dwell_seconds = _read_dwell_seconds()
        self._auto_mode = auto_mode_enabled()
        self._clock = clock
        self._task: asyncio.Task[None] | None = None
        self._stop_requested = False

    # ----- Lifecycle gates ---------------------------------------------------

    @classmethod
    def is_active_from_env(cls) -> bool:
        """SC-004 + V12 gate: True iff the controller should spawn for this session.

        Returns False when:
            - ``SACP_TOPOLOGY=7`` (research §7 forward-proof gate), or
            - none of the four ``SACP_DMA_*_THRESHOLD`` env vars are set.

        Spec 014's loop integration consults this before constructing the
        controller; FR-015's additive-when-unset contract relies on this gate.
        """
        if _topology_disables_controller():
            log.info(
                "DMA controller disabled: SACP_TOPOLOGY=7 (spec 014 research §7)",
            )
            return False
        return _any_threshold_configured()

    # ----- Decision cycle ----------------------------------------------------

    def evaluate_cycle(self) -> DecisionOutcome | None:
        """Run one decision cycle (synchronous core; called by ``_tick``).

        Returns None when the budget rejected the cycle (throttled). Otherwise
        returns a :class:`DecisionOutcome` describing the proposed action.
        """
        cycle_start = time.monotonic()
        if not self._budget.try_acquire():
            return None
        now = self._clock()
        triggered, observations, unavailable = self._poll_signals(now)
        configured = [s for s in self._sources if s.is_configured()]
        action = self._decide_action(now, configured, triggered)
        outcome = DecisionOutcome(
            decision_at=now,
            action=action,
            triggers=sorted(s.name for s in triggered),
            signal_observations=sorted(observations, key=lambda o: o.signal_name),
            dwell_floor_at=self._state.dwell_floor_at,
            unavailable_signals=unavailable,
        )
        record_stage("dma_controller_eval_ms", int((time.monotonic() - cycle_start) * 1000))
        return outcome

    def _poll_signals(
        self,
        now: datetime,
    ) -> tuple[list[SignalSource], list[SignalObservation], list[str]]:
        """Sample configured sources; return (triggered, observations, unavailable).

        Per FR-004, only sources whose ``is_configured()`` returns True
        contribute. Unavailable sources are recorded for the rate-limited
        ``signal_source_unavailable`` emission path.
        """
        triggered: list[SignalSource] = []
        observations: list[SignalObservation] = []
        unavailable: list[str] = []
        for source in self._sources:
            if not source.is_configured():
                continue
            self._poll_one(source, now, triggered, observations, unavailable)
        return triggered, observations, unavailable

    def _poll_one(
        self,
        source: SignalSource,
        now: datetime,
        triggered: list[SignalSource],
        observations: list[SignalObservation],
        unavailable: list[str],
    ) -> None:
        """Sample one configured signal source and update aggregator lists in place."""
        stage_start = time.monotonic()
        # Snapshot prior state so audit's last_known_state is the pre-overwrite value.
        prior = self._state.signal_health.get(source.name, "AVAILABLE")
        self._state.prior_signal_health[source.name] = prior
        try:
            if not source.is_available():
                self._state.signal_health[source.name] = "UNAVAILABLE"
                unavailable.append(source.name)
                return
            value = source.sample()
            if value is None:
                unavailable.append(source.name)
                return
            self._state.signal_health[source.name] = "AVAILABLE"
            self._signals.append(source.name, value, now=now)
            if source.evaluate(self._signals.values(source.name)):
                threshold = source.threshold()
                if threshold is not None:
                    triggered.append(source)
                    observations.append(SignalObservation(source.name, value, threshold))
        finally:
            record_stage(
                f"dma_signal_{source.name}_ms",
                int((time.monotonic() - stage_start) * 1000),
            )

    def _decide_action(
        self,
        now: datetime,
        configured: list[SignalSource],
        triggered: list[SignalSource],
    ) -> Action:
        """Apply FR-009 asymmetry: ANY trigger → ENGAGE; ALL below for dwell → DISENGAGE."""
        if triggered:
            self._state.sustained_below_since = None
            return "ENGAGE"
        # No signals firing this cycle. Are ALL configured sources below?
        if not configured:
            return "NORMAL"
        if self._state.sustained_below_since is None:
            self._state.sustained_below_since = now
        sustained_for = now - self._state.sustained_below_since
        if sustained_for >= timedelta(seconds=self._dwell_seconds):
            return "DISENGAGE"
        # Sustained-below window not yet full — carry the previous action.
        return self._state.last_emitted_action or "NORMAL"

    # ----- Dwell & auto-apply (FR-007 / FR-008 / FR-011) ---------------------

    def is_dwell_blocking(self, now: datetime) -> bool:
        """True iff a counter-direction transition is blocked by dwell.

        Per FR-007 + data-model.md: dwell_floor_at = last_transition_at +
        SACP_DMA_DWELL_TIME_S. Until ``now >= dwell_floor_at``, the auto-
        apply path emits ``mode_transition_suppressed`` instead of acting.
        """
        if self._state.dwell_floor_at is None:
            return False
        return now < self._state.dwell_floor_at

    def apply_transition(self, action: Action, now: datetime) -> tuple[list[str], list[str]]:
        """Mutate spec-013 activation flags per the decision (auto-apply only).

        Returns (engaged_mechanisms, skipped_mechanisms) — the bookkeeping
        the audit row records. Mechanisms whose env vars are unset always
        land in skipped[]; per the spec edge case the controller skips
        them silently.
        """
        engaged: list[str] = []
        skipped: list[str] = []
        for name in ALL_MECHANISMS:
            if action == "ENGAGE":
                if self._runtime.engage_mechanism(name):
                    engaged.append(name)
                else:
                    skipped.append(name)
            elif action == "DISENGAGE":
                if self._runtime.disengage_mechanism(name):
                    engaged.append(name)
                else:
                    skipped.append(name)
        self._state.last_transition_at = now
        self._state.dwell_floor_at = now + timedelta(seconds=self._dwell_seconds)
        self._state.reset_dwell_emissions()
        return engaged, skipped

    # ----- Convenience accessors used by the emission path -------------------

    @property
    def state(self) -> ControllerState:
        return self._state

    @property
    def runtime(self) -> HighTrafficRuntime:
        return self._runtime

    @property
    def auto_mode(self) -> bool:
        return self._auto_mode

    @property
    def dwell_seconds(self) -> int:
        return self._dwell_seconds

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def budget(self) -> DecisionCycleBudget:
        return self._budget

    @property
    def signals(self) -> SessionSignals:
        return self._signals

    @property
    def configured_signal_names(self) -> list[str]:
        return sorted(s.name for s in self._sources if s.is_configured())

    # ----- async lifecycle ---------------------------------------------------

    async def start(self) -> asyncio.Task[None]:
        """Spawn the per-session asyncio task that drives ``run_decision_cycle``.

        The caller (``ConversationLoop``) stores the returned task on the
        session's runtime context and cancels it in the teardown path
        (research §3 + T015). No-op if the topology gate or unconfigured
        threshold gate would otherwise short-circuit (caller is expected to
        check ``DmaController.is_active_from_env()`` before constructing).
        """
        if self._task is not None and not self._task.done():
            return self._task
        self._stop_requested = False
        self._task = asyncio.create_task(self._run_loop())
        return self._task

    async def stop(self) -> None:
        """Cancel the controller task; idempotent."""
        self._stop_requested = True
        if self._task is None:
            return
        self._task.cancel()
        # Teardown best-effort: any task-level exception is logged at WARNING
        # by the asyncio task layer; we only need the join, not propagation.
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task
        self._task = None

    async def _run_loop(self) -> None:
        """Per-session driver: awakens at decision_interval, runs one cycle.

        Cancellation is best-effort (research §3): an in-flight cycle
        completes before the task exits. New tick after stop() = no-op.
        """
        interval = self._budget.refill_interval_s
        while not self._stop_requested:
            try:
                await run_decision_cycle(self)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — never let the controller take down the loop
                log.exception("DMA decision cycle failed for session %s", self._session_id)
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise


# ---------------------------------------------------------------------------
# Mode emitter — translates DecisionOutcome into audit rows (T009 helpers)
# ---------------------------------------------------------------------------


class ModeEmitter:
    """Adapter over ``LogRepository`` mode_* helpers (T009).

    Holds the session_id + facilitator_id so the controller's emission path
    doesn't have to thread them through every call. The emitter is the
    single point that audit-event payloads land — keeps the controller
    free of repository-layer concerns (V9 separation).
    """

    def __init__(self, log_repo: object, session_id: str, facilitator_id: str) -> None:
        self._log_repo = log_repo
        self._session_id = session_id
        self._facilitator_id = facilitator_id

    @property
    def log_repo(self) -> object:
        return self._log_repo

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def facilitator_id(self) -> str:
        return self._facilitator_id

    async def emit_recommendation(
        self,
        *,
        previous_action: Action | None,
        outcome: DecisionOutcome,
    ) -> None:
        await self._log_repo.log_mode_recommendation(
            session_id=self._session_id,
            facilitator_id=self._facilitator_id,
            previous_action=previous_action,
            action=outcome.action,
            triggers=outcome.triggers,
            signal_observations=[
                {
                    "signal_name": o.signal_name,
                    "observed_value": o.observed_value,
                    "configured_threshold": o.configured_threshold,
                }
                for o in outcome.signal_observations
            ],
            dwell_floor_at=outcome.dwell_floor_at,
        )

    async def emit_transition(
        self,
        *,
        previous_action: Action | None,
        outcome: DecisionOutcome,
        engaged_mechanisms: list[str],
        skipped_mechanisms: list[str],
    ) -> None:
        await self._log_repo.log_mode_transition(
            session_id=self._session_id,
            facilitator_id=self._facilitator_id,
            previous_action=previous_action,
            action=outcome.action,
            triggers=outcome.triggers,
            signal_observations=[
                {
                    "signal_name": o.signal_name,
                    "observed_value": o.observed_value,
                    "configured_threshold": o.configured_threshold,
                }
                for o in outcome.signal_observations
            ],
            engaged_mechanisms=engaged_mechanisms,
            skipped_mechanisms=skipped_mechanisms,
            dwell_floor_at=outcome.dwell_floor_at,
        )

    async def emit_transition_suppressed(
        self,
        *,
        current_action: Action | None,
        would_have_fired: Action,
        eligible_at: datetime,
    ) -> None:
        await self._log_repo.log_mode_transition_suppressed(
            session_id=self._session_id,
            facilitator_id=self._facilitator_id,
            current_action=current_action,
            would_have_fired=would_have_fired,
            eligible_at=eligible_at,
        )

    async def emit_decision_cycle_throttled(
        self,
        *,
        cap_per_minute: int,
        last_cycle_at: datetime | None,
        next_eligible_at: datetime,
    ) -> None:
        await self._log_repo.log_decision_cycle_throttled(
            session_id=self._session_id,
            facilitator_id=self._facilitator_id,
            cap_per_minute=cap_per_minute,
            last_cycle_at=last_cycle_at,
            next_eligible_at=next_eligible_at,
        )

    async def emit_signal_source_unavailable(
        self,
        *,
        signal_name: str,
        last_known_state: SignalHealthFlag,
        since: datetime,
        rate_limited_until: datetime,
    ) -> None:
        await self._log_repo.log_signal_source_unavailable(
            session_id=self._session_id,
            facilitator_id=self._facilitator_id,
            signal_name=signal_name,
            last_known_state=last_known_state,
            since=since,
            rate_limited_until=rate_limited_until,
        )


# ---------------------------------------------------------------------------
# Decision-cycle driver (used by tests + loop integration)
# ---------------------------------------------------------------------------


async def run_decision_cycle(controller: DmaController) -> DecisionOutcome | None:
    """Execute one full decision cycle, including emission side effects.

    Returns the resulting :class:`DecisionOutcome` (or None if throttled).
    Splits emission into recommendation + transition + suppressed paths per
    FR-005 (advisory ALWAYS emits) and FR-006 / FR-008 (auto-apply gates on
    dwell). Used by ``loop.py``'s controller-task body and by tests.
    """
    outcome = controller.evaluate_cycle()
    if outcome is None:
        await _maybe_emit_throttled(controller)
        return None
    await _maybe_emit_unavailability(controller, outcome)
    # Research §6 deduplication: emit only on action change. The initial
    # NORMAL action carries no audit value (it is the controller's pre-
    # observation baseline) so we never emit it as a recommendation.
    is_initial_normal = controller.state.last_emitted_action is None and outcome.action == "NORMAL"
    if is_initial_normal or outcome.action == controller.state.last_emitted_action:
        if is_initial_normal:
            controller.state.last_emitted_action = "NORMAL"
        return outcome
    previous_action = controller.state.last_emitted_action
    if controller._emitter is not None:
        await controller._emitter.emit_recommendation(
            previous_action=previous_action,
            outcome=outcome,
        )
    controller.state.last_emitted_action = outcome.action
    if controller.auto_mode and outcome.action in ("ENGAGE", "DISENGAGE"):
        await _handle_auto_apply(controller, outcome, previous_action)
    return outcome


async def _handle_auto_apply(
    controller: DmaController,
    outcome: DecisionOutcome,
    previous_action: Action | None,
) -> None:
    """Auto-apply path: dwell-gate, mutate flags, emit transition (or suppressed)."""
    if controller.is_dwell_blocking(outcome.decision_at):
        eligible_at = controller.state.dwell_floor_at or outcome.decision_at
        if controller._emitter is not None:
            await controller._emitter.emit_transition_suppressed(
                current_action=previous_action,
                would_have_fired=outcome.action,
                eligible_at=eligible_at,
            )
        return
    engaged, skipped = controller.apply_transition(outcome.action, outcome.decision_at)
    if controller._emitter is not None:
        await controller._emitter.emit_transition(
            previous_action=previous_action,
            outcome=outcome,
            engaged_mechanisms=engaged,
            skipped_mechanisms=skipped,
        )


async def _maybe_emit_throttled(controller: DmaController) -> None:
    """FR-013: emit ``decision_cycle_throttled`` at most once per dwell window."""
    if controller.state.throttle_emitted_in_dwell or controller._emitter is None:
        return
    next_eligible_at = controller._clock() + timedelta(
        seconds=controller.budget.next_eligible_seconds_from_now()
    )
    await controller._emitter.emit_decision_cycle_throttled(
        cap_per_minute=controller.budget.cap_per_minute,
        last_cycle_at=controller.state.last_transition_at,
        next_eligible_at=next_eligible_at,
    )
    controller.state.throttle_emitted_in_dwell = True


async def _maybe_emit_unavailability(
    controller: DmaController,
    outcome: DecisionOutcome,
) -> None:
    """FR-013: emit ``signal_source_unavailable`` at most once per dwell per signal."""
    if controller._emitter is None:
        return
    rate_limited_until = controller._clock() + timedelta(seconds=controller.dwell_seconds)
    for signal_name in outcome.unavailable_signals:
        if signal_name in controller.state.unavailability_emitted_in_dwell:
            continue
        last_known = controller.state.prior_signal_health.get(signal_name, "AVAILABLE")
        await controller._emitter.emit_signal_source_unavailable(
            signal_name=signal_name,
            last_known_state=last_known,
            since=outcome.decision_at,
            rate_limited_until=rate_limited_until,
        )
        controller.state.unavailability_emitted_in_dwell.add(signal_name)
