"""SSE streaming endpoint — real-time turn updates per session."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant

log = logging.getLogger(__name__)

router = APIRouter(tags=["sse"])

_KEEPALIVE_TIMEOUT = 30.0  # seconds between keepalive comments
_DEFAULT_MAX_SUBSCRIBERS = 64  # 006 §FR-019; configurable via SACP_MAX_SUBSCRIBERS_PER_SESSION


def _max_subscribers_per_session() -> int:
    """Read the per-session SSE subscriber cap from env (006 §FR-019).

    Default 64: 64 × 256-event queue × ~1KB/event ≈ 16MB/session memory
    ceiling. Read each call so tests can monkeypatch without app restart.
    """
    raw = os.environ.get("SACP_MAX_SUBSCRIBERS_PER_SESSION", "").strip()
    if not raw:
        return _DEFAULT_MAX_SUBSCRIBERS
    try:
        val = int(raw)
    except ValueError:
        return _DEFAULT_MAX_SUBSCRIBERS
    return val if val > 0 else _DEFAULT_MAX_SUBSCRIBERS


async def _event_stream(
    cm: object,
    session_id: str,
    participant_id: str,
) -> AsyncGenerator[str, None]:
    """Yield SSE lines from the session queue until the client disconnects."""
    q = await cm.subscribe(session_id)
    log.info("SSE connection opened for session %s participant %s", session_id, participant_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=_KEEPALIVE_TIMEOUT)
                yield f"data: {json.dumps(event)}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        cm.unsubscribe(session_id, q)
        log.info(
            "SSE connection closed for session %s participant %s",
            session_id,
            participant_id,
        )


@router.get("/sse/{session_id}")
async def sse_stream(
    session_id: str,
    request: Request,
    participant: Participant = Depends(get_current_participant),
) -> StreamingResponse:
    """Stream turn-completion events to an authenticated participant.

    Each event is a JSON object:
        data: {"turn": <int>, "speaker_id": "<uuid>", "action": "<str>", "skipped": <bool>}

    A keepalive comment (`: keepalive`) is sent every 30 s to prevent proxy timeouts.
    Reconnection: use the same bearer token. Missed turns: GET /tools/participant/history.
    """
    if participant.session_id != session_id:
        raise HTTPException(status_code=403, detail="Token is not valid for this session")
    cm = request.app.state.connection_manager
    cap = _max_subscribers_per_session()
    if cm.subscriber_count(session_id) >= cap:
        raise HTTPException(status_code=503, detail="subscriber_cap_reached")
    return StreamingResponse(
        _event_stream(cm, session_id, participant.id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
