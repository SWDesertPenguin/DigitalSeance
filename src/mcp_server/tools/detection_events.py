# SPDX-License-Identifier: AGPL-3.0-or-later

"""Detection-event history endpoint (spec 022 FR-001 + FR-013 + FR-014).

The router mounts conditionally on ``SACP_DETECTION_HISTORY_ENABLED=true``;
when disabled the route is absent and ALL callers receive ``HTTP 404`` per
FR-016. The mount decision lives in ``src/mcp_server/app.py`` so the master
switch hides the surface from probe-based discovery.

Authorization (per ``contracts/detection-events-endpoint.md``):

- Caller MUST be a facilitator (FR-002) — non-facilitators receive ``HTTP 403``.
- Caller MUST belong to the requested session (FR-003) — cross-session reads
  receive ``HTTP 403``.

Read-only invariant (FR-004): NONE of the source tables are mutated by this
endpoint. The POST .../resurface endpoint (FR-006) is the only write site
in spec 022's surface and ships in Sweep 3.

The page response carries the persisted ``DetectionEvent`` rows verbatim
plus the registry-derived ``event_class_label`` for display.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant
from src.observability.instrumentation import instrument_stage
from src.orchestrator.time_format import format_iso, format_iso_or_none
from src.repositories.detection_event_repo import apply_resurface
from src.web_ui.cross_instance_broadcast import broadcast_session_event
from src.web_ui.detection_events import format_class_label
from src.web_ui.events import (
    build_detection_event_payload,
    detection_event_resurfaced_event,
)

router = APIRouter(prefix="/tools/admin", tags=["admin"])


@router.get("/detection_events")
async def get_detection_events(
    request: Request,
    session_id: str,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Return the detection-event history page for ``session_id``.

    See ``specs/022-detection-event-history/contracts/detection-events-endpoint.md``
    for the full request/response contract. Newest-first ordering per
    research.md §12; client-side filter axes operate over the returned set.
    """
    _authorize(participant, session_id)
    max_events = _resolved_max_events()
    since = _resolved_since()
    state = request.app.state
    async with instrument_stage(
        "detection_events.page_load",
        session_id=session_id,
    ) as stage:
        rows = await state.log_repo.get_detection_events_page(
            session_id,
            max_events=max_events,
            since=since,
        )
        stage["row_count"] = len(rows)
    events = [_decorate_event(row) for row in rows]
    as_of = format_iso_or_none(datetime.now(UTC))
    return {
        "session_id": session_id,
        "events": events,
        "count": len(events),
        "max_events_applied": max_events is not None and len(events) == max_events,
        "as_of": as_of,
    }


def _decorate_event(row: dict) -> dict:
    """Project a DB row into the wire shape (adds event_class_label)."""
    return {
        "event_id": row["id"],
        "event_class": row["event_class"],
        "event_class_label": format_class_label(row["event_class"]),
        "participant_id": row["participant_id"],
        "trigger_snippet": row["trigger_snippet"],
        "detector_score": row["detector_score"],
        "turn_number": row["turn_number"],
        "timestamp": format_iso_or_none(row["timestamp"]),
        "disposition": row["disposition"],
        "last_disposition_change_at": format_iso_or_none(row["last_disposition_change_at"]),
    }


def _authorize(participant: Participant, session_id: str) -> None:
    """Enforce facilitator-only + session-binding authorization (FR-002/003)."""
    if participant.role != "facilitator":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "facilitator_only",
                "message": "detection event history access requires facilitator role",
            },
        )
    if participant.session_id != session_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "facilitator_only",
                "message": "detection event history access requires facilitator role",
            },
        )


def _resolved_max_events() -> int | None:
    """Read SACP_DETECTION_HISTORY_MAX_EVENTS; ``None`` means no cap."""
    raw = os.environ.get("SACP_DETECTION_HISTORY_MAX_EVENTS")
    if raw is None or raw.strip() == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _resolved_since() -> datetime | None:
    """Read SACP_DETECTION_HISTORY_RETENTION_DAYS; compute the lower bound.

    Returns ``None`` (no lower bound) when the env var is unset or empty.
    Otherwise returns ``NOW() - INTERVAL '<value> days'`` as a UTC datetime.
    """
    raw = os.environ.get("SACP_DETECTION_HISTORY_RETENTION_DAYS")
    if raw is None or raw.strip() == "":
        return None
    try:
        days = int(raw)
    except ValueError:
        return None
    if days <= 0:
        return None
    return datetime.now(UTC) - timedelta(days=days)


@router.get("/detection_events/{event_id}/timeline")
async def get_disposition_timeline(
    event_id: int,
    session_id: str,
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Disposition transition history for one event (FR-010 click-expand)."""
    _authorize(participant, session_id)
    state = request.app.state
    rows = await state.log_repo.get_disposition_timeline(session_id, event_id)
    return {
        "event_id": event_id,
        "transitions": [
            {
                "audit_row_id": row["id"],
                "action": row["action"],
                "facilitator_id": row["facilitator_id"],
                "timestamp": format_iso_or_none(row["timestamp"]),
            }
            for row in rows
        ],
    }


@router.post("/detection_events/{event_id}/resurface")
async def post_resurface(
    event_id: int,
    session_id: str,
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Re-surface a dispositioned detection event (FR-006)."""
    _authorize(participant, session_id)
    state = request.app.state
    async with instrument_stage(
        "detection_events.resurface_same_instance",
        session_id=session_id,
        event_id=event_id,
    ):
        row = await _lookup_event_row(state, session_id, event_id)
        await _verify_session_active(state, session_id)
        audit_row_id, broadcast_path = await _emit_resurface(
            state,
            session_id,
            event_id,
            participant.id,
            row,
        )
    return {
        "event_id": event_id,
        "audit_row_id": audit_row_id,
        "broadcast": _build_resurface_envelope(row)["event"],
        "broadcast_path": broadcast_path,
    }


async def _lookup_event_row(state, session_id: str, event_id: int) -> dict:
    """Fetch the detection_events row by id+session; 404 if missing."""
    rows = await state.log_repo.get_detection_events_page(
        session_id,
        max_events=None,
        since=None,
    )
    for row in rows:
        if row["id"] == event_id:
            return row
    raise HTTPException(
        status_code=404,
        detail={"error": "event_not_found", "message": "no matching detection event"},
    )


async def _verify_session_active(state, session_id: str) -> None:
    """409 if the session is archived (FR-008)."""
    session = await state.session_repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "session_not_found", "message": "session not found"},
        )
    if getattr(session, "status", None) == "archived":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "session_archived",
                "message": "re-surface requires an active session",
            },
        )


async def _emit_resurface(state, session_id, event_id, facilitator_id, row):
    """Write the audit row and broadcast the resurface envelope."""
    audit_row_id = await apply_resurface(
        state.log_repo._pool,
        session_id=session_id,
        event_id=event_id,
        facilitator_id=facilitator_id,
    )
    envelope = _build_resurface_envelope(row, audit_row_id=audit_row_id)
    await broadcast_session_event(session_id, envelope, pool=state.log_repo._pool)
    return audit_row_id, "same_instance"


def _build_resurface_envelope(row: dict, *, audit_row_id: int | None = None) -> dict:
    """Compose the detection_event_resurfaced envelope from a row."""
    from src.web_ui.events import DetectionEventDraft

    draft = DetectionEventDraft(
        session_id=row.get("session_id", ""),
        event_class=row["event_class"],
        participant_id=row["participant_id"],
        trigger_snippet=row.get("trigger_snippet"),
        detector_score=row.get("detector_score"),
        turn_number=row.get("turn_number"),
    )
    payload = build_detection_event_payload(
        draft,
        row["id"],
        format_iso(row["timestamp"]),
        disposition=row.get("disposition", "pending"),
    )
    return detection_event_resurfaced_event(
        event=payload,
        resurface_audit_row_id=audit_row_id or 0,
    )


def is_detection_history_enabled() -> bool:
    """Return True when SACP_DETECTION_HISTORY_ENABLED is on.

    Treats any truthy bool-string as enabled (``true``/``1`` case-insensitive).
    Validator already constrained valid values; this helper is a thin parser.
    """
    raw = os.environ.get("SACP_DETECTION_HISTORY_ENABLED", "")
    return raw.strip().lower() in ("true", "1")
