# SPDX-License-Identifier: AGPL-3.0-or-later
"""Review-gate tool happy-path + error-path tests. Spec 030 Phase 3, T093."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.session import MCPSessionStore
from src.mcp_protocol.tools.review_gate_tools import (
    _dispatch_review_gate_approve,
    _dispatch_review_gate_edit_and_approve,
    _dispatch_review_gate_list_pending,
    _dispatch_review_gate_reject,
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
        scopes=frozenset({"facilitator"}),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="req-1",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=db_pool,
    )


def test_tools_list_includes_review_gate_tools(client) -> None:
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "review_gate.list_pending" in names
    assert "review_gate.approve" in names
    assert "review_gate.reject" in names
    assert "review_gate.edit_and_approve" in names


def test_review_gate_list_pending_without_db(client) -> None:
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 2,
            "params": {"name": "review_gate.list_pending", "arguments": {}},
        },
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code in (200, 400)
    body = resp.json()
    assert "result" in body or "error" in body


def test_review_gate_tools_not_ai_accessible() -> None:
    from src.mcp_protocol.tools import REGISTRY

    for name in ("review_gate.approve", "review_gate.reject", "review_gate.edit_and_approve"):
        entry = REGISTRY[name]
        assert not entry.definition.aiAccessible, f"{name} should not be AI-accessible"


@pytest.mark.asyncio
async def test_review_gate_approve_no_pool() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_review_gate_approve(ctx, {"draft_id": "d1"})
    assert result.get("error") == "SACP_E_INTERNAL"


@pytest.mark.asyncio
async def test_review_gate_reject_no_pool() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_review_gate_reject(ctx, {"draft_id": "d1"})
    assert result.get("error") == "SACP_E_INTERNAL"


@pytest.mark.asyncio
async def test_review_gate_edit_and_approve_no_pool() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_review_gate_edit_and_approve(
        ctx, {"draft_id": "d1", "edited_content": "new text"}
    )
    assert result.get("error") == "SACP_E_INTERNAL"


@pytest.mark.asyncio
async def test_review_gate_approve_missing_draft_id() -> None:
    from unittest.mock import MagicMock

    ctx = _make_ctx(db_pool=MagicMock())
    result = await _dispatch_review_gate_approve(ctx, {})
    assert result.get("error") == "SACP_E_VALIDATION"


@pytest.mark.asyncio
async def test_review_gate_list_pending_no_pool_returns_empty() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_review_gate_list_pending(ctx, {})
    assert result == {"drafts": [], "next_cursor": None}


# --- Real DB tests ---


@pytest.mark.asyncio
async def test_review_gate_approve_real_db(pool) -> None:
    """review_gate.approve resolves a pending draft in the DB."""
    from src.repositories.review_gate_repo import ReviewGateRepository
    from src.repositories.session_repo import SessionRepository

    session, facilitator, branch = await SessionRepository(pool).create_session(
        "RG-Test",
        facilitator_display_name="Facil",
        facilitator_provider="human",
        facilitator_model="human",
        facilitator_model_tier="n/a",
        facilitator_model_family="human",
        facilitator_context_window=0,
    )
    rg_repo = ReviewGateRepository(pool)
    draft = await rg_repo.create_draft(
        session_id=session.id,
        participant_id=facilitator.id,
        turn_number=1,
        draft_content="Draft response",
        context_summary="test context",
    )
    ctx = CallerContext(
        participant_id=facilitator.id,
        session_id=session.id,
        scopes=frozenset({"facilitator"}),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="req-rg-approve",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=pool,
    )
    result = await _dispatch_review_gate_approve(ctx, {"draft_id": draft.id})
    assert "error" not in result, f"Unexpected error: {result}"
    assert result.get("status") == "approved"
    assert "id" in result


@pytest.mark.asyncio
async def test_review_gate_edit_and_approve_real_db(pool) -> None:
    """review_gate.edit_and_approve sets edited_content and resolves the draft."""
    from src.repositories.review_gate_repo import ReviewGateRepository
    from src.repositories.session_repo import SessionRepository

    session, facilitator, branch = await SessionRepository(pool).create_session(
        "RG-Edit-Test",
        facilitator_display_name="Facil",
        facilitator_provider="human",
        facilitator_model="human",
        facilitator_model_tier="n/a",
        facilitator_model_family="human",
        facilitator_context_window=0,
    )
    rg_repo = ReviewGateRepository(pool)
    draft = await rg_repo.create_draft(
        session_id=session.id,
        participant_id=facilitator.id,
        turn_number=2,
        draft_content="Original draft",
        context_summary="test",
    )
    ctx = CallerContext(
        participant_id=facilitator.id,
        session_id=session.id,
        scopes=frozenset({"facilitator"}),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="req-rg-edit",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=pool,
    )
    result = await _dispatch_review_gate_edit_and_approve(
        ctx, {"draft_id": draft.id, "edited_content": "Edited version"}
    )
    assert "error" not in result, f"Unexpected error: {result}"
    assert result.get("status") == "edited_and_approved"
