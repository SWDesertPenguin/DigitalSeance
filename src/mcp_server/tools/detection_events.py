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
from src.orchestrator.time_format import format_iso_or_none
from src.web_ui.detection_events import format_class_label

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
    rows = await state.log_repo.get_detection_events_page(
        session_id,
        max_events=max_events,
        since=since,
    )
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


def is_detection_history_enabled() -> bool:
    """Return True when SACP_DETECTION_HISTORY_ENABLED is on.

    Treats any truthy bool-string as enabled (``true``/``1`` case-insensitive).
    Validator already constrained valid values; this helper is a thin parser.
    """
    raw = os.environ.get("SACP_DETECTION_HISTORY_ENABLED", "")
    return raw.strip().lower() in ("true", "1")
