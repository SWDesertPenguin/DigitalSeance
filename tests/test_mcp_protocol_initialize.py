# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP initialize handler tests. Spec 030 Phase 2, FR-014 + FR-015 + FR-020 + FR-022."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.session import MCPSessionStore
from src.mcp_protocol.transport import mcp_router


def _make_app(enabled: bool = True) -> FastAPI:
    app = FastAPI()
    if enabled:
        app.include_router(mcp_router)
    return app


def _init_body(protocol_version: str = "2025-11-25") -> dict:
    return {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "capabilities": {"roots": {"listChanged": False}, "sampling": {}},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
        "id": "init-1",
    }


@pytest.fixture(autouse=True)
def _reset_session_store(monkeypatch) -> None:
    """Start each test with a clean session store."""
    store = MCPSessionStore()
    monkeypatch.setattr("src.mcp_protocol.session._store", store)
    monkeypatch.setattr("src.mcp_protocol.handshake.get_session_store", lambda: store)
    monkeypatch.setattr("src.mcp_protocol.transport.get_session_store", lambda: store)


@pytest.fixture()
def enabled_env(monkeypatch) -> None:
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "true")


def test_initialize_happy_path(enabled_env) -> None:
    """Valid initialize request returns 200 + Mcp-Session-Id header + capabilities."""
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json=_init_body(),
        headers={"Authorization": "Bearer test-token-abc123"},
    )
    assert resp.status_code == 200
    assert "mcp-session-id" in resp.headers
    sid = resp.headers["mcp-session-id"]
    assert len(sid) == 64
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "init-1"
    result = body["result"]
    assert result["protocolVersion"] == "2025-11-25"
    assert "tools" in result["capabilities"]
    assert "logging" in result["capabilities"]
    assert "prompts" not in result["capabilities"]
    assert "resources" not in result["capabilities"]
    assert result["serverInfo"]["name"] == "SACP"


@pytest.mark.parametrize("client_version", ["2025-03-26", "2025-06-18", "2025-11-25"])
def test_initialize_echoes_supported_version(enabled_env, client_version: str) -> None:
    """Each supported protocolVersion is echoed back in the result."""
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json=_init_body(client_version),
        headers={"Authorization": "Bearer test-token-abc123"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"]["protocolVersion"] == client_version


def test_initialize_unsupported_version_returns_preferred(enabled_env) -> None:
    """Unknown protocolVersion: server returns its preferred version, no error.

    Per MCP lifecycle spec, the client decides whether to proceed with the
    server's response. No graceful-downgrade error.
    """
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json=_init_body("2024-01-01"),
        headers={"Authorization": "Bearer test-token-abc123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "error" not in body
    assert body["result"]["protocolVersion"] == "2025-11-25"


def test_initialize_missing_protocol_version_returns_preferred(enabled_env) -> None:
    """Omitted protocolVersion is treated as 'no preference' and gets the preferred."""
    app = _make_app()
    client = TestClient(app)
    body = _init_body()
    del body["params"]["protocolVersion"]
    resp = client.post(
        "/mcp",
        json=body,
        headers={"Authorization": "Bearer test-token-abc123"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"]["protocolVersion"] == "2025-11-25"


def test_initialize_malformed_protocol_version_errors(enabled_env) -> None:
    """A non-string protocolVersion is a structural error returning -32602."""
    app = _make_app()
    client = TestClient(app)
    body = _init_body()
    body["params"]["protocolVersion"] = 12345
    resp = client.post(
        "/mcp",
        json=body,
        headers={"Authorization": "Bearer test-token-abc123"},
    )
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["code"] == -32602
    assert "supported" in err["data"]


def test_initialize_missing_bearer() -> None:
    """Missing Authorization header returns 401."""
    app = _make_app()
    client = TestClient(app)

    import os

    os.environ["SACP_MCP_PROTOCOL_ENABLED"] = "true"
    try:
        resp = client.post("/mcp", json=_init_body())
    finally:
        del os.environ["SACP_MCP_PROTOCOL_ENABLED"]

    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == -32001


def test_initialize_invalid_bearer_format(enabled_env) -> None:
    """Non-Bearer Authorization header returns 401."""
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json=_init_body(),
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert resp.status_code == 401
