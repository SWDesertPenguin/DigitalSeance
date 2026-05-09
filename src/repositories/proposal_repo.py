# SPDX-License-Identifier: AGPL-3.0-or-later

"""Proposal and Vote repository — decision-making with acceptance modes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.repositories.base import BaseRepository
from src.repositories.errors import DuplicateVoteError


@dataclass(frozen=True, slots=True)
class Proposal:
    """A decision proposal awaiting resolution."""

    id: str
    session_id: str
    proposed_by: str
    topic: str
    position: str
    status: str
    acceptance_mode: str
    expires_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime

    @classmethod
    def from_record(cls, record: Any) -> Proposal:
        """Construct from an asyncpg Record."""
        return cls(**{f: record[f] for f in cls.__slots__})


@dataclass(frozen=True, slots=True)
class Vote:
    """A participant's vote on a proposal (immutable)."""

    proposal_id: str
    participant_id: str
    vote: str
    comment: str | None
    created_at: datetime

    @classmethod
    def from_record(cls, record: Any) -> Vote:
        """Construct from an asyncpg Record."""
        return cls(**{f: record[f] for f in cls.__slots__})


class ProposalRepository(BaseRepository):
    """Data access for proposals and votes."""

    async def create_proposal(
        self,
        *,
        session_id: str,
        proposed_by: str,
        topic: str,
        position: str,
        acceptance_mode: str,
        expires_at: datetime | None = None,
    ) -> Proposal:
        """Create a new proposal."""
        proposal_id = uuid.uuid4().hex[:12]
        record = await self._fetch_one(
            _INSERT_PROPOSAL_SQL,
            proposal_id,
            session_id,
            proposed_by,
            topic,
            position,
            acceptance_mode,
            expires_at,
        )
        return Proposal.from_record(record)

    async def get_proposal(self, proposal_id: str) -> Proposal | None:
        """Fetch a proposal by id (cross-session lookup)."""
        record = await self._fetch_one(
            "SELECT * FROM proposals WHERE id = $1",
            proposal_id,
        )
        return Proposal.from_record(record) if record else None

    async def cast_vote(
        self,
        *,
        proposal_id: str,
        participant_id: str,
        vote: str,
        comment: str | None = None,
    ) -> Vote:
        """Cast a vote. Raises DuplicateVoteError if already voted."""
        existing = await self._fetch_one(
            _CHECK_VOTE_SQL,
            proposal_id,
            participant_id,
        )
        if existing:
            raise DuplicateVoteError("Already voted on this proposal")
        record = await self._fetch_one(
            _INSERT_VOTE_SQL,
            proposal_id,
            participant_id,
            vote,
            comment,
        )
        return Vote.from_record(record)

    async def get_votes(
        self,
        proposal_id: str,
    ) -> list[Vote]:
        """Fetch all votes for a proposal."""
        rows = await self._fetch_all(
            "SELECT * FROM votes WHERE proposal_id = $1",
            proposal_id,
        )
        return [Vote.from_record(r) for r in rows]

    async def resolve_proposal(
        self,
        proposal_id: str,
        status: str,
    ) -> Proposal:
        """Resolve a proposal: accepted, rejected, or expired."""
        record = await self._fetch_one(
            _RESOLVE_SQL,
            status,
            proposal_id,
        )
        return Proposal.from_record(record)

    async def get_open_proposals(
        self,
        session_id: str,
    ) -> list[Proposal]:
        """Fetch all open proposals for a session."""
        rows = await self._fetch_all(
            _OPEN_PROPOSALS_SQL,
            session_id,
        )
        return [Proposal.from_record(r) for r in rows]

    async def get_resolved_proposals(
        self,
        session_id: str,
        *,
        limit: int = 50,
    ) -> list[Proposal]:
        """Fetch resolved proposals (accepted / rejected / withdrawn) for history."""
        rows = await self._fetch_all(
            "SELECT * FROM proposals WHERE session_id = $1 AND status != 'open' "
            "ORDER BY created_at DESC LIMIT $2",
            session_id,
            limit,
        )
        return [Proposal.from_record(r) for r in rows]


_INSERT_PROPOSAL_SQL = """
    INSERT INTO proposals
        (id, session_id, proposed_by, topic,
         position, acceptance_mode, expires_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    RETURNING *
"""

_CHECK_VOTE_SQL = """
    SELECT 1 FROM votes
    WHERE proposal_id = $1 AND participant_id = $2
"""

_INSERT_VOTE_SQL = """
    INSERT INTO votes (proposal_id, participant_id, vote, comment)
    VALUES ($1, $2, $3, $4)
    RETURNING *
"""

_RESOLVE_SQL = """
    UPDATE proposals
    SET status = $1, resolved_at = NOW()
    WHERE id = $2
    RETURNING *
"""

_OPEN_PROPOSALS_SQL = """
    SELECT * FROM proposals
    WHERE session_id = $1 AND status = 'open'
    ORDER BY created_at
"""
