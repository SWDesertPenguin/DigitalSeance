"""Conversation loop — serialized turn execution engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import asyncpg

from src.api_bridge.format import to_provider_messages
from src.api_bridge.provider import dispatch_with_retry
from src.orchestrator.branch import get_main_branch_id
from src.orchestrator.budget import BudgetEnforcer
from src.orchestrator.cadence import CadenceController
from src.orchestrator.circuit_breaker import CircuitBreaker
from src.orchestrator.context import ContextAssembler
from src.orchestrator.convergence import ConvergenceDetector
from src.orchestrator.router import TurnRouter
from src.orchestrator.types import ProviderResponse, TurnResult
from src.repositories.errors import (
    AllParticipantsExhaustedError,
    ProviderDispatchError,
)
from src.repositories.interrupt_repo import InterruptRepository
from src.repositories.log_repo import LogRepository
from src.repositories.message_repo import MessageRepository
from src.repositories.review_gate_repo import ReviewGateRepository
from src.security.exfiltration import filter_exfiltration
from src.security.output_validator import validate as validate_output

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
        self._convergence = ConvergenceDetector(self._log_repo)
        self._convergence.load_model()
        self._cadence_presets: dict[str, str] = {}

    def set_cadence_preset(
        self,
        session_id: str,
        preset: str,
    ) -> None:
        """Cache the cadence preset for a running session."""
        self._cadence_presets[session_id] = preset

    async def execute_turn(self, session_id: str) -> TurnResult:
        """Execute a single turn iteration."""
        speaker = await self._router.next_speaker(session_id)
        if speaker is None:
            raise AllParticipantsExhaustedError("No active participants")

        skip = await _check_skip_conditions(
            self._budget,
            self._breaker,
            speaker,
            session_id,
        )
        if skip:
            return skip

        return await self._execute_routed_turn(session_id, speaker)

    async def _execute_routed_turn(
        self,
        session_id: str,
        speaker: object,
    ) -> TurnResult:
        """Route, assemble, dispatch, and persist a turn."""
        interjections = await self._int_repo.get_pending(session_id)
        log.debug("Fetched %d interjections for %s", len(interjections), session_id)
        # Interjections are persisted to the transcript at enqueue time
        # (see inject_message). Here we only use them for routing and
        # cadence signals, then mark delivered.
        if interjections:
            self._cadence.reset_on_interjection(session_id)
        decision = await self._router.route(
            speaker,
            has_interjection=bool(interjections),
        )
        if decision.action in ("skipped", "burst_accumulating"):
            await _log_routing(self._log_repo, session_id, decision)
            return _skip_from_decision(session_id, decision)
        ctx = self._build_turn_context(session_id)
        # Interjections are now persisted as messages above, so they appear
        # in history naturally. Pass empty list to avoid duplicating them
        # as priority context (which caused back-to-back user messages).
        result = await self._dispatch_with_delay(
            ctx,
            speaker,
            decision,
            [],
        )
        await _mark_delivered(self._int_repo, interjections)
        return result

    async def _dispatch_with_delay(
        self,
        ctx: _TurnContext,
        speaker: object,
        decision: object,
        interjections: list,
    ) -> TurnResult:
        """Dispatch turn then compute cadence delay."""
        result, content = await _dispatch_and_persist(
            ctx,
            self._assembler,
            self._breaker,
            speaker,
            decision,
            interjections=interjections,
        )
        delay = await self._compute_turn_delay(
            ctx.session_id,
            result.turn_number,
            content,
        )
        return _with_delay(result, delay)

    async def _compute_turn_delay(
        self,
        session_id: str,
        turn_number: int,
        content: str,
    ) -> float:
        """Compute post-turn delay via convergence + cadence."""
        if not content:
            return 0.0
        similarity = await self._convergence.process_turn(
            turn_number=turn_number,
            session_id=session_id,
            content=content,
        )
        preset = self._cadence_presets.get(session_id, "cruise")
        return self._cadence.compute_delay(
            session_id,
            similarity=similarity,
            preset=preset,
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


async def _mark_delivered(
    int_repo: InterruptRepository,
    interjections: list,
) -> None:
    """Mark only the interjections that were used in context."""
    for intr in interjections:
        await int_repo.mark_delivered(intr.id)


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
) -> tuple[TurnResult, str]:
    """Assemble context, dispatch to provider, persist result."""
    response = await _assemble_and_dispatch(
        ctx,
        assembler,
        breaker,
        speaker,
        interjections,
    )
    if response is None:
        return _skip_result(ctx.session_id, speaker.id, "provider_error"), ""

    if decision.action == "review_gated":
        result = await _stage_for_review(ctx, speaker, decision, response)
        return result, response.content

    result = await _validate_and_persist(ctx, speaker, decision, response)
    return result, response.content


async def _assemble_and_dispatch(
    ctx: _TurnContext,
    assembler: ContextAssembler,
    breaker: CircuitBreaker,
    speaker: object,
    interjections: list | None = None,
) -> ProviderResponse | None:
    """Build context, call provider, handle errors."""
    context = await assembler.assemble(
        session_id=ctx.session_id,
        participant=speaker,
        interjections=interjections,
    )
    messages = to_provider_messages(context)
    try:
        response = await _dispatch_to_provider(
            speaker,
            messages,
            ctx.encryption_key,
        )
        await breaker.record_success(speaker.id)
        return response
    except ProviderDispatchError as e:
        log.warning("Provider dispatch failed for %s: %s", speaker.id, e)
        await breaker.record_failure(speaker.id)
        return None


async def _validate_and_persist(
    ctx: _TurnContext,
    speaker: object,
    decision: object,
    response: ProviderResponse,
) -> TurnResult:
    """Run security pipeline then persist."""
    validation = validate_output(response.content)
    if validation.blocked:
        log.warning("Blocked %s: %s", speaker.id, validation.findings)
        return await _stage_for_review(ctx, speaker, decision, response)
    cleaned, _ = filter_exfiltration(response.content)
    if not cleaned.strip():
        log.warning("Skipped empty response from %s", speaker.id)
        return _skip_result(ctx.session_id, speaker.id, "empty_response")
    safe = _with_cleaned_content(response, cleaned)
    return await _persist_turn(ctx, speaker, decision, safe)


async def _dispatch_to_provider(
    speaker: object,
    messages: list[dict[str, str]],
    encryption_key: str,
) -> ProviderResponse:
    """Dispatch context to the speaker's AI provider."""
    return await dispatch_with_retry(
        model=speaker.model,
        messages=messages,
        api_key_encrypted=speaker.api_key_encrypted,
        encryption_key=encryption_key,
        api_base=speaker.api_endpoint,
        timeout=speaker.turn_timeout_seconds,
        max_tokens=speaker.max_tokens_per_turn,
    )


async def _persist_turn(
    ctx: _TurnContext,
    speaker: object,
    decision: object,
    response: ProviderResponse,
) -> TurnResult:
    """Persist response as message and log routing + usage."""
    branch_id = await get_main_branch_id(ctx.pool, ctx.session_id)
    msg = await ctx.msg_repo.append_message(
        session_id=ctx.session_id,
        branch_id=branch_id,
        speaker_id=speaker.id,
        speaker_type="ai",
        content=response.content,
        token_count=response.input_tokens + response.output_tokens,
        complexity_score=decision.complexity,
        cost_usd=response.cost_usd,
    )
    await _log_routing(ctx.log_repo, ctx.session_id, decision, turn_number=msg.turn_number)
    await _log_usage(ctx.log_repo, speaker, msg.turn_number, response)
    return _turn_result(ctx.session_id, msg.turn_number, speaker, decision, response)


async def _stage_for_review(
    ctx: _TurnContext,
    speaker: object,
    decision: object,
    response: ProviderResponse,
) -> TurnResult:
    """Stage response as review gate draft."""
    await ctx.gate_repo.create_draft(
        session_id=ctx.session_id,
        participant_id=speaker.id,
        turn_number=0,
        draft_content=response.content,
        context_summary="Auto-generated turn response",
    )
    await _log_routing(ctx.log_repo, ctx.session_id, decision)
    return _turn_result(ctx.session_id, -1, speaker, decision, response)


async def _log_routing(
    log_repo: LogRepository,
    session_id: str,
    decision: object,
    *,
    turn_number: int = -1,
) -> None:
    """Log the routing decision."""
    await log_repo.log_routing(
        session_id=session_id,
        turn_number=turn_number,
        intended=decision.intended,
        actual=decision.actual,
        action=decision.action,
        complexity=decision.complexity,
        domain_match=decision.domain_match,
        reason=decision.reason,
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
