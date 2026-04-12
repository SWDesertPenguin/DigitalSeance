"""Facilitator tool endpoints — invite, approve, remove, revoke, transfer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant

router = APIRouter(prefix="/tools/facilitator", tags=["facilitator"])


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
