# SPDX-License-Identifier: AGPL-3.0-or-later

"""Facilitator tool endpoints — invite, approve, remove, revoke, transfer."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from src.api_bridge.tokenizer import default_estimator
from src.models.participant import Participant
from src.orchestrator.branch import get_main_branch_id
from src.orchestrator.loop import run_security_pipeline
from src.participant_api.middleware import get_current_participant

router = APIRouter(prefix="/tools/facilitator", tags=["facilitator"])

_SWAGGER_PLACEHOLDER = "string"
_MAX_REJECT_REASON_CHARS = 2_000
# Facilitator review-gate edits can rewrite a full AI draft. Typical Haiku
# / gpt-4o-mini drafts run 1500-2500 chars at 300-500 output tokens; 8 KB is
# a 4x cushion over that without re-introducing the 64 KB attack surface.
_MAX_FACILITATOR_EDIT_CHARS = 8_000


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
    max_tokens_per_turn: int | None = None

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
    """Add a participant directly (facilitator only, auto-approved)."""
    p_repo = request.app.state.participant_repo
    await _reject_duplicate_display_name(p_repo, participant.session_id, body.display_name)
    new_p = await _persist_added_participant(p_repo, participant.id, participant.session_id, body)
    auth_token = await request.app.state.auth_service.rotate_token(new_p.id)
    from src.web_ui.events import broadcast_participant_update

    await broadcast_participant_update(
        participant.session_id,
        new_p.id,
        p_repo,
        request.app.state.log_repo,
    )
    from src.orchestrator.announcements import announce_arrival
    from src.participant_api.tools.session import is_loop_running

    if is_loop_running(participant.session_id):
        await announce_arrival(
            pool=request.app.state.pool,
            msg_repo=request.app.state.message_repo,
            session_id=participant.session_id,
            speaker_id=new_p.id,
            joining_name=new_p.display_name,
            kind="joined the session",
        )
    return {"participant_id": new_p.id, "auth_token": auth_token, "role": new_p.role}


async def _persist_added_participant(
    p_repo: object,
    inviter_id: str,
    session_id: str,
    body: _AddParticipantBody,
) -> Participant:
    """Wrap repo.add_participant for the facilitator add path."""
    new_p, _ = await p_repo.add_participant(
        session_id=session_id,
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
        max_tokens_per_turn=body.max_tokens_per_turn,
        auto_approve=True,
        invited_by=inviter_id,
    )
    return new_p


_DEPARTED_STATUSES = frozenset({"removed", "offline", "reset"})


async def _reject_duplicate_display_name(
    p_repo: object,
    session_id: str,
    display_name: str,
) -> None:
    """409 if an active participant already has this display_name in the session.

    Statuses in ``_DEPARTED_STATUSES`` are skipped so a released slot
    ('reset') or a removed participant ('offline') frees the name for
    re-add. Without this, the latent bug was that ``depart_participant``
    set status='offline' but the guard only skipped 'removed', so any
    removed name was blocked forever.
    """
    cleaned = display_name.strip().lower()
    existing = await p_repo.list_participants(session_id)
    for p in existing:
        if p.status in _DEPARTED_STATUSES:
            continue
        if p.display_name.strip().lower() == cleaned:
            raise HTTPException(
                409,
                f"A participant named '{p.display_name}' is already in this session",
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
    from src.orchestrator.announcements import announce_arrival
    from src.participant_api.tools.session import is_loop_running

    if is_loop_running(participant.session_id):
        await announce_arrival(
            pool=request.app.state.pool,
            msg_repo=request.app.state.message_repo,
            session_id=participant.session_id,
            speaker_id=result.id,
            joining_name=result.display_name,
            kind="was admitted to the session",
        )
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
    """Remove an active participant and any AIs they sponsored.

    Cascade removes every AI whose ``invited_by`` is the target, so a
    sponsor's AIs don't keep spending their API budget after the
    sponsor leaves (Test06-Web07). Humans removed by the facilitator
    still drag their sponsored AIs with them.
    """
    p_repo = request.app.state.participant_repo
    target = await p_repo.get_participant(participant_id)
    auth = request.app.state.auth_service
    await auth.remove_participant(
        facilitator_id=participant.id,
        session_id=participant.session_id,
        participant_id=participant_id,
        reason=reason,
    )
    request.app.state.rate_limiter.forget(participant_id)
    await _close_ws_for_participant(participant.session_id, participant_id)
    await _push_participant_update(request, participant.session_id, participant_id)
    if target is not None:
        await _announce_removed(request, participant, target)
    await _cascade_remove_sponsored_ais(request, participant, participant_id, reason)
    return {"status": "removed"}


async def _announce_removed(request: Request, caller: Participant, target: Participant) -> None:
    """System message when a participant is removed by the facilitator."""
    from src.orchestrator.announcements import announce_departure

    await announce_departure(
        pool=request.app.state.pool,
        msg_repo=request.app.state.message_repo,
        session_id=caller.session_id,
        speaker_id=caller.id,
        departing_name=target.display_name,
        kind="was removed by the facilitator",
    )


async def _cascade_remove_sponsored_ais(
    request: Request,
    caller: Participant,
    removed_id: str,
    reason: str,
) -> None:
    """Depart every active AI whose invited_by is the removed participant."""
    p_repo = request.app.state.participant_repo
    all_participants = await p_repo.list_participants(caller.session_id)
    sponsored = [
        p
        for p in all_participants
        if p.invited_by == removed_id and p.provider != "human" and p.status == "active"
    ]
    auth = request.app.state.auth_service
    for ai in sponsored:
        await auth.remove_participant(
            facilitator_id=caller.id,
            session_id=caller.session_id,
            participant_id=ai.id,
            reason=reason or f"sponsor {removed_id} was removed",
        )
        request.app.state.rate_limiter.forget(ai.id)
        await _close_ws_for_participant(caller.session_id, ai.id)
        await _push_participant_update(request, caller.session_id, ai.id)
        await _announce_removed(request, caller, ai)


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


class _ResetAICredentialsBody(BaseModel):
    """Request body for rotating an AI's API key in place.

    Optional swap fields are nullable but cannot be empty/whitespace —
    a blank provider or model would otherwise overwrite the existing
    value with `""` via COALESCE in `reset_ai_credentials`, leaving the
    AI un-dispatchable. Send `None` (or omit the field) to keep the
    current value, send a real string to swap.
    """

    participant_id: str
    # Optional: only required when the effective post-reset provider needs a
    # key. Ollama doesn't auth, so resetting an ollama participant (or swapping
    # to ollama) accepts a missing key. Validation lives in the handler since
    # the body alone doesn't know the participant's current provider.
    api_key: str | None = Field(default=None, min_length=1)
    provider: str | None = None
    model: str | None = None
    api_endpoint: str | None = None

    @field_validator("provider", "model", "api_endpoint")
    @classmethod
    def _reject_blank_optional(cls, v: str | None, info) -> str | None:
        """Reject whitespace-only swaps; leave None alone for 'keep current'."""
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            msg = f"{info.field_name} must be omitted or non-blank, not whitespace"
            raise ValueError(msg)
        return cleaned


@router.post("/reset_ai_credentials")
async def reset_ai_credentials(
    request: Request,
    body: _ResetAICredentialsBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Rotate an AI's API key in place (facilitator or sponsor).

    Use case: the stored key burned out / was wrong / hit a tier limit.
    The AI keeps its participant_id (and therefore its message history
    attribution), the new key is encrypted and swapped, and the next
    dispatch picks up the new credentials. Humans cannot be reset — they
    have no credentials to rotate.
    """
    p_repo = request.app.state.participant_repo
    target = await _load_ai_target(p_repo, participant.session_id, body.participant_id)
    _require_facilitator_or_inviter(participant, target)
    # Ollama is the only provider that doesn't authenticate; for everything
    # else, require a key. Effective post-reset provider = body.provider when
    # swapping, otherwise the participant's current provider.
    effective_provider = body.provider or target.provider
    if effective_provider != "ollama" and not body.api_key:
        raise HTTPException(
            status_code=422,
            detail=f"api_key is required when provider is '{effective_provider}'",
        )
    await p_repo.reset_ai_credentials(
        body.participant_id,
        api_key=body.api_key,
        provider=body.provider,
        model=body.model,
        api_endpoint=body.api_endpoint,
    )
    from src.orchestrator.circuit_breaker import close_on_key_update

    await close_on_key_update(
        participant.session_id,
        body.participant_id,
        request.app.state.pool,
    )
    await _audit_reset(request, participant, target)
    await _push_participant_update(request, participant.session_id, body.participant_id)
    return {"status": "reset", "participant_id": body.participant_id}


class _ReleaseAISlotBody(BaseModel):
    """Request body for releasing an AI slot so the name becomes reservable."""

    participant_id: str
    reason: str = Field(default="", max_length=_MAX_REJECT_REASON_CHARS)


@router.post("/release_ai_slot")
async def release_ai_slot(
    request: Request,
    body: _ReleaseAISlotBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Unbind an AI's credentials and free the display_name for re-add.

    Softer than ``remove_participant``: the row stays (so prior messages
    keep their attribution), credentials are nulled, and status flips to
    'reset'. The dedupe guard treats 'reset' as a free slot, so the
    facilitator can re-add a fresh AI under the same display_name
    without hitting 409. No cascade to sponsored AIs — release is
    recoverable and a cascade would be surprising.
    """
    p_repo = request.app.state.participant_repo
    target = await _load_ai_target(p_repo, participant.session_id, body.participant_id)
    _require_facilitator_or_inviter(participant, target)
    await p_repo.release_ai_slot(body.participant_id)
    await _close_ws_for_participant(participant.session_id, body.participant_id)
    await _audit_release(request, participant, target, body.reason)
    await _push_participant_update(request, participant.session_id, body.participant_id)
    from src.orchestrator.announcements import announce_departure

    await announce_departure(
        pool=request.app.state.pool,
        msg_repo=request.app.state.message_repo,
        session_id=participant.session_id,
        speaker_id=participant.id,
        departing_name=target.display_name,
        kind="was released",
    )
    return {"status": "released", "participant_id": body.participant_id}


async def _load_ai_target(
    p_repo: object,
    session_id: str,
    participant_id: str,
) -> Participant:
    """Fetch the target participant, rejecting missing rows and humans."""
    target = await p_repo.get_participant(participant_id)
    if target is None or target.session_id != session_id:
        raise HTTPException(404, "participant not found in session")
    if target.provider == "human":
        raise HTTPException(400, "Only AI participants can be reset or released")
    return target


async def _audit_reset(
    request: Request,
    caller: Participant,
    target: Participant,
) -> None:
    """Log a reset_ai_credentials entry with the previous key's last 4 chars."""
    await request.app.state.log_repo.log_admin_action(
        session_id=caller.session_id,
        facilitator_id=caller.id,
        action="reset_ai_credentials",
        target_id=target.id,
        previous_value=_key_tail(target.api_key_encrypted),
        new_value="rekeyed",
        broadcast_session_id=caller.session_id,
    )


async def _audit_release(
    request: Request,
    caller: Participant,
    target: Participant,
    reason: str,
) -> None:
    """Log a release_ai_slot entry capturing the prior status + optional reason."""
    await request.app.state.log_repo.log_admin_action(
        session_id=caller.session_id,
        facilitator_id=caller.id,
        action="release_ai_slot",
        target_id=target.id,
        previous_value=target.status,
        new_value=reason or "reset",
        broadcast_session_id=caller.session_id,
    )


def _key_tail(encrypted: str | None) -> str:
    """Return a short identifier for the prior key for forensic audit.

    The stored value is Fernet ciphertext, not the plaintext key, so
    "last 4 chars of ciphertext" is the cheapest signal that uniquely
    identifies which key was rotated without ever revealing it.
    """
    if not encrypted:
        return "none"
    return f"...{encrypted[-4:]}"


@router.post("/revoke_token")
async def revoke_token(
    request: Request,
    participant_id: str,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Revoke a participant's auth token.

    After the repo revocation lands, we close the target's open WS
    connections with 4401 so their UI force-redirects to the guest
    landing instead of silently losing the ability to mutate state.
    The HttpOnly cookie remains but points to an invalidated token
    hash; the client's /me probe on reload returns 401 → landing.
    """
    auth = request.app.state.auth_service
    await auth.revoke_token(
        facilitator_id=participant.id,
        session_id=participant.session_id,
        participant_id=participant_id,
    )
    request.app.state.rate_limiter.forget(participant_id)
    await _close_ws_for_participant(participant.session_id, participant_id)
    await _push_participant_update(request, participant.session_id, participant_id)
    return {"status": "revoked"}


async def _close_ws_for_participant(session_id: str, participant_id: str) -> None:
    """Boot any live WS for this participant with the 4401 close code."""
    from src.web_ui.websocket import get_ws_manager

    await get_ws_manager().close_for_participant(session_id, participant_id)


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
    await _rename_facilitator_prefix(request, participant.id, target_id)
    await _broadcast_transfer(request, participant.session_id, participant.id, target_id)
    return {"status": "transferred", "new_facilitator": target_id}


async def _rename_facilitator_prefix(
    request: Request,
    demoted_id: str,
    promoted_id: str,
) -> None:
    """Move the 'Facilitator-' display_name prefix from old to new."""
    pool = request.app.state.pool
    p_repo = request.app.state.participant_repo
    demoted = await p_repo.get_participant(demoted_id)
    promoted = await p_repo.get_participant(promoted_id)
    if demoted and demoted.display_name.startswith("Facilitator-"):
        stripped = demoted.display_name[len("Facilitator-") :]
        await _rename_participant(pool, demoted_id, stripped)
    if promoted and not promoted.display_name.startswith("Facilitator-"):
        await _rename_participant(pool, promoted_id, f"Facilitator-{promoted.display_name}")


async def _rename_participant(pool: object, participant_id: str, new_name: str) -> None:
    """Raw display_name update used by the facilitator-prefix shuffle."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET display_name = $1 WHERE id = $2",
            new_name,
            participant_id,
        )


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
    # When the frontend Honor-exit button flips an AI to observer, it sends
    # reason="honored_exit" so the backend can post a transcript notice. Plain
    # routing changes leave reason=None and stay silent.
    reason: str | None = None


@router.post("/set_routing_preference")
async def set_routing_preference(
    request: Request,
    body: _SetRoutingBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Set routing preference on a participant (facilitator or sponsor)."""
    p_repo = request.app.state.participant_repo
    target = await p_repo.get_participant(body.participant_id)
    if target is None or target.session_id != participant.session_id:
        raise HTTPException(404, "participant not found in session")
    _require_facilitator_or_inviter(participant, target)
    _capture_prior_if_gating(request, target, body.preference)
    await _write_routing(request, body, participant.session_id)
    from src.web_ui.events import broadcast_participant_update

    await broadcast_participant_update(
        participant.session_id,
        body.participant_id,
        p_repo,
        request.app.state.log_repo,
    )
    await _maybe_announce_honored_exit(request, participant, target, body)
    return {
        "status": "updated",
        "participant_id": body.participant_id,
        "preference": body.preference,
    }


async def _maybe_announce_honored_exit(
    request: Request,
    caller: Participant,
    target: Participant,
    body: _SetRoutingBody,
) -> None:
    """Post a transcript notice when the Honor-exit button flipped to observer."""
    if body.reason != "honored_exit" or body.preference != "observer":
        return
    from src.orchestrator.announcements import announce_departure

    await announce_departure(
        pool=request.app.state.pool,
        msg_repo=request.app.state.message_repo,
        session_id=caller.session_id,
        speaker_id=caller.id,
        departing_name=target.display_name,
        kind="stepped back to observer",
    )


def _capture_prior_if_gating(request: Request, target: Participant, new_pref: str) -> None:
    """Remember prior routing so resolve-a-draft can one-shot back to it.

    Without this, flipping an AI to ``review_gate`` would stick even after
    the first draft is resolved — every subsequent turn would stage
    another draft (Test06-Web07).
    """
    if new_pref != "review_gate" or target.routing_preference == "review_gate":
        return
    loop = getattr(request.app.state, "conversation_loop", None)
    if loop is not None:
        loop.remember_prior_routing(target.id, target.routing_preference)


async def _write_routing(request: Request, body: _SetRoutingBody, session_id: str) -> None:
    """Raw UPDATE for routing_preference; 404 if the row moved sessions."""
    async with request.app.state.pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE participants SET routing_preference = $1 WHERE id = $2 AND session_id = $3",
            body.preference,
            body.participant_id,
            session_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(404, "participant not found in session")


class _SetRoutingAllBody(BaseModel):
    """Request body for bulk-setting routing on every AI in the session."""

    preference: _RoutingPreference


@router.post("/set_routing_all_ais")
async def set_routing_all_ais(
    request: Request,
    body: _SetRoutingAllBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """One-click flip every AI's routing preference (facilitator only).

    Added so the facilitator can gate or ungate every AI at once instead
    of editing each row. Typical use: set to ``review_gate`` before a
    sensitive section of the conversation, then back to ``always``.
    """
    if participant.role != "facilitator":
        raise HTTPException(403, "Only the facilitator can bulk-update routing")
    rows = await _bulk_flip_routing(request, participant.session_id, body.preference)
    await _audit_bulk_routing(request, participant, rows, body.preference)
    from src.web_ui.events import broadcast_participant_update

    for row in rows:
        await broadcast_participant_update(
            participant.session_id,
            row["id"],
            request.app.state.participant_repo,
            request.app.state.log_repo,
        )
    return {"status": "updated", "preference": body.preference, "count": len(rows)}


async def _audit_bulk_routing(
    request: Request,
    facilitator: Participant,
    rows: list,
    new_pref: str,
) -> None:
    """Write one admin_audit_log entry per flipped AI.

    Without this trail, forensic reconstruction of a session (why did the
    router behave that way at turn N?) is impossible — Test07-Web08
    hit exactly this gap when trying to explain a consecutive_timeouts
    count on a participant whose routing had been silently bulk-flipped.
    """
    log_repo = request.app.state.log_repo
    for row in rows:
        prior = row["routing_preference"] or "unknown"
        await log_repo.log_admin_action(
            session_id=facilitator.session_id,
            facilitator_id=facilitator.id,
            action="set_routing_all_ais",
            target_id=row["id"],
            previous_value=prior,
            new_value=new_pref,
            broadcast_session_id=facilitator.session_id,
        )


async def _bulk_flip_routing(request: Request, session_id: str, new_pref: str) -> list:
    """Capture prior routing (for gate revert), then flip all AIs in session."""
    async with request.app.state.pool.acquire() as conn, conn.transaction():
        priors = await conn.fetch(
            "SELECT id, routing_preference FROM participants "
            "WHERE session_id = $1 AND provider != 'human' AND status = 'active'",
            session_id,
        )
        await conn.execute(
            "UPDATE participants SET routing_preference = $1 "
            "WHERE session_id = $2 AND provider != 'human' AND status = 'active'",
            new_pref,
            session_id,
        )
    _remember_bulk_priors(request, priors, new_pref)
    return list(priors)


def _remember_bulk_priors(request: Request, rows: list, new_pref: str) -> None:
    """Cache pre-flip routing for each AI whose mode is now review_gate."""
    if new_pref != "review_gate":
        return
    loop = getattr(request.app.state, "conversation_loop", None)
    if loop is None:
        return
    for row in rows:
        prior = row["routing_preference"]
        if prior and prior != "review_gate":
            loop.remember_prior_routing(row["id"], prior)


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
        broadcast_session_id=participant.session_id,
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


_LengthCapKind = Literal["none", "time", "turns", "both"]
_CapInterpretation = Literal["absolute", "relative"]


class _SetLengthCapBody(BaseModel):
    """Spec 025 FR-003 / FR-026 cap-set request body."""

    length_cap_kind: _LengthCapKind = "none"
    length_cap_seconds: int | None = None
    length_cap_turns: int | None = None
    interpretation: _CapInterpretation | None = None

    @field_validator("length_cap_seconds")
    @classmethod
    def _seconds_in_range(cls, v: int | None) -> int | None:
        if v is not None and not 60 <= v <= 2_592_000:
            msg = "length_cap_seconds must be in [60, 2_592_000] (1 minute to 30 days)"
            raise ValueError(msg)
        return v

    @field_validator("length_cap_turns")
    @classmethod
    def _turns_in_range(cls, v: int | None) -> int | None:
        if v is not None and not 1 <= v <= 10_000:
            msg = "length_cap_turns must be in [1, 10_000]"
            raise ValueError(msg)
        return v


@router.post("/set_length_cap")
async def set_length_cap(
    request: Request,
    body: _SetLengthCapBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Spec 025 FR-003: set or update the session-length cap (facilitator only).

    Returns a 409 with both interpretation options when the submitted value
    lands below current elapsed AND no `interpretation` field is supplied
    (FR-026). On commit, emits a routing_log row with `reason='cap_set'`.
    """
    if participant.role != "facilitator":
        raise HTTPException(403, "facilitator_only")
    _validate_cross_column(body)
    return await _commit_or_disambiguate(request, participant, body)


def _validate_cross_column(body: _SetLengthCapBody) -> None:
    """FR-022 cross-column consistency: kind must match the value pattern."""
    kind = body.length_cap_kind
    seconds = body.length_cap_seconds
    turns = body.length_cap_turns
    if kind == "none" and (seconds is not None or turns is not None):
        raise HTTPException(422, "length_cap_kind_none_forbids_values")
    if kind == "time" and (seconds is None or turns is not None):
        raise HTTPException(422, "length_cap_kind_time_requires_seconds")
    if kind == "turns" and (turns is None or seconds is not None):
        raise HTTPException(422, "length_cap_kind_turns_requires_turns")
    if kind == "both" and (seconds is None or turns is None):
        raise HTTPException(422, "length_cap_kind_both_requires_both")


async def _commit_or_disambiguate(
    request: Request,
    participant: Participant,
    body: _SetLengthCapBody,
) -> dict:
    """Run the FR-026 disambiguation check; commit OR raise 409."""
    from src.orchestrator import length_cap as lc

    session_id = participant.session_id
    session_repo = request.app.state.session_repo
    session = await session_repo.get_session(session_id)
    if session is None:
        raise HTTPException(404, "session_not_found")
    current_seconds = lc.effective_active_seconds(session)
    intent = lc.detect_decrease_intent(
        submitted_kind=body.length_cap_kind,
        submitted_seconds=body.length_cap_seconds,
        submitted_turns=body.length_cap_turns,
        current_turns=session.current_turn,
        current_seconds=current_seconds,
        interpretation=body.interpretation,
    )
    if isinstance(intent, lc.DisambiguationRequired):
        raise HTTPException(409, _disambiguation_payload(intent))
    return await _commit_cap_update(request, participant, session, intent)


def _disambiguation_payload(intent: object) -> dict:
    """Build the 409 body per contracts/cap-set-endpoint.md."""
    return {
        "error": "cap_decrease_requires_interpretation",
        "current_elapsed": {
            "turns": intent.current_turns,
            "seconds": intent.current_seconds,
        },
        "submitted": {
            "length_cap_kind": intent.submitted_kind,
            "length_cap_seconds": intent.submitted_seconds,
            "length_cap_turns": intent.submitted_turns,
        },
        "options": {
            "absolute": {
                "effective_cap_turns": intent.absolute_effective_turns,
                "effective_cap_seconds": intent.absolute_effective_seconds,
                "consequence": "immediate_conclude_phase",
            },
            "relative": {
                "effective_cap_turns": intent.relative_effective_turns,
                "effective_cap_seconds": intent.relative_effective_seconds,
                "consequence": "loop_continues_until_trigger",
            },
        },
    }


async def _commit_cap_update(
    request: Request,
    participant: Participant,
    session: object,
    plan: object,
) -> dict:
    """Persist the cap update, emit cap_set row, broadcast session_updated."""
    session_repo = request.app.state.session_repo
    old_cap_repr = _cap_repr(
        session.length_cap_kind, session.length_cap_seconds, session.length_cap_turns
    )
    new_cap_repr = _cap_repr(plan.new_kind, plan.new_seconds, plan.new_turns)
    await session_repo.update_length_cap(
        participant.session_id,
        kind=plan.new_kind,
        seconds=plan.new_seconds,
        turns=plan.new_turns,
    )
    await _emit_cap_set_audit(
        request,
        participant,
        session=session,
        old_cap_repr=old_cap_repr,
        new_cap_repr=new_cap_repr,
        plan=plan,
    )
    await _maybe_exit_conclude_on_extension(request, participant, session, plan)
    return {"status": "updated", **new_cap_repr, "interpretation": plan.interpretation}


async def _maybe_exit_conclude_on_extension(
    request: Request,
    participant: Participant,
    session: object,
    plan: object,
) -> None:
    """Spec 025 FR-013: clear conclude phase when extension lifts trigger past elapsed."""
    from src.orchestrator import length_cap as lc

    if session.conclude_phase_started_at is None:
        return
    new_cap = lc.SessionLengthCap(
        kind=plan.new_kind, seconds=plan.new_seconds, turns=plan.new_turns
    )
    elapsed_seconds = lc.effective_active_seconds(session)
    if not lc.should_exit_conclude_on_extension(
        new_cap,
        elapsed_turns=session.current_turn,
        elapsed_seconds=elapsed_seconds,
    ):
        return
    await _emit_conclude_exit(request, participant, session.current_turn)


async def _emit_conclude_exit(
    request: Request, participant: Participant, current_turn: int
) -> None:
    """Clear conclude_phase_started_at and write the routing-log row."""
    await request.app.state.session_repo.clear_conclude_phase(participant.session_id)
    await request.app.state.log_repo.log_routing(
        session_id=participant.session_id,
        turn_number=current_turn,
        intended=participant.id,
        actual=participant.id,
        action="phase_transition",
        complexity="n/a",
        domain_match=False,
        reason="conclude_phase_exited",
    )


async def _emit_cap_set_audit(
    request: Request,
    participant: Participant,
    *,
    session: object,
    old_cap_repr: dict,
    new_cap_repr: dict,
    plan: object,
) -> None:
    """Write routing_log.cap_set + admin_audit_log entry for the cap commit."""
    log_repo = request.app.state.log_repo
    await log_repo.log_routing(
        session_id=participant.session_id,
        turn_number=session.current_turn,
        intended=participant.id,
        actual=participant.id,
        action="cap_set",
        complexity="n/a",
        domain_match=False,
        reason="cap_set",
    )
    await log_repo.log_admin_action(
        session_id=participant.session_id,
        facilitator_id=participant.id,
        action="set_length_cap",
        target_id=participant.session_id,
        previous_value=json.dumps(old_cap_repr),
        new_value=json.dumps({**new_cap_repr, "interpretation": plan.interpretation}),
        broadcast_session_id=participant.session_id,
    )


def _cap_repr(kind: str, seconds: int | None, turns: int | None) -> dict:
    """Audit-log + response shape for a cap snapshot."""
    return {
        "length_cap_kind": kind,
        "length_cap_seconds": seconds,
        "length_cap_turns": turns,
    }


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
        broadcast_session_id=participant.session_id,
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

    Sovereignty: the consecutive_timeouts counter is a spec 015
    circuit-breaker primitive (auto-pause input for failing AIs).
    Mutating it for another participant is a session-control action,
    not a sponsor-of-AI action — so the guard is facilitator-only
    rather than the inviter-OR-facilitator pattern used by
    ``set_budget``.
    """
    _require_facilitator(participant)
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
        broadcast_session_id=participant.session_id,
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
    """Request body for setting participant budget limits and output token cap."""

    participant_id: str
    budget_hourly: float | None = None
    budget_daily: float | None = None
    max_tokens_per_turn: int | None = None


@router.post("/set_budget")
async def set_budget(
    request: Request,
    body: _SetBudgetBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Set or clear spend caps on a participant.

    Authorized for (a) the session facilitator and (b) the human who
    invited this AI (participant.id == target.invited_by). The sponsor
    path lets a non-facilitator manage the AI they brought without
    requiring a facilitator handoff. Audit-logged and broadcast live.
    """
    _reject_negative_budget(body.budget_hourly, body.budget_daily)
    # 0 means "no cap" — nobody sensibly wants a zero-dollar cap, and the
    # prior semantics (0 blocks every dispatch) silently broke AIs when a
    # facilitator tried to clear a cap by typing 0 into the input.
    body.budget_hourly = _zero_as_none(body.budget_hourly)
    body.budget_daily = _zero_as_none(body.budget_daily)
    p_repo = request.app.state.participant_repo
    target = await p_repo.get_participant(body.participant_id)
    if target is None or target.session_id != participant.session_id:
        raise HTTPException(404, "participant not found in session")
    _require_facilitator_or_inviter(participant, target)
    await p_repo.update_budget(
        body.participant_id,
        budget_hourly=body.budget_hourly,
        budget_daily=body.budget_daily,
        max_tokens_per_turn=body.max_tokens_per_turn,
    )
    await _audit_and_broadcast_budget(request, participant, target, body)
    return {
        "status": "updated",
        "participant_id": body.participant_id,
        "budget_hourly": body.budget_hourly,
        "budget_daily": body.budget_daily,
        "max_tokens_per_turn": body.max_tokens_per_turn,
    }


def _require_facilitator_or_inviter(caller: Participant, target: Participant) -> None:
    """403 unless caller is the facilitator or invited the target."""
    if caller.role == "facilitator":
        return
    if target.invited_by == caller.id:
        return
    raise HTTPException(403, "Only the facilitator or the participant's sponsor may edit this")


def _reject_negative_budget(hourly: float | None, daily: float | None) -> None:
    """400 on negative caps."""
    if (hourly is not None and hourly < 0) or (daily is not None and daily < 0):
        raise HTTPException(400, "Budget values must be non-negative")


def _zero_as_none(v: float | None) -> float | None:
    """Normalize a 0-dollar cap to None (no cap)."""
    return None if v is not None and v <= 0 else v


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
        previous_value=f"{target.budget_hourly}/{target.budget_daily}/{target.max_tokens_per_turn}",
        new_value=f"{body.budget_hourly}/{body.budget_daily}/{body.max_tokens_per_turn}",
        broadcast_session_id=facilitator.session_id,
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
    """Request body for approving a staged draft verbatim.

    ``override_reason`` is required when the draft content re-flags the
    security pipeline on re-validation (spec 012 FR-006 / Constitution
    §4.9 approach (b)). The endpoint returns 422 when the content still
    flags and no justification is supplied.
    """

    draft_id: str
    override_reason: str | None = Field(None, max_length=1024)


class _RejectDraftBody(BaseModel):
    """Request body for rejecting a draft."""

    draft_id: str
    reason: str = Field("", max_length=_MAX_REJECT_REASON_CHARS)


class _EditDraftBody(BaseModel):
    """Request body for editing a draft before approval.

    ``override_reason`` is required when the *edited* content still
    re-flags the pipeline after the facilitator's changes (spec 012
    FR-006). If the edit removes the flagged content the endpoint
    proceeds without a justification.
    """

    draft_id: str
    edited_content: str = Field(..., min_length=1, max_length=_MAX_FACILITATOR_EDIT_CHARS)
    override_reason: str | None = Field(None, max_length=1024)


@router.post("/approve_draft")
async def approve_draft(
    request: Request,
    body: _DraftIdBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Approve a staged draft; re-run the security pipeline first.

    Spec 012 FR-006 / Constitution §4.9 approach (b): defenses do not
    cease at role boundary. The draft content is re-validated before
    persisting. If it re-flags:
      - No override_reason → 422 (facilitator must justify or reject)
      - override_reason present → persist + log facilitator_override row
    If it passes the pipeline on re-run → persist normally (no override
    row needed).
    """
    draft = await _require_pending_draft(request, body.draft_id, participant.session_id)
    await _repipeline_or_raise(
        request, participant, draft.draft_content, draft, body.override_reason
    )
    gate_repo = request.app.state.review_gate_repo
    await gate_repo.resolve(draft.id, resolution="approved")
    msg = await _append_draft_to_transcript(request, draft, draft.draft_content)
    await _log_gate_action(request, participant, "review_gate_approve", draft.id)
    _skip_in_rotation(request, draft)
    await _restore_routing_after_gate(request, draft, participant.session_id)
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
    await _restore_routing_after_gate(request, draft, participant.session_id)
    await _emit_resolved(participant.session_id, draft.id, "rejected", None)
    return {"status": "rejected", "draft_id": draft.id}


@router.post("/edit_draft")
async def edit_draft(
    request: Request,
    body: _EditDraftBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Edit and approve a staged draft; re-run the pipeline on edited content.

    Spec 012 FR-006 / Constitution §4.9 approach (b): the edited content
    is re-validated before persisting. If it still flags and the
    facilitator supplies override_reason, the override is logged and the
    content is persisted. If it still flags with no justification → 422.
    If the edit resolves the flags, the content is persisted as cleaned.
    """
    draft = await _require_pending_draft(request, body.draft_id, participant.session_id)
    content_to_persist = await _repipeline_or_raise(
        request, participant, body.edited_content, draft, body.override_reason
    )
    gate_repo = request.app.state.review_gate_repo
    await gate_repo.resolve(draft.id, resolution="edited", edited_content=content_to_persist)
    msg = await _append_draft_to_transcript(request, draft, content_to_persist)
    await _log_gate_action(
        request,
        participant,
        "review_gate_edit",
        draft.id,
        {"previous": draft.draft_content, "new": content_to_persist},
    )
    _skip_in_rotation(request, draft)
    await _restore_routing_after_gate(request, draft, participant.session_id)
    await _emit_resolved(participant.session_id, draft.id, "edited", msg.turn_number)
    return {"status": "edited", "draft_id": draft.id, "turn_number": msg.turn_number}


async def _repipeline_or_raise(
    request: Request,
    participant: Participant,
    content: str,
    draft: object,
    override_reason: str | None,
) -> str:
    """Re-run security pipeline; raise 422 or log override; return content.

    Implements Constitution §4.9 approach (b):
    * Pipeline passes → return cleaned content (sanitization preserved).
    * Pipeline flags + no override_reason → 422.
    * Pipeline flags + override_reason → log facilitator_override row,
      return original content (facilitator owns the decision).
    """
    validation, cleaned, _, _, _ = run_security_pipeline(content)
    if not validation.blocked:
        return cleaned
    if not override_reason:
        raise HTTPException(
            422,
            "Content re-flags the security pipeline; supply override_reason to proceed",
        )
    log_repo = request.app.state.log_repo
    await log_repo.log_security_event(
        session_id=draft.session_id,
        speaker_id=participant.id,
        turn_number=draft.turn_number,
        layer="facilitator_override",
        findings=json.dumps(list(validation.findings)),
        risk_score=validation.risk_score,
        blocked=False,
        override_reason=override_reason,
        override_actor_id=participant.id,
    )
    return content


async def _restore_routing_after_gate(request: Request, draft: object, session_id: str) -> None:
    """Flip the drafter's routing back to its pre-gate value.

    Without this, once an AI is set to ``review_gate`` the mode sticks
    and every subsequent turn stages a draft forever (Test06-Web07).
    ``remember_prior_routing`` captured the pre-gate value when the
    flip happened; we pop it here and write it back. Fallback to
    ``always`` if no cached prior (direct-from-create review_gate).
    """
    loop = getattr(request.app.state, "conversation_loop", None)
    if loop is None:
        return
    prior = loop.pop_prior_routing(draft.participant_id) or "always"
    async with request.app.state.pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET routing_preference = $1 WHERE id = $2 AND session_id = $3",
            prior,
            draft.participant_id,
            session_id,
        )
    from src.web_ui.events import broadcast_participant_update

    await broadcast_participant_update(
        session_id,
        draft.participant_id,
        request.app.state.participant_repo,
        request.app.state.log_repo,
    )


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
        token_count=max(default_estimator().count_tokens(content), 1),
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
        broadcast_session_id=participant.session_id,
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


# --- Spec 021 register-slider endpoints (T040 + T052) ---
# FR-007 / FR-008: facilitator-controlled session slider and per-participant
# override. Both endpoints emit register-change audit rows via
# ``LogRepository.log_register_change``. Slider value validated 1-5; ID
# validation is delegated to ``RegisterRepository`` (which trusts FK
# constraints) and the participant existence check below.


class _SetSessionRegisterBody(BaseModel):
    """Request body for setting the session-level register slider."""

    slider_value: int = Field(..., ge=1, le=5)


class _SetParticipantOverrideBody(BaseModel):
    """Request body for setting a per-participant register override."""

    participant_id: str = Field(..., min_length=1)
    slider_value: int = Field(..., ge=1, le=5)


class _ClearParticipantOverrideBody(BaseModel):
    """Request body for clearing a per-participant register override."""

    participant_id: str = Field(..., min_length=1)


def _register_payload(slider: int | None) -> dict:
    """Render a slider value as the audit-row payload dict.

    ``None`` slider -> ``None`` payload (used on first-time-set
    ``previous_value``); 1-5 -> ``{slider_value, preset}``. Late-imports
    ``preset_for_slider`` so the facilitator module's import graph stays
    free of the prompts package at module-load time.
    """
    if slider is None:
        return None  # type: ignore[return-value]
    from src.prompts.register_presets import preset_for_slider

    return {"slider_value": slider, "preset": preset_for_slider(slider).name}


def _require_facilitator(participant: Participant) -> None:
    """Raise 403 unless the caller is the session facilitator."""
    if participant.role != "facilitator":
        raise HTTPException(403, "facilitator_only")


async def _resolve_target_participant(
    request: Request,
    caller: Participant,
    target_id: str,
) -> None:
    """Raise 404 unless the target is in the caller's session."""
    p_repo = request.app.state.participant_repo
    target = await p_repo.get_participant(target_id)
    if target is None or target.session_id != caller.session_id:
        raise HTTPException(404, "participant_not_found")


@router.post("/set_session_register")
async def set_session_register(
    request: Request,
    body: _SetSessionRegisterBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Spec 021 FR-007 / FR-009: set the session-level register slider.

    Idempotent: a no-op set (same value as the existing row) still
    bumps ``last_changed_at`` and emits an audit row per FR-008's
    "submit a slider value equal to the existing value" clarification.
    """
    _require_facilitator(participant)
    register_repo = request.app.state.register_repo
    new_row, previous = await register_repo.upsert_session_register(
        session_id=participant.session_id,
        slider_value=body.slider_value,
        facilitator_id=participant.id,
    )
    await request.app.state.log_repo.log_register_change(
        action="session_register_changed",
        session_id=participant.session_id,
        target_id=participant.session_id,
        previous_value=_register_payload(previous.slider_value if previous else None),
        new_value=_register_payload(new_row.slider_value),
        facilitator_id=participant.id,
    )
    return {"status": "set", **_register_payload(new_row.slider_value)}


@router.post("/set_participant_register_override")
async def set_participant_register_override(
    request: Request,
    body: _SetParticipantOverrideBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Spec 021 FR-008: set a per-participant register override.

    Override scope is one participant; other participants in the same
    session are unaffected per FR-008 + SC-005. Audit row carries
    ``session_slider_at_time`` so retroactive review can reconstruct
    what the override was overriding at the moment of set.
    """
    _require_facilitator(participant)
    await _resolve_target_participant(request, participant, body.participant_id)
    register_repo = request.app.state.register_repo
    new_row, previous = await register_repo.upsert_participant_override(
        participant_id=body.participant_id,
        session_id=participant.session_id,
        slider_value=body.slider_value,
        facilitator_id=participant.id,
    )
    await _emit_override_set_audit(
        request,
        caller=participant,
        target_id=body.participant_id,
        new_slider=new_row.slider_value,
        previous_slider=previous.slider_value if previous else None,
    )
    return {
        "status": "set",
        "participant_id": body.participant_id,
        **_register_payload(new_row.slider_value),
    }


async def _emit_override_set_audit(
    request: Request,
    *,
    caller: Participant,
    target_id: str,
    new_slider: int,
    previous_slider: int | None,
) -> None:
    """Write the participant_register_override_set audit row.

    Reads the live session slider one extra time so the audit row's
    ``session_slider_at_time`` reflects what the override is overriding
    at the moment of set — useful for retroactive review per
    contracts/audit-events.md.
    """
    register_repo = request.app.state.register_repo
    session_row = await register_repo.get_session_register(caller.session_id)
    new_payload = _register_payload(new_slider)
    new_payload["session_slider_at_time"] = session_row.slider_value if session_row else None
    await request.app.state.log_repo.log_register_change(
        action="participant_register_override_set",
        session_id=caller.session_id,
        target_id=target_id,
        previous_value=_register_payload(previous_slider),
        new_value=new_payload,
        facilitator_id=caller.id,
    )


@router.post("/clear_participant_register_override")
async def clear_participant_register_override(
    request: Request,
    body: _ClearParticipantOverrideBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Spec 021 FR-008: explicitly clear a per-participant override.

    Explicit clears emit a ``participant_register_override_cleared``
    audit row; cascades do NOT (research.md §8). Calling on a
    participant with no override is idempotent.
    """
    _require_facilitator(participant)
    await _resolve_target_participant(request, participant, body.participant_id)
    register_repo = request.app.state.register_repo
    cleared = await register_repo.clear_participant_override(body.participant_id)
    if cleared is None:
        return {"status": "absent", "participant_id": body.participant_id}
    await request.app.state.log_repo.log_register_change(
        action="participant_register_override_cleared",
        session_id=participant.session_id,
        target_id=body.participant_id,
        previous_value=_register_payload(cleared.slider_value),
        new_value={"slider_value": None, "fallback_to": "session"},
        facilitator_id=participant.id,
    )
    return {"status": "cleared", "participant_id": body.participant_id}
