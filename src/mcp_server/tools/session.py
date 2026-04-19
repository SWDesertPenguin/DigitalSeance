"""Session lifecycle and loop control endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, field_validator

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant
from src.orchestrator.branch import get_main_branch_id
from src.repositories.errors import (
    AllParticipantsExhaustedError,
    SessionNotActiveError,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/session", tags=["session"])

# In-memory loop tasks per session
_loop_tasks: dict[str, asyncio.Task] = {}


_SWAGGER_PLACEHOLDER = "string"


class _CreateSessionBody(BaseModel):
    """Request body for session creation.

    For a human facilitator, only ``name`` and ``display_name`` are
    required — all AI-specific fields default to ``"human"`` / ``0``.
    """

    name: str
    display_name: str
    provider: str = "human"
    model: str = "human"
    model_tier: str = "n/a"
    model_family: str = "human"
    context_window: int = 0
    api_key: str = ""
    api_endpoint: str = ""
    review_gate_pause_scope: Literal["session", "participant"] = "session"

    @field_validator("name", "display_name")
    @classmethod
    def _reject_placeholder(cls, v: str, info) -> str:
        cleaned = (v or "").strip()
        if not cleaned or cleaned.lower() == _SWAGGER_PLACEHOLDER:
            msg = f"{info.field_name} must not be blank or the placeholder 'string'"
            raise ValueError(msg)
        return cleaned


@router.post("/create")
async def create_session(
    request: Request,
    body: _CreateSessionBody,
) -> dict:
    """Create a new session. API key sent in body, never in URL."""
    session_repo = request.app.state.session_repo
    session, facilitator, branch = await session_repo.create_session(
        body.name,
        facilitator_display_name=body.display_name,
        facilitator_provider=body.provider,
        facilitator_model=body.model,
        facilitator_model_tier=body.model_tier,
        facilitator_model_family=body.model_family,
        facilitator_context_window=body.context_window,
        facilitator_api_endpoint=body.api_endpoint or None,
        review_gate_pause_scope=body.review_gate_pause_scope,
    )
    if body.api_key:
        p_repo = request.app.state.participant_repo
        await _set_facilitator_key(p_repo, facilitator.id, body.api_key)
    auth = request.app.state.auth_service
    token = await auth.rotate_token(facilitator.id)
    result = _format_created(session, facilitator, branch)
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
    """Resume a paused session. Idempotent if already active."""
    session_repo = request.app.state.session_repo
    current = await session_repo.get_session(participant.session_id)
    if current and current.status == "active":
        return {"status": "active"}
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
    session_repo = request.app.state.session_repo
    session = await session_repo.get_session(sid)
    if session and session.status != "active":
        return {"status": "error", "detail": f"session is {session.status}"}
    loop = request.app.state.conversation_loop
    cm = request.app.state.connection_manager
    _loop_tasks[sid] = asyncio.create_task(
        _run_loop(loop, sid, session_repo, cm),
    )
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
    branch_id = await get_main_branch_id(
        request.app.state.pool,
        participant.session_id,
    )
    messages = await msg_repo.get_recent(participant.session_id, branch_id, 10000)
    lines = [_format_md_message(m) for m in messages]
    return {"format": "markdown", "content": "\n\n".join(lines)}


@router.get("/export_json")
async def export_json(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Export transcript as JSON."""
    msg_repo = request.app.state.message_repo
    branch_id = await get_main_branch_id(
        request.app.state.pool,
        participant.session_id,
    )
    messages = await msg_repo.get_recent(participant.session_id, branch_id, 10000)
    data = [_format_json_message(m) for m in messages]
    return {"format": "json", "content": json.dumps(data)}


async def _broadcast_turn(cm: object, session_id: str, result: object) -> None:
    """Broadcast a completed turn event to all SSE subscribers."""
    await cm.broadcast(
        session_id,
        {
            "turn": result.turn_number,
            "speaker_id": result.speaker_id,
            "action": result.action,
            "skipped": False,
        },
    )


async def _init_loop_from_session(
    loop: object,
    session_id: str,
    session_repo: object,
) -> None:
    """Load per-session config into the in-memory conversation loop."""
    session = await session_repo.get_session(session_id)
    if not session:
        return
    loop.set_cadence_preset(session_id, session.cadence_preset)
    loop.set_review_gate_pause_scope(session_id, session.review_gate_pause_scope)


async def _run_loop(
    loop: object,
    session_id: str,
    session_repo: object,
    connection_manager: object | None = None,
) -> None:
    """Run the conversation loop with cadence-based pacing."""
    await _init_loop_from_session(loop, session_id, session_repo)
    while True:
        try:
            result = await loop.execute_turn(session_id)
            if result.skipped:
                log.info("Skipped %s: %s", result.speaker_id, result.skip_reason)
            else:
                log.info("Turn %d done, delay=%.1fs", result.turn_number, result.delay_seconds)
            if connection_manager and not result.skipped:
                await _broadcast_turn(connection_manager, session_id, result)
            delay = result.delay_seconds or (5.0 if result.skipped else 0)
            if delay > 0:
                await asyncio.sleep(delay)
        except AllParticipantsExhaustedError:
            break
        except SessionNotActiveError:
            log.info("Session %s paused/archived, loop stopping", session_id)
            break
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("Loop crashed for session %s", session_id)
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
