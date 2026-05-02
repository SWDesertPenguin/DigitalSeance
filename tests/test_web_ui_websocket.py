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
from src.web_ui.session_store import get_session_store
from src.web_ui.websocket import (
    CLOSE_FORBIDDEN,
    CLOSE_TOO_MANY,
    CLOSE_UNAUTHENTICATED,
    WebSocketManager,
    broadcast_to_session,
    get_ws_manager,
)

_SECURE_KEY = Fernet.generate_key().decode()
_COOKIE_KEY = "test-cookie-key-with-at-least-thirty-two-chars-of-entropy-xyz"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_ENCRYPTION_KEY", _SECURE_KEY)
    monkeypatch.setenv("SACP_WEB_UI_COOKIE_KEY", _COOKIE_KEY)
    monkeypatch.setenv("SACP_WEB_UI_INSECURE_COOKIES", "1")


def _app():  # type: ignore[no-untyped-def]
    from src.web_ui.app import create_web_app

    return create_web_app()


_GOOD_ORIGIN_HEADERS = {"origin": "http://testserver"}


def test_ws_rejects_missing_origin() -> None:
    """SR-004: upgrade without Origin header closes with 4403."""
    with (
        TestClient(_app()) as client,
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect("/ws/some-session") as ws,
    ):
        ws.receive_text()
    assert excinfo.value.code == CLOSE_FORBIDDEN


def test_ws_rejects_bad_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-004: upgrade with an Origin not in the allowlist closes with 4403."""
    monkeypatch.setenv("SACP_WEB_UI_ALLOWED_ORIGINS", "http://ok.example")
    with (
        TestClient(_app()) as client,
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect(
            "/ws/some-session", headers={"origin": "http://evil.example"}
        ) as ws,
    ):
        ws.receive_text()
    assert excinfo.value.code == CLOSE_FORBIDDEN


def test_ws_rejects_missing_cookie() -> None:
    """WebSocket without sacp_ui_token closes with 4401 (Origin is valid)."""
    with (
        TestClient(_app()) as client,
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect("/ws/some-session", headers=_GOOD_ORIGIN_HEADERS) as ws,
    ):
        ws.receive_text()
    assert excinfo.value.code == CLOSE_UNAUTHENTICATED


@pytest.mark.asyncio
async def test_ws_rejects_wrong_session_cookie() -> None:
    """Cookie bound to session A cannot open a WS for session B."""
    store = get_session_store()
    sid = await store.create("pid-1", "session-A", "tok")
    try:
        cookie = _make_cookie_value(sid)
        with TestClient(_app()) as client:
            client.cookies.set("sacp_ui_token", cookie)
            with (
                pytest.raises(WebSocketDisconnect) as excinfo,
                client.websocket_connect("/ws/session-B", headers=_GOOD_ORIGIN_HEADERS) as ws,
            ):
                ws.receive_text()
        assert excinfo.value.code == CLOSE_FORBIDDEN
    finally:
        await store.delete(sid)


@pytest.mark.asyncio
async def test_ws_rejects_unknown_sid() -> None:
    """A signed cookie carrying an sid not in the store closes 4401.

    Audit H-02 / M-08: cookie signature still passes (it's an opaque
    token signed with the cookie key), but server-side state has no
    binding for it — so the WS upgrade fails closed exactly as if the
    cookie had been missing entirely.
    """
    cookie = _make_cookie_value("never-issued-sid")
    with TestClient(_app()) as client:
        client.cookies.set("sacp_ui_token", cookie)
        with (
            pytest.raises(WebSocketDisconnect) as excinfo,
            client.websocket_connect("/ws/anything", headers=_GOOD_ORIGIN_HEADERS) as ws,
        ):
            ws.receive_text()
    assert excinfo.value.code == CLOSE_UNAUTHENTICATED


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


@pytest.mark.asyncio
async def test_per_ip_cap_blocks_excess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit H-03: at the cap, reserve_ip_slot returns False so the endpoint
    will close 4429 instead of accepting a runaway connection from one host."""
    monkeypatch.setenv("SACP_WS_MAX_CONNECTIONS_PER_IP", "2")
    mgr = WebSocketManager()
    assert await mgr.reserve_ip_slot("10.0.0.1") is True
    assert await mgr.reserve_ip_slot("10.0.0.1") is True
    assert await mgr.reserve_ip_slot("10.0.0.1") is False
    # Other IPs are unaffected.
    assert await mgr.reserve_ip_slot("10.0.0.2") is True


@pytest.mark.asyncio
async def test_unregister_releases_ip_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Counter is pruned on unregister so a closed connection frees its slot."""
    monkeypatch.setenv("SACP_WS_MAX_CONNECTIONS_PER_IP", "1")
    mgr = WebSocketManager()

    class _FakeWS:
        async def send_text(self, text: str) -> None: ...

    ws = _FakeWS()
    assert await mgr.reserve_ip_slot("10.0.0.3") is True
    await mgr.register("sid", ws, client_ip="10.0.0.3")  # type: ignore[arg-type]
    # Cap=1 → second reserve fails while the first connection is open.
    assert await mgr.reserve_ip_slot("10.0.0.3") is False
    await mgr.unregister("sid", ws)  # type: ignore[arg-type]
    assert mgr.ip_count("10.0.0.3") == 0
    # Slot is reusable after unregister.
    assert await mgr.reserve_ip_slot("10.0.0.3") is True


def test_close_too_many_constant_matches_contract() -> None:
    """websocket-events.md pins 4429 as the per-IP-cap close code."""
    assert CLOSE_TOO_MANY == 4429
