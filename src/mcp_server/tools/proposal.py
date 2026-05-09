# SPDX-License-Identifier: AGPL-3.0-or-later

"""Proposal tool endpoints — create, vote, resolve, list.

Phase 2c backend gap (T150). The underlying ProposalRepository
existed from Phase 1 but was unexposed over HTTP. These four
endpoints wrap it for the Web UI's ProposalTracker (T151–T153)
and also broadcast v1 WS events so connected clients update in
real time without polling.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.auth.guards import require_facilitator
from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant
from src.repositories.errors import DuplicateVoteError
from src.repositories.proposal_repo import Proposal, ProposalRepository

router = APIRouter(prefix="/tools/proposal", tags=["proposal"])


class _CreateProposalBody(BaseModel):
    """Request body for creating a proposal."""

    topic: str = Field(..., min_length=1, max_length=500)
    position: str = Field(..., min_length=1, max_length=5000)


class _VoteBody(BaseModel):
    """Request body for casting a vote."""

    proposal_id: str
    vote: Literal["accept", "reject", "abstain"]
    comment: str | None = None


class _ResolveBody(BaseModel):
    """Request body for resolving a proposal."""

    proposal_id: str
    status: Literal["accepted", "rejected", "expired"]


@router.post("/create")
async def create_proposal(
    request: Request,
    body: _CreateProposalBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Create a new proposal attributed to the caller."""
    session_repo = request.app.state.session_repo
    session = await session_repo.get_session(participant.session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    repo = ProposalRepository(request.app.state.pool)
    proposal = await repo.create_proposal(
        session_id=participant.session_id,
        proposed_by=participant.id,
        topic=body.topic,
        position=body.position,
        acceptance_mode=session.acceptance_mode,
    )
    await _broadcast("proposal_created", participant.session_id, proposal=_serialize(proposal))
    return {"status": "created", "proposal": _serialize(proposal)}


@router.post("/vote")
async def vote_on_proposal(
    request: Request,
    body: _VoteBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Cast a vote on an open proposal in the caller's session."""
    repo = ProposalRepository(request.app.state.pool)
    proposal = await repo.get_proposal(body.proposal_id)
    if proposal is None or proposal.session_id != participant.session_id:
        raise HTTPException(404, "proposal not found in session")
    try:
        vote = await repo.cast_vote(
            proposal_id=body.proposal_id,
            participant_id=participant.id,
            vote=body.vote,
            comment=body.comment,
        )
    except DuplicateVoteError as e:
        raise HTTPException(409, str(e)) from None
    tally = await _tally(repo, body.proposal_id)
    await _broadcast(
        "proposal_voted",
        participant.session_id,
        proposal_id=body.proposal_id,
        voter_id=participant.id,
        vote=body.vote,
        tally=tally,
    )
    return {"status": "voted", "proposal_id": body.proposal_id, "vote": vote.vote, "tally": tally}


@router.post("/resolve")
async def resolve_proposal(
    request: Request,
    body: _ResolveBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Resolve a proposal in the caller's session (facilitator only)."""
    await require_facilitator(request.app.state.pool, participant.session_id, participant.id)
    repo = ProposalRepository(request.app.state.pool)
    existing = await repo.get_proposal(body.proposal_id)
    if existing is None or existing.session_id != participant.session_id:
        raise HTTPException(404, "proposal not found in session")
    proposal = await repo.resolve_proposal(body.proposal_id, body.status)
    tally = await _tally(repo, proposal.id)
    await _broadcast(
        "proposal_resolved",
        participant.session_id,
        proposal_id=proposal.id,
        status=proposal.status,
        tally=tally,
    )
    return {"status": "resolved", "proposal": _serialize(proposal), "tally": tally}


@router.get("/list")
async def list_proposals(
    request: Request,
    *,
    include_resolved: bool = False,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """List proposals for the caller's session.

    Defaults to open only. Pass ``include_resolved=true`` to also get
    the most-recent 50 resolved entries in a separate ``resolved``
    field so the UI can render a history section alongside the
    active-vote pane.
    """
    repo = ProposalRepository(request.app.state.pool)
    proposals = await repo.get_open_proposals(participant.session_id)
    tallies = {p.id: await _tally(repo, p.id) for p in proposals}
    payload: dict = {
        "proposals": [{**_serialize(p), "tally": tallies[p.id]} for p in proposals],
    }
    if include_resolved:
        resolved = await repo.get_resolved_proposals(participant.session_id)
        resolved_tallies = {p.id: await _tally(repo, p.id) for p in resolved}
        payload["resolved"] = [{**_serialize(p), "tally": resolved_tallies[p.id]} for p in resolved]
    return payload


async def _tally(repo: ProposalRepository, proposal_id: str) -> dict:
    """Count votes by outcome for a proposal."""
    votes = await repo.get_votes(proposal_id)
    tally = {"accept": 0, "reject": 0, "abstain": 0}
    for v in votes:
        tally[v.vote] = tally.get(v.vote, 0) + 1
    return tally


def _serialize(p: Proposal) -> dict:
    """Flatten a Proposal dataclass for JSON output."""
    return {
        "id": p.id,
        "session_id": p.session_id,
        "proposed_by": p.proposed_by,
        "topic": p.topic,
        "position": p.position,
        "status": p.status,
        "acceptance_mode": p.acceptance_mode,
        "expires_at": p.expires_at.isoformat() if p.expires_at else None,
        "resolved_at": p.resolved_at.isoformat() if p.resolved_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


async def _broadcast(event_type: str, session_id: str, **fields) -> None:  # type: ignore[no-untyped-def]
    """Fan out a v1 WS event to all web-UI subscribers."""
    from src.web_ui.events import (
        proposal_created_event,
        proposal_resolved_event,
        proposal_voted_event,
    )
    from src.web_ui.websocket import broadcast_to_session

    builders = {
        "proposal_created": lambda: proposal_created_event(fields["proposal"]),
        "proposal_voted": lambda: proposal_voted_event(
            proposal_id=fields["proposal_id"],
            voter_id=fields["voter_id"],
            vote=fields["vote"],
            tally=fields["tally"],
        ),
        "proposal_resolved": lambda: proposal_resolved_event(
            proposal_id=fields["proposal_id"],
            status=fields["status"],
            tally=fields.get("tally"),
        ),
    }
    build = builders.get(event_type)
    if build is None:
        return
    await broadcast_to_session(session_id, build())
