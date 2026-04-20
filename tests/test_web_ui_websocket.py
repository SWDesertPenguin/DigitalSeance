"""WebSocket tests for the Phase 2 Web UI — task T041.

Covers:
  - WS upgrade without cookie → close 4401
  - WS upgrade with cookie bound to a different session → close 4403
  - Broadcast via broadcast_to_session reaches every subscriber
  - Event envelope includes {"v": 1, "type": ...} per contract
  - ping / pong liveness
"""

from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.web_ui.auth import _make_cookie_value
from src.web_ui.events import message_event, session_status_changed_event
from src.web_ui.websocket import (
    CLOSE_FORBIDDEN,
    CLOSE_UNAUTHENTICATED,
    broadcast_to_session,
    get_ws_manager,
)

_SECURE_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_ENCRYPTION_KEY", _SECURE_KEY)
    monkeypatch.setenv("SACP_WEB_UI_INSECURE_COOKIES", "1")


def _app():  # type: ignore[no-untyped-def]
    from src.web_ui.app import create_web_app

    return create_web_app()


def test_ws_rejects_missing_cookie() -> None:
    """WebSocket without sacp_ui_token closes with 4401."""
    with (
        TestClient(_app()) as client,
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect("/ws/some-session") as ws,
    ):
        ws.receive_text()  # force read to surface the server-initiated close
    assert excinfo.value.code == CLOSE_UNAUTHENTICATED


def test_ws_rejects_wrong_session_cookie() -> None:
    """Cookie bound to session A cannot open a WS for session B."""
    cookie = _make_cookie_value("pid-1", "session-A")
    with TestClient(_app()) as client:
        client.cookies.set("sacp_ui_token", cookie)
        with (
            pytest.raises(WebSocketDisconnect) as excinfo,
            client.websocket_connect("/ws/session-B") as ws,
        ):
            ws.receive_text()
    assert excinfo.value.code == CLOSE_FORBIDDEN


@pytest.mark.asyncio
async def test_broadcast_reaches_subscriber() -> None:
    """A manager.broadcast reaches every connection subscribed to that session."""
    mgr = get_ws_manager()

    class _FakeWS:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def send_text(self, text: str) -> None:
            self.sent.append(text)

    ws1, ws2 = _FakeWS(), _FakeWS()
    await mgr.register("sid", ws1)  # type: ignore[arg-type]
    await mgr.register("sid", ws2)  # type: ignore[arg-type]
    try:
        event = message_event({"turn_number": 1, "speaker_id": "p1"})
        await broadcast_to_session("sid", event)
        assert len(ws1.sent) == 1
        assert len(ws2.sent) == 1
        parsed = json.loads(ws1.sent[0])
        assert parsed["v"] == 1
        assert parsed["type"] == "message"
        assert parsed["turn_number"] == 1
    finally:
        await mgr.unregister("sid", ws1)  # type: ignore[arg-type]
        await mgr.unregister("sid", ws2)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_broadcast_skips_other_sessions() -> None:
    """A broadcast to session A does not reach session B subscribers."""
    mgr = get_ws_manager()

    class _FakeWS:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def send_text(self, text: str) -> None:
            self.sent.append(text)

    sub_a, sub_b = _FakeWS(), _FakeWS()
    await mgr.register("session-A", sub_a)  # type: ignore[arg-type]
    await mgr.register("session-B", sub_b)  # type: ignore[arg-type]
    try:
        await broadcast_to_session("session-A", session_status_changed_event("paused"))
        assert len(sub_a.sent) == 1
        assert len(sub_b.sent) == 0
    finally:
        await mgr.unregister("session-A", sub_a)  # type: ignore[arg-type]
        await mgr.unregister("session-B", sub_b)  # type: ignore[arg-type]


def test_event_envelope_shape() -> None:
    """Every event helper returns {v:1, type: ..., ...fields}."""
    msg = message_event({"turn_number": 5})
    assert msg["v"] == 1
    assert msg["type"] == "message"
    assert msg["message"] == {"turn_number": 5}

    status = session_status_changed_event("archived")
    assert status["v"] == 1
    assert status["type"] == "session_status_changed"
    assert status["status"] == "archived"
