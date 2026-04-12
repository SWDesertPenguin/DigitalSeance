"""Interrupt queue repository — priority-ordered human interjections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class InterruptEntry:
    """A queued human interjection."""

    id: int
    session_id: str
    participant_id: str
    content: str
    priority: int
    status: str
    created_at: datetime
    delivered_at: datetime | None

    @classmethod
    def from_record(cls, record: Any) -> InterruptEntry:
        """Construct from an asyncpg Record."""
        return cls(**{f: record[f] for f in cls.__slots__})


class InterruptRepository(BaseRepository):
    """Data access for the priority interrupt queue."""

    async def enqueue(
        self,
        *,
        session_id: str,
        participant_id: str,
        content: str,
        priority: int = 1,
    ) -> InterruptEntry:
        """Add an interjection to the queue."""
        record = await self._fetch_one(
            _INSERT_SQL,
            session_id,
            participant_id,
            content,
            priority,
        )
        return InterruptEntry.from_record(record)

    async def get_pending(
        self,
        session_id: str,
    ) -> list[InterruptEntry]:
        """Fetch pending interjections, priority DESC then FIFO."""
        rows = await self._fetch_all(_PENDING_SQL, session_id)
        return [InterruptEntry.from_record(r) for r in rows]

    async def mark_delivered(
        self,
        interrupt_id: int,
    ) -> InterruptEntry:
        """Mark an interjection as delivered with timestamp."""
        record = await self._fetch_one(
            _DELIVER_SQL,
            interrupt_id,
        )
        return InterruptEntry.from_record(record)


_INSERT_SQL = """
    INSERT INTO interrupt_queue
        (session_id, participant_id, content, priority)
    VALUES ($1, $2, $3, $4)
    RETURNING *
"""

_PENDING_SQL = """
    SELECT * FROM interrupt_queue
    WHERE session_id = $1 AND status = 'pending'
    ORDER BY priority DESC, created_at ASC
"""

_DELIVER_SQL = """
    UPDATE interrupt_queue
    SET status = 'delivered', delivered_at = NOW()
    WHERE id = $1
    RETURNING *
"""
