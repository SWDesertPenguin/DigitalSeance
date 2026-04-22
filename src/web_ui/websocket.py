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
import os
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
        # Per-ws participant tag so revoke/remove can target a specific user.
        self._ws_pid: dict[int, str] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        session_id: str,
        ws: WebSocket,
        participant_id: str | None = None,
    ) -> None:
        """Add a subscriber, optionally tagged with its participant id."""
        async with self._lock:
            self._subs.setdefault(session_id, set()).add(ws)
            if participant_id:
                self._ws_pid[id(ws)] = participant_id
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
            self._ws_pid.pop(id(ws), None)
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

    async def close_for_participant(self, session_id: str, participant_id: str) -> int:
        """Close every WS belonging to a participant with code 4401.

        Called on revoke / remove so a booted user's UI force-redirects to
        landing instead of silently losing the ability to act.
        """
        closed = 0
        targets = [
            ws
            for ws in list(self._subs.get(session_id, set()))
            if self._ws_pid.get(id(ws)) == participant_id
        ]
        for ws in targets:
            try:
                await ws.close(code=CLOSE_UNAUTHENTICATED, reason="token revoked")
                closed += 1
            except Exception:  # noqa: BLE001 — socket may already be dead
                log.debug("WS close_for_participant failed for %s", participant_id)
        return closed


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
    await _MANAGER.register(session_id, websocket, participant.get("pid"))
    try:
        await _pump_client_frames(websocket)
    finally:
        await _MANAGER.unregister(session_id, websocket)


async def _authenticate_ws(websocket: WebSocket, session_id: str) -> dict[str, Any] | None:
    """Resolve the cookie + Origin; close on failure.

    Constitution §9 + SR-004 require Origin validation on every WebSocket
    upgrade to prevent cross-site WebSocket hijacking. We reject upgrades
    whose Origin does not match the UI's own origin or an explicit
    env-configured allowlist.
    """
    if not _origin_allowed(websocket):
        await websocket.close(code=CLOSE_FORBIDDEN, reason="origin not allowed")
        return None
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


def _origin_allowed(websocket: WebSocket) -> bool:
    """Check Origin against SACP_WEB_UI_ALLOWED_ORIGINS or same-origin default.

    A request with no Origin header is rejected.
    """
    origin = websocket.headers.get("origin")
    if not origin:
        return False
    env_raw = os.environ.get("SACP_WEB_UI_ALLOWED_ORIGINS", "").strip()
    if env_raw:
        allowed = {o.strip() for o in env_raw.split(",") if o.strip()}
        return origin in allowed
    host = websocket.headers.get("host", "")
    return origin in (f"http://{host}", f"https://{host}")


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
    """Handle inbound frames: close if no traffic within 2× heartbeat.

    Previous version used an unreachable elapsed-since-last-pong check
    that never fired, leaking dead sockets. Now any 2×_PONG_TIMEOUT
    silence closes the connection.
    """
    try:
        while True:
            try:
                text = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=_PONG_TIMEOUT_SECONDS * 2,
                )
            except TimeoutError:
                await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="no pong")
                return
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
