# SPDX-License-Identifier: AGPL-3.0-or-later
"""Admin tool happy-path + error-path tests. Spec 030 Phase 3, T099."""

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


def test_tools_list_includes_admin_tools(client) -> None:
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "admin.list_sessions" in names
    assert "admin.list_participants" in names
    assert "admin.transfer_facilitator" in names
    assert "admin.archive_session" in names


def test_admin_transfer_facilitator_not_ai_accessible() -> None:
    from src.mcp_protocol.tools import REGISTRY

    entry = REGISTRY["admin.transfer_facilitator"]
    assert not entry.definition.aiAccessible
    assert entry.definition.idempotencySupported


def test_admin_list_sessions_without_db(client) -> None:
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 2,
            "params": {"name": "admin.list_sessions", "arguments": {}},
        },
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code in (200, 400)
    body = resp.json()
    result = body.get("result", {})
    assert "sessions" in result or "error" in result or "error" in body
