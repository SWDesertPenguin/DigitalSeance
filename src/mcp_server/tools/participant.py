"""Participant tool endpoints — inject, history, status, config."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant

router = APIRouter(prefix="/tools/participant", tags=["participant"])


@router.post("/inject_message")
async def inject_message(
    request: Request,
    content: str,
    *,
    priority: int = 1,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Inject a human message into the interrupt queue."""
    int_repo = request.app.state.interrupt_repo
    entry = await int_repo.enqueue(
        session_id=participant.session_id,
        participant_id=participant.id,
        content=content,
        priority=priority,
    )
    return {"status": "enqueued", "id": entry.id}


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


@router.post("/set_routing_preference")
async def set_routing_preference(
    request: Request,
    preference: str,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Update routing preference."""
    p_repo = request.app.state.participant_repo
    await p_repo.update_role(participant.id, participant.role)
    # Update routing preference via direct SQL
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET routing_preference = $1" " WHERE id = $2",
            preference,
            participant.id,
        )
    return {"status": "updated", "preference": preference}


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
