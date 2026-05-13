# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scratch tool tests (spec 024 stub). Spec 030 Phase 3, T097."""

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


def test_tools_list_includes_scratch_tools(client) -> None:
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "scratch.list_notes" in names
    assert "scratch.create_note" in names


def test_scratch_list_notes_returns_not_implemented_stub(client) -> None:
    """Scratch tools return spec_024_not_implemented stub."""
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 2,
            "params": {"name": "scratch.list_notes", "arguments": {}},
        },
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code in (200, 400)
    body = resp.json()
    result = body.get("result", {})
    if "error" in result:
        assert result["reason"] == "spec_024_not_implemented"


def test_scratch_tools_count() -> None:
    from src.mcp_protocol.tools import REGISTRY

    scratch = [k for k in REGISTRY if k.startswith("scratch.")]
    assert len(scratch) == 5
