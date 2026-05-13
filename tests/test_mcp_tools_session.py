# SPDX-License-Identifier: AGPL-3.0-or-later
"""Session tool happy-path + error-path tests. Spec 030 Phase 3, T090."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.session import MCPSessionStore
from src.mcp_protocol.tools.session_tools import (
    _dispatch_session_archive,
    _dispatch_session_create,
    _dispatch_session_delete,
    _dispatch_session_list,
    _dispatch_session_update_settings,
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
    monkeypatch.setenv("SACP_MCP_TOOL_SESSION_ENABLED", "true")
    return TestClient(_make_app())


def _make_ctx(db_pool=None) -> CallerContext:
    return CallerContext(
        participant_id="pid-test",
        session_id="sid-test",
        scopes=frozenset({"facilitator"}),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="req-1",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=db_pool,
    )


def test_tools_list_includes_session_tools(client) -> None:
    """tools/list returns at least the session category tools."""
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "session.get" in names
    assert "session.list" in names


def test_session_get_returns_not_found_without_db(client) -> None:
    """session.get with no DB pool returns an error dict, not a 500."""
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 2,
            "params": {"name": "session.get", "arguments": {"session_id": "nonexistent"}},
        },
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    result = body.get("result", {})
    assert "error" in result or "session_id" in result or "id" in result


def test_session_category_disabled_returns_not_found(monkeypatch) -> None:
    """When SACP_MCP_TOOL_SESSION_ENABLED=false, session tools are absent."""
    monkeypatch.setenv("SACP_MCP_PROTOCOL_ENABLED", "true")
    monkeypatch.setenv("SACP_MCP_TOOL_SESSION_ENABLED", "false")
    import importlib

    import src.mcp_protocol.tools as mod

    importlib.reload(mod)
    from src.mcp_protocol.tools import REGISTRY

    assert "session.get" not in REGISTRY
    # reload back to default
    monkeypatch.delenv("SACP_MCP_TOOL_SESSION_ENABLED", raising=False)
    importlib.reload(mod)


@pytest.mark.asyncio
async def test_session_create_no_pool_returns_error() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_session_create(ctx, {"display_name": "TestFacil"})
    assert result.get("error") == "SACP_E_INTERNAL"
    assert result.get("reason") == "no_db_pool"


@pytest.mark.asyncio
async def test_session_create_with_mock_repo(monkeypatch) -> None:
    """session.create calls SessionRepository and returns session fields when repo succeeds."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    fake_session = SimpleNamespace(id="sess-abc", name="amber-wolf-1234", status="active")
    fake_facilitator = SimpleNamespace(id="fac-xyz")
    fake_branch = SimpleNamespace(id="main-sess-abc")

    mock_repo_instance = AsyncMock()
    mock_repo_instance.create_session.return_value = (fake_session, fake_facilitator, fake_branch)

    import src.repositories.session_repo as sr_mod

    monkeypatch.setattr(sr_mod, "SessionRepository", MagicMock(return_value=mock_repo_instance))

    ctx = _make_ctx(db_pool=MagicMock())
    result = await _dispatch_session_create(ctx, {"display_name": "Alice"})

    assert "error" not in result, f"Unexpected error: {result}"
    assert result["session_id"] == "sess-abc"


@pytest.mark.asyncio
async def test_session_delete_no_pool_returns_error() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_session_delete(ctx, {"session_id": "s1"})
    assert result.get("error") == "SACP_E_INTERNAL"


@pytest.mark.asyncio
async def test_session_delete_missing_session_id() -> None:
    mock_pool = MagicMock()
    ctx = _make_ctx(db_pool=mock_pool)
    ctx = CallerContext(
        participant_id="pid",
        session_id=None,
        scopes=frozenset(),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="r",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=mock_pool,
    )
    result = await _dispatch_session_delete(ctx, {})
    assert result.get("error") == "SACP_E_VALIDATION"


@pytest.mark.asyncio
async def test_session_archive_no_pool_returns_error() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_session_archive(ctx, {"session_id": "s1"})
    assert result.get("error") == "SACP_E_INTERNAL"


@pytest.mark.asyncio
async def test_session_list_no_pool_returns_empty() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_session_list(ctx, {})
    assert result == {"sessions": [], "next_cursor": None}


@pytest.mark.asyncio
async def test_session_update_settings_no_pool() -> None:
    ctx = _make_ctx(db_pool=None)
    result = await _dispatch_session_update_settings(ctx, {"session_id": "s1", "name": "new"})
    assert result.get("error") == "SACP_E_INTERNAL"


# --- Real DB tests (skipped when Postgres is unavailable) ---


@pytest.mark.asyncio
async def test_session_create_real_db(pool) -> None:
    """session.create returns session_id when given a real pool."""
    ctx = CallerContext(
        participant_id="pid-real",
        session_id=None,
        scopes=frozenset({"facilitator"}),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="req-real",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=pool,
    )
    result = await _dispatch_session_create(ctx, {"display_name": "RealFacil"})
    assert "error" not in result, f"Unexpected error: {result}"
    assert "session_id" in result
    assert result["session_id"]


@pytest.mark.asyncio
async def test_session_delete_real_db(pool) -> None:
    """session.delete removes a session that was just created."""
    ctx = CallerContext(
        participant_id="pid-del",
        session_id=None,
        scopes=frozenset({"facilitator"}),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="req-del",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=pool,
    )
    created = await _dispatch_session_create(ctx, {"display_name": "ToDelete"})
    assert "session_id" in created
    sid = created["session_id"]

    ctx_del = CallerContext(
        participant_id="pid-del",
        session_id=sid,
        scopes=frozenset({"facilitator"}),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="req-del2",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=pool,
    )
    result = await _dispatch_session_delete(ctx_del, {"session_id": sid})
    assert "error" not in result
    assert result["status"] == "deleted"
