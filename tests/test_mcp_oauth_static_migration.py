# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test static bearer migration prompt on MCP endpoint. Spec 030 Phase 4 FR-083."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.dispatcher import check_static_bearer_migration


def _make_ctx(pool=None) -> CallerContext:
    return CallerContext(
        participant_id="part001",
        session_id=None,
        scopes=frozenset({"participant"}),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="req001",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=pool,
        encryption_key=None,
    )


@pytest.mark.asyncio
async def test_no_pool_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("SACP_OAUTH_ENABLED", "true")
    ctx = _make_ctx(pool=None)
    result = await check_static_bearer_migration("static_token", ctx)
    assert result is None


@pytest.mark.asyncio
async def test_oauth_disabled_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("SACP_OAUTH_ENABLED", "false")
    ctx = _make_ctx(pool=MagicMock())
    result = await check_static_bearer_migration("static_token", ctx)
    assert result is None


@pytest.mark.asyncio
async def test_first_prompt_sets_prompted_at_and_returns_dict(monkeypatch) -> None:
    monkeypatch.setenv("SACP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("SACP_OAUTH_STATIC_TOKEN_GRACE_DAYS", "90")

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"mcp_oauth_migration_prompted_at": None})
    mock_conn.execute = AsyncMock(return_value=None)
    mock_ctx_mgr = MagicMock()
    mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_ctx_mgr)

    ctx = _make_ctx(pool=mock_pool)
    result = await check_static_bearer_migration("static_token", ctx)
    assert result is not None
    assert result.get("migration_prompt") is True
