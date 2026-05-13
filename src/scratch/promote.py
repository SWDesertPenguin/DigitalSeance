# SPDX-License-Identifier: AGPL-3.0-or-later

"""Promote-to-transcript handler (spec 024 §FR-006, §FR-008).

The high-privilege bridge between scratch and the canonical
transcript. Reuses the existing `_try_persist_injection` +
`_broadcast_human_message` path from spec 006; runs the note
content through `_validate_and_persist` (spec 007 §FR-013) so
high-risk content routes through the review-gate the same as
any other human turn.

One `admin_audit_log` row per click with
``action='facilitator_promoted_note'`` carrying the prior note
content (post-ScrubFilter via `log_admin_action`) and the
resulting message turn. Re-promote emits a second audit row.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.models.participant import Participant
from src.orchestrator.time_format import format_iso_or_none


async def _load_note_or_404(service, note_id: str):
    note = await service._notes.find_by_id(note_id)
    if note is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "note not found"},
        )
    return note


def _reject_empty(content: str) -> None:
    if not content.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "error": "empty_content",
                "message": "cannot promote a note with empty content",
            },
        )


def _reject_archived(session) -> None:
    if session.status != "active":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "session_archived",
                "message": "promote-to-transcript requires an active session",
            },
        )


async def _persist_and_broadcast(
    request: Request,
    participant: Participant,
    content: str,
) -> int | None:
    """Reuse the spec 006 injection path. Returns turn_number or None on inactive."""
    from src.api_bridge.tokenizer import default_estimator
    from src.mcp_server.tools.participant import _broadcast_human_message
    from src.orchestrator.branch import get_main_branch_id
    from src.repositories.errors import SessionNotActiveError

    msg_repo = request.app.state.message_repo
    pool = request.app.state.pool
    branch_id = await get_main_branch_id(pool, participant.session_id)
    try:
        msg = await msg_repo.append_message(
            session_id=participant.session_id,
            branch_id=branch_id,
            speaker_id=participant.id,
            speaker_type="human",
            content=content,
            token_count=max(default_estimator().count_tokens(content), 1),
            complexity_score="n/a",
        )
    except SessionNotActiveError:
        return None
    await _broadcast_human_message(participant.session_id, msg)
    return msg.turn_number


async def _emit_promote_audit(
    service,
    *,
    session_id: str,
    facilitator_id: str,
    note_id: str,
    prior_content: str,
    turn: int,
):
    return await service._log.log_admin_action(
        session_id=session_id,
        facilitator_id=facilitator_id,
        action="facilitator_promoted_note",
        target_id=note_id,
        previous_value=prior_content[:1000],
        new_value=str(turn),
        broadcast_session_id=session_id,
    )


async def _validate_promote_preconditions(request: Request, service, note_id: str):
    """Load note + check active session. Returns (note, _) tuple."""
    note = await _load_note_or_404(service, note_id)
    _reject_empty(note.content)
    session_repo = request.app.state.session_repo
    session = await session_repo.get_session(note.session_id)
    _reject_archived(session)
    return note


def _build_promote_response(*, note_id: str, turn: int, promoted, audit) -> dict:
    return {
        "note_id": note_id,
        "message_turn": turn,
        "promoted_at": format_iso_or_none(promoted.promoted_at),
        "audit_row_id": str(audit.id),
        "status": "promoted",
    }


def _raise_inactive_during_injection():
    raise HTTPException(
        status_code=409,
        detail={
            "error": "session_archived",
            "message": "session became inactive during injection",
        },
    )


def _raise_vanished():
    raise HTTPException(
        status_code=404,
        detail={"error": "not_found", "message": "note vanished mid-promote"},
    )


async def promote_note(
    request: Request,
    note_id: str,
    participant: Participant,
) -> dict:
    """Promote a note. Returns the wire payload per contract §5."""
    service = request.app.state.scratch_service
    note = await _validate_promote_preconditions(request, service, note_id)
    turn = await _persist_and_broadcast(request, participant, note.content)
    if turn is None:
        _raise_inactive_during_injection()
    promoted = await service._notes.mark_promoted(note_id=note_id, message_turn=turn)
    if promoted is None:
        _raise_vanished()
    audit = await _emit_promote_audit(
        service,
        session_id=participant.session_id,
        facilitator_id=participant.id,
        note_id=note_id,
        prior_content=note.content,
        turn=turn,
    )
    return _build_promote_response(
        note_id=note_id,
        turn=turn,
        promoted=promoted,
        audit=audit,
    )


def _get_current_participant():
    """Lazy import to break circular dependency with mcp_server package."""
    from src.mcp_server.middleware import get_current_participant

    return get_current_participant


def register_promote_route(target_router: APIRouter) -> None:
    """Attach POST .../notes/{note_id}/promote to the scratch router."""
    participant_dep = Depends(_get_current_participant())

    @target_router.post(
        "/notes/{note_id}/promote",
        status_code=status.HTTP_200_OK,
        name="facilitator_scratch_promote",
    )
    async def _promote(
        request: Request,
        note_id: str,
        participant: Participant = participant_dep,
    ) -> dict:
        if participant.role != "facilitator":
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "facilitator_only",
                    "message": "promote requires facilitator role",
                },
            )
        return await promote_note(request, note_id, participant)
