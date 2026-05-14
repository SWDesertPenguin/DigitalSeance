# SPDX-License-Identifier: AGPL-3.0-or-later
"""Spec 017 unit tests: per-participant tool-list freshness.

Covers the core tool_list_freshness module: hash invariants, refresh
logic, poll-interval gate, isolation, size cap, failure preservation,
and V16 validator exit behavior.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.orchestrator.tool_list_freshness as tlf
from src.config import validators

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_registries() -> None:
    """Reset in-memory registry between tests."""
    tlf._REGISTRIES.clear()


@pytest.fixture()
def mock_pool() -> MagicMock:
    """Minimal mock asyncpg pool for audit-row tests."""
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value="facilitator-001")
    conn.execute = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=conn)
    return pool


def _make_tool(name: str, description: str = "desc", schema: dict | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": schema or {"type": "object", "properties": {}},
    }


# ---------------------------------------------------------------------------
# T001: Hash is order-independent (FR-003)
# ---------------------------------------------------------------------------


def test_hash_order_independent() -> None:
    """Same tools in different order produce the same hash."""
    tools_a = [_make_tool("alpha"), _make_tool("beta"), _make_tool("gamma")]
    tools_b = [_make_tool("gamma"), _make_tool("alpha"), _make_tool("beta")]
    assert tlf._compute_hash(tools_a) == tlf._compute_hash(tools_b)


def test_hash_empty_list() -> None:
    """Empty tool list produces a stable hash."""
    h1 = tlf._compute_hash([])
    h2 = tlf._compute_hash([])
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_hash_different_tools_differ() -> None:
    """Different tool sets produce different hashes."""
    tools_a = [_make_tool("alpha")]
    tools_b = [_make_tool("beta")]
    assert tlf._compute_hash(tools_a) != tlf._compute_hash(tools_b)


# ---------------------------------------------------------------------------
# T002: Refresh detects change (FR-004)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_detects_change_returns_true(mock_pool: MagicMock) -> None:
    """refresh_tool_list returns True and emits audit row on hash change."""
    session_id = "s-001"
    participant_id = "p-001"
    old_tools = [_make_tool("tool_a"), _make_tool("tool_b")]
    new_tools = [_make_tool("tool_a")]  # tool_b removed

    registry = tlf.ParticipantToolRegistry(
        session_id=session_id,
        participant_id=participant_id,
        tools=old_tools,
        tool_set_hash=tlf._compute_hash(old_tools),
        last_refreshed_at=datetime.now(UTC),
    )
    tlf._REGISTRIES[(session_id, participant_id)] = registry

    with patch.object(tlf, "_fetch_tools", AsyncMock(return_value=new_tools)):
        changed = await tlf.refresh_tool_list(
            session_id, participant_id, "http://mcp.local/", mock_pool
        )

    assert changed is True
    assert registry.tool_set_hash == tlf._compute_hash(new_tools)
    assert registry.tools == new_tools
    # Audit row emitted
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    assert conn.execute.call_count >= 1


@pytest.mark.asyncio
async def test_refresh_no_change_returns_false(mock_pool: MagicMock) -> None:
    """refresh_tool_list returns False and emits no audit row when unchanged."""
    session_id = "s-002"
    participant_id = "p-002"
    tools = [_make_tool("tool_a")]

    registry = tlf.ParticipantToolRegistry(
        session_id=session_id,
        participant_id=participant_id,
        tools=tools,
        tool_set_hash=tlf._compute_hash(tools),
        last_refreshed_at=datetime.now(UTC),
    )
    tlf._REGISTRIES[(session_id, participant_id)] = registry

    with patch.object(tlf, "_fetch_tools", AsyncMock(return_value=list(tools))):
        changed = await tlf.refresh_tool_list(
            session_id, participant_id, "http://mcp.local/", mock_pool
        )

    assert changed is False
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    assert conn.execute.call_count == 0


# ---------------------------------------------------------------------------
# T003: Poll interval gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_maybe_refresh_no_op_if_interval_not_elapsed(
    monkeypatch: pytest.MonkeyPatch, mock_pool: MagicMock
) -> None:
    """maybe_refresh returns False without calling refresh if interval not elapsed."""
    monkeypatch.setenv("SACP_TOOL_REFRESH_POLL_INTERVAL_S", "60")
    session_id = "s-003"
    participant_id = "p-003"
    tools = [_make_tool("tool_a")]

    registry = tlf.ParticipantToolRegistry(
        session_id=session_id,
        participant_id=participant_id,
        tools=tools,
        tool_set_hash=tlf._compute_hash(tools),
        last_refreshed_at=datetime.now(UTC),  # just refreshed
    )
    tlf._REGISTRIES[(session_id, participant_id)] = registry

    with patch.object(tlf, "refresh_tool_list", AsyncMock(return_value=True)) as mock_ref:
        result = await tlf.maybe_refresh(session_id, participant_id, "http://mcp.local/", mock_pool)

    assert result is False
    mock_ref.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_refresh_calls_refresh_when_elapsed(
    monkeypatch: pytest.MonkeyPatch, mock_pool: MagicMock
) -> None:
    """maybe_refresh calls refresh_tool_list when interval has elapsed."""
    monkeypatch.setenv("SACP_TOOL_REFRESH_POLL_INTERVAL_S", "30")
    session_id = "s-004"
    participant_id = "p-004"
    tools = [_make_tool("tool_x")]

    registry = tlf.ParticipantToolRegistry(
        session_id=session_id,
        participant_id=participant_id,
        tools=tools,
        tool_set_hash=tlf._compute_hash(tools),
        last_refreshed_at=datetime.now(UTC) - timedelta(seconds=60),  # stale
    )
    tlf._REGISTRIES[(session_id, participant_id)] = registry

    with patch.object(tlf, "refresh_tool_list", AsyncMock(return_value=True)) as mock_ref:
        result = await tlf.maybe_refresh(session_id, participant_id, "http://mcp.local/", mock_pool)

    assert result is True
    mock_ref.assert_called_once()


# ---------------------------------------------------------------------------
# T004: Unset poll interval -> always no-op (SC-005)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_maybe_refresh_no_op_when_interval_unset(
    monkeypatch: pytest.MonkeyPatch, mock_pool: MagicMock
) -> None:
    """SC-005: maybe_refresh is a no-op when SACP_TOOL_REFRESH_POLL_INTERVAL_S unset."""
    monkeypatch.delenv("SACP_TOOL_REFRESH_POLL_INTERVAL_S", raising=False)
    session_id = "s-005"
    participant_id = "p-005"
    tools = [_make_tool("tool_y")]

    registry = tlf.ParticipantToolRegistry(
        session_id=session_id,
        participant_id=participant_id,
        tools=tools,
        tool_set_hash=tlf._compute_hash(tools),
        last_refreshed_at=datetime.now(UTC) - timedelta(days=1),  # very stale
    )
    tlf._REGISTRIES[(session_id, participant_id)] = registry

    with patch.object(tlf, "refresh_tool_list", AsyncMock(return_value=True)) as mock_ref:
        result = await tlf.maybe_refresh(session_id, participant_id, "http://mcp.local/", mock_pool)

    assert result is False
    mock_ref.assert_not_called()


# ---------------------------------------------------------------------------
# T005: FR-006 isolation — change for A has no effect on B (SC-003)
# ---------------------------------------------------------------------------


def _make_registry(session_id: str, pid: str, tools: list) -> tlf.ParticipantToolRegistry:
    return tlf.ParticipantToolRegistry(
        session_id=session_id,
        participant_id=pid,
        tools=list(tools),
        tool_set_hash=tlf._compute_hash(tools),
        last_refreshed_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_refresh_isolation_participant_b_unaffected(mock_pool: MagicMock) -> None:
    """SC-003: refresh for participant A does not affect participant B."""
    session_id = "s-006"
    tools_a = [_make_tool("tool_a")]
    tools_b = [_make_tool("tool_b")]
    new_tools_a = [_make_tool("tool_a"), _make_tool("tool_a2")]

    reg_a = _make_registry(session_id, "p-a", tools_a)
    reg_b = _make_registry(session_id, "p-b", tools_b)
    tlf._REGISTRIES[(session_id, "p-a")] = reg_a
    tlf._REGISTRIES[(session_id, "p-b")] = reg_b
    b_hash_before = reg_b.tool_set_hash

    with patch.object(tlf, "_fetch_tools", AsyncMock(return_value=new_tools_a)):
        await tlf.refresh_tool_list(session_id, "p-a", "http://mcp.local/", mock_pool)

    assert reg_b.tool_set_hash == b_hash_before
    assert reg_b.tools == tools_b


# ---------------------------------------------------------------------------
# T006: FR-010 size cap
# ---------------------------------------------------------------------------


def test_apply_size_cap_no_truncation() -> None:
    """Small list is not truncated."""
    tools = [_make_tool("t1"), _make_tool("t2")]
    result, truncated = tlf._apply_size_cap(tools, 65536)
    assert not truncated
    assert result == tools


def test_apply_size_cap_truncates() -> None:
    """List exceeding cap is truncated."""
    # Create tools that will exceed a tiny cap
    tools = [_make_tool(f"tool_{i}", "x" * 100) for i in range(20)]
    result, truncated = tlf._apply_size_cap(tools, 200)
    assert truncated
    assert len(result) < len(tools)
    assert len(json.dumps(result).encode()) <= 200


@pytest.mark.asyncio
async def test_refresh_emits_audit_on_truncation(
    monkeypatch: pytest.MonkeyPatch, mock_pool: MagicMock
) -> None:
    """FR-010: refresh emits audit row when tool list is truncated."""
    monkeypatch.setenv("SACP_TOOL_LIST_MAX_BYTES", "100")
    session_id = "s-007"
    participant_id = "p-007"
    old_tools: list = []
    big_tools = [_make_tool(f"tool_{i}", "x" * 50) for i in range(10)]

    registry = tlf.ParticipantToolRegistry(
        session_id=session_id,
        participant_id=participant_id,
        tools=old_tools,
        tool_set_hash=tlf._compute_hash(old_tools),
        last_refreshed_at=datetime.now(UTC),
    )
    tlf._REGISTRIES[(session_id, participant_id)] = registry

    with patch.object(tlf, "_fetch_tools", AsyncMock(return_value=big_tools)):
        await tlf.refresh_tool_list(session_id, participant_id, "http://mcp.local/", mock_pool)

    conn = mock_pool.acquire.return_value.__aenter__.return_value
    assert conn.execute.call_count >= 1
    # Audit row should have been written
    call_args = conn.execute.call_args_list[0][0]
    assert "tool_list_changed" in call_args


# ---------------------------------------------------------------------------
# T007: FR-011 failure preservation
# ---------------------------------------------------------------------------


def _assert_refresh_failed_audit(mock_pool: MagicMock) -> None:
    """Assert that exactly one refresh_failed audit row was emitted."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    assert conn.execute.call_count == 1
    assert "refresh_failed" in str(conn.execute.call_args_list[0])


@pytest.mark.asyncio
async def test_refresh_failure_preserves_old_tools(mock_pool: MagicMock) -> None:
    """FR-011: exception during refresh keeps old tools; audit refresh_failed emitted."""
    session_id = "s-008"
    participant_id = "p-008"
    old_tools = [_make_tool("important_tool")]

    registry = _make_registry(session_id, participant_id, old_tools)
    tlf._REGISTRIES[(session_id, participant_id)] = registry

    with patch.object(tlf, "_fetch_tools", AsyncMock(side_effect=OSError("connection refused"))):
        changed = await tlf.refresh_tool_list(
            session_id, participant_id, "http://mcp.local/", mock_pool
        )

    assert changed is False
    assert registry.tools == old_tools
    assert registry.consecutive_failures == 1
    _assert_refresh_failed_audit(mock_pool)


# ---------------------------------------------------------------------------
# T008: FR-014 — invalid env var exits (validator level)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected_failure",
    [
        ("10", True),  # below minimum 15
        ("3601", True),  # above maximum 3600
        ("abc", True),  # not integer
        ("30", False),  # valid
        ("", False),  # unset -> None -> valid
    ],
)
def test_validator_poll_interval(
    monkeypatch: pytest.MonkeyPatch, value: str, expected_failure: bool
) -> None:
    """FR-014: invalid SACP_TOOL_REFRESH_POLL_INTERVAL_S causes ValidationFailure."""
    if value:
        monkeypatch.setenv("SACP_TOOL_REFRESH_POLL_INTERVAL_S", value)
    else:
        monkeypatch.delenv("SACP_TOOL_REFRESH_POLL_INTERVAL_S", raising=False)
    result = validators.validate_sacp_tool_refresh_poll_interval_s()
    if expected_failure:
        assert result is not None
        assert result.var_name == "SACP_TOOL_REFRESH_POLL_INTERVAL_S"
    else:
        assert result is None


@pytest.mark.parametrize(
    "value,expected_failure",
    [
        ("0", True),  # below minimum 1
        ("31", True),  # above maximum 30
        ("bad", True),
        ("10", False),
    ],
)
def test_validator_refresh_timeout(
    monkeypatch: pytest.MonkeyPatch, value: str, expected_failure: bool
) -> None:
    monkeypatch.setenv("SACP_TOOL_REFRESH_TIMEOUT_S", value)
    result = validators.validate_sacp_tool_refresh_timeout_s()
    if expected_failure:
        assert result is not None
    else:
        assert result is None


@pytest.mark.parametrize(
    "value,expected_failure",
    [
        ("500", True),  # below 1024
        ("2097152", True),  # above 1048576
        ("65536", False),
    ],
)
def test_validator_max_bytes(
    monkeypatch: pytest.MonkeyPatch, value: str, expected_failure: bool
) -> None:
    monkeypatch.setenv("SACP_TOOL_LIST_MAX_BYTES", value)
    result = validators.validate_sacp_tool_list_max_bytes()
    if expected_failure:
        assert result is not None
    else:
        assert result is None


@pytest.mark.parametrize(
    "value,expected_failure",
    [
        ("yes", True),
        ("TRUE", False),
        ("false", False),
        ("1", False),
        ("0", False),
    ],
)
def test_validator_push_enabled(
    monkeypatch: pytest.MonkeyPatch, value: str, expected_failure: bool
) -> None:
    monkeypatch.setenv("SACP_TOOL_REFRESH_PUSH_ENABLED", value)
    result = validators.validate_sacp_tool_refresh_push_enabled()
    if expected_failure:
        assert result is not None
    else:
        assert result is None


# ---------------------------------------------------------------------------
# T009: get_tools returns correct list
# ---------------------------------------------------------------------------


def test_get_tools_no_registry() -> None:
    """get_tools returns empty list when no registry exists."""
    assert tlf.get_tools("s-missing", "p-missing") == []


def test_get_tools_returns_cached() -> None:
    """get_tools returns current cached tools."""
    session_id = "s-009"
    participant_id = "p-009"
    tools = [_make_tool("t1"), _make_tool("t2")]
    registry = tlf.ParticipantToolRegistry(
        session_id=session_id,
        participant_id=participant_id,
        tools=list(tools),
        tool_set_hash=tlf._compute_hash(tools),
        last_refreshed_at=datetime.now(UTC),
    )
    tlf._REGISTRIES[(session_id, participant_id)] = registry
    result = tlf.get_tools(session_id, participant_id)
    assert result == tools


# ---------------------------------------------------------------------------
# T010: evict_session removes all registries for session
# ---------------------------------------------------------------------------


def test_evict_session() -> None:
    """evict_session removes all (session_id, *) registries."""
    session_id = "s-010"
    for pid in ("p-a", "p-b", "p-c"):
        tlf._REGISTRIES[(session_id, pid)] = tlf.ParticipantToolRegistry(
            session_id=session_id, participant_id=pid
        )
    # Different session should survive
    tlf._REGISTRIES[("other-session", "p-x")] = tlf.ParticipantToolRegistry(
        session_id="other-session", participant_id="p-x"
    )

    tlf.evict_session(session_id)

    assert not any(k[0] == session_id for k in tlf._REGISTRIES)
    assert ("other-session", "p-x") in tlf._REGISTRIES


# ---------------------------------------------------------------------------
# T011: Diff logic
# ---------------------------------------------------------------------------


def test_diff_detects_added() -> None:
    old = [_make_tool("t1")]
    new = [_make_tool("t1"), _make_tool("t2")]
    changes = tlf._diff_tool_lists(old, new)
    kinds = [c[0] for c in changes]
    names = [c[1] for c in changes]
    assert "added" in kinds
    assert "t2" in names


def test_diff_detects_removed() -> None:
    old = [_make_tool("t1"), _make_tool("t2")]
    new = [_make_tool("t1")]
    changes = tlf._diff_tool_lists(old, new)
    kinds = [c[0] for c in changes]
    names = [c[1] for c in changes]
    assert "removed" in kinds
    assert "t2" in names


def test_diff_detects_description_changed() -> None:
    old = [_make_tool("t1", description="original")]
    new = [_make_tool("t1", description="updated")]
    changes = tlf._diff_tool_lists(old, new)
    assert any(c[0] == "description_changed" and c[1] == "t1" for c in changes)


def test_diff_detects_schema_changed() -> None:
    old = [_make_tool("t1", schema={"type": "object"})]
    new = [_make_tool("t1", schema={"type": "string"})]
    changes = tlf._diff_tool_lists(old, new)
    assert any(c[0] == "schema_changed" and c[1] == "t1" for c in changes)


def test_diff_reorder_no_change() -> None:
    """Reordered tool list produces no diff changes (hash is identical)."""
    tools = [_make_tool("alpha"), _make_tool("beta")]
    # No changes expected for same tools
    changes = tlf._diff_tool_lists(tools, [_make_tool("beta"), _make_tool("alpha")])
    assert changes == []
