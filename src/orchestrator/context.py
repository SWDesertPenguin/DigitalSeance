# SPDX-License-Identifier: AGPL-3.0-or-later

"""Context assembly — 5-priority token budget builder."""

from __future__ import annotations

import logging
import os

import asyncpg

from src.api_bridge.model_limits import known_max_input_tokens
from src.api_bridge.tokenizer import default_estimator, get_tokenizer_for_model
from src.models.message import Message
from src.models.participant import Participant
from src.orchestrator.branch import get_main_branch_id
from src.orchestrator.types import ContextMessage
from src.prompts.tiers import assemble_prompt
from src.repositories.interrupt_repo import InterruptRepository
from src.repositories.message_repo import MessageRepository
from src.repositories.proposal_repo import ProposalRepository
from src.repositories.register_repo import RegisterRepository
from src.security.sanitizer import sanitize
from src.security.spotlighting import should_spotlight, spotlight

log = logging.getLogger(__name__)

INTERJECTION_BUDGET = 500
PROPOSAL_BUDGET = 500
MVC_FLOOR_TURNS = 3
RESPONSE_RESERVE = 2000
_DEFAULT_HISTORY_TURNS = 20


def _history_turns() -> int:
    """Read SACP_CONTEXT_MAX_TURNS; default 20.

    Why: On small/CPU-hosted models the prompt-eval cost scales with
    transcript length even when the token budget technically fits. A
    turn cap bounds latency independent of context_window.
    """
    raw = os.environ.get("SACP_CONTEXT_MAX_TURNS")
    if not raw:
        return _DEFAULT_HISTORY_TURNS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_HISTORY_TURNS
    return max(value, MVC_FLOOR_TURNS)


class ContextAssembler:
    """Builds context payloads with strict priority ordering."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._msg_repo = MessageRepository(pool)
        self._int_repo = InterruptRepository(pool)
        self._prop_repo = ProposalRepository(pool)
        self._register_repo = RegisterRepository(pool)

    async def assemble(
        self,
        *,
        session_id: str,
        participant: Participant,
        interjections: list | None = None,
        phase: str = "running",
        always_mode_wait_active: bool = False,
    ) -> list[ContextMessage]:
        """Build context in 5-priority order within token budget.

        Spec 025 FR-008: when ``phase='conclude'`` the system prompt picks
        up the Tier 4 conclude delta. Default ``phase='running'`` preserves
        pre-feature behavior.

        Spec 027 FR-015: when ``always_mode_wait_active=True`` the system
        prompt picks up the Tier 4 wait-acknowledgment delta as the third
        additive fragment (after register + conclude).

        Spec 028 §FR-006: when CAPCOM is assigned for the session, the
        message-load path applies ``_filter_visibility`` so panel AIs
        receive only ``visibility='public'`` rows. Loaded once per
        ``assemble`` from ``sessions.capcom_participant_id``.
        """
        budget = _available_budget(participant)
        context: list[ContextMessage] = []
        capcom_id = await self._fetch_capcom_id(session_id)
        register_delta = await self._resolve_register_delta(session_id, participant.id)
        await self._maybe_trigger_deferred_partition(session_id, participant)
        used = _add_system_prompt(
            context,
            participant,
            phase=phase,
            register_delta_text=register_delta,
            always_mode_wait_active=always_mode_wait_active,
        )
        roster = await self._fetch_roster(session_id)
        used = _add_participant_roster(context, roster, participant.id, used)
        used = await self._add_priorities(
            context,
            session_id,
            used,
            budget,
            participant=participant,
            interjections=interjections,
            roster=roster,
            capcom_id=capcom_id,
        )
        return _reorder_chronologically(context)

    async def _fetch_capcom_id(self, session_id: str) -> str | None:
        """Read ``sessions.capcom_participant_id`` once per assemble.

        Returns ``None`` when CAPCOM is not assigned for the session
        (the visibility filter then passes through every message
        unchanged — pre-feature behavior).
        """
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT capcom_participant_id FROM sessions WHERE id = $1",
                session_id,
            )

    async def _maybe_trigger_deferred_partition(
        self,
        session_id: str,
        participant: Participant,
    ) -> None:
        """Spec 018 Phase 2 — fire the initial partition on first turn-prep.

        Resolves the participant's `DeferredToolIndex`; if it's a live
        index (master switch on) and has never been computed, kicks off
        `compute_partition`. The tool list comes from the spec 018
        tool-list-provider hook (set externally by spec 017's
        ParticipantToolRegistry once that lands on main). Until then,
        the provider returns an empty list and the partition records a
        zero-tools decision — observable via the audit log as the
        signal that deferral is active for this participant.

        Best-effort: any failure here is logged and swallowed so the
        rest of context assembly proceeds unblocked.
        """
        from src.orchestrator.deferred_tool_index import (
            _LiveIndex,
            get_deferred_index_for_participant,
            get_tool_list_provider,
        )

        try:
            idx = get_deferred_index_for_participant(session_id, participant.id)
            if not isinstance(idx, _LiveIndex):
                return
            if not idx.is_empty():
                return
            provider = get_tool_list_provider()
            tools = await provider(session_id, participant.id) if provider else []
            tokenizer = get_tokenizer_for_model(participant.model)
            budget = _read_loaded_token_budget()
            await idx.compute_partition(tools, budget=budget, tokenizer=tokenizer)
        except Exception:
            log.exception(
                "deferred_tool_partition trigger failed (session=%s participant=%s)",
                session_id,
                participant.id,
            )

    async def _resolve_register_delta(
        self,
        session_id: str,
        participant_id: str,
    ) -> str | None:
        """Resolve the participant's effective register-preset Tier 4 delta.

        Spec 021 T042. Single resolver call per prompt assembly per
        contracts/register-preset-interface.md "Prompt-assembly
        integration". Returns ``None`` for slider 3 (Balanced) so the
        assembler falls back to tier text alone (FR-007 / FR-013), and
        ``None`` whenever resolver lookup raises (defense-in-depth: the
        slider must never block prompt assembly).

        Independent of ``SACP_RESPONSE_SHAPING_ENABLED`` per spec edge
        case — slider deltas always emit regardless of the master switch.
        """
        try:
            _, preset, _ = await self._register_repo.resolve_register(
                participant_id=participant_id,
                session_id=session_id,
            )
        except Exception:
            log.exception(
                "register resolver failed (session=%s participant=%s); falling back to no delta",
                session_id,
                participant_id,
            )
            return None
        return preset.tier4_delta

    async def _fetch_roster(self, session_id: str) -> dict[str, dict[str, str]]:
        """Lightweight participant lookup: id → {display_name, provider}.

        Used by the prompt assembler so AIs can see *who* said *what*
        with type disambiguation (human vs AI:provider) — today the
        prompt only carries `<sacp:human>` / `<sacp:ai>` tags without
        names, so multi-AI sessions can't reliably address a specific
        peer or distinguish human voices from each other.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, display_name, provider FROM participants WHERE session_id = $1",
                session_id,
            )
        return {r["id"]: dict(r) for r in rows}

    async def _add_priorities(
        self,
        context: list[ContextMessage],
        session_id: str,
        used: int,
        budget: int,
        *,
        participant: Participant,
        interjections: list | None = None,
        roster: dict[str, dict[str, str]] | None = None,
        capcom_id: str | None = None,
    ) -> int:
        """Add P2-P6 content in priority order."""
        bid = await get_main_branch_id(self._pool, session_id)
        if interjections is None:
            interjections = await self._int_repo.get_pending(session_id)
        used = _add_interjections(context, interjections, used)
        proposals = await self._prop_repo.get_open_proposals(session_id)
        used = _add_proposals(context, proposals, used)
        all_recent = await self._msg_repo.get_recent(session_id, bid, _history_turns())
        all_recent = _filter_visibility(all_recent, participant, capcom_id)
        floor = all_recent[:MVC_FLOOR_TURNS]
        used = _add_messages(context, floor, used, budget, speaker_id=participant.id, roster=roster)
        summaries = await self._msg_repo.get_summaries(session_id, bid)
        summaries = _filter_visibility(summaries, participant, capcom_id)
        if summaries:
            used = _add_summary(context, summaries[-1], used, budget)
        if used < budget:
            _add_history(
                context,
                all_recent,
                used,
                budget,
                floor,
                speaker_id=participant.id,
                roster=roster,
            )
        return used


def _filter_visibility(
    messages: list[Message],
    participant: Participant,
    capcom_id: str | None,
) -> list[Message]:
    """Spec 028 §FR-006 — last context-assembly step before security wrap.

    - Humans see every message (humans hold CAPCOM-or-broader visibility).
    - The active CAPCOM AI sees every message.
    - When no CAPCOM is assigned (capcom_id is None) every participant sees
      every message — pre-feature behavior preserved.
    - Every other AI participant (the panel) sees ``visibility='public'``
      messages only; ``capcom_only`` rows are filtered out.
    """
    if capcom_id is None or participant.provider == "human":
        return messages
    if participant.id == capcom_id:
        return messages
    return [m for m in messages if m.visibility == "public"]


def _reorder_chronologically(context: list[ContextMessage]) -> list[ContextMessage]:
    """Put non-system messages in chronological (turn) order.

    Why: _add_messages loads recent turns, then _fill_history APPENDS
    older turns after — so the final list has older messages at the
    end. Providers read context positionally; Claude was answering the
    original stale prompt (last in list) instead of continuing from
    its most recent turn, and _has_new_input was misled by the same
    reversal. Pending interjections (turn_number=None) sort last as
    they represent the newest pending input.
    """
    system = [m for m in context if m.role == "system"]
    others = [m for m in context if m.role != "system"]
    others.sort(key=lambda m: (m.source_turn is None, m.source_turn or 0))
    return system + others


_clamp_warned: set[tuple[str, str]] = set()


def _available_budget(participant: Participant) -> int:
    """Calculate available token budget for context.

    Uses the participant's per-provider tokenizer adapter (spec 003
    §FR-034) so the prompt-estimate is landed against the actual
    target tokenizer rather than a generic char/4 heuristic.

    Defends against operator-supplied `context_window` values that
    exceed the model's actual provider limit (spec 003 §FR-035) by
    clamping against the known-models catalog. A single warning per
    (session, participant) records the misconfiguration without
    spamming the log on every turn.
    """
    declared = participant.context_window
    catalog = known_max_input_tokens(participant.model)
    if catalog is not None and declared > catalog:
        key = (participant.session_id, participant.id)
        if key not in _clamp_warned:
            _clamp_warned.add(key)
            log.warning(
                "declared context_window %d exceeds catalog %d for %s; clamping",
                declared,
                catalog,
                participant.model,
            )
        window = catalog
    else:
        window = declared
    reserve = participant.max_tokens_per_turn or RESPONSE_RESERVE
    tokenizer = get_tokenizer_for_model(participant.model)
    prompt_est = tokenizer.count_tokens(participant.system_prompt or "")
    return max(window - reserve - prompt_est, 0)


def _estimate_tokens(text: str) -> int:
    """Token estimate via the default tiktoken adapter (spec 003 §FR-034).

    Used by helper paths that lack per-participant scope (interjection
    + proposal accumulation, history-fill against a chronological
    sort). The participant-specific adapter still gates the budget
    floor in `_available_budget`.
    """
    if not text:
        return 0
    return max(default_estimator().count_tokens(text), 1)


def _read_deferred_index_max_tokens() -> int:
    """Spec 018 SACP_TOOL_DEFER_INDEX_MAX_TOKENS reader; default 256."""
    import os as _os

    raw = _os.environ.get("SACP_TOOL_DEFER_INDEX_MAX_TOKENS", "").strip()
    if not raw:
        return 256
    try:
        return int(raw)
    except ValueError:
        return 256


def _read_loaded_token_budget() -> int:
    """Spec 018 SACP_TOOL_LOADED_TOKEN_BUDGET reader; default 1500."""
    import os as _os

    raw = _os.environ.get("SACP_TOOL_LOADED_TOKEN_BUDGET", "").strip()
    if not raw:
        return 1500
    try:
        return int(raw)
    except ValueError:
        return 1500


def _add_system_prompt(
    context: list[ContextMessage],
    participant: Participant,
    *,
    phase: str = "running",
    register_delta_text: str | None = None,
    always_mode_wait_active: bool = False,
) -> int:
    """Add tiered system prompt as first context message.

    Spec 025 FR-008/FR-009: when ``phase='conclude'`` the prompt assembler
    receives the conclude delta as a Tier 4 additive fragment, appended
    after participant ``custom_prompt``.

    Spec 021 T042: ``register_delta_text`` carries the per-session-slider
    Tier 4 delta from ``RegisterRepository.resolve_register``. ``None``
    skips injection (slider 3 / Balanced or resolver failure).

    Spec 027 FR-015: when ``always_mode_wait_active=True``, the
    standby-ack delta appends LAST in the Tier 4 composition chain.

    Spec 018 FR-014: the participant's `DeferredToolIndex` is consulted
    once per turn-prep; its compact index entries (empty in Phase 1) are
    threaded through to ``assemble_prompt`` so the deferred-tool list
    surfaces in the system prompt when Phase 2's working partition is
    active. Phase 1 (the v1 default) sees an empty list and the prompt
    is byte-identical to the pre-feature baseline.
    """
    from src.orchestrator.deferred_tool_index import (
        get_deferred_index_for_participant,
    )
    from src.prompts.conclude_delta import conclude_delta
    from src.prompts.standby_ack_delta import standby_ack_delta

    delta = conclude_delta(active=(phase == "conclude"))
    standby_delta = standby_ack_delta(active=always_mode_wait_active)
    deferred_index = get_deferred_index_for_participant(participant.session_id, participant.id)
    deferred_entries, _ = deferred_index.render_index_entries(_read_deferred_index_max_tokens())
    prompt = assemble_prompt(
        prompt_tier=participant.prompt_tier,
        custom_prompt=participant.system_prompt,
        participant_id=participant.id,
        register_delta_text=register_delta_text,
        conclude_delta=delta,
        standby_ack_delta=standby_delta,
        deferred_index_entries=deferred_entries or None,
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
            continue
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
    *,
    speaker_id: str,
    roster: dict[str, dict[str, str]] | None = None,
) -> int:
    """Add messages with sanitization + conditional spotlighting."""
    for msg in messages:
        content = _secure_content(msg, speaker_id, roster)
        tokens = _estimate_tokens(content)
        if used + tokens > budget:
            break
        role = _message_role(msg.speaker_type, msg.speaker_id, speaker_id)
        context.append(ContextMessage(role, content, msg.turn_number))
        used += tokens
    return used


def _secure_content(
    msg: Message,
    current_speaker_id: str,
    roster: dict[str, dict[str, str]] | None = None,
) -> str:
    """Sanitize, tag, and spotlight messages.

    For same-speaker (self) messages we skip both the <sacp:TYPE> tag
    and spotlighting — the role field (assistant/user) already carries
    that signal, the XML-like wrapper just confuses smaller models and
    the trust boundary doesn't exist when you're reading your own output.

    Per-message speaker labels (added in PR #124) were removed after
    Gemini 2.5-flash-lite was observed reading the `[Name (kind)] `
    prefix as a chat-app role marker — it copied other speakers'
    content verbatim and prefixed its own responses with the format.
    The `[Participants]` roster (still in `_add_participant_roster`)
    delivers the speaker-typing information AIs need without giving
    smaller models a per-line pattern to mimic. The `roster` parameter
    is kept on the signature for the moment — threading it out across
    `_add_messages`/`_add_history` is a separate cleanup PR.
    """
    del roster  # unused after the prefix was dropped; see docstring
    cleaned = sanitize(msg.content)
    if msg.speaker_id == current_speaker_id:
        return cleaned
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
    *,
    speaker_id: str,
    roster: dict[str, dict[str, str]] | None = None,
) -> None:
    """Fill remaining budget with additional history."""
    added_turns = {m.turn_number for m in already_added}
    for msg in messages:
        if msg.turn_number in added_turns:
            continue
        tokens = _estimate_tokens(msg.content)
        if used + tokens > budget:
            break
        role = _message_role(msg.speaker_type, msg.speaker_id, speaker_id)
        content = _secure_content(msg, speaker_id, roster)
        context.append(ContextMessage(role, content, msg.turn_number))
        used += tokens
        added_turns.add(msg.turn_number)


def _add_participant_roster(
    context: list[ContextMessage],
    roster: dict[str, dict[str, str]],
    self_id: str,
    used: int,
) -> int:
    """Inject a system-level roster so AIs know who's in the room."""
    lines = [_roster_line(p, self_id == p["id"]) for p in roster.values()]
    if not lines:
        return used
    body = "[Participants]\n" + "\n".join(lines)
    context.append(ContextMessage("system", body, None))
    return used + _estimate_tokens(body)


def _roster_line(p: dict[str, str], is_self: bool) -> str:
    """Format one roster entry with type marker + (you) flag for the speaker."""
    name = p.get("display_name") or p.get("id") or "?"
    provider = p.get("provider") or ""
    kind = "human" if provider == "human" else f"AI:{provider}"
    suffix = " (you)" if is_self else ""
    return f"- {name} ({kind}){suffix}"


def _message_role(
    speaker_type: str,
    msg_speaker_id: str,
    current_speaker_id: str,
) -> str:
    """Map speaker type + identity to provider role.

    Why: Anthropic's API requires strict user/assistant alternation and
    the last message must not be 'assistant'. Mapping every AI message to
    'assistant' (regardless of whose) produced consecutive-assistant
    sequences when a different AI had spoken since the current speaker,
    and Claude silently returned empty. Treating any other speaker as
    'user' from the current speaker's POV keeps alternation valid.
    """
    if speaker_type == "summary":
        return "system"
    if speaker_type == "ai" and msg_speaker_id == current_speaker_id:
        return "assistant"
    return "user"
