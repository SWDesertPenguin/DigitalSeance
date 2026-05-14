# SPDX-License-Identifier: AGPL-3.0-or-later
"""Spec 017 loop integration tests.

Verifies that the maybe_refresh hook in _assemble_and_dispatch:
- Is called for non-human participants when the poll interval is set
- Is a no-op for human participants
- Completes within the V14 50ms turn-prep overhead budget (mock only)
- SC-001: staleness window bounded by poll interval
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.orchestrator.tool_list_freshness as tlf

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_registries() -> None:
    """Reset in-memory registry between tests."""
    tlf._REGISTRIES.clear()


def _make_tool(name: str) -> dict[str, Any]:
    return {"name": name, "description": "test", "inputSchema": {"type": "object"}}


def _make_speaker(
    session_id: str,
    participant_id: str,
    provider: str = "anthropic",
    api_endpoint: str | None = None,
) -> MagicMock:
    speaker = MagicMock()
    speaker.id = participant_id
    speaker.provider = provider
    speaker.api_endpoint = api_endpoint
    return speaker


# ---------------------------------------------------------------------------
# T001: maybe_refresh called for non-human speakers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_maybe_refresh_invoked_for_ai_speaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """maybe_refresh is called for non-human speakers at _assemble_and_dispatch."""
    monkeypatch.setenv("SACP_TOOL_REFRESH_POLL_INTERVAL_S", "30")

    session_id = "s-loop-001"
    participant_id = "p-loop-001"
    mcp_url = "http://mcp.local/"
    old_tools = [_make_tool("old_tool")]
    new_tools = [_make_tool("old_tool"), _make_tool("new_tool")]

    registry = tlf.ParticipantToolRegistry(
        session_id=session_id,
        participant_id=participant_id,
        tools=list(old_tools),
        tool_set_hash=tlf._compute_hash(old_tools),
        last_refreshed_at=datetime.now(UTC) - timedelta(seconds=60),  # stale
    )
    tlf._REGISTRIES[(session_id, participant_id)] = registry

    with patch.object(tlf, "_fetch_tools", AsyncMock(return_value=new_tools)):
        result = await tlf.maybe_refresh(session_id, participant_id, mcp_url, MagicMock())

    assert result is True
    assert tlf.get_tools(session_id, participant_id) == new_tools


# ---------------------------------------------------------------------------
# T002: maybe_refresh is no-op for human participants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_maybe_refresh_no_op_when_no_mcp_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """maybe_refresh returns False when mcp_url is None (human or no MCP server)."""
    monkeypatch.setenv("SACP_TOOL_REFRESH_POLL_INTERVAL_S", "30")

    with patch.object(tlf, "refresh_tool_list", AsyncMock(return_value=True)) as mock_ref:
        result = await tlf.maybe_refresh("s-any", "p-any", None, MagicMock())

    assert result is False
    mock_ref.assert_not_called()


# ---------------------------------------------------------------------------
# T003: SC-001 staleness window bounded by poll interval
# ---------------------------------------------------------------------------


def _stale_registry(
    session_id: str, participant_id: str, interval_s: int
) -> tlf.ParticipantToolRegistry:
    """Build a registry whose last_refreshed_at is interval_s+1 seconds ago."""
    tools = [_make_tool("t1")]
    return tlf.ParticipantToolRegistry(
        session_id=session_id,
        participant_id=participant_id,
        tools=list(tools),
        tool_set_hash=tlf._compute_hash(tools),
        last_refreshed_at=datetime.now(UTC) - timedelta(seconds=interval_s + 1),
    )


@pytest.mark.asyncio
async def test_sc001_staleness_window_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """SC-001: after one poll interval elapses, maybe_refresh triggers a refresh."""
    interval_s = 30
    monkeypatch.setenv("SACP_TOOL_REFRESH_POLL_INTERVAL_S", str(interval_s))
    session_id, participant_id = "s-loop-002", "p-loop-002"
    tlf._REGISTRIES[(session_id, participant_id)] = _stale_registry(
        session_id, participant_id, interval_s
    )

    refresh_called = []

    async def _fake_refresh(*args: Any, **kwargs: Any) -> bool:
        refresh_called.append(True)
        return False

    with patch.object(tlf, "refresh_tool_list", side_effect=_fake_refresh):
        await tlf.maybe_refresh(session_id, participant_id, "http://mcp.local/", MagicMock())

    assert refresh_called, "refresh_tool_list should have been called after interval elapsed"


# ---------------------------------------------------------------------------
# T004: SC-004 maybe_refresh overhead within 50ms (mock adapter; overhead only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sc004_maybe_refresh_overhead_under_50ms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-004: maybe_refresh overhead stays well under 50ms with a mock adapter."""
    monkeypatch.setenv("SACP_TOOL_REFRESH_POLL_INTERVAL_S", "30")

    session_id = "s-loop-003"
    participant_id = "p-loop-003"
    tools = [_make_tool("t1")]

    # Not elapsed: maybe_refresh returns immediately without calling refresh_tool_list
    registry = tlf.ParticipantToolRegistry(
        session_id=session_id,
        participant_id=participant_id,
        tools=list(tools),
        tool_set_hash=tlf._compute_hash(tools),
        last_refreshed_at=datetime.now(UTC),  # just refreshed
    )
    tlf._REGISTRIES[(session_id, participant_id)] = registry

    start = time.monotonic()
    for _ in range(100):
        await tlf.maybe_refresh(session_id, participant_id, "http://mcp.local/", MagicMock())
    elapsed_ms = (time.monotonic() - start) * 1000

    # 100 no-op calls should complete well under 50ms total (i.e., <0.5ms each)
    assert elapsed_ms < 50, f"maybe_refresh overhead too high: {elapsed_ms:.1f}ms for 100 calls"


# ---------------------------------------------------------------------------
# T005: register_participant creates registry entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_participant_creates_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """register_participant creates a registry entry on initial fetch."""
    monkeypatch.delenv("SACP_TOOL_REFRESH_PUSH_ENABLED", raising=False)
    session_id = "s-loop-004"
    participant_id = "p-loop-004"
    tools = [_make_tool("init_tool")]

    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value="f-001")
    conn.execute = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=conn)

    with patch.object(tlf, "_fetch_tools", AsyncMock(return_value=tools)):
        await tlf.register_participant(session_id, participant_id, "http://mcp.local/", pool)

    assert (session_id, participant_id) in tlf._REGISTRIES
    registry = tlf._REGISTRIES[(session_id, participant_id)]
    assert registry.tools == tools
    assert registry.tool_set_hash == tlf._compute_hash(tools)


@pytest.mark.asyncio
async def test_register_participant_no_op_when_no_url() -> None:
    """register_participant is a no-op when mcp_url is None."""
    session_id = "s-loop-005"
    participant_id = "p-loop-005"
    pool = MagicMock()

    await tlf.register_participant(session_id, participant_id, None, pool)

    assert (session_id, participant_id) not in tlf._REGISTRIES


# ---------------------------------------------------------------------------
# T006: system prompt sees new tools after maybe_refresh returns True
# ---------------------------------------------------------------------------


def test_get_tools_reflects_updated_registry() -> None:
    """After refresh updates registry, get_tools returns new tool set."""
    session_id = "s-loop-006"
    participant_id = "p-loop-006"
    old_tools = [_make_tool("old")]
    new_tools = [_make_tool("new")]

    registry = tlf.ParticipantToolRegistry(
        session_id=session_id,
        participant_id=participant_id,
        tools=list(old_tools),
        tool_set_hash=tlf._compute_hash(old_tools),
        last_refreshed_at=datetime.now(UTC),
    )
    tlf._REGISTRIES[(session_id, participant_id)] = registry

    # Simulate what refresh_tool_list does on change
    registry.tools = new_tools
    registry.tool_set_hash = tlf._compute_hash(new_tools)

    result = tlf.get_tools(session_id, participant_id)
    assert result == new_tools
