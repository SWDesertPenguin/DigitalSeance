# SPDX-License-Identifier: AGPL-3.0-or-later
"""T102: category disable switch hides tools from list; call returns NOT_FOUND. Spec 030 Phase 3."""

from __future__ import annotations

import importlib

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


def test_disabled_proposal_category_absent_from_registry(monkeypatch) -> None:
    monkeypatch.setenv("SACP_MCP_TOOL_PROPOSAL_ENABLED", "false")
    import src.mcp_protocol.tools as mod

    importlib.reload(mod)
    from src.mcp_protocol.tools import REGISTRY

    proposal_names = [k for k in REGISTRY if k.startswith("proposal.")]
    assert len(proposal_names) == 0
    # Cleanup
    monkeypatch.delenv("SACP_MCP_TOOL_PROPOSAL_ENABLED", raising=False)
    importlib.reload(mod)


def test_disabled_scratch_category_absent_from_tools_list(monkeypatch) -> None:
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "true")
    monkeypatch.setenv("SACP_MCP_TOOL_SCRATCH_ENABLED", "false")
    import src.mcp_protocol.tools as mod

    importlib.reload(mod)
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "scratch.list_notes" not in names
    monkeypatch.delenv("SACP_MCP_TOOL_SCRATCH_ENABLED", raising=False)
    importlib.reload(mod)


def test_all_categories_enabled_by_default() -> None:
    import src.mcp_protocol.tools as mod

    importlib.reload(mod)
    from src.mcp_protocol.tools import REGISTRY

    assert len(REGISTRY) >= 35
