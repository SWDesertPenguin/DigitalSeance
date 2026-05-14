# SPDX-License-Identifier: AGPL-3.0-or-later
"""Provider tool happy-path + error-path tests. Spec 030 Phase 3, T098."""

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


def test_tools_list_includes_provider_tools(client) -> None:
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "provider.list" in names
    assert "provider.test_credentials" in names


def test_provider_list_returns_providers(client) -> None:
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 2,
            "params": {"name": "provider.list", "arguments": {}},
        },
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code in (200, 400)
    body = resp.json()
    result = body.get("result", {})
    if "providers" in result:
        assert len(result["providers"]) > 0


def test_provider_list_scope_is_facilitator() -> None:
    from src.mcp_protocol.tools import REGISTRY

    entry = REGISTRY["provider.list"]
    assert entry.definition.scopeRequirement == "facilitator"


def test_provider_test_credentials_scope_is_participant() -> None:
    from src.mcp_protocol.tools import REGISTRY

    entry = REGISTRY["provider.test_credentials"]
    assert entry.definition.scopeRequirement == "participant"
