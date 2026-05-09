# SPDX-License-Identifier: AGPL-3.0-or-later

"""Review gate draft repository — AI response staging for human review."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class ReviewGateDraft:
    """A staged AI response awaiting human review."""

    id: str
    session_id: str
    participant_id: str
    turn_number: int
    draft_content: str
    context_summary: str
    status: str
    edited_content: str | None
    created_at: datetime
    resolved_at: datetime | None

    @classmethod
    def from_record(cls, record: Any) -> ReviewGateDraft:
        """Construct from an asyncpg Record."""
        return cls(**{f: record[f] for f in cls.__slots__})


class ReviewGateRepository(BaseRepository):
    """Data access for review gate draft lifecycle."""

    async def create_draft(
        self,
        *,
        session_id: str,
        participant_id: str,
        turn_number: int,
        draft_content: str,
        context_summary: str,
    ) -> ReviewGateDraft:
        """Stage an AI response for human review."""
        draft_id = uuid.uuid4().hex[:12]
        record = await self._fetch_one(
            _INSERT_SQL,
            draft_id,
            session_id,
            participant_id,
            turn_number,
            draft_content,
            context_summary,
        )
        return ReviewGateDraft.from_record(record)

    async def get_pending(
        self,
        session_id: str,
    ) -> list[ReviewGateDraft]:
        """Fetch all pending drafts for a session."""
        rows = await self._fetch_all(_PENDING_SQL, session_id)
        return [ReviewGateDraft.from_record(r) for r in rows]

    async def get_by_id(
        self,
        draft_id: str,
    ) -> ReviewGateDraft | None:
        """Fetch a single draft by id. Returns None if not found."""
        row = await self._fetch_one(_BY_ID_SQL, draft_id)
        return ReviewGateDraft.from_record(row) if row else None

    async def resolve(
        self,
        draft_id: str,
        *,
        resolution: str,
        edited_content: str | None = None,
    ) -> ReviewGateDraft:
        """Resolve a draft: approved, edited, rejected, or timed_out."""
        if resolution == "edited" and edited_content:
            record = await self._fetch_one(
                _RESOLVE_WITH_EDIT_SQL,
                resolution,
                edited_content,
                draft_id,
            )
        else:
            record = await self._fetch_one(
                _RESOLVE_SQL,
                resolution,
                draft_id,
            )
        return ReviewGateDraft.from_record(record)


_INSERT_SQL = """
    INSERT INTO review_gate_drafts
        (id, session_id, participant_id,
         turn_number, draft_content, context_summary)
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING *
"""

_PENDING_SQL = """
    SELECT * FROM review_gate_drafts
    WHERE session_id = $1 AND status = 'pending'
    ORDER BY created_at
"""

_BY_ID_SQL = "SELECT * FROM review_gate_drafts WHERE id = $1"

_RESOLVE_SQL = """
    UPDATE review_gate_drafts
    SET status = $1, resolved_at = NOW()
    WHERE id = $2
    RETURNING *
"""

_RESOLVE_WITH_EDIT_SQL = """
    UPDATE review_gate_drafts
    SET status = $1, edited_content = $2, resolved_at = NOW()
    WHERE id = $3
    RETURNING *
"""
