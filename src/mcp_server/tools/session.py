"""Session lifecycle and loop control endpoints."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant

router = APIRouter(prefix="/tools/session", tags=["session"])

# In-memory loop tasks per session
_loop_tasks: dict[str, asyncio.Task] = {}


@router.post("/create")
async def create_session(
    request: Request,
    name: str,
    *,
    display_name: str,
    provider: str,
    model: str,
    model_tier: str,
    model_family: str,
    context_window: int,
    api_key: str = "",
) -> dict:
    """Create a new session. Returns facilitator token."""
    session_repo = request.app.state.session_repo
    session, facilitator, branch = await session_repo.create_session(
        name,
        facilitator_display_name=display_name,
        facilitator_provider=provider,
        facilitator_model=model,
        facilitator_model_tier=model_tier,
        facilitator_model_family=model_family,
        facilitator_context_window=context_window,
    )
    # Set API key and generate auth token if provided
    token = None
    if api_key:
        p_repo = request.app.state.participant_repo
        auth = request.app.state.auth_service
        await _set_facilitator_key(p_repo, facilitator.id, api_key)
        token = await auth.rotate_token(facilitator.id)
    result = _format_created(session, facilitator, branch)
    if token:
        result["auth_token"] = token
    return result


async def _set_facilitator_key(
    p_repo: object,
    facilitator_id: str,
    api_key: str,
) -> None:
    """Encrypt and store the facilitator's API key."""
    from src.database.encryption import encrypt_value

    encrypted = encrypt_value(api_key, key=p_repo._encryption_key)
    await p_repo._execute(
        "UPDATE participants SET api_key_encrypted = $1" " WHERE id = $2",
        encrypted,
        facilitator_id,
    )


@router.post("/pause")
async def pause_session(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Pause the session."""
    session_repo = request.app.state.session_repo
    session = await session_repo.update_status(
        participant.session_id,
        "paused",
    )
    return {"status": session.status}


@router.post("/resume")
async def resume_session(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Resume a paused session."""
    session_repo = request.app.state.session_repo
    session = await session_repo.update_status(
        participant.session_id,
        "active",
    )
    return {"status": session.status}


@router.post("/archive")
async def archive_session(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Archive the session (read-only)."""
    session_repo = request.app.state.session_repo
    session = await session_repo.update_status(
        participant.session_id,
        "archived",
    )
    return {"status": session.status}


@router.post("/start_loop")
async def start_loop(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Start the conversation loop for this session."""
    sid = participant.session_id
    if sid in _loop_tasks and not _loop_tasks[sid].done():
        return {"status": "already_running"}
    loop = request.app.state.conversation_loop
    _loop_tasks[sid] = asyncio.create_task(_run_loop(loop, sid))
    return {"status": "started"}


@router.post("/stop_loop")
async def stop_loop(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Stop the conversation loop for this session."""
    sid = participant.session_id
    task = _loop_tasks.pop(sid, None)
    if task and not task.done():
        task.cancel()
    return {"status": "stopped"}


@router.get("/export_markdown")
async def export_markdown(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Export transcript as markdown."""
    msg_repo = request.app.state.message_repo
    messages = await msg_repo.get_recent(
        participant.session_id,
        "main",
        10000,
    )
    lines = [_format_md_message(m) for m in messages]
    return {"format": "markdown", "content": "\n\n".join(lines)}


@router.get("/export_json")
async def export_json(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Export transcript as JSON."""
    msg_repo = request.app.state.message_repo
    messages = await msg_repo.get_recent(
        participant.session_id,
        "main",
        10000,
    )
    data = [_format_json_message(m) for m in messages]
    return {"format": "json", "content": json.dumps(data)}


async def _run_loop(loop: object, session_id: str) -> None:
    """Run the conversation loop until cancelled."""
    from src.repositories.errors import AllParticipantsExhaustedError

    while True:
        try:
            await loop.execute_turn(session_id)
        except AllParticipantsExhaustedError:
            break
        except asyncio.CancelledError:
            break


def _format_created(
    session: object,
    facilitator: object,
    branch: object,
) -> dict:
    """Format session creation response."""
    return {
        "session_id": session.id,
        "facilitator_id": facilitator.id,
        "branch_id": branch.id,
        "status": session.status,
    }


def _format_md_message(msg: object) -> str:
    """Format a message as markdown."""
    return f"**[{msg.speaker_type}]** {msg.content}"


def _format_json_message(msg: object) -> dict:
    """Format a message for JSON export."""
    return {
        "turn": msg.turn_number,
        "speaker": msg.speaker_id,
        "type": msg.speaker_type,
        "content": msg.content,
    }
