"""Context assembly — 5-priority token budget builder."""

from __future__ import annotations

import asyncpg

from src.models.message import Message
from src.models.participant import Participant
from src.orchestrator.branch import get_main_branch_id
from src.orchestrator.types import ContextMessage
from src.prompts.tiers import assemble_prompt
from src.repositories.interrupt_repo import InterruptRepository
from src.repositories.message_repo import MessageRepository
from src.repositories.proposal_repo import ProposalRepository
from src.security.sanitizer import sanitize
from src.security.spotlighting import should_spotlight, spotlight

INTERJECTION_BUDGET = 500
PROPOSAL_BUDGET = 500
MVC_FLOOR_TURNS = 3
RESPONSE_RESERVE = 2000


class ContextAssembler:
    """Builds context payloads with strict priority ordering."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._msg_repo = MessageRepository(pool)
        self._int_repo = InterruptRepository(pool)
        self._prop_repo = ProposalRepository(pool)

    async def assemble(
        self,
        *,
        session_id: str,
        participant: Participant,
        interjections: list | None = None,
    ) -> list[ContextMessage]:
        """Build context in 5-priority order within token budget."""
        budget = _available_budget(participant)
        context: list[ContextMessage] = []
        used = _add_system_prompt(context, participant)
        used = await self._add_priorities(
            context,
            session_id,
            used,
            budget,
            interjections,
        )
        return context

    async def _add_priorities(
        self,
        context: list[ContextMessage],
        session_id: str,
        used: int,
        budget: int,
        interjections: list | None = None,
    ) -> int:
        """Add P2-P6 content in priority order."""
        bid = await get_main_branch_id(self._pool, session_id)
        if interjections is None:
            interjections = await self._int_repo.get_pending(session_id)
        used = _add_interjections(context, interjections, used)
        used = _add_proposals(
            context,
            await self._prop_repo.get_open_proposals(session_id),
            used,
        )
        recent = await self._msg_repo.get_recent(session_id, bid, MVC_FLOOR_TURNS)
        used = _add_messages(context, recent, used, budget)
        summaries = await self._msg_repo.get_summaries(session_id, bid)
        if summaries:
            used = _add_summary(context, summaries[-1], used, budget)
        if used < budget:
            await self._fill_history(context, session_id, used, budget, recent)
        return used

    async def _fill_history(
        self,
        context: list[ContextMessage],
        session_id: str,
        used: int,
        budget: int,
        already: list[Message],
    ) -> None:
        """Fill remaining budget with additional history."""
        bid = await get_main_branch_id(self._pool, session_id)
        more = await self._msg_repo.get_recent(session_id, bid, 50)
        _add_history(context, more, used, budget, already)


def _available_budget(participant: Participant) -> int:
    """Calculate available token budget for context."""
    window = participant.context_window
    reserve = participant.max_tokens_per_turn or RESPONSE_RESERVE
    prompt_est = _estimate_tokens(participant.system_prompt)
    return max(window - reserve - prompt_est, 0)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token)."""
    return max(len(text) // 4, 1) if text else 0


def _add_system_prompt(
    context: list[ContextMessage],
    participant: Participant,
) -> int:
    """Add tiered system prompt as first context message."""
    prompt = assemble_prompt(
        prompt_tier=participant.prompt_tier,
        custom_prompt=participant.system_prompt,
    )
    ctx = ContextMessage("system", prompt, None)
    context.append(ctx)
    return _estimate_tokens(ctx.content)


def _add_interjections(
    context: list[ContextMessage],
    interjections: list,
    used: int,
) -> int:
    """Add interjections up to budget."""
    for intr in interjections:
        content = f"<sacp:human>[Priority] {intr.content}"
        tokens = _estimate_tokens(content)
        if tokens > INTERJECTION_BUDGET:
            break
        context.append(ContextMessage("user", content, None))
        used += tokens
    return used


def _add_proposals(
    context: list[ContextMessage],
    proposals: list,
    used: int,
) -> int:
    """Add open proposals up to budget."""
    for prop in proposals:
        content = f"[Proposal] {prop.topic}: {prop.position}"
        tokens = _estimate_tokens(content)
        if tokens > PROPOSAL_BUDGET:
            break
        context.append(ContextMessage("user", content, None))
        used += tokens
    return used


def _add_messages(
    context: list[ContextMessage],
    messages: list[Message],
    used: int,
    budget: int,
) -> int:
    """Add messages with sanitization + spotlighting."""
    for msg in messages:
        content = _secure_content(msg)
        tokens = _estimate_tokens(content)
        if used + tokens > budget:
            break
        role = _message_role(msg.speaker_type)
        context.append(ContextMessage(role, content, msg.turn_number))
        used += tokens
    return used


def _secure_content(msg: Message) -> str:
    """Sanitize and optionally spotlight a message."""
    cleaned = sanitize(msg.content)
    tagged = f"<sacp:{msg.speaker_type}>{cleaned}"
    if should_spotlight(msg.speaker_type):
        return spotlight(tagged, msg.speaker_id)
    return tagged


def _add_summary(
    context: list[ContextMessage],
    summary: Message,
    used: int,
    budget: int,
) -> int:
    """Add latest summary if budget allows."""
    tokens = _estimate_tokens(summary.content)
    if used + tokens <= budget:
        content = f"[Summary] {summary.content}"
        context.append(
            ContextMessage("system", content, summary.turn_number),
        )
        used += tokens
    return used


def _add_history(
    context: list[ContextMessage],
    messages: list[Message],
    used: int,
    budget: int,
    already_added: list[Message],
) -> None:
    """Fill remaining budget with additional history."""
    added_turns = {m.turn_number for m in already_added}
    for msg in messages:
        if msg.turn_number in added_turns:
            continue
        tokens = _estimate_tokens(msg.content)
        if used + tokens > budget:
            break
        role = _message_role(msg.speaker_type)
        marker = f"<sacp:{msg.speaker_type}>{msg.content}"
        context.append(ContextMessage(role, marker, msg.turn_number))
        used += tokens
        added_turns.add(msg.turn_number)


def _message_role(speaker_type: str) -> str:
    """Map speaker type to provider role."""
    if speaker_type == "human":
        return "user"
    if speaker_type in ("ai", "summary"):
        return "assistant"
    return "system"
