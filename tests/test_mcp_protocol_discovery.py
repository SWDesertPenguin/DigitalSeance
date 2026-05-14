# SPDX-License-Identifier: AGPL-3.0-or-later
"""Discovery endpoint tests. Spec 030 Phase 2, FR-024 + SC-023."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.discovery import discovery_router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(discovery_router)
    return app


def test_discovery_enabled_shape(monkeypatch) -> None:
    """When switch is on, response includes enabled+true, protocol_version, endpoint_url."""
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "true")
    client = TestClient(_make_app())
    resp = client.get("/.well-known/mcp-server")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["protocol_version"] == "2025-11-25"
    assert "/mcp" in body["endpoint_url"]
    assert body["auth"]["scheme"] == "bearer"
    assert body["server"]["name"] == "SACP"


def test_discovery_disabled_shape(monkeypatch) -> None:
    """When switch is off, response includes enabled+false (SC-023)."""
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "false")
    client = TestClient(_make_app())
    resp = client.get("/.well-known/mcp-server")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["server"]["name"] == "SACP"
    assert "protocol_version" not in body


def test_discovery_defaults_to_disabled() -> None:
    """Unset SACP_MCP_PROTOCOL_ENABLED defaults to disabled."""
    import os

    saved = os.environ.pop("SACP_MCP_PROTOCOL_ENABLED", None)
    try:
        client = TestClient(_make_app())
        resp = client.get("/.well-known/mcp-server")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False
    finally:
        if saved is not None:
            os.environ["SACP_MCP_PROTOCOL_ENABLED"] = saved
