# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP ping tests. Spec 030 Phase 2, FR-018 + T208."""

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


def test_ping_returns_success_envelope(enabled_client) -> None:
    """ping method returns JSON-RPC 2.0 success with empty result."""
    resp = enabled_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "ping", "id": "ping-1"},
        headers={"Authorization": "Bearer test-token-ping"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "ping-1"
    assert "result" in body
    assert "error" not in body


def test_ping_echoes_request_id(enabled_client) -> None:
    """ping echoes the request id back in the response."""
    resp = enabled_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "ping", "id": "custom-id-42"},
        headers={"Authorization": "Bearer test-token-ping2"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == "custom-id-42"


def test_ping_without_bearer_returns_401(enabled_client) -> None:
    """ping without Authorization header returns 401."""
    resp = enabled_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "ping", "id": "noauth"},
    )
    assert resp.status_code == 401
