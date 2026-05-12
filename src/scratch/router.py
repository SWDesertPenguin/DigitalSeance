# SPDX-License-Identifier: AGPL-3.0-or-later

"""Scratch endpoints (spec 024 §FR-002..FR-007 + FR-019 + FR-021).

Router mounts conditionally on ``SACP_SCRATCH_ENABLED=1``; when
disabled, every endpoint returns HTTP 404 from absence of the route
rather than a 200 with empty data (FR-019). Facilitator-only
authorization is enforced via the existing
``get_current_participant`` dependency (FR-021).

Promote-to-transcript (FR-006) is implemented in
``src/scratch/promote.py`` and registered as a separate route on
this same router to keep the surface unified.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.models.facilitator_note import FacilitatorNote
from src.models.participant import Participant
from src.orchestrator.audit_labels import format_label
from src.orchestrator.time_format import format_iso_or_none

router = APIRouter(prefix="/tools/facilitator/scratch", tags=["scratch"])

_DEFAULT_NOTE_MAX_KB = 64
_SUMMARY_PREVIEW_CHARS = 200


def is_scratch_enabled() -> bool:
    """Per FR-019: master switch reads ``SACP_SCRATCH_ENABLED``."""
    return os.environ.get("SACP_SCRATCH_ENABLED", "0") == "1"


def _note_max_bytes() -> int:
    """Per FR-010: ``SACP_SCRATCH_NOTE_MAX_KB`` * 1024."""
    raw = os.environ.get("SACP_SCRATCH_NOTE_MAX_KB")
    if raw is None or raw.strip() == "":
        return _DEFAULT_NOTE_MAX_KB * 1024
    try:
        kb = int(raw)
    except ValueError:
        return _DEFAULT_NOTE_MAX_KB * 1024
    return kb * 1024


def _get_current_participant():
    """Lazy import to break circular dependency with mcp_server package."""
    from src.mcp_server.middleware import get_current_participant

    return get_current_participant


def _authorize(participant: Participant, session_id: str) -> None:
    """Per FR-021: facilitator-only AND session-bound."""
    if participant.role != "facilitator":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "facilitator_only",
                "message": "scratch access requires facilitator role",
            },
        )
    if participant.session_id != session_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "facilitator_only",
                "message": "scratch access requires session-bound facilitator",
            },
        )


def _enforce_size(content: str) -> None:
    """Per FR-010: HTTP 413 above the cap."""
    if len(content.encode("utf-8")) > _note_max_bytes():
        raise HTTPException(
            status_code=413,
            detail={
                "error": "content_too_large",
                "message": "note content exceeds SACP_SCRATCH_NOTE_MAX_KB",
            },
        )


def _note_to_dict(note: FacilitatorNote) -> dict:
    """Project a note row into the wire shape."""
    return {
        "id": note.id,
        "content": note.content,
        "version": note.version,
        "created_at": format_iso_or_none(note.created_at),
        "updated_at": format_iso_or_none(note.updated_at),
        "promoted_at": format_iso_or_none(note.promoted_at),
        "promoted_message_turn": note.promoted_message_turn,
    }


def _summary_content_preview(content: str | None) -> str:
    """Truncate summary narrative for the panel preview (FR-011)."""
    if content is None:
        return ""
    if len(content) <= _SUMMARY_PREVIEW_CHARS:
        return content
    return content[:_SUMMARY_PREVIEW_CHARS]


def _summary_to_dict(message: object) -> dict:
    """Project a summary-message row into the panel wire shape."""
    return {
        "id": str(getattr(message, "id", "")),
        "turn_number": getattr(message, "turn_number", None),
        "summary_epoch": getattr(message, "summary_epoch", None),
        "content_preview": _summary_content_preview(getattr(message, "content", "")),
        "content": getattr(message, "content", ""),
        "created_at": format_iso_or_none(getattr(message, "created_at", None)),
    }


def _review_gate_to_dict(row: dict) -> dict:
    """Project a review-gate admin_audit_log row into the panel wire shape."""
    action = str(row.get("action", ""))
    timestamp = row.get("timestamp")
    return {
        "id": str(row.get("id")),
        "action": action,
        "action_label": format_label(action),
        "actor_participant_id": row.get("facilitator_id"),
        "target_id": row.get("target_id"),
        "previous_value": row.get("previous_value"),
        "new_value": row.get("new_value"),
        "timestamp": format_iso_or_none(timestamp),
    }


class _CreateNoteBody(BaseModel):
    """POST body for creating a note."""

    content: str = Field(..., min_length=1)


class _UpdateNoteBody(BaseModel):
    """PUT body for updating a note via OCC."""

    content: str = Field(..., min_length=1)
    version: int = Field(..., ge=1)


async def _list_scratch(request: Request, session_id: str, facilitator_id: str) -> dict:
    service = request.app.state.scratch_service
    notes, account_id = await service.list_for_session(
        session_id=session_id,
        facilitator_id=facilitator_id,
    )
    scope = "account" if account_id is not None else "session"
    summaries_items, summaries_total = await _load_summaries_page(request, session_id, page=0)
    review_gate_rows = await service.list_review_gate_events(session_id=session_id)
    return {
        "scope": scope,
        "account_id": account_id,
        "session_id": session_id,
        "notes": [_note_to_dict(n) for n in notes],
        "summaries": {
            "items": summaries_items,
            "page": 0,
            "page_size": 20,
            "total": summaries_total,
        },
        "review_gate_events": [_review_gate_to_dict(r) for r in review_gate_rows],
    }


async def _load_summaries_page(request: Request, session_id: str, *, page: int) -> tuple[list, int]:
    """Load one page of summaries and project to wire shape."""
    from src.orchestrator.branch import get_main_branch_id

    service = request.app.state.scratch_service
    branch_id = await get_main_branch_id(request.app.state.pool, session_id)
    items, total = await service.list_summaries(
        session_id=session_id,
        branch_id=branch_id,
        page=page,
        page_size=20,
    )
    return [_summary_to_dict(m) for m in items], total


async def _create_one(request: Request, participant: Participant, content: str) -> dict:
    service = request.app.state.scratch_service
    note = await service.create_note(
        session_id=participant.session_id,
        facilitator_id=participant.id,
        content=content,
    )
    return {
        **_note_to_dict(note),
        "scope": "account" if note.account_id is not None else "session",
        "account_id": note.account_id,
    }


async def _update_one(
    request: Request,
    participant: Participant,
    note_id: str,
    expected_version: int,
    content: str,
) -> dict:
    service = request.app.state.scratch_service
    updated = await service.update_note(
        session_id=participant.session_id,
        facilitator_id=participant.id,
        note_id=note_id,
        expected_version=expected_version,
        content=content,
    )
    if updated is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "stale_version",
                "message": "note version is stale or note has been deleted",
            },
        )
    return _note_to_dict(updated)


async def _delete_one(request: Request, participant: Participant, note_id: str) -> None:
    service = request.app.state.scratch_service
    success = await service.delete_note(
        session_id=participant.session_id,
        facilitator_id=participant.id,
        note_id=note_id,
    )
    if not success:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "note not found"},
        )


def _register_get_route(target_router: APIRouter, participant_dep) -> None:
    @target_router.get("")
    async def get_scratch_payload(
        request: Request,
        session_id: str,
        participant: Participant = participant_dep,
    ) -> dict:
        _authorize(participant, session_id)
        return await _list_scratch(request, session_id, participant.id)


def _register_create_route(target_router: APIRouter, participant_dep) -> None:
    @target_router.post("/notes", status_code=status.HTTP_201_CREATED)
    async def create_note(
        request: Request,
        body: _CreateNoteBody,
        participant: Participant = participant_dep,
    ) -> dict:
        _authorize(participant, participant.session_id)
        _enforce_size(body.content)
        return await _create_one(request, participant, body.content)


def _register_update_route(target_router: APIRouter, participant_dep) -> None:
    @target_router.put("/notes/{note_id}")
    async def update_note(
        request: Request,
        note_id: str,
        body: _UpdateNoteBody,
        participant: Participant = participant_dep,
    ) -> dict:
        _authorize(participant, participant.session_id)
        _enforce_size(body.content)
        return await _update_one(
            request,
            participant,
            note_id,
            body.version,
            body.content,
        )


def _register_delete_route(target_router: APIRouter, participant_dep) -> None:
    @target_router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_note(
        request: Request,
        note_id: str,
        participant: Participant = participant_dep,
    ) -> None:
        _authorize(participant, participant.session_id)
        await _delete_one(request, participant, note_id)


def _register_summaries_route(target_router: APIRouter, participant_dep) -> None:
    """Per contract §6: paginated summary archive endpoint."""

    @target_router.get("/summaries")
    async def get_summaries_page(
        request: Request,
        session_id: str,
        page: int = 0,
        participant: Participant = participant_dep,
    ) -> dict:
        _authorize(participant, session_id)
        if page < 0:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_params", "message": "page must be >= 0"},
            )
        items, total = await _load_summaries_page(request, session_id, page=page)
        return {"items": items, "page": page, "page_size": 20, "total": total}


def register_routes(target_router: APIRouter) -> None:
    """Attach all CRUD routes; called from mcp_server.app to avoid circular import."""
    participant_dep = Depends(_get_current_participant())
    _register_get_route(target_router, participant_dep)
    _register_create_route(target_router, participant_dep)
    _register_update_route(target_router, participant_dep)
    _register_delete_route(target_router, participant_dep)
    _register_summaries_route(target_router, participant_dep)
