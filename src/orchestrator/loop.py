"""Conversation loop — serialized turn execution engine."""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg

from src.api_bridge.adapter import ProviderRequest, get_adapter
from src.api_bridge.caching import build_session_cache_directives
from src.api_bridge.format import to_provider_messages
from src.api_bridge.tokenizer import default_estimator
from src.orchestrator.branch import get_main_branch_id
from src.orchestrator.budget import BudgetEnforcer
from src.orchestrator.cadence import CadenceController
from src.orchestrator.circuit_breaker import CircuitBreaker
from src.orchestrator.context import ContextAssembler
from src.orchestrator.convergence import DIVERGENCE_PROMPT, ConvergenceDetector
from src.orchestrator.dma_controller import DmaController
from src.orchestrator.dma_signals import (
    ConvergenceDerivativeSignal,
    DensityAnomalySignal,
    QueueDepthSignal,
    TurnRateSignal,
)
from src.orchestrator.high_traffic import HighTrafficRuntime, HighTrafficSessionConfig
from src.orchestrator.observer_downgrade import (
    Downgrade,
    NoOp,
    Suppressed,
    downgrade_audit_payload,
    evaluate_downgrade,
    evaluate_restore,
    suppressed_audit_payload,
)
from src.orchestrator.router import TurnRouter
from src.orchestrator.summarizer import SummarizationManager
from src.orchestrator.timing import (
    get_timings,
    record_stage,
    start_turn,
    with_stage_timing,
)
from src.orchestrator.types import ProviderResponse, TurnResult
from src.repositories.errors import (
    AllParticipantsExhaustedError,
    CompoundRetryExhaustedError,
    ContextWindowOverflowError,
    ProviderDispatchError,
    SessionNotActiveError,
)
from src.repositories.interrupt_repo import InterruptRepository
from src.repositories.log_repo import LogRepository
from src.repositories.message_repo import MessageRepository
from src.repositories.review_gate_repo import ReviewGateRepository
from src.repositories.session_repo import SessionRepository
from src.security.exfiltration import filter_exfiltration
from src.security.output_validator import validate as validate_output
from src.web_ui.batch_scheduler import BatchScheduler

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _TurnContext:
    """Bundles all dependencies for a single turn."""

    session_id: str
    encryption_key: str
    pool: asyncpg.Pool
    msg_repo: MessageRepository
    log_repo: LogRepository
    gate_repo: ReviewGateRepository


class ConversationLoop:
    """Serialized turn execution engine for SACP sessions."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        encryption_key: str,
    ) -> None:
        self._pool = pool
        self._encryption_key = encryption_key
        self._assembler = ContextAssembler(pool)
        self._router = TurnRouter(pool, encryption_key=encryption_key)
        self._budget = BudgetEnforcer(LogRepository(pool))
        self._breaker = CircuitBreaker(pool)
        self._int_repo = InterruptRepository(pool)
        self._msg_repo = MessageRepository(pool)
        self._log_repo = LogRepository(pool)
        self._gate_repo = ReviewGateRepository(pool)
        self._cadence = CadenceController()
        self._high_traffic_config = HighTrafficSessionConfig.resolve_from_env()
        self._high_traffic_runtime = HighTrafficRuntime(config=self._high_traffic_config)
        self._batch_scheduler = _maybe_make_batch_scheduler(self._high_traffic_config)
        self._convergence = ConvergenceDetector(
            self._log_repo,
            session_repo=SessionRepository(pool),
            **_convergence_threshold_kwarg(self._high_traffic_config),
        )
        self._convergence.load_model()
        self._summarizer = SummarizationManager(pool, encryption_key=encryption_key)
        self._init_per_session_state()

    def _init_per_session_state(self) -> None:
        """Per-session in-process state — keyed by session_id."""
        self._cadence_presets: dict[str, str] = {}
        self._pause_scopes: dict[str, str] = {}
        self._last_skip: dict[str, str] = {}
        self._prior_routing: dict[str, str] = {}
        self._last_downgrade_at: dict[str, datetime] = {}
        self._sustained_low_traffic_started_at: dict[str, datetime] = {}
        # Spec 025: turn at which conclude phase started (FR-007). Restored
        # on first cap-check after restart from the routing_log row written
        # by `conclude_phase_entered`.
        self._conclude_started_turn: dict[str, int] = {}
        # Spec 014 (research §3): per-session DMA controller; constructed lazily
        # when ``start_dma_controller`` fires from the session-init path.
        self._dma_controllers: dict[str, DmaController] = {}
        # Spec 014: per-session turn-rate observation, fed by the loop's
        # per-turn callback. Maps session_id -> turns observed in last minute.
        self._turn_rate_observations: dict[str, int] = {}

    @property
    def batch_scheduler(self) -> BatchScheduler | None:
        """013 §FR-001: per-session flush task; None when batching env var unset."""
        return self._batch_scheduler

    def remember_prior_routing(self, participant_id: str, prior: str) -> None:
        """Cache prior routing before a flip to review_gate."""
        self._prior_routing[participant_id] = prior

    def pop_prior_routing(self, participant_id: str) -> str | None:
        """Return (and clear) a cached prior routing, if any."""
        return self._prior_routing.pop(participant_id, None)

    def set_cadence_preset(
        self,
        session_id: str,
        preset: str,
    ) -> None:
        """Cache the cadence preset for a running session."""
        self._cadence_presets[session_id] = preset

    def set_review_gate_pause_scope(
        self,
        session_id: str,
        scope: str,
    ) -> None:
        """Cache the review-gate pause scope for a running session."""
        self._pause_scopes[session_id] = scope

    def mark_draft_resolved(
        self,
        session_id: str,
        participant_id: str,
    ) -> None:
        """Tell the router to skip this participant on the next rotation slot."""
        self._router.mark_resolved(session_id, participant_id)

    async def _log_skip_once(self, session_id: str, skip: object) -> None:
        """Log a skip once per (pid, reason) change and emit turn_skipped.

        The v1 `turn_skipped` WebSocket event powers FR-020's per-participant
        skip-reason tooltip. Deduplicated alongside the log write so the
        UI sees the same noise-reduction the audit log does.
        """
        pid = getattr(skip, "intended", None) or skip.speaker_id
        reason = getattr(skip, "reason", None) or skip.skip_reason
        turn = getattr(skip, "turn_number", -1)
        skip_key = f"{pid}:{reason}"
        if self._last_skip.get(session_id) != skip_key:
            await _log_skip_entry(self._log_repo, session_id, pid, reason)
            await _emit_turn_skipped(session_id, pid, reason, turn)
            self._last_skip[session_id] = skip_key

    async def execute_turn(self, session_id: str) -> TurnResult:
        """Execute a single turn iteration."""
        start_turn()
        await self._gate_active_or_capped(session_id)
        await self._maybe_evaluate_observer_downgrade(session_id)
        speaker = await self._router.next_speaker(session_id)
        if speaker is None:
            raise AllParticipantsExhaustedError("No active participants")

        skip = await _check_skip_conditions(self._budget, self._breaker, speaker, session_id)
        if skip:
            await self._log_skip_once(session_id, skip)
            return skip

        phase = await _read_loop_phase(self._pool, session_id)
        return await self._execute_routed_turn(session_id, speaker, phase=phase)

    async def _gate_active_or_capped(self, session_id: str) -> None:
        """Raise SessionNotActiveError if the session is paused OR auto-pauses now (FR-012)."""
        if not await _session_is_active(self._pool, session_id):
            msg = f"Session {session_id} is not active"
            raise SessionNotActiveError(msg)
        # Spec 025 SC-001: short-circuits internally for `length_cap_kind='none'`.
        if await self._evaluate_length_cap(session_id):
            msg = f"Session {session_id} auto-paused at length cap"
            raise SessionNotActiveError(msg)

    async def _execute_routed_turn(
        self,
        session_id: str,
        speaker: object,
        *,
        phase: str = "running",
    ) -> TurnResult:
        """Route, assemble, dispatch, and persist a turn.

        Spec 025: ``phase`` flows from `execute_turn` (which reads it from
        the session row) so the assembler injects the conclude delta and
        the cadence floors the delay during conclude phase.
        """
        interjections = await self._int_repo.get_pending(session_id)
        log.debug("Fetched %d interjections for %s", len(interjections), session_id)
        if interjections:
            self._cadence.reset_on_interjection(session_id)
        decision, early = await self._check_route(session_id, speaker, bool(interjections))
        if early:
            return early
        self._last_skip.pop(session_id, None)
        ctx = self._build_turn_context(session_id)
        # Interjections are persisted as messages above, so pass [] here
        # to avoid duplicating them as priority context.
        result = await self._dispatch_with_delay(ctx, speaker, decision, [], phase=phase)
        await _mark_delivered(self._int_repo, interjections)
        return result

    @with_stage_timing("route")
    async def _check_route(
        self,
        session_id: str,
        speaker: object,
        has_interjection: bool,
    ) -> tuple[object, TurnResult | None]:
        """Route speaker; return early-exit result if skipped or blocked."""
        recent_text = await self._latest_human_text(session_id)
        decision = await self._router.route(
            speaker,
            recent_text=recent_text,
            has_interjection=has_interjection,
        )
        if decision.action in ("skipped", "burst_accumulating"):
            await self._log_skip_once(session_id, decision)
            return decision, _skip_from_decision(session_id, decision)
        blocked = await self._block_for_pending_draft(session_id, speaker)
        if blocked:
            return decision, blocked
        return decision, None

    async def _latest_human_text(self, session_id: str) -> str:
        """Return the most recent human message content, or '' if none.

        Fed into the router so addressed_only can check for @<name>
        mentions and the classifier can score complexity off real input
        instead of an empty string.
        """
        branch_id = await get_main_branch_id(self._pool, session_id)
        recent = await self._msg_repo.get_recent(session_id, branch_id, limit=5)
        for m in reversed(recent):
            if m.speaker_type == "human":
                return m.content or ""
        return ""

    async def _dispatch_with_delay(
        self,
        ctx: _TurnContext,
        speaker: object,
        decision: object,
        interjections: list,
        *,
        phase: str = "running",
    ) -> TurnResult:
        """Dispatch turn then compute cadence delay.

        Spec 025: ``phase`` flows into the assembler (FR-008 conclude delta)
        and the cadence (FR-010 floor delay during conclude). Default
        ``'running'`` preserves pre-feature behavior.
        """
        result, content = await _dispatch_and_persist(
            ctx,
            self._assembler,
            self._breaker,
            speaker,
            decision,
            interjections=interjections,
            batch_scheduler=self._batch_scheduler,
            batching_engaged=self._high_traffic_runtime.is_mechanism_engaged("batching"),
            phase=phase,
        )
        if result.skipped:
            return result
        delay = await self._compute_turn_delay(
            ctx.session_id,
            result.turn_number,
            content,
            phase=phase,
        )
        await self._maybe_summarize(ctx.session_id, result.turn_number)
        return _with_delay(result, delay)

    async def _evaluate_length_cap(self, session_id: str) -> bool:
        """Spec 025 per-dispatch cap-check + conclude finalization (FR-005..FR-012).

        Returns True when the session has just been auto-paused (caller
        should treat this as session-not-active). Returns False otherwise,
        including the no-op case for sessions with `length_cap_kind='none'`.
        """
        from src.orchestrator import length_cap as lc

        _cap_start = time.monotonic()
        session = await self._session_repo().get_session(session_id)
        if session is None or session.length_cap_kind == "none":
            record_stage("cap_check", int((time.monotonic() - _cap_start) * 1000))
            return False
        cap = lc.cap_from_session(session)
        evaluation = lc.evaluate_per_dispatch_cap(
            cap,
            elapsed_turns=session.current_turn,
            elapsed_seconds=lc.effective_active_seconds(session),
            already_in_conclude=lc.is_in_conclude_phase(session),
        )
        record_stage("cap_check", int((time.monotonic() - _cap_start) * 1000))
        return await self._apply_cap_evaluation(session_id, session, evaluation)

    async def _apply_cap_evaluation(
        self, session_id: str, session: object, evaluation: object
    ) -> bool:
        """Apply the result of `evaluate_per_dispatch_cap` — transition or finalize."""
        if evaluation.enter_conclude:
            conclude_start = time.monotonic()
            await self._enter_conclude_phase(
                session_id, session.current_turn, evaluation.trigger_dimension or "turns"
            )
            record_stage("conclude_transition", int((time.monotonic() - conclude_start) * 1000))
            return False
        from src.orchestrator import length_cap as lc

        if lc.is_in_conclude_phase(session):
            return await self._maybe_finalize_conclude_phase(session_id, session)
        return False

    async def _enter_conclude_phase(
        self,
        session_id: str,
        current_turn: int,
        trigger_dimension: str,
    ) -> None:
        """Mark the session in conclude phase, emit routing-log row, broadcast WS event."""
        await self._session_repo().mark_conclude_phase_started(session_id)
        self._conclude_started_turn[session_id] = current_turn
        await self._log_repo.log_routing(
            session_id=session_id,
            turn_number=current_turn,
            intended=session_id,
            actual=session_id,
            action="phase_transition",
            complexity="n/a",
            domain_match=False,
            reason="conclude_phase_entered",
        )
        await _broadcast_session_concluding(
            session_id, current_turn=current_turn, trigger_dimension=trigger_dimension
        )

    async def _maybe_finalize_conclude_phase(
        self,
        session_id: str,
        session: object,
    ) -> bool:
        """Run the final summarizer + auto-pause if every active AI has wrapped.

        Returns True when finalization fired (caller treats session as
        not-active for this iteration); False when more conclude turns
        remain.
        """
        from src.orchestrator import length_cap as lc

        started = self._conclude_started_turn.get(session_id, session.current_turn)
        active_ai_count = await _count_active_ai(self._pool, session_id)
        if not lc.should_finalize_conclude_phase(
            current_turn=session.current_turn,
            conclude_started_turn=started,
            active_ai_count=active_ai_count,
        ):
            return False
        await self._run_finalization(session_id, session.current_turn)
        return True

    async def _run_finalization(self, session_id: str, current_turn: int) -> None:
        """Spec 025 FR-011/FR-012: summarizer + paused transition + auto_pause_on_cap row."""
        outcome = "success"
        try:
            await self._summarizer.run_final_summarizer(session_id)
        except Exception:
            log.exception("Final summarizer failed for session %s", session_id)
            outcome = "failed_closed"
        await self._session_repo().update_status(session_id, "paused")
        await self._log_repo.log_routing(
            session_id=session_id,
            turn_number=current_turn,
            intended=session_id,
            actual=session_id,
            action="phase_transition",
            complexity="n/a",
            domain_match=False,
            reason="auto_pause_on_cap",
        )
        await _broadcast_session_concluded(
            session_id, pause_reason="auto_pause_on_cap", summarizer_outcome=outcome
        )
        self._conclude_started_turn.pop(session_id, None)

    def _session_repo(self) -> SessionRepository:
        """Lazy SessionRepository handle so ConversationLoop owns one shared instance."""
        if not hasattr(self, "_session_repo_instance"):
            self._session_repo_instance = SessionRepository(self._pool)
        return self._session_repo_instance

    async def _maybe_summarize(self, session_id: str, turn_number: int) -> None:
        """Run a summarization checkpoint if the threshold has been reached."""
        async with self._pool.acquire() as conn:
            last = await conn.fetchval(
                "SELECT last_summary_turn FROM sessions WHERE id = $1",
                session_id,
            )
        if last is None or not self._summarizer.should_summarize(turn_number, last):
            return
        try:
            await self._summarizer.run_checkpoint(session_id)
        except Exception:
            log.exception("Summarization failed for session %s", session_id)

    async def _block_for_pending_draft(
        self,
        session_id: str,
        speaker: object,
    ) -> TurnResult | None:
        """Skip dispatch when review-gate drafts are pending (scope-aware)."""
        pending = await self._gate_repo.get_pending(session_id)
        if not pending:
            return None
        scope = self._pause_scopes.get(session_id, "session")
        if scope == "participant" and not any(d.participant_id == speaker.id for d in pending):
            return None
        skip = _skip_result(session_id, speaker.id, "review_gate_pending")
        await self._log_skip_once(session_id, skip)
        return _with_delay(skip, 5.0)

    async def _compute_turn_delay(
        self,
        session_id: str,
        turn_number: int,
        content: str,
        *,
        phase: str = "running",
    ) -> float:
        """Compute post-turn delay via convergence + cadence.

        Also enqueues a divergence prompt as a facilitator-attributed
        interrupt when convergence crosses threshold, so the next AI
        is nudged away from the mirror-response pattern.

        Spec 025 FR-010: ``phase='conclude'`` floors the cadence so wrap-up
        turns dispatch responsively.
        """
        if not content or turn_number <= 0:
            return 0.0
        similarity, diverge = await self._convergence.process_turn(
            turn_number=turn_number,
            session_id=session_id,
            content=content,
        )
        await _emit_convergence(session_id, turn_number, similarity, diverge)
        if diverge:
            await self._enqueue_divergence(session_id)
        preset = self._cadence_presets.get(session_id, "cruise")
        return self._cadence.compute_delay(
            session_id,
            similarity=similarity,
            preset=preset,
            phase=phase,
        )

    async def _enqueue_divergence(self, session_id: str) -> None:
        """Inject DIVERGENCE_PROMPT as a facilitator-attributed interjection."""
        async with self._pool.acquire() as conn:
            fid = await conn.fetchval(
                "SELECT facilitator_id FROM sessions WHERE id = $1",
                session_id,
            )
        if not fid:
            return
        branch_id = await get_main_branch_id(self._pool, session_id)
        await self._msg_repo.append_message(
            session_id=session_id,
            branch_id=branch_id,
            speaker_id=fid,
            speaker_type="human",
            content=DIVERGENCE_PROMPT,
            token_count=max(default_estimator().count_tokens(DIVERGENCE_PROMPT), 1),
            complexity_score="n/a",
        )
        await self._int_repo.enqueue(
            session_id=session_id,
            participant_id=fid,
            content=DIVERGENCE_PROMPT,
            priority=2,
        )

    def _build_turn_context(self, session_id: str) -> _TurnContext:
        """Create a TurnContext with current dependencies."""
        return _TurnContext(
            session_id=session_id,
            encryption_key=self._encryption_key,
            pool=self._pool,
            msg_repo=self._msg_repo,
            log_repo=self._log_repo,
            gate_repo=self._gate_repo,
        )

    async def start_dma_controller(self, session_id: str, facilitator_id: str) -> None:
        """Spec 014 (research §3): spawn the per-session DMA controller task.

        No-op when ``DmaController.is_active_from_env()`` returns False
        (FR-015 additive-when-unset gate). Caller (session-init path) invokes
        once per session lifetime; ``stop_dma_controller`` cancels at
        teardown.
        """
        if not DmaController.is_active_from_env():
            return
        if session_id in self._dma_controllers:
            return
        from src.orchestrator.dma_controller import ModeEmitter

        sources = self._build_dma_signal_sources(session_id)
        emitter = ModeEmitter(self._log_repo, session_id, facilitator_id)
        controller = DmaController(
            session_id=session_id,
            runtime=self._high_traffic_runtime,
            signal_sources=sources,
            emitter=emitter,
        )
        self._dma_controllers[session_id] = controller
        await controller.start()

    async def stop_dma_controller(self, session_id: str) -> None:
        """Spec 014 (research §3): cancel the controller task on session teardown."""
        controller = self._dma_controllers.pop(session_id, None)
        if controller is None:
            return
        await controller.stop()

    def _build_dma_signal_sources(self, session_id: str) -> list:
        """Wire the four DMA signal adapters to per-session data feeds.

        Each adapter pulls its data from a tiny callable; this isolates the
        loop's existing internal state from the controller. Per FR-004,
        adapters whose env vars are unset will be ignored by the decision
        cycle regardless of what they sample.
        """
        return [
            TurnRateSignal(sampler=lambda sid=session_id: self._turn_rate_observations.get(sid)),
            ConvergenceDerivativeSignal(
                similarity_provider=lambda: self._convergence.last_similarity,
            ),
            QueueDepthSignal(
                depth_sampler=lambda: self._sample_queue_depth(),
                availability=lambda: self._batch_scheduler is not None,
            ),
            DensityAnomalySignal(
                count_sampler=lambda sid=session_id: self._sample_density_anomalies(sid),
            ),
        ]

    def _sample_queue_depth(self) -> int | None:
        """Read the per-session batch scheduler's queue depth, or None.

        Spec 013's BatchScheduler doesn't (yet) expose a public depth
        accessor. Until it does, this sampler returns 0 when batching is
        configured but no queue introspection is available. Adapter's
        ``is_available()`` already gates on ``batch_scheduler is not None``.
        """
        if self._batch_scheduler is None:
            return None
        # Reach for an internal queue map if the BatchScheduler exposes one;
        # otherwise return 0 as the safe-floor. Refined in spec 013's
        # public-API amendment (out of scope for spec 014's hook).
        queues = getattr(self._batch_scheduler, "_queues", None)
        if queues is None:
            return 0
        try:
            return max((len(q) for q in queues.values()), default=0)
        except (AttributeError, TypeError):
            return 0

    def _sample_density_anomalies(self, session_id: str) -> int | None:
        """Sliding-count of density-anomaly rows in the prior minute.

        Per research §1: counts ``convergence_log`` rows with
        ``tier='density_anomaly'`` produced in the prior minute. Returns 0
        when the table is empty (signal source is structurally available
        once the convergence engine has produced any measurement).
        """
        # Synchronous in-memory shortcut to avoid a DB round-trip on the
        # hot path; the controller runs at most every 5 seconds so the
        # full window stays small. Returns 0 as a safe floor — a real DB
        # sample lands when the signal source is wired through the loop's
        # async machinery in a future amendment.
        del session_id
        return 0

    async def _maybe_evaluate_observer_downgrade(self, session_id: str) -> None:
        """013 §FR-008-§FR-012: turn-prep observer-downgrade + restore evaluator.

        No-op when ``HighTrafficSessionConfig.observer_downgrade is None`` (env unset).
        Audit row writes BEFORE role mutation per contracts/audit-events.md sequencing.

        Spec 014 (research §4): also short-circuits when the controller has
        disengaged the mechanism via ``MechanismActivation.observer_downgrade``.
        Default activation = True so spec-013 baseline is unchanged when no
        controller runs (FR-015 additive contract).
        """
        config = self._high_traffic_config
        if config is None or config.observer_downgrade is None:
            return
        if not self._high_traffic_runtime.is_mechanism_engaged("observer_downgrade"):
            return
        thresholds = config.observer_downgrade
        participants = await _list_active_participants(self._pool, session_id)
        current_tpm = await _compute_current_tpm(self._pool, session_id)
        decision = await _timed_evaluate_downgrade(
            participants=participants, current_tpm=current_tpm, thresholds=thresholds
        )
        await self._apply_downgrade_decision(session_id, decision)
        self._update_sustained_window(session_id, current_tpm, thresholds.tpm)
        await self._maybe_restore(session_id, current_tpm, thresholds)

    async def _apply_downgrade_decision(self, session_id: str, decision: object) -> None:
        """Write audit BEFORE role mutation per contracts sequencing rule."""
        if isinstance(decision, NoOp):
            return
        facilitator_id = await _fetch_facilitator(self._pool, session_id)
        if facilitator_id is None:
            return
        if isinstance(decision, Suppressed):
            await self._write_suppressed_row(session_id, facilitator_id, decision)
            return
        if isinstance(decision, Downgrade):
            await self._write_downgrade_row(session_id, facilitator_id, decision)
            await _set_role(self._pool, decision.participant.id, "observer")
            self._last_downgrade_at[session_id] = datetime.now(UTC)

    async def _write_suppressed_row(
        self, session_id: str, facilitator_id: str, decision: Suppressed
    ) -> None:
        payload = suppressed_audit_payload(decision)
        await self._log_repo.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="observer_downgrade_suppressed",
            target_id=decision.participant.id,
            previous_value=payload["previous_value"],
            new_value=payload["new_value"],
        )

    async def _write_downgrade_row(
        self, session_id: str, facilitator_id: str, decision: Downgrade
    ) -> None:
        payload = downgrade_audit_payload(decision)
        await self._log_repo.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="observer_downgrade",
            target_id=decision.participant.id,
            previous_value=payload["previous_value"],
            new_value=payload["new_value"],
        )

    def _update_sustained_window(
        self, session_id: str, current_tpm: int, threshold_tpm: int
    ) -> None:
        """Track when sustained-low-traffic window started for restore eligibility."""
        if current_tpm < threshold_tpm:
            self._sustained_low_traffic_started_at.setdefault(session_id, datetime.now(UTC))
        else:
            self._sustained_low_traffic_started_at.pop(session_id, None)

    async def _maybe_restore(self, session_id: str, current_tpm: int, thresholds: object) -> None:
        """Call evaluate_restore each turn-prep after evaluate_downgrade (FR-010)."""
        decision = evaluate_restore(
            last_downgrade_at=self._last_downgrade_at.get(session_id),
            sustained_low_traffic_started_at=self._sustained_low_traffic_started_at.get(session_id),
            current_tpm=current_tpm,
            thresholds=thresholds,
        )
        # observer_downgrade.evaluate_restore returns NoOp for now (Phase 5 wiring
        # will supply the participant_id from per-session state when restore fires);
        # this hook is the integration point.
        del decision


async def _list_active_participants(pool: asyncpg.Pool, session_id: str) -> list[Any]:
    """Fetch participants needed by observer_downgrade.evaluate_downgrade (FR-008)."""
    from src.models.participant import Participant

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM participants WHERE session_id = $1",
            session_id,
        )
    return [Participant.from_record(r) for r in rows]


async def _compute_current_tpm(pool: asyncpg.Pool, session_id: str) -> int:
    """Compute turns-per-minute from messages in the last 60s (FR-008 input)."""
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM messages"
            " WHERE session_id = $1 AND created_at >= NOW() - INTERVAL '1 minute'",
            session_id,
        )
    return int(count or 0)


async def _fetch_facilitator(pool: asyncpg.Pool, session_id: str) -> str | None:
    """Look up the session's current facilitator id (acts on their behalf in audit rows)."""
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT facilitator_id FROM sessions WHERE id = $1",
            session_id,
        )


async def _set_role(pool: asyncpg.Pool, participant_id: str, new_role: str) -> None:
    """Mutate participant.role; called only after the audit row lands."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET role = $1 WHERE id = $2",
            new_role,
            participant_id,
        )


@with_stage_timing("observer_downgrade_eval_ms")
async def _timed_evaluate_downgrade(
    *,
    participants: list[Any],
    current_tpm: int,
    thresholds: Any,
) -> Any:
    """013 §FR-012 / SC-004: capture per-turn evaluator cost into routing_log timings."""
    return evaluate_downgrade(
        participants=participants,
        current_tpm=current_tpm,
        thresholds=thresholds,
    )


async def _mark_delivered(
    int_repo: InterruptRepository,
    interjections: list,
) -> None:
    """Mark only the interjections that were used in context."""
    for intr in interjections:
        await int_repo.mark_delivered(intr.id)


async def _session_is_active(pool: asyncpg.Pool, session_id: str) -> bool:
    """Return True only when the session row's status is 'active'."""
    async with pool.acquire() as conn:
        status = await conn.fetchval(
            "SELECT status FROM sessions WHERE id = $1",
            session_id,
        )
    return status == "active"


async def _check_skip_conditions(
    budget: BudgetEnforcer,
    breaker: CircuitBreaker,
    speaker: object,
    session_id: str,
) -> TurnResult | None:
    """Return a skip result if speaker should be skipped."""
    if not await budget.check_budget(speaker):
        return _skip_result(session_id, speaker.id, "budget_exceeded")
    if await breaker.is_open(speaker.id):
        return _skip_result(session_id, speaker.id, "circuit_open")
    return None


async def _dispatch_and_persist(
    ctx: _TurnContext,
    assembler: ContextAssembler,
    breaker: CircuitBreaker,
    speaker: object,
    decision: object,
    *,
    interjections: list | None = None,
    batch_scheduler: BatchScheduler | None = None,
    batching_engaged: bool = True,
    phase: str = "running",
) -> tuple[TurnResult, str]:
    """Assemble context, dispatch to provider, persist result.

    Spec 014: ``batching_engaged`` is the DMA controller's per-session
    activation flag (research §4). Default ``True`` so the spec-013
    baseline holds when no controller runs (FR-015 additive contract).
    """
    response, skip_reason = await _assemble_and_dispatch(
        ctx,
        assembler,
        breaker,
        speaker,
        interjections,
        phase=phase,
    )
    if response is None:
        return _skip_result(ctx.session_id, speaker.id, skip_reason or "provider_error"), ""

    if decision.action == "review_gated":
        result = await _stage_for_review(ctx, speaker, decision, response)
        return result, response.content

    result = await _validate_and_persist(
        ctx,
        speaker,
        decision,
        response,
        breaker,
        batch_scheduler=batch_scheduler,
        batching_engaged=batching_engaged,
    )
    return result, response.content


async def _assemble_and_dispatch(
    ctx: _TurnContext,
    assembler: ContextAssembler,
    breaker: CircuitBreaker,
    speaker: object,
    interjections: list | None = None,
    *,
    phase: str = "running",
) -> tuple[ProviderResponse | None, str | None]:
    """Build context, call provider, handle errors.

    Returns (response, skip_reason). Short-circuits with 'no_new_input'
    when context ends with the current speaker's own turn — asking
    Anthropic to "continue" its own message returns empty and would
    otherwise trip the circuit breaker on a healthy participant.

    Spec 025 FR-008: ``phase`` plumbs through to the assembler so the
    conclude delta lands at Tier 4 only when the loop is in conclude
    phase; default ``'running'`` preserves pre-feature output.
    """
    assemble_start = time.monotonic()
    context = await assembler.assemble(
        session_id=ctx.session_id,
        participant=speaker,
        interjections=interjections,
        phase=phase,
    )
    record_stage("assemble", int((time.monotonic() - assemble_start) * 1000))
    if not _has_new_input(context):
        log.info("Skipping %s: last message was same speaker", speaker.id)
        return None, "no_new_input"
    messages = to_provider_messages(context)
    try:
        return await _dispatch_to_provider(
            speaker, messages, ctx.encryption_key, session_id=ctx.session_id
        ), None
    except _DISPATCH_FAILURE_TYPES as e:
        log.warning("%s for %s: %s", _DISPATCH_FAILURE_LABEL[type(e)], speaker.id, e)
        await _record_failure_and_announce(ctx, breaker, speaker)
        await _broadcast_provider_error(ctx.session_id, speaker, e)
        return None, _DISPATCH_FAILURE_REASON[type(e)]


_DISPATCH_FAILURE_LABEL: dict[type, str] = {
    ContextWindowOverflowError: "Context window overflow",
    CompoundRetryExhaustedError: "Compound retry exhausted",
    ProviderDispatchError: "Provider dispatch failed",
}
_DISPATCH_FAILURE_REASON: dict[type, str] = {
    ContextWindowOverflowError: "context_window_overflow",
    CompoundRetryExhaustedError: "compound_retry_exhausted",
    ProviderDispatchError: "provider_error",
}
# Order matters — most-specific subclasses first so isinstance routes correctly.
_DISPATCH_FAILURE_TYPES = (
    ContextWindowOverflowError,
    CompoundRetryExhaustedError,
    ProviderDispatchError,
)


async def _record_failure_and_announce(
    ctx: _TurnContext,
    breaker: CircuitBreaker,
    speaker: object,
) -> None:
    """Increment breaker; broadcast updated health state; if newly open, announce."""
    just_opened = await breaker.record_failure(speaker.id)
    from src.repositories.participant_repo import ParticipantRepository
    from src.web_ui.events import broadcast_participant_update

    repo = ParticipantRepository(ctx.pool, encryption_key=ctx.encryption_key)
    await broadcast_participant_update(ctx.session_id, speaker.id, repo, ctx.log_repo)
    if not just_opened:
        return
    from src.orchestrator.announcements import announce_departure

    await announce_departure(
        pool=ctx.pool,
        msg_repo=ctx.msg_repo,
        session_id=ctx.session_id,
        speaker_id=speaker.id,
        departing_name=speaker.display_name,
        kind="paused — provider unreachable (circuit breaker open)",
    )


async def _broadcast_provider_error(session_id: str, speaker: object, err: Exception) -> None:
    """Surface provider failures so the UI can show a toast — not silent."""
    from src.web_ui.events import error_event
    from src.web_ui.websocket import broadcast_to_session

    # If the model string already carries the provider prefix (e.g.
    # `gemini/gemini-2.0-flash`, `groq/...`, `anthropic/...`), don't
    # double-prefix it. OpenAI models like `gpt-4o-mini` don't carry
    # a prefix so we still want `openai/gpt-4o-mini` for clarity.
    label = speaker.model if "/" in (speaker.model or "") else f"{speaker.provider}/{speaker.model}"
    message = f"Provider {label} failed: {err}"
    await broadcast_to_session(session_id, error_event("provider_unreachable", message))


def _has_new_input(context: list) -> bool:
    """True unless the last non-system message is 'assistant' (same speaker's own turn).

    Relies on ContextAssembler sorting non-system messages chronologically;
    an empty/system-only context counts as new input.
    """
    for msg in reversed(context):
        if msg.role == "system":
            continue
        return msg.role != "assistant"
    return True


def run_security_pipeline(content: str) -> tuple[object, str, list[str], int, int]:
    """Run validate + exfiltration with per-layer timing (007 §FR-020).

    Returns (validation, cleaned, exfil_flags, validator_ms, exfil_ms).
    Per-layer durations are captured even if a downstream layer raises;
    raise propagates to the caller's fail-closed handler.

    Public so the facilitator layer (spec 012 FR-006) can re-run the
    pipeline on approve / edit before persisting without importing a
    private symbol.
    """
    validator_start = time.monotonic()
    validation = validate_output(content)
    validator_ms = int((time.monotonic() - validator_start) * 1000)

    exfil_start = time.monotonic()
    cleaned, exfil_flags = filter_exfiltration(content)
    exfil_ms = int((time.monotonic() - exfil_start) * 1000)

    return validation, cleaned, exfil_flags, validator_ms, exfil_ms


async def _log_security_events(
    ctx: _TurnContext,
    speaker_id: str,
    validation: object,
    exfil_flags: list[str],
    layer_durations: dict[str, int],
) -> None:
    """Persist per-layer findings to security_events for post-hoc review (CHK008).

    ``layer_durations`` carries 007 §FR-020 wall-clock samples keyed by
    layer name (``output_validator`` / ``exfiltration``).
    """
    if validation.findings or validation.blocked:
        await ctx.log_repo.log_security_event(
            session_id=ctx.session_id,
            speaker_id=speaker_id,
            turn_number=-1,
            layer="output_validator",
            findings=json.dumps(list(validation.findings)),
            risk_score=validation.risk_score,
            blocked=validation.blocked,
            layer_duration_ms=layer_durations.get("output_validator"),
        )
    if exfil_flags:
        await ctx.log_repo.log_security_event(
            session_id=ctx.session_id,
            speaker_id=speaker_id,
            turn_number=-1,
            layer="exfiltration",
            findings=json.dumps(exfil_flags),
            blocked=False,
            layer_duration_ms=layer_durations.get("exfiltration"),
        )


async def _log_pipeline_error(ctx: _TurnContext, speaker_id: str) -> None:
    """Record a fail-closed security-pipeline crash (012 US6 / 007 §FR-020)."""
    await ctx.log_repo.log_security_event(
        session_id=ctx.session_id,
        speaker_id=speaker_id,
        turn_number=-1,
        layer="pipeline_error",
        findings=json.dumps(["pipeline_exception"]),
        blocked=True,
    )


async def _validate_and_persist(
    ctx: _TurnContext,
    speaker: object,
    decision: object,
    response: ProviderResponse,
    breaker: CircuitBreaker,
    *,
    batch_scheduler: BatchScheduler | None = None,
    batching_engaged: bool = True,
) -> TurnResult:
    """Run security pipeline then persist. Pipeline crashes fail closed without a breaker hit."""
    try:
        validation, cleaned, exfil_flags, validator_ms, exfil_ms = run_security_pipeline(
            response.content
        )
    except Exception:  # noqa: BLE001 — fail-closed on any pipeline error
        log.exception("Security pipeline crashed for %s; failing closed", speaker.id)
        await _log_pipeline_error(ctx, speaker.id)
        return _skip_result(ctx.session_id, speaker.id, "security_pipeline_error")
    durations = {"output_validator": validator_ms, "exfiltration": exfil_ms}
    await _log_security_events(ctx, speaker.id, validation, exfil_flags, durations)
    return await _route_validated_response(
        ctx,
        speaker,
        decision,
        response,
        breaker,
        validation=validation,
        cleaned=cleaned,
        batch_scheduler=batch_scheduler,
        batching_engaged=batching_engaged,
    )


async def _route_validated_response(
    ctx: _TurnContext,
    speaker: object,
    decision: object,
    response: ProviderResponse,
    breaker: CircuitBreaker,
    *,
    validation: object,
    cleaned: str,
    batch_scheduler: BatchScheduler | None,
    batching_engaged: bool,
) -> TurnResult:
    """Dispatch a validated security-pipeline result to its terminal handler."""
    if validation.blocked:
        log.warning("Blocked %s: %s", speaker.id, validation.findings)
        return await _stage_for_review(ctx, speaker, decision, response)
    skip_reason = _quality_skip_reason(cleaned)
    if skip_reason is not None:
        log.warning("Skipped %s response from %s", skip_reason.split("_")[0], speaker.id)
        await _record_failure_and_announce(ctx, breaker, speaker)
        return _skip_result(ctx.session_id, speaker.id, skip_reason)
    await breaker.record_success(speaker.id)
    return await _persist_turn(
        ctx,
        speaker,
        decision,
        _with_cleaned_content(response, cleaned),
        batch_scheduler=batch_scheduler,
        batching_engaged=batching_engaged,
    )


def _quality_skip_reason(cleaned: str) -> str | None:
    """Return the skip-reason if the cleaned output is empty or degenerate, else None."""
    if not cleaned.strip():
        return "empty_response"
    if _is_degenerate(cleaned):
        return "degenerate_output"
    return None


def _is_degenerate(text: str) -> bool:
    """Detect repetitive degenerate output (e.g. 'on on on on...').

    Legitimate prose has top-3 tokens around 10-15% of total. A threshold of
    >50% catches pathological repetition while leaving normal text alone.
    """
    words = text.split()
    if len(words) < 100:
        return False
    top3 = sum(c for _, c in Counter(words).most_common(3))
    return top3 / len(words) > 0.5


@with_stage_timing("dispatch")
async def _dispatch_to_provider(
    speaker: object,
    messages: list[dict[str, str]],
    encryption_key: str,
    *,
    session_id: str,
) -> ProviderResponse:
    """Dispatch context to the speaker's AI provider."""
    directives = build_session_cache_directives(
        session_id=session_id,
        model=speaker.model,
    )
    return await get_adapter().dispatch_with_retry(
        ProviderRequest(
            model=speaker.model,
            messages=messages,
            api_key_encrypted=speaker.api_key_encrypted,
            encryption_key=encryption_key,
            api_base=speaker.api_endpoint,
            timeout=speaker.turn_timeout_seconds,
            max_tokens=speaker.max_tokens_per_turn,
            cache_directives=directives,
        )
    )


async def _persist_turn(
    ctx: _TurnContext,
    speaker: object,
    decision: object,
    response: ProviderResponse,
    *,
    batch_scheduler: BatchScheduler | None = None,
    batching_engaged: bool = True,
) -> TurnResult:
    """Persist response as message and log routing + usage."""
    msg = await _append_message_timed(ctx, speaker, decision, response)
    await _log_routing(
        ctx.log_repo, ctx.session_id, decision, turn_number=msg.turn_number, timings=get_timings()
    )
    await _log_usage(ctx.log_repo, speaker, msg.turn_number, response)
    await _sync_current_turn(ctx.pool, ctx.session_id, msg.turn_number)
    await _emit_persist_signals(
        ctx,
        speaker,
        msg,
        response,
        batch_scheduler=batch_scheduler,
        batching_engaged=batching_engaged,
    )
    return _turn_result(ctx.session_id, msg.turn_number, speaker, decision, response)


async def _append_message_timed(
    ctx: _TurnContext,
    speaker: object,
    decision: object,
    response: ProviderResponse,
) -> object:
    """Append AI turn message; capture persist + advisory_lock_wait timings."""
    persist_start = time.monotonic()
    branch_id = await get_main_branch_id(ctx.pool, ctx.session_id)
    lock_out: dict[str, int] = {}
    msg = await ctx.msg_repo.append_message(
        session_id=ctx.session_id,
        branch_id=branch_id,
        speaker_id=speaker.id,
        speaker_type="ai",
        content=response.content,
        token_count=response.input_tokens + response.output_tokens,
        complexity_score=decision.complexity,
        cost_usd=response.cost_usd,
        _lock_wait_ms_out=lock_out,
    )
    record_stage("persist", int((time.monotonic() - persist_start) * 1000))
    if "lock_wait_ms" in lock_out:
        record_stage("advisory_lock_wait", lock_out["lock_wait_ms"])
    return msg


async def _emit_persist_signals(
    ctx: _TurnContext,
    speaker: object,
    msg: object,
    response: ProviderResponse,
    *,
    batch_scheduler: BatchScheduler | None = None,
    batching_engaged: bool = True,
) -> None:
    """Broadcast post-persist WS events: message, spend update, AI signals.

    Spec 014: ``batching_engaged`` reflects the DMA controller's activation
    flag for the batching mechanism (research §4). Default ``True`` so the
    spec-013 baseline is unchanged when no controller runs (FR-015 additive
    contract).
    """
    await _emit_message_to_web_ui(ctx.session_id, msg, response.cost_usd)
    await _emit_spend_update(ctx, speaker.id)
    await _emit_ai_signals(ctx, speaker, msg)
    if (
        batch_scheduler is not None
        and batching_engaged
        and getattr(speaker, "provider", None) != "human"
    ):
        await _enqueue_batched_for_humans(
            ctx.pool, batch_scheduler, ctx.session_id, msg, response.cost_usd
        )


async def _enqueue_batched_for_humans(
    pool: asyncpg.Pool,
    batch_scheduler: BatchScheduler,
    session_id: str,
    msg: object,
    cost_usd: float | None,
) -> None:
    """Enqueue an AI-to-human message into the per-recipient batch envelope (013 §FR-001).

    State-change events (convergence, session_status, participant_update) bypass
    this path entirely per FR-004 — they call broadcast_to_session directly.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id FROM participants"
            " WHERE session_id = $1 AND provider = 'human' AND status != 'paused'",
            session_id,
        )
    if not rows:
        return
    payload = _build_message_payload(msg, cost_usd)
    source_turn_id = f"{session_id}:{msg.turn_number}"
    for row in rows:
        batch_scheduler.enqueue(
            session_id=session_id,
            recipient_id=row["id"],
            source_turn_id=source_turn_id,
            message=payload,
        )


def _build_message_payload(msg: object, cost_usd: float | None) -> dict[str, Any]:
    """Build a message_event-compatible payload dict from a persisted Message."""
    return {
        "turn_number": msg.turn_number,
        "speaker_id": msg.speaker_id,
        "speaker_type": msg.speaker_type,
        "content": msg.content,
        "token_count": msg.token_count,
        "cost_usd": cost_usd,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "summary_epoch": msg.summary_epoch,
    }


async def _emit_ai_signals(
    ctx: _TurnContext,
    speaker: object,
    msg: object,
) -> None:
    """Detect open questions / exit-intent in AI output and broadcast WS events.

    Heuristic detectors live in src.orchestrator.signals. False positives
    are intentionally cheap — both events are advisory: the question
    panel surfaces them for humans to resolve, and the exit badge waits
    for the facilitator to click "honor" (flip to observer). Nothing
    auto-mutes the AI based on detection alone.
    """
    from src.orchestrator.signals import detect_exit_intent, extract_questions
    from src.web_ui.events import ai_exit_requested_event, ai_question_opened_event
    from src.web_ui.websocket import broadcast_to_session

    roster = await _fetch_signal_roster(ctx.pool, ctx.session_id)
    questions = extract_questions(msg.content, roster)
    exit_phrase = detect_exit_intent(msg.content)
    if questions:
        await broadcast_to_session(
            ctx.session_id,
            ai_question_opened_event(
                participant_id=speaker.id,
                turn_number=msg.turn_number,
                questions=questions,
            ),
        )
    if exit_phrase:
        await broadcast_to_session(
            ctx.session_id,
            ai_exit_requested_event(
                participant_id=speaker.id,
                turn_number=msg.turn_number,
                phrase=exit_phrase,
            ),
        )


async def _fetch_signal_roster(
    pool: asyncpg.Pool,
    session_id: str,
) -> dict[str, dict[str, str]]:
    """Lightweight participant lookup for question-detection name matching."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, display_name, provider FROM participants WHERE session_id = $1",
            session_id,
        )
    return {r["id"]: dict(r) for r in rows}


async def _emit_message_to_web_ui(
    session_id: str,
    msg: object,
    cost_usd: float | None,
) -> None:
    """Push a v1 message event with the full persisted Message shape.

    Fix for C8: the earlier TurnResult-only broadcast omitted content /
    speaker_type / created_at, so every live turn rendered as an empty
    card in the transcript.
    """
    from src.web_ui.events import message_event
    from src.web_ui.websocket import broadcast_to_session

    payload = {
        "turn_number": msg.turn_number,
        "speaker_id": msg.speaker_id,
        "speaker_type": msg.speaker_type,
        "content": msg.content,
        "token_count": msg.token_count,
        "cost_usd": cost_usd,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "summary_epoch": msg.summary_epoch,
    }
    await broadcast_to_session(session_id, message_event(payload))


async def _emit_spend_update(ctx: _TurnContext, participant_id: str) -> None:
    """Broadcast participant_update with a fresh daily-spend aggregate (C3)."""
    from src.repositories.participant_repo import ParticipantRepository
    from src.web_ui.events import broadcast_participant_update

    repo = ParticipantRepository(ctx.pool, encryption_key=ctx.encryption_key)
    await broadcast_participant_update(
        ctx.session_id,
        participant_id,
        repo,
        ctx.log_repo,
    )


async def _stage_for_review(
    ctx: _TurnContext,
    speaker: object,
    decision: object,
    response: ProviderResponse,
) -> TurnResult:
    """Stage response as review gate draft. Returns skip to pause the loop."""
    draft = await ctx.gate_repo.create_draft(
        session_id=ctx.session_id,
        participant_id=speaker.id,
        turn_number=0,
        draft_content=response.content,
        context_summary="Auto-generated turn response",
    )
    log.info("Staged draft %s for review (participant=%s)", draft.id, speaker.id)
    await _log_routing(
        ctx.log_repo,
        ctx.session_id,
        decision,
        timings=get_timings(),
    )
    await _emit_draft_staged(ctx.session_id, draft)
    skip = _skip_result(ctx.session_id, speaker.id, "review_gate_staged")
    return _with_delay(skip, 5.0)


async def _emit_turn_skipped(
    session_id: str,
    participant_id: str,
    reason: str,
    turn_number: int,
) -> None:
    """Push a v1 turn_skipped event for the health-badge tooltip (C7)."""
    from src.web_ui.events import turn_skipped_event
    from src.web_ui.websocket import broadcast_to_session

    await broadcast_to_session(
        session_id,
        turn_skipped_event(participant_id, reason, turn_number),
    )


async def _emit_convergence(
    session_id: str,
    turn_number: int,
    similarity: float,
    diverge: bool,
) -> None:
    """Push a convergence_update event to Web UI subscribers."""
    from src.web_ui.events import convergence_update_event
    from src.web_ui.websocket import broadcast_to_session

    point = {
        "turn_number": turn_number,
        "similarity_score": similarity,
        "divergence_prompted": diverge,
    }
    await broadcast_to_session(session_id, convergence_update_event(point))


async def _emit_draft_staged(session_id: str, draft: object) -> None:
    """Push a review_gate_staged WS event (Phase 2 Web UI)."""
    from src.web_ui.events import review_gate_staged_event
    from src.web_ui.websocket import broadcast_to_session

    payload = {
        "id": draft.id,
        "participant_id": draft.participant_id,
        "draft_content": draft.draft_content,
        "context_summary": draft.context_summary,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }
    await broadcast_to_session(session_id, review_gate_staged_event(payload))


async def _broadcast_session_concluding(
    session_id: str,
    *,
    current_turn: int,
    trigger_dimension: str,
) -> None:
    """Spec 025 FR-017: broadcast `session_concluding` to all session participants."""
    from src.orchestrator.length_cap import DEFAULT_TRIGGER_FRACTION
    from src.web_ui.events import session_concluding_event
    from src.web_ui.websocket import broadcast_to_session

    event = session_concluding_event(
        trigger_reason=trigger_dimension,
        trigger_value_turns=current_turn,
        trigger_value_seconds=0,
        remaining_turns=None,
        remaining_seconds=None,
        trigger_fraction=DEFAULT_TRIGGER_FRACTION,
    )
    await broadcast_to_session(session_id, event)


async def _broadcast_session_concluded(
    session_id: str,
    *,
    pause_reason: str,
    summarizer_outcome: str,
) -> None:
    """Spec 025 FR-018: broadcast `session_concluded` to all session participants."""
    from src.web_ui.events import session_concluded_event
    from src.web_ui.websocket import broadcast_to_session

    event = session_concluded_event(
        pause_reason=pause_reason, summarizer_outcome=summarizer_outcome
    )
    await broadcast_to_session(session_id, event)


async def _read_loop_phase(pool: asyncpg.Pool, session_id: str) -> str:
    """Spec 025: read 'running' or 'conclude' from `sessions.conclude_phase_started_at`.

    Pure read helper so callers don't need to thread the SessionRepository
    just for the phase string.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT conclude_phase_started_at FROM sessions WHERE id = $1",
            session_id,
        )
    if row is None or row["conclude_phase_started_at"] is None:
        return "running"
    return "conclude"


async def _count_active_ai(pool: asyncpg.Pool, session_id: str) -> int:
    """Count active AI participants for a session (FR-011 finalization gate)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM participants "
            "WHERE session_id = $1 AND role = 'participant' "
            "AND status = 'active' AND provider != 'human'",
            session_id,
        )
    return int(row["n"]) if row else 0


async def _log_routing(
    log_repo: LogRepository,
    session_id: str,
    decision: object,
    *,
    turn_number: int = -1,
    timings: dict[str, int] | None = None,
) -> None:
    """Log the routing decision."""
    timings = timings or {}
    await log_repo.log_routing(
        session_id=session_id,
        turn_number=turn_number,
        intended=decision.intended,
        actual=decision.actual,
        action=decision.action,
        complexity=decision.complexity,
        domain_match=decision.domain_match,
        reason=decision.reason,
        route_ms=timings.get("route"),
        assemble_ms=timings.get("assemble"),
        dispatch_ms=timings.get("dispatch"),
        persist_ms=timings.get("persist"),
        advisory_lock_wait_ms=timings.get("advisory_lock_wait"),
    )


async def _log_skip_entry(
    log_repo: LogRepository,
    session_id: str,
    participant_id: str,
    reason: str,
) -> None:
    """Write a skip to routing_log (budget, circuit, observer, etc.)."""
    await log_repo.log_routing(
        session_id=session_id,
        turn_number=-1,
        intended=participant_id,
        actual=participant_id,
        action="skipped",
        complexity="n/a",
        domain_match=False,
        reason=reason,
    )


async def _sync_current_turn(
    pool: asyncpg.Pool,
    session_id: str,
    turn_number: int,
) -> None:
    """Update session.current_turn to match the latest persisted turn."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE sessions SET current_turn = $1 WHERE id = $2",
            turn_number,
            session_id,
        )


async def _log_usage(
    log_repo: LogRepository,
    speaker: object,
    turn_number: int,
    response: ProviderResponse,
) -> None:
    """Log token usage for the turn."""
    await log_repo.log_usage(
        participant_id=speaker.id,
        turn_number=turn_number,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=response.cost_usd,
    )


def _turn_result(
    session_id: str,
    turn_number: int,
    speaker: object,
    decision: object,
    response: ProviderResponse,
) -> TurnResult:
    """Build a TurnResult from components."""
    return TurnResult(
        session_id=session_id,
        turn_number=turn_number,
        speaker_id=speaker.id,
        action=decision.action,
        tokens_used=response.input_tokens + response.output_tokens,
        cost_usd=response.cost_usd,
        skipped=False,
        skip_reason=None,
    )


def _skip_result(
    session_id: str,
    speaker_id: str,
    reason: str,
) -> TurnResult:
    """Create a skipped turn result."""
    return TurnResult(
        session_id=session_id,
        turn_number=-1,
        speaker_id=speaker_id,
        action="skipped",
        tokens_used=0,
        cost_usd=0.0,
        skipped=True,
        skip_reason=reason,
    )


def _skip_from_decision(
    session_id: str,
    decision: object,
) -> TurnResult:
    """Create a skipped result from a routing decision."""
    return TurnResult(
        session_id=session_id,
        turn_number=-1,
        speaker_id=decision.intended,
        action=decision.action,
        tokens_used=0,
        cost_usd=0.0,
        skipped=True,
        skip_reason=decision.reason,
    )


def _with_delay(result: TurnResult, delay: float) -> TurnResult:
    """Return a TurnResult with delay_seconds set."""
    return TurnResult(
        session_id=result.session_id,
        turn_number=result.turn_number,
        speaker_id=result.speaker_id,
        action=result.action,
        tokens_used=result.tokens_used,
        cost_usd=result.cost_usd,
        skipped=result.skipped,
        skip_reason=result.skip_reason,
        delay_seconds=delay,
    )


def _with_cleaned_content(
    response: ProviderResponse,
    cleaned: str,
) -> ProviderResponse:
    """Return a new ProviderResponse with cleaned content."""
    return ProviderResponse(
        content=cleaned,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=response.cost_usd,
        model=response.model,
        latency_ms=response.latency_ms,
    )


def _maybe_make_batch_scheduler(
    config: HighTrafficSessionConfig | None,
) -> BatchScheduler | None:
    """Build a BatchScheduler iff config enables batching (013 §FR-001)."""
    if config is None or config.batch_cadence_s is None:
        return None
    from src.web_ui.websocket import broadcast_to_session

    return BatchScheduler(cadence_s=config.batch_cadence_s, broadcast=broadcast_to_session)


def _convergence_threshold_kwarg(
    config: HighTrafficSessionConfig | None,
) -> dict[str, float]:
    """Return ``{}`` (use spec-004 default) or ``{"threshold": override}`` per 013 §FR-005."""
    if config is None or config.convergence_threshold_override is None:
        return {}
    return {"threshold": config.convergence_threshold_override}
