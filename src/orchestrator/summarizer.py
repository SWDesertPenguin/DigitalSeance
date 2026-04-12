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
from src.repositories.message_repo import MessageRepository
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

log = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 50

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
        cheapest = await _find_cheapest_model(
            self._participant_repo,
            session_id,
        )
        if cheapest is None:
            log.warning("No participants available for summarization")
            return
        await self._generate_and_store(session_id, session, cheapest)

    async def _generate_and_store(
        self,
        session_id: str,
        session: object,
        cheapest: Participant,
    ) -> None:
        """Fetch turns, generate summary, persist result."""
        turns = await _fetch_turns_since(
            self._msg_repo,
            self._pool,
            session_id,
            session.last_summary_turn,
        )
        if not turns:
            return
        summary_json = await _generate_summary(
            turns,
            cheapest,
            self._encryption_key,
        )
        await _store_summary(
            self._msg_repo,
            self._pool,
            session_id,
            summary_json,
            session.current_turn,
        )
        await _update_session_turn(
            self._pool,
            session_id,
            session.current_turn,
        )


async def _find_cheapest_model(
    repo: ParticipantRepository,
    session_id: str,
) -> Participant | None:
    """Find the participant with the lowest input token cost."""
    participants = await repo.list_participants(
        session_id,
        status_filter="active",
    )
    if not participants:
        return None
    return min(
        participants,
        key=lambda p: p.cost_per_input_token or 0.0,
    )


async def _fetch_turns_since(
    msg_repo: MessageRepository,
    pool: asyncpg.Pool,
    session_id: str,
    last_summary_turn: int,
) -> list[ContextMessage]:
    """Fetch turns since the last checkpoint as context messages."""
    bid = await get_main_branch_id(pool, session_id)
    messages = await msg_repo.get_range(
        session_id,
        bid,
        start_turn=last_summary_turn + 1,
        end_turn=last_summary_turn + 1000,
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
    cheapest: Participant,
    encryption_key: str,
) -> str:
    """Generate summary via cheapest model with JSON retry."""
    messages = to_provider_messages(
        [
            ContextMessage("system", SUMMARIZATION_PROMPT, None),
            *turns,
        ]
    )
    for attempt in range(3):
        response = await dispatch_with_retry(
            model=cheapest.model,
            messages=messages,
            api_key_encrypted=cheapest.api_key_encrypted,
            encryption_key=encryption_key,
            api_base=cheapest.api_endpoint,
            timeout=120,
        )
        parsed = _validate_summary_json(response.content)
        if parsed is not None:
            return json.dumps(parsed)
        log.warning("Invalid JSON on attempt %d", attempt + 1)

    log.warning("Falling back to narrative-only summary")
    return _narrative_fallback(response.content)


def _validate_summary_json(content: str) -> dict | None:
    """Parse and validate summary JSON. Returns None on failure."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    return _normalize_summary(data)


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
) -> None:
    """Store summary as an immutable message."""
    bid = await get_main_branch_id(pool, session_id)
    await msg_repo.append_message(
        session_id=session_id,
        branch_id=bid,
        speaker_id="system",
        speaker_type="summary",
        content=summary_json,
        token_count=len(summary_json) // 4,
        complexity_score="low",
        summary_epoch=current_turn,
    )


async def _update_session_turn(
    pool: asyncpg.Pool,
    session_id: str,
    turn: int,
) -> None:
    """Update session's last_summary_turn."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE sessions SET last_summary_turn = $1" " WHERE id = $2",
            turn,
            session_id,
        )
