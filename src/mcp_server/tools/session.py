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

# Per-session lock serializing summarize_now / archive-time summarization so
# concurrent clicks can't race on last_summary_turn (observed bug: second
# call read stale last_summary_turn and wrote an older epoch over the newer).
_summary_locks: dict[str, asyncio.Lock] = {}


def _summary_lock(session_id: str) -> asyncio.Lock:
    """Return (creating if needed) the per-session summary lock."""
    lock = _summary_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _summary_locks[session_id] = lock
    return lock


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
    await _reject_duplicate_human_name(p_repo, body.session_id, body.display_name)
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
    """Public endpoint — swap an invite token for a pre-approved auth token."""
    invite = await _redeem_or_raise(request, body.invite_token)
    p_repo = request.app.state.participant_repo
    await _reject_duplicate_human_name(p_repo, invite.session_id, body.display_name)
    new_p = await _persist_invite_redeemer(p_repo, invite, body.display_name)
    auth_token = await _issue_and_broadcast(request, invite.session_id, new_p.id, p_repo)
    if is_loop_running(invite.session_id):
        from src.orchestrator.announcements import announce_arrival

        await announce_arrival(
            pool=request.app.state.pool,
            msg_repo=request.app.state.message_repo,
            session_id=invite.session_id,
            speaker_id=new_p.id,
            joining_name=new_p.display_name,
            kind="joined the session",
        )
    return {
        "participant_id": new_p.id,
        "session_id": invite.session_id,
        "role": new_p.role,
        "auth_token": auth_token,
    }


async def _reject_duplicate_human_name(
    p_repo: object,
    session_id: str,
    display_name: str,
) -> None:
    """409 if a human participant already has this display_name in the session.

    Shares ``_DEPARTED_STATUSES`` with the facilitator guard so offline
    or released ('reset') humans don't block the same name from being
    redeemed on a fresh invite.
    """
    from src.mcp_server.tools.facilitator import _DEPARTED_STATUSES

    cleaned = display_name.strip().lower()
    existing = await p_repo.list_participants(session_id)
    for p in existing:
        if p.status in _DEPARTED_STATUSES:
            continue
        if p.provider == "human" and p.display_name.strip().lower() == cleaned:
            raise HTTPException(
                409,
                f"A participant named '{p.display_name}' is already in this session",
            )


async def _persist_invite_redeemer(
    p_repo: object,
    invite: object,
    display_name: str,
) -> Participant:
    """Wrap repo.add_participant for the invite-redeem flow (auto-approved)."""
    new_p, _ = await p_repo.add_participant(
        session_id=invite.session_id,
        display_name=display_name,
        provider="human",
        model="human",
        model_tier="n/a",
        model_family="human",
        context_window=0,
        auto_approve=True,
        invited_by=invite.created_by,
    )
    return new_p


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
    """Pause the session. Facilitator only."""
    if participant.role != "facilitator":
        raise HTTPException(403, "Only the facilitator can pause the session")
    session_repo = request.app.state.session_repo
    current = await session_repo.get_session(participant.session_id)
    prior = current.status if current else "unknown"
    session = await session_repo.update_status(participant.session_id, "paused")
    await _broadcast_status(participant.session_id, session.status)
    await _audit_status_change(request, participant, "pause_session", prior, session.status)
    return {"status": session.status}


@router.post("/resume")
async def resume_session(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Resume a paused session. Idempotent if already active. Facilitator only."""
    if participant.role != "facilitator":
        raise HTTPException(403, "Only the facilitator can resume the session")
    session_repo = request.app.state.session_repo
    current = await session_repo.get_session(participant.session_id)
    if current and current.status == "active":
        return {"status": "active"}
    prior = current.status if current else "unknown"
    session = await session_repo.update_status(participant.session_id, "active")
    await _broadcast_status(participant.session_id, session.status)
    await _audit_status_change(request, participant, "resume_session", prior, session.status)
    return {"status": session.status}


async def _audit_status_change(
    request: Request,
    participant: Participant,
    action: str,
    prior: str,
    new: str,
) -> None:
    """Log a facilitator-triggered session-lifecycle transition.

    Closes the forensic-trail gap flagged by Test07-Web08: pause/resume/
    archive/start_loop/stop_loop/summarize_now all meaningfully change
    state but previously left no admin_audit_log entry, so a reviewer
    couldn't reconstruct why the loop was idle at a given turn.
    """
    log_repo = request.app.state.log_repo
    await log_repo.log_admin_action(
        session_id=participant.session_id,
        facilitator_id=participant.id,
        action=action,
        target_id=participant.session_id,
        previous_value=prior,
        new_value=new,
    )


@router.post("/archive")
async def archive_session(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Archive the session: stop the loop, auto-summarize, flip status.

    Summarization must run BEFORE the status flip — appending the summary
    message goes through ``_verify_session_active`` which rejects non-
    active sessions, so archiving first would make the final summary
    always fail (exactly what happened in Test06-Web05).
    """
    if participant.role != "facilitator":
        raise HTTPException(403, "Only the facilitator can archive the session")
    sid = participant.session_id
    task = _loop_tasks.pop(sid, None)
    if task and not task.done():
        task.cancel()
    loop = request.app.state.conversation_loop
    async with _summary_lock(sid):
        try:
            await loop._summarizer.run_checkpoint(sid)  # noqa: SLF001
        except Exception:  # noqa: BLE001 — archive must not fail on summary hiccup
            log.exception("Archive-time summary failed for %s", sid)
    session_repo = request.app.state.session_repo
    current = await session_repo.get_session(sid)
    prior = current.status if current else "unknown"
    session = await session_repo.update_status(sid, "archived")
    await _broadcast_status(sid, session.status)
    await _broadcast_loop_status(sid, running=False)
    await _audit_status_change(request, participant, "archive_session", prior, session.status)
    return {"status": session.status}


@router.post("/summarize_now")
async def summarize_now(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Force a summarization checkpoint off-cadence. Facilitator only.

    Serialized per session — concurrent clicks would otherwise both read
    ``last_summary_turn`` before either wrote, producing an older epoch
    overwriting a newer one (Test06-Web05 repro).
    """
    if participant.role != "facilitator":
        raise HTTPException(403, "Only the facilitator can trigger a summary")
    loop = request.app.state.conversation_loop
    async with _summary_lock(participant.session_id):
        try:
            await loop._summarizer.run_checkpoint(participant.session_id)  # noqa: SLF001
        except Exception as e:  # noqa: BLE001 — expose the failure reason
            raise HTTPException(500, f"Summary generation failed: {e}") from None
    await _audit_status_change(request, participant, "summarize_now", "", "forced")
    return {"status": "ok"}


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
    """Start the conversation loop for this session. Facilitator only.

    Refuses to start when no human message exists yet so the first turn
    can't be an AI hallucinating a welcome ("Understood! I look forward
    to…"). The facilitator must send an opening message first.
    """
    if participant.role != "facilitator":
        raise HTTPException(403, "Only the facilitator can start the loop")
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
            "Send an opening message before starting the loop — AIs shouldn't speak first.",
        )
    loop = request.app.state.conversation_loop
    cm = request.app.state.connection_manager
    _loop_tasks[sid] = asyncio.create_task(
        _run_loop(loop, sid, session_repo, cm),
    )
    await _broadcast_loop_status(sid, running=True)
    await _audit_status_change(request, participant, "start_loop", "idle", "running")
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
    """Stop the conversation loop for this session. Facilitator only."""
    if participant.role != "facilitator":
        raise HTTPException(403, "Only the facilitator can stop the loop")
    sid = participant.session_id
    was_running = sid in _loop_tasks and not _loop_tasks[sid].done()
    task = _loop_tasks.pop(sid, None)
    if task and not task.done():
        task.cancel()
    await _broadcast_loop_status(sid, running=False)
    if was_running:
        await _audit_status_change(request, participant, "stop_loop", "running", "idle")
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


@router.get("/list_summaries")
async def list_summaries(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Return the chronological history of summary checkpoints.

    Each entry includes turn_number, summary_epoch, created_at, and the
    parsed JSON body (or a narrative fallback if parsing fails). The
    Web UI renders this as a collapsible "Summary History" panel so
    operators can scroll back through earlier checkpoints — today only
    the latest summary is visible without re-running summarize_now.
    """
    msg_repo = request.app.state.message_repo
    branch_id = await get_main_branch_id(request.app.state.pool, participant.session_id)
    summaries = await msg_repo.get_summaries(participant.session_id, branch_id)
    return {"summaries": [_format_summary_row(s) for s in summaries]}


def _format_summary_row(s: object) -> dict:
    """Shape a summary Message row for the list_summaries response."""
    try:
        parsed = json.loads(s.content)
    except (json.JSONDecodeError, TypeError):
        parsed = {"narrative": s.content}
    return {
        "turn_number": s.turn_number,
        "summary_epoch": s.summary_epoch,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "summary": parsed,
    }


@router.get("/list_review_gates")
async def list_review_gates(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Return review-gate audit history (approve / reject / edit) for the session.

    Sourced from admin_audit_log; the panel renders it next to summary
    checkpoints so operators can scroll back through what was edited or
    rejected. Newest first.
    """
    log_repo = request.app.state.log_repo
    rows = await log_repo.get_audit_log(participant.session_id)
    gates = [_format_gate_row(r) for r in rows if r.action.startswith("review_gate_")]
    gates.reverse()
    return {"review_gates": gates}


def _format_gate_row(r: object) -> dict:
    """Shape an admin_audit_log row for the list_review_gates response."""
    return {
        "action": r.action,
        "draft_id": r.target_id,
        "facilitator_id": r.facilitator_id,
        "reason": r.new_value,
        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
    }


@router.get("/export_summaries")
async def export_summaries(
    request: Request,
    *,
    fmt: Literal["json", "markdown"] = "json",
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Export the full summary history as JSON or markdown.

    Mirrors the transcript-export pattern (export_json / export_markdown).
    Markdown emits a per-checkpoint header + the structured fields so
    operators can paste a session digest into a notebook or ticket.
    """
    msg_repo = request.app.state.message_repo
    branch_id = await get_main_branch_id(request.app.state.pool, participant.session_id)
    summaries = await msg_repo.get_summaries(participant.session_id, branch_id)
    rows = [_format_summary_row(s) for s in summaries]
    if fmt == "markdown":
        return {"format": "markdown", "content": _summaries_to_markdown(rows)}
    return {"format": "json", "content": json.dumps(rows, indent=2)}


def _summaries_to_markdown(rows: list[dict]) -> str:
    """Render summary rows as a markdown digest, newest at the bottom."""
    if not rows:
        return "_No summaries yet._"
    return "\n\n---\n\n".join(_summary_section(r) for r in rows)


def _summary_section(row: dict) -> str:
    """Render a single summary checkpoint as markdown."""
    s = row.get("summary") or {}
    header = f"## Checkpoint @ turn {row['turn_number']}"
    if row.get("created_at"):
        header += f"  _{row['created_at']}_"
    parts = [header]
    if s.get("narrative"):
        parts.append(s["narrative"])
    for label, key in [
        ("Decisions", "decisions"),
        ("Open questions", "open_questions"),
        ("Key positions", "key_positions"),
    ]:
        items = s.get(key) or []
        if items:
            parts.append(f"**{label}:**\n" + "\n".join(f"- {i}" for i in items))
    return "\n\n".join(parts)


@router.get("/export_markdown")
async def export_markdown(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Export transcript as markdown."""
    msg_repo = request.app.state.message_repo
    branch_id = await get_main_branch_id(request.app.state.pool, participant.session_id)
    messages = await msg_repo.get_recent(participant.session_id, branch_id, 10000)
    name_by_id = await _participant_names(request, participant.session_id)
    lines = [_format_md_message(m, name_by_id) for m in messages]
    return {"format": "markdown", "content": "\n\n".join(lines)}


@router.get("/export_json")
async def export_json(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Export transcript as JSON."""
    msg_repo = request.app.state.message_repo
    branch_id = await get_main_branch_id(request.app.state.pool, participant.session_id)
    messages = await msg_repo.get_recent(participant.session_id, branch_id, 10000)
    name_by_id = await _participant_names(request, participant.session_id)
    data = [_format_json_message(m, name_by_id) for m in messages]
    return {"format": "json", "content": json.dumps(data)}


async def _participant_names(request: Request, session_id: str) -> dict[str, str]:
    """Return id → display_name map for transcript export labeling."""
    participants = await request.app.state.participant_repo.list_participants(session_id)
    return {p.id: p.display_name for p in participants}


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

    AllParticipantsExhaustedError no longer terminates the loop — instead
    we sleep with the same backoff and retry. That way adding an AI
    mid-session (e.g. via Reset/Release-then-Add) is picked up on the
    next tick without the operator having to manually restart the loop.
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
            skips += 1
            delay = min(_SKIP_BACKOFF_BASE_S * (2 ** (skips - 1)), _SKIP_BACKOFF_MAX_S)
            log.info(
                "No active AI in %s; sleeping %.1fs before retry (skips=%d)",
                session_id,
                delay,
                skips,
            )
            await asyncio.sleep(delay)
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
        "name": session.name,
        "facilitator_id": facilitator.id,
        "branch_id": branch.id,
        "status": session.status,
    }


def _format_md_message(msg: object, name_by_id: dict[str, str]) -> str:
    """Format a message as markdown with the speaker's display_name."""
    name = name_by_id.get(msg.speaker_id, "unknown")
    return f"**[{msg.speaker_type}: {name}]** {msg.content}"


def _format_json_message(msg: object, name_by_id: dict[str, str]) -> dict:
    """Format a message for JSON export, embedding speaker_display_name."""
    return {
        "turn": msg.turn_number,
        "speaker": msg.speaker_id,
        "speaker_display_name": name_by_id.get(msg.speaker_id, "unknown"),
        "type": msg.speaker_type,
        "content": msg.content,
    }
