# SPDX-License-Identifier: AGPL-3.0-or-later

"""US9: Proposals and voting — acceptance modes and duplicate prevention."""

from __future__ import annotations

import asyncpg
import pytest

from src.repositories.errors import DuplicateVoteError
from src.repositories.proposal_repo import ProposalRepository
from src.repositories.session_repo import SessionRepository


@pytest.fixture
async def session_and_participants(
    pool: asyncpg.Pool,
) -> tuple[str, str, str]:
    """Create a session with 2 participants, return IDs."""
    repo = SessionRepository(pool)
    session, facilitator, _ = await repo.create_session(
        "Proposal Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    # Add second participant directly via SQL
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO participants
               (id, session_id, display_name, role, provider, model,
                model_tier, model_family, context_window)
               VALUES ('bob-id', $1, 'Bob', 'participant',
                       'openai', 'gpt-4o', 'high', 'gpt', 128000)""",
            session.id,
        )
    return session.id, facilitator.id, "bob-id"


@pytest.fixture
def repo(pool: asyncpg.Pool) -> ProposalRepository:
    """Provide a ProposalRepository."""
    return ProposalRepository(pool)


async def test_create_proposal(
    repo: ProposalRepository,
    session_and_participants: tuple[str, str, str],
) -> None:
    """Proposals are created with correct fields."""
    sid, pid, _ = session_and_participants
    proposal = await repo.create_proposal(
        session_id=sid,
        proposed_by=pid,
        topic="Architecture choice",
        position="Use microservices",
        acceptance_mode="unanimous",
    )
    assert proposal.status == "open"
    assert proposal.topic == "Architecture choice"
    assert proposal.acceptance_mode == "unanimous"


async def test_cast_vote(
    repo: ProposalRepository,
    session_and_participants: tuple[str, str, str],
) -> None:
    """Votes are recorded correctly."""
    sid, pid, _ = session_and_participants
    proposal = await repo.create_proposal(
        session_id=sid,
        proposed_by=pid,
        topic="Test",
        position="Yes",
        acceptance_mode="unanimous",
    )
    vote = await repo.cast_vote(
        proposal_id=proposal.id,
        participant_id=pid,
        vote="accept",
    )
    assert vote.vote == "accept"
    assert vote.proposal_id == proposal.id


async def test_duplicate_vote_rejected(
    repo: ProposalRepository,
    session_and_participants: tuple[str, str, str],
) -> None:
    """Second vote from same participant is rejected."""
    sid, pid, _ = session_and_participants
    proposal = await repo.create_proposal(
        session_id=sid,
        proposed_by=pid,
        topic="Test",
        position="Yes",
        acceptance_mode="unanimous",
    )
    await repo.cast_vote(
        proposal_id=proposal.id,
        participant_id=pid,
        vote="accept",
    )
    with pytest.raises(DuplicateVoteError):
        await repo.cast_vote(
            proposal_id=proposal.id,
            participant_id=pid,
            vote="reject",
        )


async def test_resolve_proposal(
    repo: ProposalRepository,
    session_and_participants: tuple[str, str, str],
) -> None:
    """Proposals can be resolved with a status."""
    sid, pid, bob_id = session_and_participants
    proposal = await repo.create_proposal(
        session_id=sid,
        proposed_by=pid,
        topic="Resolve test",
        position="Yes",
        acceptance_mode="unanimous",
    )
    await repo.cast_vote(
        proposal_id=proposal.id,
        participant_id=pid,
        vote="accept",
    )
    await repo.cast_vote(
        proposal_id=proposal.id,
        participant_id=bob_id,
        vote="accept",
    )
    resolved = await repo.resolve_proposal(proposal.id, "accepted")
    assert resolved.status == "accepted"
    assert resolved.resolved_at is not None


async def test_get_open_proposals(
    repo: ProposalRepository,
    session_and_participants: tuple[str, str, str],
) -> None:
    """get_open_proposals only returns open proposals."""
    sid, pid, _ = session_and_participants
    p1 = await repo.create_proposal(
        session_id=sid,
        proposed_by=pid,
        topic="Open",
        position="Yes",
        acceptance_mode="facilitator",
    )
    await repo.create_proposal(
        session_id=sid,
        proposed_by=pid,
        topic="Also open",
        position="Maybe",
        acceptance_mode="facilitator",
    )
    await repo.resolve_proposal(p1.id, "accepted")

    open_proposals = await repo.get_open_proposals(sid)
    assert len(open_proposals) == 1
    assert open_proposals[0].topic == "Also open"
