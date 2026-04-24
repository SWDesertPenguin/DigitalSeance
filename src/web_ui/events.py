"""v1 WebSocket event schema + helpers.

Contract lives in ``specs/011-web-ui/contracts/websocket-events.md``.
Every payload starts with ``{"v": 1, "type": "..."}`` so the client can
refuse to act on unknown versions. These helpers keep serialization
and field ordering consistent across the many broadcast sites that
will call them (orchestrator loop, review-gate repo, summarizer, etc.).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

SCHEMA_VERSION = 1


def _envelope(event_type: str, **fields: Any) -> dict[str, Any]:
    """Wrap an event payload in the standard {v, type, ...} envelope."""
    return {"v": SCHEMA_VERSION, "type": event_type, **fields}


def message_event(message: dict[str, Any]) -> dict[str, Any]:
    """A completed turn was persisted — push full message content."""
    return _envelope(
        "message",
        message=message,
        turn_number=message.get("turn_number"),
    )


def turn_skipped_event(participant_id: str, reason: str, turn_number: int) -> dict[str, Any]:
    """The loop skipped a turn (budget / circuit / review_gate / no_new_input)."""
    return _envelope(
        "turn_skipped",
        participant_id=participant_id,
        reason=reason,
        turn_number=turn_number,
    )


def participant_update_event(participant: dict[str, Any]) -> dict[str, Any]:
    """A participant row changed (role, status, consecutive_timeouts, ...)."""
    return _envelope("participant_update", participant=participant)


def participant_removed_event(participant_id: str) -> dict[str, Any]:
    """A participant row is gone (hard-delete from reject_participant)."""
    return _envelope("participant_removed", participant_id=participant_id)


def convergence_update_event(point: dict[str, Any]) -> dict[str, Any]:
    """One turn's convergence score."""
    return _envelope("convergence_update", point=point)


def review_gate_staged_event(draft: dict[str, Any]) -> dict[str, Any]:
    """A new review-gate draft was created."""
    return _envelope("review_gate_staged", draft=draft)


def review_gate_resolved_event(
    draft_id: str,
    resolution: str,
    turn_number: int | None,
) -> dict[str, Any]:
    """A draft was approved / rejected / edited / timed-out."""
    return _envelope(
        "review_gate_resolved",
        draft_id=draft_id,
        resolution=resolution,
        turn_number=turn_number,
    )


def summary_created_event(summary: dict[str, Any]) -> dict[str, Any]:
    """A summarization checkpoint was written."""
    return _envelope("summary_created", summary=summary)


def session_status_changed_event(status: str) -> dict[str, Any]:
    """Session lifecycle transition (active/paused/archived)."""
    return _envelope("session_status_changed", status=status)


def session_updated_event(updates: dict[str, Any]) -> dict[str, Any]:
    """Partial session-row update (e.g. rename). UI merges into state.session."""
    return _envelope("session_updated", updates=updates)


def loop_status_event(running: bool) -> dict[str, Any]:
    """Loop-running indicator transition."""
    return _envelope("loop_status", running=running)


def error_event(code: str, message: str) -> dict[str, Any]:
    """Non-fatal server-side warning for the UI to surface."""
    return _envelope("error", code=code, message=message)


def pong_event() -> dict[str, Any]:
    """Reply to the client's ping frame."""
    return _envelope("pong")


def audit_entry_event(entry: dict[str, Any]) -> dict[str, Any]:
    """A facilitator action was logged (T252 audit push)."""
    return _envelope("audit_entry", entry=entry)


def ai_question_opened_event(
    *,
    participant_id: str,
    turn_number: int,
    questions: list[str],
) -> dict[str, Any]:
    """An AI's turn contained a question that looks like an open prompt.

    Detected by the heuristics in src.orchestrator.signals; surfaced
    in the Web UI's "Open AI questions" panel so humans don't miss
    questions that scrolled past while the loop kept dispatching.
    """
    return _envelope(
        "ai_question_opened",
        participant_id=participant_id,
        turn_number=turn_number,
        questions=questions,
        at=datetime.utcnow().isoformat(),
    )


def ai_exit_requested_event(
    *,
    participant_id: str,
    turn_number: int,
    phrase: str,
) -> dict[str, Any]:
    """An AI signaled voluntary exit ('I'm stepping back', etc.).

    Advisory only — the facilitator decides whether to honor by flipping
    the AI's routing_preference to observer. Captures the exact phrase
    so the facilitator can sanity-check the detection.
    """
    return _envelope(
        "ai_exit_requested",
        participant_id=participant_id,
        turn_number=turn_number,
        phrase=phrase,
        at=datetime.utcnow().isoformat(),
    )


def proposal_created_event(
    proposal: dict[str, Any],
    tally: dict[str, int] | None = None,
) -> dict[str, Any]:
    """A new proposal was opened (US7 T153)."""
    return _envelope(
        "proposal_created",
        proposal=proposal,
        tally=tally or {"accept": 0, "reject": 0, "abstain": 0},
    )


def proposal_voted_event(
    *,
    proposal_id: str,
    voter_id: str,
    vote: str,
    tally: dict[str, int],
) -> dict[str, Any]:
    """A vote was cast; includes the updated tally."""
    return _envelope(
        "proposal_voted",
        proposal_id=proposal_id,
        voter_id=voter_id,
        vote=vote,
        tally=tally,
    )


def proposal_resolved_event(
    *,
    proposal_id: str,
    status: str,
    tally: dict[str, int] | None = None,
) -> dict[str, Any]:
    """A proposal was resolved by the facilitator (includes final tally)."""
    return _envelope(
        "proposal_resolved",
        proposal_id=proposal_id,
        status=status,
        tally=tally,
    )


def state_snapshot_event(
    *,
    session: dict[str, Any],
    me: dict[str, Any],
    participants: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    pending_drafts: list[dict[str, Any]],
    open_proposals: list[dict[str, Any]],
    latest_summary: dict[str, Any] | None,
    convergence_scores: list[dict[str, Any]],
) -> dict[str, Any]:
    """Full initial payload sent on WS connect + after every reconnect."""
    return _envelope(
        "state_snapshot",
        session=session,
        me=me,
        participants=participants,
        messages=messages,
        pending_drafts=pending_drafts,
        open_proposals=open_proposals,
        latest_summary=latest_summary,
        convergence_scores=convergence_scores,
    )


def iso(dt: datetime | None) -> str | None:
    """Serialize a datetime to ISO-8601 or None."""
    return dt.isoformat() if dt is not None else None


async def broadcast_participant_update(
    session_id: str,
    participant_id: str,
    participant_repo: Any,
    log_repo: Any = None,
) -> None:
    """Fetch a fresh participant row and push a participant_update event.

    If the row no longer exists (hard-delete from ``reject_participant``),
    emit a ``participant_removed`` event instead so the UI can clean its
    state — silently returning here is what made Test06-Web06's reject
    look frozen.
    """
    from src.web_ui.websocket import broadcast_to_session

    p = await participant_repo.get_participant(participant_id)
    if p is None:
        await broadcast_to_session(session_id, participant_removed_event(participant_id))
        return
    spend_daily = None
    spend_hourly = None
    if log_repo is not None:
        spend_daily = await log_repo.get_participant_cost(p.id, period="daily")
        if p.budget_hourly is not None:
            spend_hourly = await log_repo.get_participant_cost(p.id, period="hourly")
    await broadcast_to_session(
        session_id,
        participant_update_event(_participant_payload(p, spend_daily, spend_hourly)),
    )


def _participant_payload(
    p: Any,
    spend_daily: float | None,
    spend_hourly: float | None = None,
) -> dict[str, Any]:
    """Serialize a Participant row for broadcast (drops encrypted fields)."""
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
        "spend_daily": spend_daily,
        "spend_hourly": spend_hourly,
        "invited_by": p.invited_by,
    }
