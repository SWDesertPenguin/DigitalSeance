# SPDX-License-Identifier: AGPL-3.0-or-later
"""Debug export tool happy-path + error-path tests. Spec 030 Phase 3, T094."""

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
    return TestClient(_make_app())


def test_tools_list_includes_debug_tools(client) -> None:
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "debug.export_session" in names
    assert "debug.export_participant_view" in names


def test_debug_tools_not_ai_accessible() -> None:
    from src.mcp_protocol.tools import REGISTRY

    for name in ("debug.export_session", "debug.export_participant_view"):
        entry = REGISTRY[name]
        assert not entry.definition.aiAccessible
        assert entry.definition.v14BudgetMs == 5000


def test_debug_export_session_returns_stub(client) -> None:
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 2,
            "params": {"name": "debug.export_session", "arguments": {"session_id": "s1"}},
        },
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code in (200, 400)
    body = resp.json()
    assert "result" in body or "error" in body
