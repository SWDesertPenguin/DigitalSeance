"""state_snapshot builder.

Gathers everything a UI needs on initial connect or after a reconnect:
session row, participant list, recent messages, pending drafts, open
proposals, latest summary, and recent convergence scores. Uses only
the repositories already attached to the Web UI app state.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from src.orchestrator.branch import get_main_branch_id
from src.web_ui.events import iso, state_snapshot_event

_RECENT_MESSAGES_CAP = 50
_CONVERGENCE_POINTS_CAP = 50


async def build_state_snapshot(
    app_state: Any,
    session_id: str,
    me_payload: dict[str, Any],
) -> dict[str, Any]:
    """Build a state_snapshot event; pending role gets a redacted view."""
    session = await _session_row(app_state, session_id)
    session["loop_running"] = _loop_running(session_id)
    if (me_payload or {}).get("role") == "pending":
        return await _pending_snapshot(app_state, session_id, me_payload, session)
    return state_snapshot_event(
        session=session,
        me=me_payload,
        participants=await _participants(app_state, session_id),
        messages=await _recent_messages(app_state, session_id),
        pending_drafts=await _pending_drafts(app_state, session_id),
        open_proposals=await _open_proposals(app_state, session_id),
        latest_summary=await _latest_summary(app_state, session_id),
        convergence_scores=await _recent_convergence(app_state, session_id),
    )


async def _pending_snapshot(
    app_state: Any,
    session_id: str,
    me_payload: dict[str, Any],
    session: dict[str, Any],
) -> dict[str, Any]:
    """Redacted snapshot for role='pending' joiners: session + humans only."""
    all_participants = await _participants(app_state, session_id)
    humans = [p for p in all_participants if p.get("provider") == "human"]
    return state_snapshot_event(
        session=session,
        me=me_payload,
        participants=humans,
        messages=[],
        pending_drafts=[],
        open_proposals=[],
        latest_summary=None,
        convergence_scores=[],
    )


def _loop_running(session_id: str) -> bool:
    """Late import to avoid circulars; mirrors session.is_loop_running."""
    from src.mcp_server.tools.session import is_loop_running

    return is_loop_running(session_id)


async def _session_row(app_state: Any, session_id: str) -> dict[str, Any]:
    """Return a curated session dict — explicit allow-list, no SELECT *."""
    session = await app_state.session_repo.get_session(session_id)
    if session is None:
        return {}
    return {
        "id": session.id,
        "name": session.name,
        "status": session.status,
        "current_turn": session.current_turn,
        "last_summary_turn": session.last_summary_turn,
        "cadence_preset": session.cadence_preset,
        "complexity_classifier_mode": session.complexity_classifier_mode,
        "min_model_tier": session.min_model_tier,
        "acceptance_mode": session.acceptance_mode,
        "review_gate_pause_scope": session.review_gate_pause_scope,
    }


async def _participants(app_state: Any, session_id: str) -> list[dict[str, Any]]:
    """All participants (UI filters by status). Includes daily spend (C3)."""
    rows = await app_state.participant_repo.list_participants(session_id)
    out: list[dict[str, Any]] = []
    for p in rows:
        spend = await app_state.log_repo.get_participant_cost(p.id, period="daily")
        out.append({**_participant_dict(p), "spend_daily": spend})
    return out


def _participant_dict(p: Any) -> dict[str, Any]:
    """Flatten a Participant dataclass, dropping encrypted fields."""
    return {
        "id": p.id,
        "session_id": p.session_id,
        "display_name": p.display_name,
        "role": p.role,
        "provider": p.provider,
        "model": p.model,
        "model_tier": p.model_tier,
        "model_family": p.model_family,
        "routing_preference": p.routing_preference,
        "status": p.status,
        "consecutive_timeouts": p.consecutive_timeouts,
        "budget_hourly": p.budget_hourly,
        "budget_daily": p.budget_daily,
        "context_window": p.context_window,
        "invited_by": p.invited_by,
    }


async def _recent_messages(app_state: Any, session_id: str) -> list[dict[str, Any]]:
    """Most recent N messages in chronological order."""
    branch_id = await get_main_branch_id(app_state.pool, session_id)
    rows = await app_state.message_repo.get_recent(session_id, branch_id, _RECENT_MESSAGES_CAP)
    return [_message_dict(m) for m in rows]


def _message_dict(m: Any) -> dict[str, Any]:
    """Flatten a Message row; parse JSON content for summaries."""
    payload: dict[str, Any] = {
        "turn_number": m.turn_number,
        "speaker_id": m.speaker_id,
        "speaker_type": m.speaker_type,
        "content": m.content,
        "token_count": m.token_count,
        "cost_usd": m.cost_usd,
        "created_at": iso(m.created_at),
        "summary_epoch": m.summary_epoch,
    }
    if m.speaker_type == "summary":
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            payload["content_json"] = json.loads(m.content)
    return payload


async def _pending_drafts(app_state: Any, session_id: str) -> list[dict[str, Any]]:
    """Review-gate drafts still awaiting approval."""
    drafts = await app_state.review_gate_repo.get_pending(session_id)
    return [
        {
            "id": d.id,
            "participant_id": d.participant_id,
            "draft_content": d.draft_content,
            "context_summary": d.context_summary,
            "created_at": iso(d.created_at),
        }
        for d in drafts
    ]


async def _open_proposals(app_state: Any, session_id: str) -> list[dict[str, Any]]:
    """Proposals in the open state (Phase 2c wires voting UI on top)."""
    from src.repositories.proposal_repo import ProposalRepository

    repo = ProposalRepository(app_state.pool)
    rows = await repo.get_open_proposals(session_id)
    return [
        {
            "id": r.id,
            "topic": r.topic,
            "position": r.position,
            "status": r.status,
            "proposed_by": r.proposed_by,  # fix: actual dataclass field name
            "acceptance_mode": r.acceptance_mode,
            "created_at": iso(r.created_at),
        }
        for r in rows
    ]


async def _latest_summary(app_state: Any, session_id: str) -> dict[str, Any] | None:
    """Most recent summarization checkpoint, if any."""
    branch_id = await get_main_branch_id(app_state.pool, session_id)
    summaries = await app_state.message_repo.get_summaries(session_id, branch_id)
    if not summaries:
        return None
    latest = summaries[-1]
    try:
        parsed = json.loads(latest.content)
    except (json.JSONDecodeError, TypeError):
        parsed = {"narrative": latest.content}
    return {
        "turn_number": latest.turn_number,
        "summary_epoch": latest.summary_epoch,
        **parsed,
    }


async def _recent_convergence(app_state: Any, session_id: str) -> list[dict[str, Any]]:
    """Last N convergence rows for the sparkline."""
    async with app_state.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT turn_number, similarity_score, divergence_prompted"
            " FROM convergence_log WHERE session_id = $1"
            " ORDER BY turn_number DESC LIMIT $2",
            session_id,
            _CONVERGENCE_POINTS_CAP,
        )
    return [dict(r) for r in reversed(rows)]
