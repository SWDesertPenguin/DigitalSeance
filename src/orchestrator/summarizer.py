"""Summarization checkpoints — periodic structured summaries."""

from __future__ import annotations

import json
import logging

import asyncpg

from src.api_bridge.format import to_provider_messages
from src.api_bridge.provider import dispatch_with_retry
from src.models.participant import Participant
from src.orchestrator.branch import get_main_branch_id
from src.orchestrator.types import ContextMessage
from src.repositories.errors import ProviderDispatchError
from src.repositories.message_repo import MessageRepository
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

log = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 10

SUMMARIZATION_PROMPT = """Summarize the conversation so far as structured JSON.

Output ONLY valid JSON with this exact structure:
{
  "decisions": [
    {"turn": <number>, "summary": "<text>", "status": "accepted|pending|rejected"}
  ],
  "open_questions": [
    {"turn": <number>, "summary": "<text>"}
  ],
  "key_positions": [
    {"participant": "<name>", "position": "<text>"}
  ],
  "narrative": "<1-2 paragraph overview>"
}

Include all decisions made, questions still open, each participant's
current stance, and a brief narrative of the conversation arc."""


class SummarizationManager:
    """Manages periodic summarization checkpoints."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        encryption_key: str,
        threshold: int = DEFAULT_THRESHOLD,
    ) -> None:
        self._pool = pool
        self._encryption_key = encryption_key
        self._threshold = threshold
        self._msg_repo = MessageRepository(pool)
        self._session_repo = SessionRepository(pool)
        self._participant_repo = ParticipantRepository(
            pool,
            encryption_key=encryption_key,
        )

    def should_summarize(
        self,
        current_turn: int,
        last_summary_turn: int,
    ) -> bool:
        """Check if checkpoint threshold is reached."""
        return (current_turn - last_summary_turn) >= self._threshold

    async def run_checkpoint(self, session_id: str) -> None:
        """Generate and store a summarization checkpoint."""
        session = await self._session_repo.get_session(session_id)
        if session is None:
            return
        candidates = await _cost_sorted_ai(
            self._participant_repo,
            session_id,
        )
        if not candidates:
            log.warning("No participants available for summarization")
            return
        await self._generate_and_store(session_id, session, candidates)

    async def _generate_and_store(
        self,
        session_id: str,
        session: object,
        candidates: list[Participant],
    ) -> None:
        """Fetch turns, generate summary, persist result.

        Watermark advances to the MAX dispatched-turn actually consumed,
        not session.current_turn — summary appends don't advance
        current_turn, so using it leaves last_summary_turn frozen and
        the next checkpoint re-reads the same range (Test06-Web06 loop).
        """
        turns = await _fetch_turns_since(
            self._msg_repo, self._pool, session_id, session.last_summary_turn
        )
        if not turns:
            return
        watermark = max(t.source_turn for t in turns)
        summary_json = await _generate_summary(turns, candidates, self._encryption_key)
        await _store_summary(
            self._msg_repo,
            self._pool,
            session_id,
            summary_json,
            watermark,
            speaker_id=session.facilitator_id,
        )
        await _update_session_turn(self._pool, session_id, watermark)
        await _emit_summary_created(session_id, summary_json, watermark)


async def _cost_sorted_ai(
    repo: ParticipantRepository,
    session_id: str,
) -> list[Participant]:
    """Active AI participants ordered cheapest-first.

    Humans have cost_per_input_token=None; missing cost is treated as +inf
    so unpriced rows don't outrank ones with real pricing. The summarizer
    walks this list head-first and falls through to the next entry on a
    ProviderDispatchError (Round09: a single participant with a dead key
    or zeroed-quota model used to 500 the whole checkpoint).
    """
    participants = await repo.list_participants(
        session_id,
        status_filter="active",
    )
    ai = [p for p in participants if p.provider != "human"]
    return sorted(ai, key=_cost_key)


def _cost_key(p: Participant) -> float:
    """Sort key: missing cost = +inf so unpriced rows don't outrank real pricing."""
    return p.cost_per_input_token if p.cost_per_input_token is not None else float("inf")


async def _fetch_turns_since(
    msg_repo: MessageRepository,
    pool: asyncpg.Pool,
    session_id: str,
    last_summary_turn: int,
) -> list[ContextMessage]:
    """Fetch turns since the last checkpoint as context messages.

    Excludes prior summary rows so the summarizer never feeds its own
    output back in as new content (Test06-Web06).
    """
    bid = await get_main_branch_id(pool, session_id)
    messages = await msg_repo.get_range(
        session_id,
        bid,
        start_turn=last_summary_turn + 1,
        end_turn=last_summary_turn + 1000,
        exclude_speaker_types=["summary"],
    )
    return [
        ContextMessage(
            role="user",
            content=f"[{m.speaker_type}] {m.content}",
            source_turn=m.turn_number,
        )
        for m in messages
    ]


async def _generate_summary(
    turns: list[ContextMessage],
    candidates: list[Participant],
    encryption_key: str,
) -> str:
    """Generate summary; walk cost-sorted AIs, fall through on dispatch failure.

    The inner per-model JSON-validity loop is kept (handles model-side
    JSON sloppiness on a working dispatch path). When ``dispatch_with_retry``
    itself fails after its own 3 rate-limit retries, we move to the
    next-cheapest participant — preserves the cost optimization while
    turning a single dead key/quota into a graceful degradation rather
    than a 500 on the whole checkpoint.
    """
    messages = to_provider_messages(
        [
            ContextMessage("system", SUMMARIZATION_PROMPT, None),
            *turns,
        ]
    )
    last_error: Exception | None = None
    for participant in candidates:
        try:
            return await _summarize_with(participant, messages, encryption_key)
        except ProviderDispatchError as exc:
            log.warning(
                "Summarizer dispatch failed on %s; trying next-cheapest",
                participant.model,
            )
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ProviderDispatchError("Summarizer found no usable AI participant")


async def _summarize_with(
    participant: Participant,
    messages: list[dict[str, str]],
    encryption_key: str,
) -> str:
    """Single-model summary attempt with JSON-validity retry."""
    response = None
    for attempt in range(3):
        response = await dispatch_with_retry(
            model=participant.model,
            messages=messages,
            api_key_encrypted=participant.api_key_encrypted,
            encryption_key=encryption_key,
            api_base=participant.api_endpoint,
            timeout=120,
        )
        parsed = _validate_summary_json(response.content)
        if parsed is not None:
            return json.dumps(parsed)
        log.warning("Invalid JSON on attempt %d", attempt + 1)

    log.warning("Falling back to narrative-only summary")
    return _narrative_fallback(response.content if response else "")


def _validate_summary_json(content: str) -> dict | None:
    """Parse and validate summary JSON. Returns None on failure.

    Claude tends to wrap JSON in ```json ... ``` fences despite
    instructions; strip them before parsing so we don't fall back to
    narrative-only when the model actually produced valid structure.
    """
    try:
        data = json.loads(_strip_code_fence(content))
    except (json.JSONDecodeError, TypeError):
        return None
    return _normalize_summary(data)


def _strip_code_fence(content: str) -> str:
    """Remove leading/trailing markdown code fences if present."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3].rstrip()
    return text.strip()


def _normalize_summary(data: dict) -> dict:
    """Ensure all required fields exist with defaults."""
    return {
        "decisions": data.get("decisions", []),
        "open_questions": data.get("open_questions", []),
        "key_positions": data.get("key_positions", []),
        "narrative": data.get("narrative", ""),
    }


def _narrative_fallback(content: str) -> str:
    """Wrap raw response as narrative-only JSON."""
    return json.dumps(
        {
            "decisions": [],
            "open_questions": [],
            "key_positions": [],
            "narrative": content,
        }
    )


async def _store_summary(
    msg_repo: MessageRepository,
    pool: asyncpg.Pool,
    session_id: str,
    summary_json: str,
    current_turn: int,
    *,
    speaker_id: str,
) -> None:
    """Store summary as an immutable message.

    Attributed to the session facilitator because the messages FK
    requires speaker_id to reference a real participant row.
    """
    bid = await get_main_branch_id(pool, session_id)
    await msg_repo.append_message(
        session_id=session_id,
        branch_id=bid,
        speaker_id=speaker_id,
        speaker_type="summary",
        content=summary_json,
        token_count=len(summary_json) // 4,
        complexity_score="low",
        summary_epoch=current_turn,
    )


async def _emit_summary_created(
    session_id: str,
    summary_json: str,
    current_turn: int,
) -> None:
    """Push a summary_created WS event for the Web UI."""
    from src.web_ui.events import summary_created_event
    from src.web_ui.websocket import broadcast_to_session

    try:
        parsed = json.loads(summary_json)
    except (json.JSONDecodeError, TypeError):
        parsed = {"narrative": summary_json}
    payload = {"turn_number": current_turn, "summary_epoch": current_turn, **parsed}
    await broadcast_to_session(session_id, summary_created_event(payload))


async def _update_session_turn(
    pool: asyncpg.Pool,
    session_id: str,
    turn: int,
) -> None:
    """Update session's last_summary_turn."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE sessions SET last_summary_turn = $1 WHERE id = $2",
            turn,
            session_id,
        )
