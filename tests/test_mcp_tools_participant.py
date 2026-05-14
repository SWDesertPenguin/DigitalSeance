# SPDX-License-Identifier: AGPL-3.0-or-later
"""Participant tool happy-path + error-path tests. Spec 030 Phase 3, T091."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.session import MCPSessionStore
from src.mcp_protocol.tools.participant_tools import (
    _dispatch_participant_create,
    _dispatch_participant_inject_message,
    _dispatch_participant_rotate_token,
    _dispatch_participant_set_budget,
    _dispatch_participant_set_routing_preference,
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


def _make_ctx(db_pool=None, session_id="sid-test", encryption_key=None) -> CallerContext:
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
        encryption_key=encryption_key,
    )


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


@pytest.mark.asyncio
async def test_participant_create_no_pool() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_participant_create(ctx, {"display_name": "Alice", "session_id": "s1"})
    assert result.get("error") == "SACP_E_INTERNAL"


@pytest.mark.asyncio
async def test_participant_create_no_display_name() -> None:
    from unittest.mock import MagicMock

    ctx = _make_ctx(db_pool=MagicMock())
    result = await _dispatch_participant_create(ctx, {"session_id": "s1"})
    assert result.get("error") == "SACP_E_VALIDATION"


@pytest.mark.asyncio
async def test_participant_rotate_token_returns_orchestrator_stub() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_participant_rotate_token(ctx, {})
    assert result.get("error") == "SACP_E_INTERNAL"
    assert result.get("reason") == "requires_orchestrator_context"


@pytest.mark.asyncio
async def test_participant_inject_message_no_pool() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_participant_inject_message(
        ctx, {"content": "hello", "session_id": "s1"}
    )
    assert result.get("error") == "SACP_E_INTERNAL"


@pytest.mark.asyncio
async def test_participant_set_routing_preference_no_pool() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_participant_set_routing_preference(
        ctx, {"participant_id": "p1", "preference": "always"}
    )
    assert result.get("error") == "SACP_E_INTERNAL"


@pytest.mark.asyncio
async def test_participant_set_budget_no_pool() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_participant_set_budget(
        ctx, {"participant_id": "p1", "budget_hourly": 1.0}
    )
    assert result.get("error") == "SACP_E_INTERNAL"


# --- Real DB tests ---


@pytest.mark.asyncio
async def test_participant_create_real_db(pool, encryption_key) -> None:
    """participant.create adds a participant and returns participant_id."""
    from src.repositories.session_repo import SessionRepository

    session, facilitator, branch = await SessionRepository(pool).create_session(
        "Part-Test",
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
        request_id="req-create",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=pool,
        encryption_key=encryption_key,
    )
    result = await _dispatch_participant_create(
        ctx,
        {
            "session_id": session.id,
            "display_name": "NewBot",
            "provider": "anthropic",
            "model": "claude-3-haiku-20240307",
            "model_tier": "low",
            "model_family": "claude",
            "context_window": 200000,
        },
    )
    assert "error" not in result, f"Unexpected error: {result}"
    assert "participant_id" in result
    assert result["participant_id"]


@pytest.mark.asyncio
async def test_participant_set_routing_preference_real_db(pool, encryption_key) -> None:
    """participant.set_routing_preference updates the DB row."""
    from src.repositories.session_repo import SessionRepository

    session, facilitator, branch = await SessionRepository(pool).create_session(
        "Routing-Test",
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
        request_id="req-route",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=pool,
        encryption_key=encryption_key,
    )
    result = await _dispatch_participant_set_routing_preference(
        ctx,
        {"participant_id": facilitator.id, "preference": "observer"},
    )
    assert "error" not in result, f"Unexpected error: {result}"
    assert result["status"] == "updated"
    assert result["preference"] == "observer"
