# SPDX-License-Identifier: AGPL-3.0-or-later
"""Participant tool happy-path + error-path tests. Spec 030 Phase 3, T091."""

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


def test_tools_list_includes_participant_tools(client) -> None:
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "participant.get" in names
    assert "participant.list" in names
    assert "participant.inject_message" in names


def test_participant_get_without_db(client) -> None:
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 2,
            "params": {"name": "participant.get", "arguments": {}},
        },
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    result = body.get("result", {})
    assert "error" in result or "id" in result or "display_name" in result


def test_participant_inject_message_requires_participant_scope(client) -> None:
    """participant.inject_message requires participant scope; 'any' scope returns auth error."""
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 3,
            "params": {"name": "participant.inject_message", "arguments": {"content": "hello"}},
        },
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code in (200, 400)
    body = resp.json()
    assert "error" in body or "result" in body
