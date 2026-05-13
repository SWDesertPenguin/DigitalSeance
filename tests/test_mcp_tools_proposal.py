# SPDX-License-Identifier: AGPL-3.0-or-later
"""Proposal tool happy-path + error-path tests. Spec 030 Phase 3, T092."""

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


def test_tools_list_includes_proposal_tools(client) -> None:
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "proposal.create" in names
    assert "proposal.cast_vote" in names
    assert "proposal.list" in names
    assert "proposal.close" in names


def test_proposal_list_without_db(client) -> None:
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 2,
            "params": {"name": "proposal.list", "arguments": {}},
        },
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    result = body.get("result", {})
    assert "proposals" in result or "error" in result


def test_proposal_close_requires_facilitator_scope(client) -> None:
    """proposal.close requires facilitator scope."""
    from src.mcp_protocol.tools import REGISTRY

    entry = REGISTRY.get("proposal.close")
    assert entry is not None
    assert entry.definition.scopeRequirement == "facilitator"
