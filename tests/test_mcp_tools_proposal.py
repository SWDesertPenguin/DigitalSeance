# SPDX-License-Identifier: AGPL-3.0-or-later
"""Proposal tool happy-path + error-path tests. Spec 030 Phase 3, T092."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.session import MCPSessionStore
from src.mcp_protocol.tools.proposal_tools import (
    _dispatch_proposal_cast_vote,
    _dispatch_proposal_close,
    _dispatch_proposal_create,
    _dispatch_proposal_list,
)
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


def _make_ctx(db_pool=None, session_id="sid-test") -> CallerContext:
    return CallerContext(
        participant_id="pid-test",
        session_id=session_id,
        scopes=frozenset({"participant"}),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="req-1",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=db_pool,
    )


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


@pytest.mark.asyncio
async def test_proposal_create_no_pool() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_proposal_create(
        ctx, {"session_id": "s1", "topic": "T", "position": "P"}
    )
    assert result.get("error") == "SACP_E_INTERNAL"


@pytest.mark.asyncio
async def test_proposal_create_missing_fields() -> None:
    from unittest.mock import MagicMock

    ctx = _make_ctx(db_pool=MagicMock())
    result = await _dispatch_proposal_create(ctx, {"session_id": "s1"})
    assert result.get("error") == "SACP_E_VALIDATION"


@pytest.mark.asyncio
async def test_proposal_cast_vote_no_pool() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_proposal_cast_vote(ctx, {"proposal_id": "p1", "vote": "accept"})
    assert result.get("error") == "SACP_E_INTERNAL"


@pytest.mark.asyncio
async def test_proposal_close_no_pool() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_proposal_close(ctx, {"proposal_id": "p1"})
    assert result.get("error") == "SACP_E_INTERNAL"


@pytest.mark.asyncio
async def test_proposal_list_no_pool_returns_empty() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_proposal_list(ctx, {})
    assert result == {"proposals": [], "next_cursor": None}


# --- Real DB tests ---


@pytest.mark.asyncio
async def test_proposal_create_real_db(pool) -> None:
    """proposal.create returns a proposal id when given a real pool."""
    from src.repositories.session_repo import SessionRepository

    session, facilitator, branch = await SessionRepository(pool).create_session(
        "Proposal-Test",
        facilitator_display_name="Facil",
        facilitator_provider="human",
        facilitator_model="human",
        facilitator_model_tier="n/a",
        facilitator_model_family="human",
        facilitator_context_window=0,
    )
    ctx = CallerContext(
        participant_id=facilitator.id,
        session_id=session.id,
        scopes=frozenset({"participant"}),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="req-prop",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=pool,
    )
    result = await _dispatch_proposal_create(
        ctx,
        {
            "session_id": session.id,
            "topic": "Use consensus",
            "position": "All decisions by consensus",
        },
    )
    assert "error" not in result, f"Unexpected error: {result}"
    assert "id" in result
    assert result["id"]


@pytest.mark.asyncio
async def test_proposal_close_real_db(pool) -> None:
    """proposal.close resolves an existing proposal."""
    from src.repositories.session_repo import SessionRepository

    session, facilitator, branch = await SessionRepository(pool).create_session(
        "Close-Test",
        facilitator_display_name="Facil",
        facilitator_provider="human",
        facilitator_model="human",
        facilitator_model_tier="n/a",
        facilitator_model_family="human",
        facilitator_context_window=0,
    )
    ctx = CallerContext(
        participant_id=facilitator.id,
        session_id=session.id,
        scopes=frozenset({"facilitator"}),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="req-close",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=pool,
    )
    created = await _dispatch_proposal_create(
        ctx,
        {"session_id": session.id, "topic": "Close me", "position": "Yes"},
    )
    assert "id" in created
    proposal_id = created["id"]

    result = await _dispatch_proposal_close(ctx, {"proposal_id": proposal_id, "status": "accepted"})
    assert "error" not in result, f"Unexpected error: {result}"
    assert result.get("resolution") == "accepted"
