"""Session lifecycle and loop control endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant
from src.orchestrator.branch import get_main_branch_id
from src.repositories.errors import (
    AllParticipantsExhaustedError,
    SessionNotActiveError,
)

# Short wordlists for git-branch-style auto-generated session names.
# Not cryptographic — just human-readable identifiers.
_SLUG_ADJECTIVES = (
    "amber",
    "brave",
    "clever",
    "crimson",
    "eager",
    "fancy",
    "gentle",
    "happy",
    "icy",
    "jade",
    "keen",
    "lively",
    "merry",
    "noble",
    "olive",
    "proud",
    "quiet",
    "rapid",
    "silver",
    "teal",
    "vivid",
    "witty",
)
_SLUG_ANIMALS = (
    "badger",
    "cheetah",
    "dolphin",
    "eagle",
    "falcon",
    "gazelle",
    "hawk",
    "iguana",
    "jaguar",
    "koala",
    "lynx",
    "mantis",
    "newt",
    "otter",
    "panda",
    "quail",
    "raven",
    "swan",
    "tiger",
    "urchin",
    "vixen",
    "wolf",
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/session", tags=["session"])

# In-memory loop tasks per session
_loop_tasks: dict[str, asyncio.Task] = {}


_SWAGGER_PLACEHOLDER = "string"


class _CreateSessionBody(BaseModel):
    """Request body for session creation.

    For a human facilitator, only ``display_name`` is required. ``name``
    may be blank — a git-branch-style slug is auto-generated on the
    server so the guest landing flow doesn't demand the user pick a
    session name before they've even started.
    """

    name: str = ""
    display_name: str
    provider: str = "human"
    model: str = "human"
    model_tier: str = "n/a"
    model_family: str = "human"
    context_window: int = 0
    api_key: str = ""
    api_endpoint: str = ""
    review_gate_pause_scope: Literal["session", "participant"] = "session"

    @field_validator("display_name")
    @classmethod
    def _reject_placeholder_display(cls, v: str, info) -> str:
        cleaned = (v or "").strip()
        if not cleaned or cleaned.lower() == _SWAGGER_PLACEHOLDER:
            msg = f"{info.field_name} must not be blank or the placeholder 'string'"
            raise ValueError(msg)
        return cleaned

    @field_validator("name")
    @classmethod
    def _reject_placeholder_name(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if cleaned.lower() == _SWAGGER_PLACEHOLDER:
            return ""
        return cleaned


def _generate_session_slug() -> str:
    """Return a short git-branch-style identifier: adjective-animal-hex."""
    adj = secrets.choice(_SLUG_ADJECTIVES)
    noun = secrets.choice(_SLUG_ANIMALS)
    suffix = secrets.token_hex(2)
    return f"{adj}-{noun}-{suffix}"


@router.post("/create")
async def create_session(
    request: Request,
    body: _CreateSessionBody,
) -> dict:
    """Create a new session. API key sent in body, never in URL."""
    session_repo = request.app.state.session_repo
    name = body.name or _generate_session_slug()
    session, facilitator, branch = await session_repo.create_session(
        name,
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
        "UPDATE participants SET api_key_encrypted = $1 WHERE id = $2",
        encrypted,
        facilitator_id,
    )


class _RequestJoinBody(BaseModel):
    """Body for the public self-service join request."""

    session_id: str
    display_name: str

    @field_validator("session_id", "display_name")
    @classmethod
    def _reject_blank(cls, v: str, info) -> str:
        cleaned = (v or "").strip()
        if not cleaned or cleaned.lower() == _SWAGGER_PLACEHOLDER:
            msg = f"{info.field_name} must not be blank or the placeholder 'string'"
            raise ValueError(msg)
        return cleaned


@router.post("/request_join")
async def request_join(request: Request, body: _RequestJoinBody) -> dict:
    """Public endpoint — create a pending participant for a self-join flow.

    The guest enters a session ID and a display name. We create a
    role='pending' participant, return an auth token so they can
    /login, and broadcast participant_update so the facilitator sees
    them appear without reloading.
    """
    session_repo = request.app.state.session_repo
    session = await session_repo.get_session(body.session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.status != "active":
        raise HTTPException(409, f"Session is {session.status}")
    p_repo = request.app.state.participant_repo
    new_p, _ = await p_repo.add_participant(
        session_id=body.session_id,
        display_name=body.display_name,
        provider="human",
        model="human",
        model_tier="n/a",
        model_family="human",
        context_window=0,
        auto_approve=False,
    )
    auth_token = await _issue_and_broadcast(request, body.session_id, new_p.id, p_repo)
    return {
        "participant_id": new_p.id,
        "session_id": body.session_id,
        "role": new_p.role,
        "auth_token": auth_token,
    }


async def _issue_and_broadcast(
    request: Request,
    session_id: str,
    participant_id: str,
    p_repo: object,
) -> str:
    """Mint an auth token for a freshly-added participant + broadcast."""
    from src.web_ui.events import broadcast_participant_update

    auth = request.app.state.auth_service
    token = await auth.rotate_token(participant_id)
    await broadcast_participant_update(
        session_id,
        participant_id,
        p_repo,
        request.app.state.log_repo,
    )
    return token


class _RedeemInviteBody(BaseModel):
    """Body for the public invite-redeem flow."""

    invite_token: str
    display_name: str

    @field_validator("invite_token", "display_name")
    @classmethod
    def _reject_blank(cls, v: str, info) -> str:
        cleaned = (v or "").strip()
        if not cleaned or cleaned.lower() == _SWAGGER_PLACEHOLDER:
            msg = f"{info.field_name} must not be blank or the placeholder 'string'"
            raise ValueError(msg)
        return cleaned


@router.post("/redeem_invite")
async def redeem_invite(request: Request, body: _RedeemInviteBody) -> dict:
    """Public endpoint — swap an invite token for a pre-approved auth token.

    Unlike /request_join (pending until approved), invite redemption
    is pre-authorized by the facilitator who issued the invite.
    """
    invite = await _redeem_or_raise(request, body.invite_token)
    p_repo = request.app.state.participant_repo
    new_p, _ = await p_repo.add_participant(
        session_id=invite.session_id,
        display_name=body.display_name,
        provider="human",
        model="human",
        model_tier="n/a",
        model_family="human",
        context_window=0,
        auto_approve=True,
        invited_by=invite.created_by,
    )
    auth_token = await _issue_and_broadcast(
        request,
        invite.session_id,
        new_p.id,
        p_repo,
    )
    return {
        "participant_id": new_p.id,
        "session_id": invite.session_id,
        "role": new_p.role,
        "auth_token": auth_token,
    }


async def _redeem_or_raise(request: Request, invite_token: str) -> object:
    """Redeem via invite_repo, mapping domain errors to 410 HTTP."""
    from src.repositories.errors import InviteExhaustedError, InviteExpiredError

    try:
        return await request.app.state.invite_repo.redeem_invite(invite_token)
    except InviteExpiredError as e:
        raise HTTPException(410, str(e)) from None
    except InviteExhaustedError as e:
        raise HTTPException(410, str(e)) from None


class _SetNameBody(BaseModel):
    """Body for session rename."""

    name: str

    @field_validator("name")
    @classmethod
    def _reject_blank(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned or cleaned.lower() == _SWAGGER_PLACEHOLDER:
            msg = "name must not be blank or the placeholder 'string'"
            raise ValueError(msg)
        return cleaned


@router.post("/set_name")
async def set_session_name(
    request: Request,
    body: _SetNameBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Rename the current session (facilitator-only)."""
    if participant.role != "facilitator":
        raise HTTPException(403, "Only the facilitator can rename a session")
    session_repo = request.app.state.session_repo
    session = await session_repo.update_name(participant.session_id, body.name)
    log_repo = request.app.state.log_repo
    await log_repo.log_admin_action(
        session_id=session.id,
        facilitator_id=participant.id,
        action="rename_session",
        target_id=session.id,
        new_value=session.name,
    )
    from src.web_ui.events import session_updated_event
    from src.web_ui.websocket import broadcast_to_session

    await broadcast_to_session(session.id, session_updated_event({"name": session.name}))
    return {"session_id": session.id, "name": session.name}


def is_loop_running(session_id: str) -> bool:
    """Expose the in-memory loop-task registry for state snapshots."""
    task = _loop_tasks.get(session_id)
    return task is not None and not task.done()


@router.get("/loop_status")
async def get_loop_status(
    request: Request,  # noqa: ARG001 — required for router signature parity
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Return whether the loop is running for this session."""
    return {
        "session_id": participant.session_id,
        "loop_running": is_loop_running(participant.session_id),
    }


@router.post("/pause")
async def pause_session(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Pause the session."""
    session_repo = request.app.state.session_repo
    session = await session_repo.update_status(participant.session_id, "paused")
    await _broadcast_status(participant.session_id, session.status)
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
    session = await session_repo.update_status(participant.session_id, "active")
    await _broadcast_status(participant.session_id, session.status)
    return {"status": session.status}


@router.post("/archive")
async def archive_session(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Archive the session (read-only)."""
    session_repo = request.app.state.session_repo
    session = await session_repo.update_status(participant.session_id, "archived")
    await _broadcast_status(participant.session_id, session.status)
    return {"status": session.status}


async def _broadcast_status(session_id: str, status: str) -> None:
    """Push a session_status_changed event to Web UI subscribers."""
    from src.web_ui.events import session_status_changed_event
    from src.web_ui.websocket import broadcast_to_session

    await broadcast_to_session(session_id, session_status_changed_event(status))


@router.post("/start_loop")
async def start_loop(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Start the conversation loop for this session.

    Refuses to start when no human message exists yet so the first turn
    can't be an AI hallucinating a welcome ("Understood! I look forward
    to…"). The facilitator must send an opening message first.
    """
    sid = participant.session_id
    if sid in _loop_tasks and not _loop_tasks[sid].done():
        return {"status": "already_running"}
    session_repo = request.app.state.session_repo
    session = await session_repo.get_session(sid)
    if session and session.status != "active":
        return {"status": "error", "detail": f"session is {session.status}"}
    if not await _has_human_message(request, sid):
        raise HTTPException(
            409,
            "Send an opening message before starting the loop — AIs " "shouldn't speak first.",
        )
    loop = request.app.state.conversation_loop
    cm = request.app.state.connection_manager
    _loop_tasks[sid] = asyncio.create_task(
        _run_loop(loop, sid, session_repo, cm),
    )
    await _broadcast_loop_status(sid, running=True)
    return {"status": "started"}


async def _has_human_message(request: Request, session_id: str) -> bool:
    """Return True if at least one human message exists in the session."""
    branch_id = await get_main_branch_id(request.app.state.pool, session_id)
    msg_repo = request.app.state.message_repo
    recent = await msg_repo.get_recent(session_id, branch_id, limit=200)
    return any(m.speaker_type == "human" for m in recent)


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
    await _broadcast_loop_status(sid, running=False)
    return {"status": "stopped"}


async def _broadcast_loop_status(session_id: str, *, running: bool) -> None:
    """Push loop_status so the UI header can toggle the Loop badge."""
    from src.web_ui.events import loop_status_event
    from src.web_ui.websocket import broadcast_to_session

    await broadcast_to_session(session_id, loop_status_event(running))


@router.get("/summary")
async def get_summary(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Return the latest summary for the session (any participant can read)."""
    msg_repo = request.app.state.message_repo
    branch_id = await get_main_branch_id(request.app.state.pool, participant.session_id)
    summaries = await msg_repo.get_summaries(participant.session_id, branch_id)
    if not summaries:
        return {"summary": None}
    latest = summaries[-1]
    try:
        parsed = json.loads(latest.content)
    except (json.JSONDecodeError, TypeError):
        parsed = {"narrative": latest.content}
    return {
        "turn_number": latest.turn_number,
        "summary_epoch": latest.summary_epoch,
        "summary": parsed,
    }


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
    """Broadcast a completed turn event to SSE subscribers (legacy shape).

    The v1 `message` event for Web UI subscribers is emitted by
    `_persist_turn` itself now (loop.py::_emit_message_to_web_ui) so it
    has access to the full persisted Message including content.
    """
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


_SKIP_BACKOFF_BASE_S = 5.0
_SKIP_BACKOFF_MAX_S = 60.0


async def _run_loop(
    loop: object,
    session_id: str,
    session_repo: object,
    connection_manager: object | None = None,
) -> None:
    """Run the conversation loop with cadence-based pacing + skip backoff.

    Consecutive skips (no_new_input, provider_error, review_gate_pending)
    ramp up the inter-tick delay exponentially from 5s to a 60s cap.
    A real turn resets the counter. This prevents the 15-skips-in-2-min
    log spam seen in Test05-Web01 when the only viable AI just spoke.
    """
    await _init_loop_from_session(loop, session_id, session_repo)
    skips = 0
    while True:
        try:
            result = await loop.execute_turn(session_id)
            skips = _log_and_count(result, skips)
            if connection_manager and not result.skipped:
                await _broadcast_turn(connection_manager, session_id, result)
            delay = _tick_delay(result, skips)
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


def _log_and_count(result: object, skips: int) -> int:
    """Emit the per-tick log line and return the new consecutive-skip count."""
    if result.skipped:
        log.info("Skipped %s: %s (skips=%d)", result.speaker_id, result.skip_reason, skips + 1)
        return skips + 1
    log.info("Turn %d done, delay=%.1fs", result.turn_number, result.delay_seconds)
    return 0


def _tick_delay(result: object, skips: int) -> float:
    """Return the sleep delay after this tick; backs off on consecutive skips."""
    if not result.skipped:
        return result.delay_seconds or 0.0
    backoff = min(_SKIP_BACKOFF_BASE_S * (2 ** max(0, skips - 1)), _SKIP_BACKOFF_MAX_S)
    return max(result.delay_seconds or 0.0, backoff)


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
