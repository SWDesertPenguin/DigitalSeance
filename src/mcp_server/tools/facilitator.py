"""Facilitator tool endpoints — invite, approve, remove, revoke, transfer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, field_validator

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant

router = APIRouter(prefix="/tools/facilitator", tags=["facilitator"])

_SWAGGER_PLACEHOLDER = "string"


class _AddParticipantBody(BaseModel):
    """Request body for adding a participant. API key sent in body, never in URL."""

    display_name: str
    provider: str
    model: str
    model_tier: str
    model_family: str
    context_window: int
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
    """Add a participant directly (facilitator only, auto-approved)."""
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
    )
    auth = request.app.state.auth_service
    auth_token = await auth.rotate_token(new_p.id)
    return {
        "participant_id": new_p.id,
        "auth_token": auth_token,
        "role": new_p.role,
    }


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
    return {"status": "removed"}


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
    """Transfer facilitator role to another participant."""
    auth = request.app.state.auth_service
    await auth.transfer_facilitator(
        facilitator_id=participant.id,
        session_id=participant.session_id,
        target_id=target_id,
    )
    return {"status": "transferred", "new_facilitator": target_id}


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
    """Set budget limits on a participant (facilitator only)."""
    p_repo = request.app.state.participant_repo
    await p_repo.update_budget(
        body.participant_id,
        budget_hourly=body.budget_hourly,
        budget_daily=body.budget_daily,
    )
    return {
        "status": "updated",
        "participant_id": body.participant_id,
        "budget_hourly": body.budget_hourly,
        "budget_daily": body.budget_daily,
    }
