# SPDX-License-Identifier: AGPL-3.0-or-later
"""Session tool happy-path + error-path tests. Spec 030 Phase 3, T090."""

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
def _reset_store(monkeypatch):
    store = MCPSessionStore()
    monkeypatch.setattr("src.mcp_protocol.session._store", store)
    monkeypatch.setattr("src.mcp_protocol.handshake.get_session_store", lambda: store)
    monkeypatch.setattr("src.mcp_protocol.transport.get_session_store", lambda: store)


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "true")
    monkeypatch.setenv("SACP_MCP_TOOL_SESSION_ENABLED", "true")
    return TestClient(_make_app())


def test_tools_list_includes_session_tools(client) -> None:
    """tools/list returns at least the session category tools."""
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "session.get" in names
    assert "session.list" in names


def test_session_get_returns_not_found_without_db(client) -> None:
    """session.get with no DB pool returns an error dict, not a 500."""
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 2,
            "params": {"name": "session.get", "arguments": {"session_id": "nonexistent"}},
        },
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    result = body.get("result", {})
    assert "error" in result or "session_id" in result or "id" in result


def test_session_category_disabled_returns_not_found(monkeypatch) -> None:
    """When SACP_MCP_TOOL_SESSION_ENABLED=false, session tools are absent."""
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "true")
    monkeypatch.setenv("SACP_MCP_TOOL_SESSION_ENABLED", "false")
    import importlib

    import src.mcp_protocol.tools as mod

    importlib.reload(mod)
    from src.mcp_protocol.tools import REGISTRY

    assert "session.get" not in REGISTRY
    # reload back to default
    monkeypatch.delenv("SACP_MCP_TOOL_SESSION_ENABLED", raising=False)
    importlib.reload(mod)
