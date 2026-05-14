# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP JSON-RPC notification ack tests.

Notifications (requests with no `id`) MUST receive HTTP 202 with no body and
no JSON-RPC envelope. mcp-remote sends `notifications/initialized` immediately
after a successful `initialize` handshake; returning a JSON-RPC error envelope
breaks the handshake.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.session import MCPSessionStore
from src.mcp_protocol.transport import mcp_router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(mcp_router)
    return app


@pytest.fixture(autouse=True)
def _reset_session_store(monkeypatch) -> None:
    store = MCPSessionStore()
    monkeypatch.setattr("src.mcp_protocol.session._store", store)
    monkeypatch.setattr("src.mcp_protocol.handshake.get_session_store", lambda: store)
    monkeypatch.setattr("src.mcp_protocol.transport.get_session_store", lambda: store)


@pytest.fixture()
def enabled_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "true")
    return TestClient(_make_app())


def test_notifications_initialized_returns_202_no_body(enabled_client) -> None:
    resp = enabled_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={"Authorization": "Bearer test-token-notif"},
    )
    assert resp.status_code == 202
    assert resp.content == b""


def test_notifications_unknown_method_also_returns_202(enabled_client) -> None:
    """Unknown notification methods are silently ack'd, not error-responded."""
    resp = enabled_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/some-future-method"},
        headers={"Authorization": "Bearer test-token-notif2"},
    )
    assert resp.status_code == 202
    assert resp.content == b""


def test_notifications_without_bearer_still_returns_401(enabled_client) -> None:
    """Auth still required; notifications happen within an established session."""
    resp = enabled_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert resp.status_code == 401
