# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP error code tests. Spec 030 Phase 2, FR-019 + SC-021."""

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
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "true")
    return TestClient(_make_app())


def test_parse_error_on_bad_json(client) -> None:
    """Malformed body returns -32700 parse error."""
    resp = client.post(
        "/mcp",
        content=b"not json{{{",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code in (400, 422)
    body = resp.json()
    if "error" in body:
        assert body["error"]["code"] == -32700


def test_method_not_found_unknown_method(client) -> None:
    """Unknown method returns -32601."""
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "no_such_method", "id": "x1"},
        headers={"Authorization": "Bearer test-token-abc"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == -32601


def test_prompts_list_returns_method_not_found(client) -> None:
    """prompts/list returns -32601 per FR-032 / SC-021."""
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "prompts/list", "id": "p1"},
        headers={"Authorization": "Bearer test-token-abc"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == -32601


def test_resources_list_returns_method_not_found(client) -> None:
    """resources/list returns -32601 per FR-032 / SC-021."""
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "resources/list", "id": "r1"},
        headers={"Authorization": "Bearer test-token-abc"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == -32601


def _do_initialize(client: TestClient) -> str:
    """Helper: run initialize and return the Mcp-Session-Id."""
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "tc", "version": "1"},
            },
            "id": "i1",
        },
        headers={"Authorization": "Bearer test-bearer-xyz"},
    )
    assert resp.status_code == 200
    return resp.headers["mcp-session-id"]


def test_tools_call_unknown_tool(client) -> None:
    """tools/call with unknown tool name returns -32601."""
    sid = _do_initialize(client)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "no.such.tool", "arguments": {}},
            "id": "tc1",
        },
        headers={"Authorization": "Bearer test-bearer-xyz", "Mcp-Session-Id": sid},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == -32601
