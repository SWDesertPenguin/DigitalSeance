"""Participant tool endpoints — inject, history, status, config."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant
from src.orchestrator.branch import get_main_branch_id
from src.repositories.errors import SessionNotActiveError

router = APIRouter(prefix="/tools/participant", tags=["participant"])


class _InjectMessageBody(BaseModel):
    """Request body for injecting a message."""

    content: str
    priority: int = 1


@router.post("/inject_message")
async def inject_message(
    request: Request,
    body: _InjectMessageBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Inject a human message: persist to transcript + enqueue for routing.

    The transcript write captures arrival-time ordering (so interjections
    sort correctly relative to concurrent AI turns). The interrupt queue
    entry still drives routing/cadence signals in the turn loop.
    """
    int_repo = request.app.state.interrupt_repo
    persisted = await _try_persist_injection(request, participant, body)
    entry = await int_repo.enqueue(
        session_id=participant.session_id,
        participant_id=participant.id,
        content=body.content,
        priority=body.priority,
    )
    status = "enqueued" if persisted else "enqueued_pending"
    return {"status": status, "id": entry.id}


async def _try_persist_injection(
    request: Request,
    participant: Participant,
    body: _InjectMessageBody,
) -> bool:
    """Write injection to transcript; return False if session is paused."""
    msg_repo = request.app.state.message_repo
    pool = request.app.state.pool
    branch_id = await get_main_branch_id(pool, participant.session_id)
    try:
        await msg_repo.append_message(
            session_id=participant.session_id,
            branch_id=branch_id,
            speaker_id=participant.id,
            speaker_type="human",
            content=body.content,
            token_count=max(len(body.content) // 4, 1),
            complexity_score="n/a",
        )
    except SessionNotActiveError:
        return False
    return True


@router.get("/status")
async def get_status(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Get session status and participant count."""
    session_repo = request.app.state.session_repo
    session = await session_repo.get_session(participant.session_id)
    return _format_status(session)


@router.get("/history")
async def get_history(
    request: Request,
    *,
    limit: int = 20,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Get recent conversation history."""
    msg_repo = request.app.state.message_repo
    branch_id = await _get_branch_id(request, participant.session_id)
    messages = await msg_repo.get_recent(
        participant.session_id,
        branch_id,
        limit,
    )
    return {"messages": [_format_message(m) for m in messages]}


@router.get("/summary")
async def get_summary(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Get latest summarization checkpoint."""
    msg_repo = request.app.state.message_repo
    branch_id = await _get_branch_id(request, participant.session_id)
    summaries = await msg_repo.get_summaries(
        participant.session_id,
        branch_id,
    )
    if not summaries:
        return {"summary": None}
    return {"summary": summaries[-1].content}


async def _get_branch_id(request: Request, session_id: str) -> str:
    """Look up the main branch ID for a session."""
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT id FROM branches WHERE session_id = $1 LIMIT 1",
            session_id,
        )
    return result or "main"


_SelfRoutingPreference = Literal[
    "always",
    "review_gate",
    "delegate_low",
    "domain_gated",
    "burst",
    "observer",
    "addressed_only",
    "human_only",
]


class _SelfRoutingBody(BaseModel):
    """Request body for a participant setting their own routing preference."""

    preference: _SelfRoutingPreference


@router.post("/set_routing_preference")
async def set_own_routing_preference(
    request: Request,
    body: _SelfRoutingBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Set the caller's own routing preference (T250 self-serve variant).

    The facilitator-only variant at /tools/facilitator/set_routing_preference
    remains for cross-participant edits; this endpoint only ever mutates
    the caller's own row, identified by the auth token.
    """
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE participants SET routing_preference = $1 WHERE id = $2",
            body.preference,
            participant.id,
        )
    if result == "UPDATE 0":
        raise HTTPException(404, "participant row not found")
    participant_repo = request.app.state.participant_repo
    from src.web_ui.events import broadcast_participant_update

    await broadcast_participant_update(
        participant.session_id,
        participant.id,
        participant_repo,
    )
    return {
        "status": "updated",
        "participant_id": participant.id,
        "preference": body.preference,
    }


@router.post("/rotate_token")
async def rotate_token(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Rotate own auth token."""
    auth_service = request.app.state.auth_service
    new_token = await auth_service.rotate_token(participant.id)
    return {"token": new_token}


def _format_status(session: object) -> dict:
    """Format session for status response."""
    return {
        "session_id": session.id,
        "name": session.name,
        "status": session.status,
        "current_turn": session.current_turn,
        "cadence": session.cadence_preset,
    }


def _format_message(msg: object) -> dict:
    """Format a message for API response."""
    return {
        "turn": msg.turn_number,
        "speaker": msg.speaker_id,
        "type": msg.speaker_type,
        "content": msg.content,
    }
