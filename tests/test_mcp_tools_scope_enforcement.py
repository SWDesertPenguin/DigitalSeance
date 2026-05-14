# SPDX-License-Identifier: AGPL-3.0-or-later
"""T104: parameterized scope + AI-accessibility enforcement. Spec 030 Phase 3."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.dispatcher import DispatchError, dispatch


def _ctx(scopes: frozenset[str], is_ai: bool = False) -> CallerContext:
    return CallerContext(
        participant_id="p1",
        session_id=None,
        scopes=scopes,
        is_ai_caller=is_ai,
        mcp_session_id=None,
        request_id="r1",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=None,
    )


@pytest.mark.asyncio
async def test_facilitator_only_tool_blocked_for_any_scope() -> None:
    ctx = _ctx(frozenset({"any"}))
    with pytest.raises(DispatchError) as exc_info:
        await dispatch(ctx, "session.list", {})
    assert exc_info.value.data["sacp_error_code"] == "SACP_E_FORBIDDEN"


@pytest.mark.asyncio
async def test_facilitator_tool_accessible_with_facilitator_scope() -> None:
    ctx = _ctx(frozenset({"facilitator"}))
    result = await dispatch(ctx, "session.list", {})
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_any_scope_tool_accessible_without_auth() -> None:
    ctx = _ctx(frozenset({"any"}))
    result = await dispatch(ctx, "session.get", {})
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_ai_caller_blocked_from_non_ai_accessible_tool() -> None:
    ctx = _ctx(frozenset({"facilitator"}), is_ai=True)
    with pytest.raises(DispatchError) as exc_info:
        await dispatch(ctx, "session.list", {})
    assert exc_info.value.data["sacp_error_code"] == "SACP_E_FORBIDDEN"


@pytest.mark.asyncio
async def test_ai_caller_allowed_on_ai_accessible_tool() -> None:
    ctx = _ctx(frozenset({"any"}), is_ai=True)
    result = await dispatch(ctx, "session.get", {})
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_unknown_tool_returns_not_found() -> None:
    ctx = _ctx(frozenset({"facilitator"}))
    with pytest.raises(DispatchError) as exc_info:
        await dispatch(ctx, "nonexistent.tool", {})
    assert exc_info.value.data["sacp_error_code"] == "SACP_E_NOT_FOUND"
