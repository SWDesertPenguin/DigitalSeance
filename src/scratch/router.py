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
from src.orchestrator.time_format import format_iso_or_none

router = APIRouter(prefix="/tools/facilitator/scratch", tags=["scratch"])

_DEFAULT_NOTE_MAX_KB = 64


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
    return {
        "scope": scope,
        "account_id": account_id,
        "session_id": session_id,
        "notes": [_note_to_dict(n) for n in notes],
    }


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


def register_routes(target_router: APIRouter) -> None:
    """Attach all CRUD routes; called from mcp_server.app to avoid circular import."""
    participant_dep = Depends(_get_current_participant())
    _register_get_route(target_router, participant_dep)
    _register_create_route(target_router, participant_dep)
    _register_update_route(target_router, participant_dep)
    _register_delete_route(target_router, participant_dep)
