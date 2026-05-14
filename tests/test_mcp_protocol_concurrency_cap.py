# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP concurrent-session cap tests. Spec 030 Phase 2, SC-020 + FR-027."""

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


def _init_request(n: int) -> dict:
    return {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": f"client-{n}", "version": "1"},
        },
        "id": f"i{n}",
    }


def test_fourth_initialize_returns_503_when_cap_is_3(monkeypatch) -> None:
    """With cap=3, the fourth initialize returns 503 + Retry-After."""
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "true")
    monkeypatch.setenv("SACP_MCP_MAX_CONCURRENT_SESSIONS", "3")
    client = TestClient(_make_app())

    for i in range(3):
        resp = client.post(
            "/mcp",
            json=_init_request(i),
            headers={"Authorization": f"Bearer token-{i}"},
        )
        assert resp.status_code == 200, f"init {i} should succeed; got {resp.status_code}"

    resp = client.post(
        "/mcp",
        json=_init_request(99),
        headers={"Authorization": "Bearer token-99"},
    )
    assert resp.status_code == 503
    assert "retry-after" in resp.headers
    body = resp.json()
    assert body["error"]["code"] == -32003


def test_retry_after_header_present_on_503(monkeypatch) -> None:
    """503 response includes a numeric Retry-After value."""
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "true")
    monkeypatch.setenv("SACP_MCP_MAX_CONCURRENT_SESSIONS", "1")
    client = TestClient(_make_app())

    client.post(
        "/mcp",
        json=_init_request(0),
        headers={"Authorization": "Bearer token-first"},
    )

    resp = client.post(
        "/mcp",
        json=_init_request(1),
        headers={"Authorization": "Bearer token-second"},
    )
    assert resp.status_code == 503
    retry_after = resp.headers.get("retry-after", "")
    assert retry_after.isdigit(), f"Retry-After should be numeric, got {retry_after!r}"
