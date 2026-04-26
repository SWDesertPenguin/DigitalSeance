"""System messages announcing participant lifecycle changes in the transcript.

Departures (remove_participant, release_ai_slot, honored exit, circuit-breaker
auto-pause) used to be silent — humans reading the transcript would not know
an AI had left. ``announce_departure`` writes a ``speaker_type='system'`` row
into the messages table and broadcasts the live ``message`` event so the chat
shows the notice without waiting for the next snapshot.

Arrivals (mid-session add, invite redemption, facilitator approval) are
symmetric: ``announce_arrival`` writes the same kind of system row so the
transcript reflects who joined and when.
"""

from __future__ import annotations

from typing import Any

from src.orchestrator.branch import get_main_branch_id


async def announce_departure(
    *,
    pool: Any,
    msg_repo: Any,
    session_id: str,
    speaker_id: str,
    departing_name: str,
    kind: str,
) -> None:
    """Write a system message + broadcast it for a departing participant.

    ``speaker_id`` must reference a real participants row (FK constraint);
    pass the facilitator id from HTTP handlers, or any active participant
    id from the orchestrator-side circuit breaker hook.
    """
    from src.web_ui.events import message_event
    from src.web_ui.websocket import broadcast_to_session

    branch_id = await get_main_branch_id(pool, session_id)
    content = f"{departing_name} {kind}."
    msg = await msg_repo.append_message(
        session_id=session_id,
        branch_id=branch_id,
        speaker_id=speaker_id,
        speaker_type="system",
        content=content,
        token_count=max(len(content) // 4, 1),
        complexity_score="n/a",
    )
    payload = {
        "turn_number": msg.turn_number,
        "speaker_id": msg.speaker_id,
        "speaker_type": msg.speaker_type,
        "content": msg.content,
        "token_count": msg.token_count,
        "cost_usd": None,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "summary_epoch": msg.summary_epoch,
    }
    await broadcast_to_session(session_id, message_event(payload))


async def announce_arrival(
    *,
    pool: Any,
    msg_repo: Any,
    session_id: str,
    speaker_id: str,
    joining_name: str,
    kind: str,
) -> None:
    """Write a system message + broadcast it for a participant who just joined.

    ``speaker_id`` must reference a real participants row (FK constraint);
    pass the new participant's own id (already inserted before this call).
    Only call this when the loop is already running so the message lands in
    an active session transcript.
    """
    from src.web_ui.events import message_event
    from src.web_ui.websocket import broadcast_to_session

    branch_id = await get_main_branch_id(pool, session_id)
    content = f"{joining_name} {kind}."
    msg = await msg_repo.append_message(
        session_id=session_id,
        branch_id=branch_id,
        speaker_id=speaker_id,
        speaker_type="system",
        content=content,
        token_count=max(len(content) // 4, 1),
        complexity_score="n/a",
    )
    payload = {
        "turn_number": msg.turn_number,
        "speaker_id": msg.speaker_id,
        "speaker_type": msg.speaker_type,
        "content": msg.content,
        "token_count": msg.token_count,
        "cost_usd": None,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "summary_epoch": msg.summary_epoch,
    }
    await broadcast_to_session(session_id, message_event(payload))
