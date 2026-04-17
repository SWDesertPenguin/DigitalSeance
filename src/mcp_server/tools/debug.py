"""Debug tool endpoints — read-only diagnostic dumps for facilitators."""

from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant
from src.orchestrator.branch import get_main_branch_id

router = APIRouter(prefix="/tools/debug", tags=["debug"])

_SENSITIVE_FIELDS = frozenset(
    {"api_key_encrypted", "auth_token_hash", "bound_ip"},
)


@router.get("/export")
async def export_session(
    request: Request,
    session_id: str,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Dump everything we know about a session for troubleshooting.

    Facilitator-only. Strips encrypted/hash fields from participants.
    Null/empty collections are included so operators can see gaps.
    """
    _authorize(participant, session_id)
    state = request.app.state
    session = await state.session_repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return await _build_dump(state, session, session_id, participant.id)


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
    branch_id = await get_main_branch_id(state.pool, session_id)
    participants = await state.participant_repo.list_participants(session_id)
    messages = await state.message_repo.get_recent(session_id, branch_id, 10_000)
    interrupts = await _fetch_all_interrupts(state.pool, session_id)
    logs = await _fetch_logs(state.pool, session_id, participants)
    spend = await _fetch_spend(state.pool, participants)
    return {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "exported_by": requester_id,
        "session": _serialize(session),
        "branch_id": branch_id,
        "participants": [_scrub(_serialize(p)) for p in participants],
        "messages": [_serialize(m) for m in messages],
        "interrupts": [_serialize(i) for i in interrupts],
        "logs": logs,
        "spend": spend,
        "config_snapshot": _config_snapshot(),
    }


async def _fetch_all_interrupts(pool: Any, session_id: str) -> list:
    """Read every interrupt row (pending + delivered) for the session."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM interrupt_queue WHERE session_id = $1 ORDER BY id",
            session_id,
        )
    return [dict(r) for r in rows]


async def _fetch_logs(
    pool: Any,
    session_id: str,
    participants: list,
) -> dict:
    """Dump routing, usage, convergence, audit logs for the session."""
    async with pool.acquire() as conn:
        routing = await conn.fetch(
            "SELECT * FROM routing_log WHERE session_id = $1 ORDER BY turn_number",
            session_id,
        )
        convergence = await conn.fetch(
            "SELECT turn_number, session_id, similarity_score, "
            "divergence_prompted, escalated_to_human "
            "FROM convergence_log WHERE session_id = $1 ORDER BY turn_number",
            session_id,
        )
        audit = await conn.fetch(
            "SELECT * FROM admin_audit_log WHERE session_id = $1 ORDER BY timestamp",
            session_id,
        )
        usage = await _fetch_usage_for_participants(conn, participants)
    return {
        "routing": [dict(r) for r in routing],
        "usage": usage,
        "convergence": [dict(r) for r in convergence],
        "audit": [dict(r) for r in audit],
    }


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
    """Per-participant spend totals vs budget limits."""
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


def _config_snapshot() -> dict:
    """Capture runtime-visible env knobs (no secrets)."""
    keys = (
        "SACP_CONTEXT_MAX_TURNS",
        "SACP_CORS_ORIGINS",
        "SACP_DEFAULT_TURN_TIMEOUT",
        "SACP_RATE_LIMIT_PER_MIN",
    )
    return {k: os.environ.get(k) for k in keys}
