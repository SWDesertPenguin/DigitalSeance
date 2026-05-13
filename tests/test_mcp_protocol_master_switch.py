# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP master switch tests. Spec 030 Phase 2, SC-016 + FR-025."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.transport import mcp_router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(mcp_router)
    return app


def test_mcp_returns_404_when_switch_off(monkeypatch) -> None:
    """/mcp returns 404 when SACP_MCP_PROTOCOL_ENABLED=false."""
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "false")
    client = TestClient(_make_app())
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "initialize", "id": "x"},
    )
    assert resp.status_code == 404


def test_mcp_returns_404_when_switch_unset() -> None:
    """/mcp returns 404 when SACP_MCP_PROTOCOL_ENABLED is not set."""
    import os

    saved = os.environ.pop("SACP_MCP_PROTOCOL_ENABLED", None)
    try:
        client = TestClient(_make_app())
        resp = client.post("/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": "y"})
        assert resp.status_code == 404
    finally:
        if saved is not None:
            os.environ["SACP_MCP_PROTOCOL_ENABLED"] = saved


def test_mcp_accessible_when_switch_on(monkeypatch) -> None:
    """/mcp is accessible when SACP_MCP_PROTOCOL_ENABLED=true."""
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "true")
    client = TestClient(_make_app())
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "ping", "id": "p"},
        headers={"Authorization": "Bearer abc"},
    )
    assert resp.status_code == 200


def test_participant_api_not_affected_by_switch(monkeypatch) -> None:
    """participant_api routes are independent of SACP_MCP_PROTOCOL_ENABLED."""
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "false")
    from src.participant_api.app import create_app

    app = create_app()
    paths = [r.path for r in app.routes]
    assert any("/tools/session" in p for p in paths)
    assert any("/tools/participant" in p for p in paths)
