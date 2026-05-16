# SPDX-License-Identifier: AGPL-3.0-or-later

"""Detection-event history endpoint (spec 022 FR-001 + FR-013 + FR-014).

The router mounts conditionally on ``SACP_DETECTION_HISTORY_ENABLED=true``;
when disabled the route is absent and ALL callers receive ``HTTP 404`` per
FR-016. The mount decision lives in ``src/participant_api/app.py`` so the master
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

from src.models.participant import Participant
from src.observability.instrumentation import instrument_stage
from src.orchestrator.time_format import format_iso, format_iso_or_none
from src.participant_api.middleware import get_current_participant
from src.repositories.detection_event_repo import apply_resurface
from src.web_ui.cross_instance_broadcast import broadcast_session_event
from src.web_ui.detection_events import format_class_label
from src.web_ui.events import (
    build_detection_event_payload,
    detection_event_resurfaced_event,
)

router = APIRouter(prefix="/tools/admin", tags=["admin"])

# Theme B of the facilitator-sovereignty audit (2026-05-15) — when the
# detection event fired on a ``visibility='capcom_only'`` message and
# the caller is a facilitator who is NOT the active CAPCOM, the trigger
# snippet (which can carry the message body) is replaced with this
# exact sentinel string. Spec 031 will reference the literal verbatim,
# so it MUST NOT drift.
CAPCOM_ONLY_REDACTION_SENTINEL = "[redacted: capcom_only message]"


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

    Theme B (2026-05-15): for events that fired on ``capcom_only``
    messages, the ``trigger_snippet`` is replaced with
    ``CAPCOM_ONLY_REDACTION_SENTINEL`` when the caller is not the
    active CAPCOM. The active CAPCOM participant — and humans/CAPCOM
    on the resurface broadcast — still see the snippet.
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
    visibility_map = await _load_visibility_map(state, session_id, rows)
    capcom_id = await _resolve_capcom_id(state, session_id) if rows else None
    events = [_decorate_event(row, visibility_map, capcom_id, participant.id) for row in rows]
    as_of = format_iso_or_none(datetime.now(UTC))
    return {
        "session_id": session_id,
        "events": events,
        "count": len(events),
        "max_events_applied": max_events is not None and len(events) == max_events,
        "as_of": as_of,
    }


def _decorate_event(
    row: dict,
    visibility_map: dict[tuple[int, str], str] | None = None,
    capcom_id: str | None = None,
    caller_id: str | None = None,
) -> dict:
    """Project a DB row into the wire shape (adds event_class_label).

    Applies the theme B trigger_snippet redaction when the source
    message was ``capcom_only`` and the caller is not the CAPCOM.
    ``visibility_map`` keyed by ``(turn_number, participant_id)``;
    a row with no matching key is treated as ``public`` (no redaction).
    """
    out = {
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
    out["trigger_snippet"] = _maybe_redact_snippet(
        row, out["trigger_snippet"], visibility_map, capcom_id, caller_id
    )
    return out


def _maybe_redact_snippet(
    row: dict,
    current_snippet: str | None,
    visibility_map: dict[tuple[int, str], str] | None,
    capcom_id: str | None,
    caller_id: str | None,
) -> str | None:
    """Swap the snippet for the sentinel on capcom_only-non-CAPCOM reads.

    Returns the redaction sentinel only when (a) the source message
    visibility is ``capcom_only`` AND (b) ``caller_id`` is set AND (c)
    the caller is not the active CAPCOM. ``None`` snippets pass through
    unchanged (no body to redact). Missing visibility map / caller_id
    leave the snippet untouched so the helper composes with the
    existing test surface that does not thread the new args.
    """
    if visibility_map is None or caller_id is None:
        return current_snippet
    turn = row.get("turn_number")
    pid = row.get("participant_id")
    if turn is None or pid is None:
        return current_snippet
    visibility = visibility_map.get((turn, pid), "public")
    if visibility != "capcom_only":
        return current_snippet
    if caller_id == capcom_id:
        return current_snippet
    return CAPCOM_ONLY_REDACTION_SENTINEL


async def _load_visibility_map(
    state, session_id: str, rows: list[dict]
) -> dict[tuple[int, str], str]:
    """Look up ``visibility`` per (turn_number, participant_id) for the events.

    One bulk SELECT against ``messages`` keyed by the (turn, speaker_id)
    pairs the page is about to render. Pairs absent from the query
    response default to ``public`` so a missing-source-message event
    surfaces its existing snippet unchanged.

    Returns ``{}`` when the state surface lacks a usable pool — keeps
    legacy unit tests that mock only ``log_repo.get_detection_events_page``
    compatible. Production wiring always populates ``log_repo._pool``.
    """
    pairs = [
        (r["turn_number"], r["participant_id"]) for r in rows if r.get("turn_number") is not None
    ]
    if not pairs:
        return {}
    pool = _resolve_pool(state)
    if pool is None:
        return {}
    turns = [t for t, _ in pairs]
    speakers = [s for _, s in pairs]
    sql = (
        "SELECT turn_number, speaker_id, visibility"
        " FROM messages"
        " WHERE session_id = $1"
        " AND turn_number = ANY($2::int[])"
        " AND speaker_id = ANY($3::text[])"
    )
    async with pool.acquire() as conn:
        records = await conn.fetch(sql, session_id, turns, speakers)
    return {(int(r["turn_number"]), r["speaker_id"]): r["visibility"] for r in records}


def _resolve_pool(state):
    """Best-effort lookup of the asyncpg pool for the visibility query.

    Production wires the pool on both ``state.pool`` and
    ``state.log_repo._pool``. Returns ``None`` when neither is present
    so the visibility lookup degrades to a no-op for legacy unit tests.
    """
    pool = getattr(state, "pool", None)
    if pool is not None:
        return pool
    log_repo = getattr(state, "log_repo", None)
    if log_repo is None:
        return None
    return getattr(log_repo, "_pool", None)


async def _resolve_capcom_id(state, session_id: str) -> str | None:
    """Return ``session.capcom_participant_id`` or ``None`` if unset/absent.

    Returns ``None`` when the state surface lacks ``session_repo`` (the
    legacy unit-test mock surface). Production wiring always populates
    it; the early-out keeps redaction disabled rather than crashing on
    a missing repo.
    """
    session_repo = getattr(state, "session_repo", None)
    if session_repo is None:
        return None
    session = await session_repo.get_session(session_id)
    if session is None:
        return None
    return getattr(session, "capcom_participant_id", None)


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
