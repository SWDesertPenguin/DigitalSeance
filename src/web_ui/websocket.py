"""WebSocket endpoint + per-session broadcast manager.

The manager is a module-level singleton so the MCP app's broadcast
sites (which run in the same process via ``src/run_apps.py``) can push
v1 events to UI clients without the UI being up.

Close-code semantics follow ``specs/011-web-ui/contracts/websocket-events.md``:
  1000  normal
  4401  unauthenticated
  4403  not a participant in this session
  4429  too many connections from IP
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from src.web_ui.auth import _parse_cookie_value
from src.web_ui.events import pong_event, state_snapshot_event
from src.web_ui.snapshot import build_state_snapshot

log = logging.getLogger(__name__)

router = APIRouter()

# Close codes beyond Starlette's 1000–1015 range for our app-level signals.
CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_TOO_MANY = 4429

# Drop a connection if no pong is received for this long.
_PONG_TIMEOUT_SECONDS = 60


class WebSocketManager:
    """Per-session WebSocket subscriber registry."""

    def __init__(self) -> None:
        self._subs: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, ws: WebSocket) -> None:
        """Add a subscriber."""
        async with self._lock:
            self._subs.setdefault(session_id, set()).add(ws)
        log.info(
            "WS subscriber added for session %s (%d total)",
            session_id,
            self.count(session_id),
        )

    async def unregister(self, session_id: str, ws: WebSocket) -> None:
        """Remove a subscriber."""
        async with self._lock:
            bucket = self._subs.get(session_id)
            if bucket:
                bucket.discard(ws)
                if not bucket:
                    del self._subs[session_id]
        log.info("WS subscriber removed for session %s", session_id)

    def count(self, session_id: str) -> int:
        """Active subscriber count for a session."""
        return len(self._subs.get(session_id, set()))

    async def broadcast(self, session_id: str, event: dict[str, Any]) -> None:
        """Push an event to every subscriber of this session."""
        targets = list(self._subs.get(session_id, set()))
        if not targets:
            return
        payload = json.dumps(event)
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:  # noqa: BLE001 — drop dead socket, don't block others
                log.debug("WS send failed for session %s; scheduling unregister", session_id)
                await self.unregister(session_id, ws)


_MANAGER = WebSocketManager()


def get_ws_manager() -> WebSocketManager:
    """Return the process-wide WebSocketManager."""
    return _MANAGER


async def broadcast_to_session(session_id: str, event: dict[str, Any]) -> None:
    """Convenience wrapper for broadcast sites that don't want a manager ref."""
    await _MANAGER.broadcast(session_id, event)


@router.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str) -> None:
    """Per-session push-only WebSocket."""
    participant = await _authenticate_ws(websocket, session_id)
    if participant is None:
        return
    await websocket.accept()
    await _send_initial_snapshot(websocket, session_id, participant)
    await _MANAGER.register(session_id, websocket)
    try:
        await _pump_client_frames(websocket)
    finally:
        await _MANAGER.unregister(session_id, websocket)


async def _authenticate_ws(websocket: WebSocket, session_id: str) -> dict[str, Any] | None:
    """Resolve the cookie to a participant; close on failure."""
    cookie = websocket.cookies.get("sacp_ui_token")
    if not cookie:
        await websocket.close(code=CLOSE_UNAUTHENTICATED, reason="no cookie")
        return None
    try:
        payload = _parse_cookie_value(cookie)
    except Exception:  # noqa: BLE001 — bad sig / expired → same 4401
        await websocket.close(code=CLOSE_UNAUTHENTICATED, reason="bad cookie")
        return None
    if payload.get("sid") != session_id:
        await websocket.close(code=CLOSE_FORBIDDEN, reason="wrong session")
        return None
    return payload


async def _send_initial_snapshot(
    websocket: WebSocket,
    session_id: str,
    participant: dict[str, Any],
) -> None:
    """Build and send the state_snapshot event on connect."""
    app_state = websocket.app.state
    if not hasattr(app_state, "pool"):
        empty = state_snapshot_event(
            session={},
            me=participant,
            participants=[],
            messages=[],
            pending_drafts=[],
            open_proposals=[],
            latest_summary=None,
            convergence_scores=[],
        )
        await websocket.send_text(json.dumps(empty))
        return
    snapshot = await build_state_snapshot(app_state, session_id, participant)
    await websocket.send_text(json.dumps(snapshot))


async def _pump_client_frames(websocket: WebSocket) -> None:
    """Handle inbound frames: ping → pong; subscribe is a no-op hint today."""
    last_pong = datetime.now(tz=UTC)
    try:
        while True:
            try:
                text = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=_PONG_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                if (datetime.now(tz=UTC) - last_pong).total_seconds() > _PONG_TIMEOUT_SECONDS:
                    await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="no pong")
                    return
                continue
            last_pong = datetime.now(tz=UTC)
            await _handle_client_frame(websocket, text)
    except WebSocketDisconnect:
        return


async def _handle_client_frame(websocket: WebSocket, text: str) -> None:
    """Decode a client frame and respond when appropriate."""
    try:
        frame = json.loads(text)
    except json.JSONDecodeError:
        return
    if frame.get("type") == "ping":
        await websocket.send_text(json.dumps(pong_event()))
