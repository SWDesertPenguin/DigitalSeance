# SPDX-License-Identifier: AGPL-3.0-or-later

"""Debug tool endpoints — read-only diagnostic dumps for facilitators."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from src.models.participant import Participant
from src.orchestrator.branch import get_main_branch_id
from src.orchestrator.time_format import format_iso
from src.participant_api.middleware import get_current_participant

router = APIRouter(prefix="/tools/debug", tags=["debug"])

# Per spec 010 §FR-4 + §SC-003. New sensitive columns added to the participants
# table (or any participant-shaped serializer) MUST extend this set. The
# tests/test_mcp_app.py::test_sensitive_fields_cover_obvious_patterns guard
# fails CI if any Participant field whose name matches the heuristic patterns
# (_encrypted / _hash / _lookup / bound_ip) is missing from this set (010 CHK001).
_SENSITIVE_FIELDS = frozenset(
    {"api_key_encrypted", "auth_token_hash", "auth_token_lookup", "bound_ip"},
)

# Defensive name-pattern guard for the config snapshot (010 §SC-006 / CHK005).
# Even if an operator names an env var with an SACP_ prefix that accidentally
# falls into the allowlist, any name matching these suffixes is filtered out
# of the snapshot. The allowlist (_CONFIG_KEYS) is the primary surface; this
# pattern is the secondary safety net.
_SECRET_NAME_PATTERN = re.compile(
    r"(?:_KEY|_SECRET|_TOKEN|_PASSWORD|_CREDENTIAL|_PASSPHRASE)$",
    re.IGNORECASE,
)


@router.get("/export")
async def export_session(
    request: Request,
    session_id: str,
    participant: Participant = Depends(get_current_participant),
    include_sponsored: bool = False,
) -> dict:
    """Dump everything we know about a session for troubleshooting.

    Facilitator-only. Strips encrypted/hash fields from participants.
    Null/empty collections are included so operators can see gaps.

    The export call itself is recorded in admin_audit_log per 010 §FR-8 /
    CHK036 so an attacker dumping session state to exfiltrate leaves a
    forensic trail. The audit row uses action='debug_export' with the
    requesting facilitator as both actor and target_id (the action operates
    on the session as a whole, not a specific participant).

    Sovereignty (themes B of facilitator-sovereignty audit, 2026-05-15):
    the per-participant ``spend`` and ``logs.usage`` arrays are scoped
    to (a) participants the caller invited or (b) the caller's own row.
    Session-level aggregates (``session_totals``) sum across every
    participant so the facilitator retains cost-control visibility.
    ``include_sponsored=true`` is reserved for a future sponsor-consent
    flow (spec 031) and returns 403 today.
    """
    _authorize(participant, session_id)
    _reject_unwired_include_sponsored(include_sponsored)
    state = request.app.state
    session = await state.session_repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await state.log_repo.log_admin_action(
        session_id=session_id,
        facilitator_id=participant.id,
        action="debug_export",
        target_id=session_id,
        broadcast_session_id=session_id,
    )
    return await _build_dump(state, session, session_id, participant.id)


def _reject_unwired_include_sponsored(include_sponsored: bool) -> None:
    """Return 403 for ``include_sponsored=true`` until spec 031 lands.

    Theme B of the facilitator-sovereignty audit (2026-05-15): cross-
    participant spend/usage requires a sponsor-recorded
    ``debug_export_consent_for_sponsor`` row. That table belongs to
    spec 031, so the path is wired with the response shape it will
    use but returns 403 until the consent flow exists.
    """
    if include_sponsored:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "sponsor_consent_required",
                "message": (
                    "cross-participant spend/usage requires per-sponsor consent;"
                    " the consent flow lands in spec 031"
                ),
            },
        )


def _authorize(participant: Participant, session_id: str) -> None:
    """Reject non-facilitators or cross-session access."""
    if participant.role != "facilitator":
        raise HTTPException(status_code=403, detail="Facilitator only")
    if participant.session_id != session_id:
        raise HTTPException(status_code=403, detail="Session mismatch")


async def _build_dump(
    state: Any,
    session: Any,
    session_id: str,
    requester_id: str,
) -> dict:
    """Collect all session data into a single JSON-safe dict."""
    sections = await _collect_dump_sections(state, session, session_id, requester_id)
    return _assemble_dump(sections, session, requester_id)


async def _collect_dump_sections(
    state: Any,
    session: Any,
    session_id: str,
    caller_id: str,
) -> dict:
    """Pull every per-session collection in one place.

    ``caller_id`` scopes the per-participant ``logs.usage`` + ``spend``
    sections (theme B): only rows for the caller's sponsored AIs or the
    caller's own participant_id are surfaced. ``session_totals`` (the
    cross-participant aggregate) is computed unconditionally so the
    facilitator retains cost-control visibility.
    """
    branch_id = await get_main_branch_id(state.pool, session_id)
    participants = await state.participant_repo.list_participants(session_id)
    scoped = _scoped_for_spend(participants, caller_id)
    messages = await state.message_repo.get_recent(session_id, branch_id, 10_000)
    interrupts = await _fetch_all_interrupts(state.pool, session_id)
    logs = await _fetch_logs(state.pool, session_id, scoped)
    spend = await _fetch_spend(state.pool, scoped)
    session_totals = await _fetch_session_totals(state.pool, participants)
    detection_events = await _fetch_detection_events(state, session_id)
    return {
        "branch_id": branch_id,
        "participants": participants,
        "messages": messages,
        "interrupts": interrupts,
        "logs": logs,
        "spend": spend,
        "session_totals": session_totals,
        "detection_events": detection_events,
    }


def _scoped_for_spend(participants: list, caller_id: str) -> list:
    """Restrict per-participant wallet reads to sponsored-or-self rows.

    Theme B: facilitator default visibility narrows to the caller's
    own row and AIs they sponsored (``invited_by == caller_id``).
    Returns a filtered copy of the participant list; the unfiltered
    list is still used for ``session_totals`` and for the participants
    listing (which carries no per-participant wallet data).
    """
    return [p for p in participants if p.id == caller_id or _sponsored_by(p, caller_id)]


def _sponsored_by(participant: Any, caller_id: str) -> bool:
    """True when ``participant`` was invited by ``caller_id``."""
    return getattr(participant, "invited_by", None) == caller_id


def _assemble_dump(sections: dict, session: Any, requester_id: str) -> dict:
    participants = sections["participants"]
    messages = sections["messages"]
    name_by_id = {p.id: p.display_name for p in participants}
    return {
        "exported_at": format_iso(datetime.now(tz=UTC)),
        "exported_by": requester_id,
        "session": _serialize(session),
        "branch_id": sections["branch_id"],
        "participants": [_scrub(_serialize(p)) for p in participants],
        "messages": [_with_speaker_name(_serialize(m), name_by_id) for m in messages],
        "visibility_partition": _visibility_partition(messages, participants, session),
        "interrupts": [_serialize(i) for i in sections["interrupts"]],
        "logs": sections["logs"],
        "detection_events": sections["detection_events"],
        "spend": sections["spend"],
        "session_totals": sections["session_totals"],
        "config_snapshot": _config_snapshot(),
    }


def _visibility_partition(messages: list, participants: list, session: Any) -> dict:
    """Spec 028 §FR-024 — per-participant visibility view for forensics.

    Returns a mapping ``{participant_id: [turn_numbers visible to them]}``
    so a reviewer can reconstruct each participant's effective transcript
    view without re-implementing the runtime filter. Humans see every
    turn; the active CAPCOM AI sees every turn; every other AI sees only
    ``visibility='public'`` turns.
    """
    capcom_id = getattr(session, "capcom_participant_id", None)
    out: dict[str, list[int]] = {}
    for p in participants:
        if p.provider == "human" or p.id == capcom_id:
            out[p.id] = [m.turn_number for m in messages]
        else:
            out[p.id] = [m.turn_number for m in messages if m.visibility == "public"]
    return out


async def _fetch_detection_events(state: Any, session_id: str) -> list:
    """Fetch every spec 022 detection_events row for the session (FR-10)."""
    rows = await state.log_repo.get_detection_events_page(
        session_id,
        max_events=None,
        since=None,
    )
    return [_jsonify(row) for row in rows]


def _with_speaker_name(row: dict, name_by_id: dict[str, str]) -> dict:
    """Inject a `speaker_display_name` next to `speaker_id` for readability.

    The raw export gave only `speaker_id` (12-char hash) and a coarse
    `speaker_type` ('human'/'ai'/'summary'), so reconstructing who said
    what required cross-referencing participants[]. Inlining the
    display_name keeps the row self-contained for forensics + LLM
    summarization workflows.
    """
    sid = row.get("speaker_id")
    if sid:
        row["speaker_display_name"] = name_by_id.get(sid, "unknown")
    return row


async def _fetch_all_interrupts(pool: Any, session_id: str) -> list:
    """Read every interrupt row (pending + delivered) for the session."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM interrupt_queue WHERE session_id = $1 ORDER BY id",
            session_id,
        )
    return [dict(r) for r in rows]


_LOG_QUERIES = {
    "routing": "SELECT * FROM routing_log WHERE session_id = $1 ORDER BY turn_number",
    "convergence": (
        "SELECT turn_number, session_id, similarity_score, "
        "divergence_prompted, escalated_to_human "
        "FROM convergence_log WHERE session_id = $1 ORDER BY turn_number"
    ),
    "audit": "SELECT * FROM admin_audit_log WHERE session_id = $1 ORDER BY timestamp",
    "security_events": "SELECT * FROM security_events WHERE session_id = $1 ORDER BY timestamp",
}


async def _fetch_logs(
    pool: Any,
    session_id: str,
    participants: list,
) -> dict:
    """Dump routing, usage, convergence, audit, security logs for the session."""
    async with pool.acquire() as conn:
        out = {
            key: [dict(r) for r in await conn.fetch(sql, session_id)]
            for key, sql in _LOG_QUERIES.items()
        }
        out["usage"] = await _fetch_usage_for_participants(conn, participants)
    return out


async def _fetch_usage_for_participants(conn: Any, participants: list) -> list:
    """Fetch usage rows for each participant (flat list with participant_id)."""
    out: list[dict] = []
    for p in participants:
        rows = await conn.fetch(
            "SELECT * FROM usage_log WHERE participant_id = $1 ORDER BY timestamp",
            p.id,
        )
        out.extend(dict(r) for r in rows)
    return out


async def _fetch_spend(pool: Any, participants: list) -> list:
    """Per-participant spend totals vs budget limits (sponsored-or-self only).

    Caller-side scoping is applied upstream in ``_scoped_for_spend`` so
    this function emits one row per ``participants`` entry without
    re-checking sponsorship. The participants list is already the
    sponsor-or-self subset for theme B of the facilitator-sovereignty
    audit (2026-05-15).
    """
    async with pool.acquire() as conn:
        out: list[dict] = []
        for p in participants:
            row = await conn.fetchrow(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total"
                " FROM usage_log WHERE participant_id = $1",
                p.id,
            )
            total = float(row["total"]) if row else 0.0
            out.append(
                {
                    "participant_id": p.id,
                    "display_name": p.display_name,
                    "total_cost_usd": total,
                    "budget_hourly": p.budget_hourly,
                    "budget_daily": p.budget_daily,
                }
            )
    return out


async def _fetch_session_totals(pool: Any, participants: list) -> dict:
    """Sum cost + tokens across every participant in the session.

    Theme B compensates the facilitator's lost per-participant
    visibility (when the caller did not invite the AI) with a session-
    level aggregate so cost-control remains visible without exposing
    individual wallets. Returns ``total_cost_usd``,
    ``total_input_tokens``, ``total_output_tokens`` — one summary
    object, no per-participant breakdown.
    """
    if not participants:
        return {
            "total_cost_usd": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }
    participant_ids = [p.id for p in participants]
    sql = (
        "SELECT COALESCE(SUM(cost_usd), 0) AS total_cost,"
        " COALESCE(SUM(input_tokens), 0) AS total_input,"
        " COALESCE(SUM(output_tokens), 0) AS total_output"
        " FROM usage_log"
        " WHERE participant_id = ANY($1::text[])"
    )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, participant_ids)
    return {
        "total_cost_usd": float(row["total_cost"]) if row else 0.0,
        "total_input_tokens": int(row["total_input"]) if row else 0,
        "total_output_tokens": int(row["total_output"]) if row else 0,
    }


def _serialize(obj: Any) -> Any:
    """Convert dataclasses / records to JSON-safe dicts."""
    if obj is None:
        return None
    if is_dataclass(obj):
        return _jsonify(asdict(obj))
    if isinstance(obj, dict):
        return _jsonify(obj)
    return _jsonify(dict(obj))


def _jsonify(value: Any) -> Any:
    """Recursively coerce datetimes / bytes into JSON primitives."""
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonify(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value


def _scrub(record: dict) -> dict:
    """Remove sensitive fields from a serialized participant."""
    return {k: v for k, v in record.items() if k not in _SENSITIVE_FIELDS}


_CONFIG_KEYS = (
    "SACP_CONTEXT_MAX_TURNS",
    "SACP_CORS_ORIGINS",
    "SACP_DEFAULT_TURN_TIMEOUT",
    "SACP_RATE_LIMIT_PER_MIN",
)


def _config_snapshot() -> dict:
    """Capture runtime-visible env knobs (no secrets).

    Two-layer filtering per 010 §SC-006 / CHK005:
    1. Hardcoded allowlist (`_CONFIG_KEYS`) — primary surface.
    2. Defensive name-pattern guard (`_SECRET_NAME_PATTERN`) — secondary
       safety net. Any allowlisted key whose name ends in `_KEY`, `_SECRET`,
       `_TOKEN`, `_PASSWORD`, `_CREDENTIAL`, or `_PASSPHRASE` is dropped
       even if the operator added it to the allowlist by mistake.
    """
    safe = [k for k in _CONFIG_KEYS if not _SECRET_NAME_PATTERN.search(k)]
    return {k: os.environ.get(k) for k in safe}
