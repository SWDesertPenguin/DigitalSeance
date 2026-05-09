# SPDX-License-Identifier: AGPL-3.0-or-later

"""Message repository — append-only transcript with prepared statements.

No update or delete methods. Immutability enforced by interface.
"""

from __future__ import annotations

import time

import asyncpg

from src.models.message import Message
from src.repositories.base import BaseRepository
from src.repositories.errors import SessionNotActiveError


class MessageRepository(BaseRepository):
    """Data access for the immutable message transcript."""

    async def append_message(
        self,
        *,
        session_id: str,
        branch_id: str,
        speaker_id: str,
        speaker_type: str,
        content: str,
        token_count: int,
        complexity_score: str,
        cost_usd: float | None = None,
        parent_turn: int | None = None,
        delegated_from: str | None = None,
        summary_epoch: int | None = None,
        _lock_wait_ms_out: dict[str, int] | None = None,
    ) -> Message:
        """Append a message, auto-assigning the next turn number.

        Uses a transaction-scoped advisory lock keyed on branch_id to
        serialize concurrent appends (AI turn + human interjection race)
        so turn_number reflects true arrival order without PK collisions.

        ``_lock_wait_ms_out``: optional single-key dict for callers that
        need the advisory-lock contention metric (003 §FR-032). When
        provided, ``_lock_wait_ms_out["lock_wait_ms"]`` is populated with
        the milliseconds spent waiting for the lock before the transaction
        body ran. Only the turn-loop persist path uses this; all other
        callers leave it as None.
        """
        async with self._pool.acquire() as conn, conn.transaction():
            record, lock_wait_ms = await _append_locked(
                conn,
                session_id=session_id,
                branch_id=branch_id,
                speaker_id=speaker_id,
                speaker_type=speaker_type,
                content=content,
                token_count=token_count,
                complexity_score=complexity_score,
                cost_usd=cost_usd,
                parent_turn=parent_turn,
                delegated_from=delegated_from,
                summary_epoch=summary_epoch,
            )
        if _lock_wait_ms_out is not None:
            _lock_wait_ms_out["lock_wait_ms"] = lock_wait_ms
        return Message.from_record(record)

    async def get_recent(
        self,
        session_id: str,
        branch_id: str,
        limit: int,
    ) -> list[Message]:
        """Fetch the most recent N messages in turn order."""
        rows = await self._fetch_all(
            _RECENT_MESSAGES_SQL,
            session_id,
            branch_id,
            limit,
        )
        return [Message.from_record(r) for r in reversed(rows)]

    async def get_range(
        self,
        session_id: str,
        branch_id: str,
        *,
        start_turn: int,
        end_turn: int,
        exclude_speaker_types: list[str] | None = None,
    ) -> list[Message]:
        """Fetch messages in a turn number range, optionally excluding types.

        ``exclude_speaker_types`` filters rows whose ``speaker_type`` matches
        any entry. Used by the summarizer to avoid feeding its own prior
        output back in as "new content" (see Test06-Web06 incident).
        """
        rows = await self._fetch_all(
            _RANGE_MESSAGES_SQL,
            session_id,
            branch_id,
            start_turn,
            end_turn,
            exclude_speaker_types,
        )
        return [Message.from_record(r) for r in rows]

    async def get_by_speaker(
        self,
        session_id: str,
        speaker_id: str,
    ) -> list[Message]:
        """Fetch all messages by a specific speaker."""
        rows = await self._fetch_all(
            _BY_SPEAKER_SQL,
            session_id,
            speaker_id,
        )
        return [Message.from_record(r) for r in rows]

    async def get_summaries(
        self,
        session_id: str,
        branch_id: str,
    ) -> list[Message]:
        """Fetch all summarization checkpoint messages."""
        rows = await self._fetch_all(
            _SUMMARIES_SQL,
            session_id,
            branch_id,
        )
        return [Message.from_record(r) for r in rows]


async def _verify_session_active(
    conn: asyncpg.Connection,
    session_id: str,
) -> None:
    """Raise SessionNotActiveError if session is not active."""
    status = await conn.fetchval(
        "SELECT status FROM sessions WHERE id = $1",
        session_id,
    )
    if status != "active":
        raise SessionNotActiveError(f"Session {session_id} is {status}")


async def _append_locked(
    conn: asyncpg.Connection,
    *,
    session_id: str,
    branch_id: str,
    speaker_id: str,
    speaker_type: str,
    content: str,
    token_count: int,
    complexity_score: str,
    cost_usd: float | None,
    parent_turn: int | None,
    delegated_from: str | None,
    summary_epoch: int | None,
) -> tuple[asyncpg.Record, int]:
    """Verify session, lock branch, insert row; return (record, lock_wait_ms)."""
    await _verify_session_active(conn, session_id)
    lock_wait_ms = await _lock_branch(conn, branch_id)
    turn = await _next_turn_number(conn, session_id, branch_id)
    await _insert_message(
        conn,
        turn_number=turn,
        session_id=session_id,
        branch_id=branch_id,
        speaker_id=speaker_id,
        speaker_type=speaker_type,
        content=content,
        token_count=token_count,
        complexity_score=complexity_score,
        cost_usd=cost_usd,
        parent_turn=parent_turn,
        delegated_from=delegated_from,
        summary_epoch=summary_epoch,
    )
    record = await conn.fetchrow(_SELECT_MESSAGE_SQL, turn, session_id, branch_id)
    return record, lock_wait_ms


async def _lock_branch(
    conn: asyncpg.Connection,
    branch_id: str,
) -> int:
    """Acquire a transaction-scoped advisory lock; return wait time in ms.

    The lock serializes concurrent appends so turn_number reflects true
    arrival order without PK collisions. The returned duration backs
    003 §FR-032 advisory-lock contention tracking via ``advisory_lock_wait_ms``
    in ``routing_log``.
    """
    lock_start = time.monotonic()
    await conn.execute(
        "SELECT pg_advisory_xact_lock(hashtext($1))",
        branch_id,
    )
    return int((time.monotonic() - lock_start) * 1000)


async def _next_turn_number(
    conn: asyncpg.Connection,
    session_id: str,
    branch_id: str,
) -> int:
    """Determine the next sequential turn number."""
    max_turn = await conn.fetchval(
        "SELECT COALESCE(MAX(turn_number), -1) FROM messages"
        " WHERE session_id = $1 AND branch_id = $2",
        session_id,
        branch_id,
    )
    return max_turn + 1


async def _insert_message(
    conn: asyncpg.Connection,
    *,
    turn_number: int,
    session_id: str,
    branch_id: str,
    speaker_id: str,
    speaker_type: str,
    content: str,
    token_count: int,
    complexity_score: str,
    cost_usd: float | None,
    parent_turn: int | None,
    delegated_from: str | None,
    summary_epoch: int | None,
) -> None:
    """Insert a message record."""
    await conn.execute(
        _INSERT_MESSAGE_SQL,
        turn_number,
        session_id,
        branch_id,
        parent_turn,
        speaker_id,
        speaker_type,
        delegated_from,
        complexity_score,
        content,
        token_count,
        cost_usd,
        summary_epoch,
    )


_INSERT_MESSAGE_SQL = """
    INSERT INTO messages
        (turn_number, session_id, branch_id, parent_turn,
         speaker_id, speaker_type, delegated_from,
         complexity_score, content, token_count,
         cost_usd, summary_epoch)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
"""

_SELECT_MESSAGE_SQL = """
    SELECT * FROM messages
    WHERE turn_number = $1 AND session_id = $2 AND branch_id = $3
"""

_RECENT_MESSAGES_SQL = """
    SELECT * FROM messages
    WHERE session_id = $1 AND branch_id = $2
    ORDER BY turn_number DESC LIMIT $3
"""

_RANGE_MESSAGES_SQL = """
    SELECT * FROM messages
    WHERE session_id = $1 AND branch_id = $2
      AND turn_number >= $3 AND turn_number <= $4
      AND ($5::text[] IS NULL OR NOT (speaker_type = ANY($5)))
    ORDER BY turn_number
"""

_BY_SPEAKER_SQL = """
    SELECT * FROM messages
    WHERE session_id = $1 AND speaker_id = $2
    ORDER BY turn_number
"""

_SUMMARIES_SQL = """
    SELECT * FROM messages
    WHERE session_id = $1 AND branch_id = $2
      AND speaker_type = 'summary'
    ORDER BY turn_number
"""
