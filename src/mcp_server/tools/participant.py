"""Participant tool endpoints — inject, history, status, config."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant
from src.orchestrator.branch import get_main_branch_id
from src.repositories.errors import SessionNotActiveError

router = APIRouter(prefix="/tools/participant", tags=["participant"])

# Per red-team runbook 3.1: oversized message bodies must be rejected before
# reaching the provider. 64 KB ≈ 16K tokens — comfortably above any realistic
# human interjection, well below the 1 MB runbook trigger.
MAX_MESSAGE_CONTENT_CHARS = 65_536


class _InjectMessageBody(BaseModel):
    """Request body for injecting a message."""

    content: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CONTENT_CHARS)
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
        msg = await msg_repo.append_message(
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
    await _broadcast_human_message(participant.session_id, msg)
    return True


async def _broadcast_human_message(session_id: str, msg) -> None:  # type: ignore[no-untyped-def]
    """Push the v1 message event so the injector sees their own post live.

    AI turns broadcast via the turn-loop's _emit_message_to_web_ui. Human
    injects bypass that path, so every subscriber — including the sender —
    relied on the next state_snapshot to see the message. Now we emit the
    same payload shape inline.
    """
    from src.web_ui.events import message_event
    from src.web_ui.websocket import broadcast_to_session

    payload = {
        "turn_number": msg.turn_number,
        "speaker_id": msg.speaker_id,
        "speaker_type": msg.speaker_type,
        "content": msg.content,
        "token_count": msg.token_count,
        "cost_usd": None,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "summary_epoch": msg.summary_epoch,
    }
    await broadcast_to_session(session_id, message_event(payload))


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


@router.post("/rotate_my_token")
async def rotate_my_token(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Mint a fresh bearer token for the caller and return it once.

    Needed because tokens are only shown at create/login; a promoted
    facilitator or a returning participant otherwise has no way to
    see their own token for API / MCP / Swagger use. Rotating
    invalidates the prior token, so the caller MUST save the new
    value immediately (same UX as the create-session reveal modal).
    """
    auth = request.app.state.auth_service
    token = await auth.rotate_token(participant.id)
    return {"participant_id": participant.id, "token": token}


class _AddAIBody(BaseModel):
    """Body for a participant to add their own AI (non-facilitator path).

    The provider whitelist mirrors the Web UI's curated list. Backend
    dispatch is LiteLLM-agnostic, so adding a provider here is mostly
    a UX gate. Gemini + Groq added for low-cost / high-speed alternatives
    to Anthropic and OpenAI.
    """

    display_name: str
    provider: Literal["anthropic", "openai", "ollama", "gemini", "groq"]
    model: str
    model_tier: str = "mid"
    model_family: str = "unknown"
    context_window: int = 0
    api_key: str = ""
    api_endpoint: str = ""
    budget_hourly: float | None = None
    budget_daily: float | None = None
    max_tokens_per_turn: int | None = None


@router.post("/add_ai")
async def add_ai_participant(
    request: Request,
    body: _AddAIBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Let a non-facilitator human sponsor an AI (auto-approved, tagged invited_by)."""
    if participant.provider != "human":
        raise HTTPException(403, "Only human participants may sponsor an AI")
    p_repo = request.app.state.participant_repo
    new_p = await _persist_sponsored_ai(p_repo, participant, body)
    auth_token = await _issue_and_broadcast_ai(
        request,
        participant.session_id,
        new_p.id,
        p_repo,
    )
    return {"participant_id": new_p.id, "auth_token": auth_token, "role": new_p.role}


async def _persist_sponsored_ai(
    p_repo: object,
    sponsor: Participant,
    body: _AddAIBody,
) -> Participant:
    """Wrap the repo add_participant call for the sponsor flow."""
    new_p, _ = await p_repo.add_participant(
        session_id=sponsor.session_id,
        display_name=body.display_name.strip(),
        provider=body.provider,
        model=body.model.strip(),
        model_tier=body.model_tier,
        model_family=body.model_family,
        context_window=body.context_window,
        api_key=body.api_key or None,
        api_endpoint=body.api_endpoint or None,
        budget_hourly=body.budget_hourly,
        budget_daily=body.budget_daily,
        max_tokens_per_turn=body.max_tokens_per_turn,
        auto_approve=True,
        invited_by=sponsor.id,
    )
    return new_p


async def _issue_and_broadcast_ai(
    request: Request,
    session_id: str,
    participant_id: str,
    p_repo: object,
) -> str:
    """Mint token + broadcast participant_update after a sponsor-AI add."""
    from src.web_ui.events import broadcast_participant_update

    token = await request.app.state.auth_service.rotate_token(participant_id)
    await broadcast_participant_update(
        session_id,
        participant_id,
        p_repo,
        request.app.state.log_repo,
    )
    return token


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
