# SPDX-License-Identifier: AGPL-3.0-or-later
"""T106: per-tool action codes emitted correctly. Spec 030 Phase 3."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.dispatcher import dispatch


class _FakeConn:
    def __init__(self):
        self.executed = []

    async def execute(self, sql, *args):
        self.executed.append(args)

    async def fetchrow(self, sql, *args):
        return None

    async def fetch(self, sql, *args):
        return []

    async def fetchval(self, sql, *args):
        return None


class _FakePool:
    def __init__(self):
        self.conn = _FakeConn()

    def acquire(self):
        return _PoolCtx(self.conn)


class _PoolCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        pass


def _ctx(pool) -> CallerContext:
    return CallerContext(
        participant_id="p1",
        session_id="s1",
        scopes=frozenset({"any"}),
        is_ai_caller=False,
        mcp_session_id=None,
        request_id="r1",
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=None,
        db_pool=pool,
    )


@pytest.mark.asyncio
async def test_dispatch_emits_per_tool_action_code() -> None:
    """Successful dispatch inserts an audit row with action='mcp_tool_<name>'."""
    pool = _FakePool()
    ctx = _ctx(pool)
    result = await dispatch(ctx, "session.get", {"session_id": "s1"})
    assert isinstance(result, dict)
    # Check that at least one execute call used the per-tool action code
    executed_actions = [args[2] for args in pool.conn.executed if len(args) > 2]
    assert any(
        a == "mcp_tool_session.get" for a in executed_actions
    ), f"expected mcp_tool_session.get in {executed_actions}"
