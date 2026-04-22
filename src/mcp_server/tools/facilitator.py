"""Facilitator tool endpoints — invite, approve, remove, revoke, transfer."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant
from src.orchestrator.branch import get_main_branch_id

router = APIRouter(prefix="/tools/facilitator", tags=["facilitator"])

_SWAGGER_PLACEHOLDER = "string"


class _AddParticipantBody(BaseModel):
    """Request body for adding a participant. API key sent in body, never in URL.

    Defaults to a human-tier participant so a body like ``{"display_name": "..."}``
    is valid. For an AI, override provider/model/model_tier/model_family/
    context_window with real values (mirrors create_session's facilitator body).
    """

    display_name: str
    provider: str = "human"
    model: str = "human"
    model_tier: str = "n/a"
    model_family: str = "human"
    context_window: int = 0
    api_key: str = ""
    api_endpoint: str = ""
    budget_hourly: float | None = None
    budget_daily: float | None = None

    @field_validator("display_name", "provider", "model", "model_tier", "model_family")
    @classmethod
    def _reject_placeholder(cls, v: str, info) -> str:
        """Reject Swagger default ('string') and blank fields.

        Why: Submitting the Swagger example unchanged created participants
        with `model='string'`, which the provider dispatcher forwarded to
        LiteLLM and failed every turn. Catch it at the edge instead.
        """
        cleaned = (v or "").strip()
        if not cleaned or cleaned.lower() == _SWAGGER_PLACEHOLDER:
            msg = f"{info.field_name} must not be blank or the placeholder 'string'"
            raise ValueError(msg)
        return cleaned


@router.post("/add_participant")
async def add_participant(
    request: Request,
    body: _AddParticipantBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Add a participant directly (facilitator only, auto-approved).

    Dedupes AI participants by (provider, model) within the session to
    prevent the "two Llama rows after a failed retry" footgun from
    Test05-Web01. Human participants share provider="human"/model="human"
    and can legitimately duplicate, so the check skips them.
    """
    await _reject_duplicate_ai(request.app.state.participant_repo, participant.session_id, body)
    p_repo = request.app.state.participant_repo
    new_p, token = await p_repo.add_participant(
        session_id=participant.session_id,
        display_name=body.display_name,
        provider=body.provider,
        model=body.model,
        model_tier=body.model_tier,
        model_family=body.model_family,
        context_window=body.context_window,
        api_key=body.api_key or None,
        api_endpoint=body.api_endpoint or None,
        budget_hourly=body.budget_hourly,
        budget_daily=body.budget_daily,
        auto_approve=True,
        invited_by=participant.id,
    )
    auth = request.app.state.auth_service
    auth_token = await auth.rotate_token(new_p.id)
    return {
        "participant_id": new_p.id,
        "auth_token": auth_token,
        "role": new_p.role,
    }


async def _reject_duplicate_ai(p_repo: object, session_id: str, body: _AddParticipantBody) -> None:
    """Raise 409 if an active participant with the same provider+model exists."""
    if body.provider == "human":
        return
    existing = await p_repo.list_participants(session_id)
    for p in existing:
        if p.provider == body.provider and p.model == body.model and p.status != "removed":
            raise HTTPException(
                409,
                f"A participant with provider={body.provider}, model={body.model} "
                f"already exists in this session (id={p.id}, status={p.status}).",
            )


@router.post("/create_invite")
async def create_invite(
    request: Request,
    *,
    max_uses: int = 1,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Generate an invite link for the session."""
    invite_repo = request.app.state.invite_repo
    invite, plaintext = await invite_repo.create_invite(
        session_id=participant.session_id,
        created_by=participant.id,
        max_uses=max_uses,
    )
    return {"invite_token": plaintext, "max_uses": max_uses}


@router.post("/approve_participant")
async def approve_participant(
    request: Request,
    participant_id: str,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Approve a pending participant."""
    auth = request.app.state.auth_service
    result = await auth.approve_participant(
        facilitator_id=participant.id,
        session_id=participant.session_id,
        participant_id=participant_id,
    )
    await _push_participant_update(request, participant.session_id, participant_id)
    return {"status": "approved", "participant_id": result.id}


@router.post("/reject_participant")
async def reject_participant(
    request: Request,
    participant_id: str,
    *,
    reason: str = "",
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Reject a pending participant."""
    auth = request.app.state.auth_service
    await auth.reject_participant(
        facilitator_id=participant.id,
        session_id=participant.session_id,
        participant_id=participant_id,
        reason=reason,
    )
    await _push_participant_update(request, participant.session_id, participant_id)
    return {"status": "rejected"}


@router.post("/remove_participant")
async def remove_participant(
    request: Request,
    participant_id: str,
    *,
    reason: str = "",
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Remove an active participant."""
    auth = request.app.state.auth_service
    await auth.remove_participant(
        facilitator_id=participant.id,
        session_id=participant.session_id,
        participant_id=participant_id,
        reason=reason,
    )
    await _push_participant_update(request, participant.session_id, participant_id)
    return {"status": "removed"}


async def _push_participant_update(
    request: Request,
    session_id: str,
    participant_id: str,
) -> None:
    """Broadcast a fresh participant row after a lifecycle change."""
    from src.web_ui.events import broadcast_participant_update

    await broadcast_participant_update(
        session_id,
        participant_id,
        request.app.state.participant_repo,
        request.app.state.log_repo,
    )


@router.post("/revoke_token")
async def revoke_token(
    request: Request,
    participant_id: str,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Revoke a participant's auth token."""
    auth = request.app.state.auth_service
    await auth.revoke_token(
        facilitator_id=participant.id,
        session_id=participant.session_id,
        participant_id=participant_id,
    )
    return {"status": "revoked"}


@router.post("/transfer_facilitator")
async def transfer_facilitator(
    request: Request,
    target_id: str,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Transfer facilitator role to another participant.

    Broadcasts participant_update for BOTH the demoted caller and the
    promoted target, plus session_updated with the new facilitator_id,
    so every connected client sees the role swap live without a
    refresh. Before this, Test06 showed the promoted user's UI didn't
    unlock facilitator controls because their me.role never changed.
    """
    auth = request.app.state.auth_service
    await auth.transfer_facilitator(
        facilitator_id=participant.id,
        session_id=participant.session_id,
        target_id=target_id,
    )
    await _broadcast_transfer(request, participant.session_id, participant.id, target_id)
    return {"status": "transferred", "new_facilitator": target_id}


async def _broadcast_transfer(
    request: Request,
    session_id: str,
    demoted_id: str,
    promoted_id: str,
) -> None:
    """Push participant_updates + session_updated after a role swap."""
    from src.web_ui.events import broadcast_participant_update, session_updated_event
    from src.web_ui.websocket import broadcast_to_session

    p_repo = request.app.state.participant_repo
    log_repo = request.app.state.log_repo
    await broadcast_participant_update(session_id, demoted_id, p_repo, log_repo)
    await broadcast_participant_update(session_id, promoted_id, p_repo, log_repo)
    await broadcast_to_session(
        session_id,
        session_updated_event({"facilitator_id": promoted_id}),
    )


_RoutingPreference = Literal[
    "always",
    "review_gate",
    "delegate_low",
    "domain_gated",
    "burst",
    "observer",
    "addressed_only",
    "human_only",
]


class _SetRoutingBody(BaseModel):
    """Request body for setting a participant's routing preference."""

    participant_id: str
    preference: _RoutingPreference


@router.post("/set_routing_preference")
async def set_routing_preference(
    request: Request,
    body: _SetRoutingBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Set routing preference on a participant (facilitator only)."""
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE participants SET routing_preference = $1 WHERE id = $2 AND session_id = $3",
            body.preference,
            body.participant_id,
            participant.session_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(404, "participant not found in session")
    return {
        "status": "updated",
        "participant_id": body.participant_id,
        "preference": body.preference,
    }


class _SetReviewGatePauseScopeBody(BaseModel):
    """Request body for setting the session's review-gate pause scope."""

    scope: Literal["session", "participant"]


@router.post("/set_review_gate_pause_scope")
async def set_review_gate_pause_scope(
    request: Request,
    body: _SetReviewGatePauseScopeBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Set review-gate pause scope on the session (facilitator only)."""
    session_repo = request.app.state.session_repo
    current = await session_repo.get_session(participant.session_id)
    previous = current.review_gate_pause_scope if current else None
    await session_repo.update_review_gate_pause_scope(participant.session_id, body.scope)
    request.app.state.conversation_loop.set_review_gate_pause_scope(
        participant.session_id,
        body.scope,
    )
    await _audit_and_broadcast_scope(request, participant, previous, body.scope)
    return {"status": "updated", "scope": body.scope}


async def _audit_and_broadcast_scope(
    request: Request,
    participant: Participant,
    previous: str | None,
    scope: str,
) -> None:
    """Log the pause-scope change and broadcast session_updated."""
    from src.web_ui.events import session_updated_event
    from src.web_ui.websocket import broadcast_to_session

    await request.app.state.log_repo.log_admin_action(
        session_id=participant.session_id,
        facilitator_id=participant.id,
        action="set_review_gate_pause_scope",
        target_id=participant.session_id,
        previous_value=previous,
        new_value=scope,
    )
    await broadcast_to_session(
        participant.session_id,
        session_updated_event({"review_gate_pause_scope": scope}),
    )


# --- T251: session config mutation endpoints (Phase 2b admin panel) ---

_CadencePreset = Literal["sprint", "cruise", "idle"]
_AcceptanceMode = Literal["unanimous", "majority"]
_ModelTier = Literal["low", "mid", "high", "max"]
_ClassifierMode = Literal["pattern", "llm"]


class _SetCadenceBody(BaseModel):
    """Request body for setting the cadence preset."""

    preset: _CadencePreset


class _SetAcceptanceBody(BaseModel):
    """Request body for setting the acceptance mode."""

    mode: _AcceptanceMode


class _SetMinTierBody(BaseModel):
    """Request body for setting the minimum model tier."""

    tier: _ModelTier


class _SetClassifierBody(BaseModel):
    """Request body for setting the complexity classifier mode."""

    mode: _ClassifierMode


@router.post("/set_cadence_preset")
async def set_cadence_preset(
    request: Request,
    body: _SetCadenceBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Set cadence preset on the session (facilitator only)."""
    previous = await _update_session_field(
        request,
        participant.session_id,
        "cadence_preset",
        body.preset,
    )
    loop = request.app.state.conversation_loop
    loop.set_cadence_preset(participant.session_id, body.preset)
    await _audit_session_config(request, participant, "set_cadence_preset", previous, body.preset)
    return {"status": "updated", "cadence_preset": body.preset}


@router.post("/set_acceptance_mode")
async def set_acceptance_mode(
    request: Request,
    body: _SetAcceptanceBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Set acceptance mode on the session (facilitator only)."""
    previous = await _update_session_field(
        request,
        participant.session_id,
        "acceptance_mode",
        body.mode,
    )
    await _audit_session_config(request, participant, "set_acceptance_mode", previous, body.mode)
    return {"status": "updated", "acceptance_mode": body.mode}


@router.post("/set_min_model_tier")
async def set_min_model_tier(
    request: Request,
    body: _SetMinTierBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Set minimum model tier for session participation (facilitator only)."""
    previous = await _update_session_field(
        request,
        participant.session_id,
        "min_model_tier",
        body.tier,
    )
    await _audit_session_config(request, participant, "set_min_model_tier", previous, body.tier)
    return {"status": "updated", "min_model_tier": body.tier}


@router.post("/set_complexity_classifier_mode")
async def set_complexity_classifier_mode(
    request: Request,
    body: _SetClassifierBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Set the complexity classifier mode on the session (facilitator only)."""
    previous = await _update_session_field(
        request,
        participant.session_id,
        "complexity_classifier_mode",
        body.mode,
    )
    await _audit_session_config(
        request, participant, "set_complexity_classifier_mode", previous, body.mode
    )
    return {"status": "updated", "complexity_classifier_mode": body.mode}


_ALLOWED_SESSION_FIELDS = {
    "cadence_preset",
    "acceptance_mode",
    "min_model_tier",
    "complexity_classifier_mode",
}


async def _update_session_field(
    request: Request,
    session_id: str,
    field: str,
    value: str,
) -> str | None:
    """UPDATE a whitelisted column on sessions, returning the previous value."""
    if field not in _ALLOWED_SESSION_FIELDS:
        raise HTTPException(400, f"unknown session field: {field}")
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        previous = await conn.fetchval(
            f"SELECT {field} FROM sessions WHERE id = $1",  # noqa: S608 — whitelisted
            session_id,
        )
        result = await conn.execute(
            f"UPDATE sessions SET {field} = $1 WHERE id = $2",  # noqa: S608 — whitelisted
            value,
            session_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(404, "session not found")
    return previous


async def _audit_session_config(
    request: Request,
    participant: Participant,
    action: str,
    previous_value: str | None,
    new_value: str,
) -> None:
    """Write an audit row for a session-config mutation."""
    log_repo = request.app.state.log_repo
    await log_repo.log_admin_action(
        session_id=participant.session_id,
        facilitator_id=participant.id,
        action=action,
        target_id=participant.session_id,
        previous_value=previous_value,
        new_value=new_value,
    )


class _DebugSetTimeoutsBody(BaseModel):
    """Request body for priming a participant's consecutive_timeouts counter."""

    participant_id: str
    consecutive_timeouts: int


@router.post("/debug_set_timeouts")
async def debug_set_timeouts(
    request: Request,
    body: _DebugSetTimeoutsBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Prime consecutive_timeouts for circuit-breaker testing (facilitator only).

    Why: T3.6 reset verification otherwise needs server-side SQL. This
    lets the facilitator set the counter to 2 (one-away-from-trip) via
    Swagger, then watch it reset to 0 on the next successful turn.
    """
    if body.consecutive_timeouts < 0:
        raise HTTPException(400, "consecutive_timeouts must be >= 0")
    await _update_timeouts(request, participant.session_id, body)
    log_repo = request.app.state.log_repo
    await log_repo.log_admin_action(
        session_id=participant.session_id,
        facilitator_id=participant.id,
        action="debug_set_timeouts",
        target_id=body.participant_id,
        previous_value=None,
        new_value=str(body.consecutive_timeouts),
    )
    return {
        "status": "updated",
        "participant_id": body.participant_id,
        "consecutive_timeouts": body.consecutive_timeouts,
    }


async def _update_timeouts(
    request: Request,
    session_id: str,
    body: _DebugSetTimeoutsBody,
) -> None:
    """Write consecutive_timeouts and 404 if the participant isn't in session."""
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE participants SET consecutive_timeouts = $1 WHERE id = $2 AND session_id = $3",
            body.consecutive_timeouts,
            body.participant_id,
            session_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(404, "participant not found in session")


class _SetBudgetBody(BaseModel):
    """Request body for setting participant budget limits."""

    participant_id: str
    budget_hourly: float | None = None
    budget_daily: float | None = None


@router.post("/set_budget")
async def set_budget(
    request: Request,
    body: _SetBudgetBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Set or clear spend caps on a participant (facilitator only).

    Covers the "human added an AI without a budget" case: the
    facilitator can backfill caps after the fact. Audit-logged and
    broadcast so every client's BudgetPanel updates live.
    """
    _reject_negative_budget(body.budget_hourly, body.budget_daily)
    p_repo = request.app.state.participant_repo
    target = await p_repo.get_participant(body.participant_id)
    if target is None or target.session_id != participant.session_id:
        raise HTTPException(404, "participant not found in session")
    await p_repo.update_budget(
        body.participant_id,
        budget_hourly=body.budget_hourly,
        budget_daily=body.budget_daily,
    )
    await _audit_and_broadcast_budget(request, participant, target, body)
    return {
        "status": "updated",
        "participant_id": body.participant_id,
        "budget_hourly": body.budget_hourly,
        "budget_daily": body.budget_daily,
    }


def _reject_negative_budget(hourly: float | None, daily: float | None) -> None:
    """400 on negative caps."""
    if (hourly is not None and hourly < 0) or (daily is not None and daily < 0):
        raise HTTPException(400, "Budget values must be non-negative")


async def _audit_and_broadcast_budget(
    request: Request,
    facilitator: Participant,
    target: Participant,
    body: _SetBudgetBody,
) -> None:
    """Log the set_budget action and push a fresh participant_update."""
    log_repo = request.app.state.log_repo
    await log_repo.log_admin_action(
        session_id=facilitator.session_id,
        facilitator_id=facilitator.id,
        action="set_budget",
        target_id=body.participant_id,
        previous_value=f"{target.budget_hourly}/{target.budget_daily}",
        new_value=f"{body.budget_hourly}/{body.budget_daily}",
    )
    from src.web_ui.events import broadcast_participant_update

    await broadcast_participant_update(
        facilitator.session_id,
        body.participant_id,
        request.app.state.participant_repo,
        log_repo,
    )


@router.get("/list_drafts")
async def list_drafts(
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """List pending review-gate drafts for the facilitator's session."""
    gate_repo = request.app.state.review_gate_repo
    drafts = await gate_repo.get_pending(participant.session_id)
    return {"drafts": [_serialize_draft(d) for d in drafts]}


class _DraftIdBody(BaseModel):
    """Request body referencing a staged draft."""

    draft_id: str


class _RejectDraftBody(BaseModel):
    """Request body for rejecting a draft."""

    draft_id: str
    reason: str = ""


class _EditDraftBody(BaseModel):
    """Request body for editing a draft before approval."""

    draft_id: str
    edited_content: str


@router.post("/approve_draft")
async def approve_draft(
    request: Request,
    body: _DraftIdBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Approve a staged draft: write to transcript, resolve as approved."""
    draft = await _require_pending_draft(request, body.draft_id, participant.session_id)
    gate_repo = request.app.state.review_gate_repo
    await gate_repo.resolve(draft.id, resolution="approved")
    msg = await _append_draft_to_transcript(request, draft, draft.draft_content)
    await _log_gate_action(request, participant, "review_gate_approve", draft.id)
    _skip_in_rotation(request, draft)
    await _emit_resolved(participant.session_id, draft.id, "approved", msg.turn_number)
    return {"status": "approved", "draft_id": draft.id, "turn_number": msg.turn_number}


@router.post("/reject_draft")
async def reject_draft(
    request: Request,
    body: _RejectDraftBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Reject a staged draft: resolve as rejected, log reason, no transcript write."""
    draft = await _require_pending_draft(request, body.draft_id, participant.session_id)
    gate_repo = request.app.state.review_gate_repo
    await gate_repo.resolve(draft.id, resolution="rejected")
    await _log_gate_action(
        request, participant, "review_gate_reject", draft.id, {"new": body.reason}
    )
    _skip_in_rotation(request, draft)
    await _emit_resolved(participant.session_id, draft.id, "rejected", None)
    return {"status": "rejected", "draft_id": draft.id}


@router.post("/edit_draft")
async def edit_draft(
    request: Request,
    body: _EditDraftBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Edit and approve a staged draft: write edited content to transcript."""
    draft = await _require_pending_draft(request, body.draft_id, participant.session_id)
    gate_repo = request.app.state.review_gate_repo
    await gate_repo.resolve(draft.id, resolution="edited", edited_content=body.edited_content)
    msg = await _append_draft_to_transcript(request, draft, body.edited_content)
    await _log_gate_action(
        request,
        participant,
        "review_gate_edit",
        draft.id,
        {"previous": draft.draft_content, "new": body.edited_content},
    )
    _skip_in_rotation(request, draft)
    await _emit_resolved(participant.session_id, draft.id, "edited", msg.turn_number)
    return {"status": "edited", "draft_id": draft.id, "turn_number": msg.turn_number}


async def _emit_resolved(
    session_id: str,
    draft_id: str,
    resolution: str,
    turn_number: int | None,
) -> None:
    """Push a review_gate_resolved event to Web UI subscribers."""
    from src.web_ui.events import review_gate_resolved_event
    from src.web_ui.websocket import broadcast_to_session

    await broadcast_to_session(
        session_id,
        review_gate_resolved_event(draft_id, resolution, turn_number),
    )


def _skip_in_rotation(request: Request, draft: object) -> None:
    """Tell the loop to skip this draft's participant on the next rotation slot.

    Why: without this, the loop's round-robin can immediately re-pick the
    just-resolved (gated) participant, who then re-stages another draft —
    a stage→reject→stage cycle that traps the conversation.
    """
    loop = request.app.state.conversation_loop
    loop.mark_draft_resolved(draft.session_id, draft.participant_id)


async def _require_pending_draft(
    request: Request,
    draft_id: str,
    session_id: str,
) -> object:
    """Fetch a draft and verify it's pending in the caller's session."""
    gate_repo = request.app.state.review_gate_repo
    draft = await gate_repo.get_by_id(draft_id)
    if draft is None or draft.session_id != session_id:
        raise HTTPException(404, "draft not found in session")
    if draft.status != "pending":
        raise HTTPException(400, f"draft already {draft.status}")
    return draft


async def _append_draft_to_transcript(
    request: Request,
    draft: object,
    content: str,
) -> object:
    """Insert an approved/edited draft into the session transcript."""
    pool = request.app.state.pool
    msg_repo = request.app.state.message_repo
    branch_id = await get_main_branch_id(pool, draft.session_id)
    return await msg_repo.append_message(
        session_id=draft.session_id,
        branch_id=branch_id,
        speaker_id=draft.participant_id,
        speaker_type="ai",
        content=content,
        token_count=max(len(content) // 4, 1),
        complexity_score="n/a",
    )


async def _log_gate_action(
    request: Request,
    participant: Participant,
    action: str,
    draft_id: str,
    values: dict | None = None,
) -> None:
    """Write a review-gate action to the admin audit log."""
    log_repo = request.app.state.log_repo
    vals = values or {}
    await log_repo.log_admin_action(
        session_id=participant.session_id,
        facilitator_id=participant.id,
        action=action,
        target_id=draft_id,
        previous_value=vals.get("previous"),
        new_value=vals.get("new"),
    )


def _serialize_draft(draft: object) -> dict:
    """Format a ReviewGateDraft for JSON response."""
    return {
        "id": draft.id,
        "participant_id": draft.participant_id,
        "draft_content": draft.draft_content,
        "context_summary": draft.context_summary,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }
