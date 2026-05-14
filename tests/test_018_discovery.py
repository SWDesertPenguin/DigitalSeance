# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 018 — Phase-2 discovery capability tests (US3).

`tools.load_deferred` promotes a deferred tool into the loaded
subset sticky-within-session, with LRU eviction when promotion
exceeds budget. Per-participant scoping is enforced by construction:
the dispatcher resolves the caller's identity from auth and routes
the index lookup through that identity.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.orchestrator.deferred_tool_index import (
    DISCOVERY_TOOL_LIST,
    DISCOVERY_TOOL_LOAD,
    DISCOVERY_TOOL_NAMES,
    ToolDefinition,
    _LiveIndex,
    clear_index_cache,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_index_cache()
    yield
    clear_index_cache()


@pytest.fixture(autouse=True)
def _deferral_on(monkeypatch):
    monkeypatch.setenv("SACP_TOOL_DEFER_ENABLED", "true")
    yield


class _CharCountTokenizer:
    def count_tokens(self, content: str) -> int:
        return max(len(content) // 4, 1) if content else 0

    def get_tokenizer_name(self) -> str:
        return "test:char_count"


def _make_tool(name: str, schema_bytes: int = 600) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"tool {name}",
        input_schema={"_pad": "x" * schema_bytes},
    )


def _participant_loaded(idx: _LiveIndex) -> list[str]:
    return [n for n in idx.loaded_tool_names() if n not in DISCOVERY_TOOL_NAMES]


# ── US3 AS1: load_deferred promotes the tool ────────────────────────


@pytest.mark.asyncio
async def test_us3_as1_load_promotes_tool() -> None:
    """Calling load_on_demand for a deferred tool moves it to loaded."""
    tools = [_make_tool(f"t_{i}") for i in range(6)]
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition(tools, budget=500, tokenizer=_CharCountTokenizer())
    deferred = idx.deferred_tool_names()
    assert deferred, "test setup expects some deferred tools"
    target = deferred[0]
    result = await idx.load_on_demand(target, all_tools=tools)
    assert result is not None
    assert result.name == target
    assert idx.is_loaded(target)
    assert target not in idx.deferred_tool_names()


@pytest.mark.asyncio
async def test_load_unknown_tool_returns_none() -> None:
    """A name not in the registry returns None (handler converts to tool_not_found)."""
    tools = [_make_tool("t_1")]
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition(tools, budget=10_000, tokenizer=_CharCountTokenizer())
    result = await idx.load_on_demand("nonexistent", all_tools=tools)
    assert result is None


@pytest.mark.asyncio
async def test_load_already_loaded_tool_returns_definition() -> None:
    """A name already in the loaded subset returns the definition without churn."""
    tools = [_make_tool("t_1")]
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition(tools, budget=10_000, tokenizer=_CharCountTokenizer())
    assert idx.is_loaded("t_1")
    loaded_count_before = idx.loaded_token_count()
    result = await idx.load_on_demand("t_1", all_tools=tools)
    assert result is not None
    assert idx.is_loaded("t_1")
    assert idx.loaded_token_count() == loaded_count_before


# ── US3 AS3: LRU eviction when promotion exceeds budget ────────────


@pytest.mark.asyncio
async def test_us3_as3_lru_eviction_on_load(monkeypatch) -> None:
    """When promotion exceeds budget, LRU evicts the oldest loaded tool."""
    monkeypatch.setenv("SACP_TOOL_LOADED_TOKEN_BUDGET", "500")
    tools = [_make_tool(f"t_{i}") for i in range(6)]
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition(tools, budget=500, tokenizer=_CharCountTokenizer())
    loaded_before = _participant_loaded(idx)
    deferred_before = idx.deferred_tool_names()
    assert loaded_before, "test setup expects some loaded"
    assert deferred_before, "test setup expects some deferred"
    target = deferred_before[0]
    await idx.load_on_demand(target, all_tools=tools)
    # The promoted tool is now in loaded; some prior-loaded tool was evicted.
    assert target in _participant_loaded(idx)
    evicted = set(loaded_before) - set(_participant_loaded(idx))
    assert evicted, (
        f"expected at least one LRU eviction at budget=500; "
        f"loaded_before={loaded_before} loaded_after={_participant_loaded(idx)}"
    )
    # The evicted tool is now in deferred.
    for e in evicted:
        assert e in idx.deferred_tool_names()


@pytest.mark.asyncio
async def test_audit_emissions_on_load_with_eviction(monkeypatch) -> None:
    """A budget-exceeding load emits paired tool_loaded_on_demand + tool_re_deferred rows."""
    monkeypatch.setenv("SACP_TOOL_LOADED_TOKEN_BUDGET", "500")
    fake_conn = AsyncMock()
    fake_conn.fetchrow = AsyncMock(return_value={"id": "fac-1"})
    fake_conn.execute = AsyncMock()
    fake_pool = _FakePool(fake_conn)
    tools = [_make_tool(f"t_{i}") for i in range(6)]
    idx = _LiveIndex("sess-1", "pid-A", pool=fake_pool)
    await idx.compute_partition(tools, budget=500, tokenizer=_CharCountTokenizer())
    fake_conn.execute.reset_mock()

    target = idx.deferred_tool_names()[0]
    await idx.load_on_demand(target, all_tools=tools)

    actions = [call.args[3] for call in fake_conn.execute.await_args_list]
    assert "tool_loaded_on_demand" in actions
    assert "tool_re_deferred" in actions


@pytest.mark.asyncio
async def test_audit_emission_without_eviction(monkeypatch) -> None:
    """A load that fits under budget emits only the load row, no re_deferred."""
    fake_conn = AsyncMock()
    fake_conn.fetchrow = AsyncMock(return_value={"id": "fac-1"})
    fake_conn.execute = AsyncMock()
    fake_pool = _FakePool(fake_conn)
    # First, partition with a low budget so some tools defer.
    monkeypatch.setenv("SACP_TOOL_LOADED_TOKEN_BUDGET", "500")
    tools = [_make_tool(f"t_{i}") for i in range(5)]
    idx = _LiveIndex("sess-1", "pid-A", pool=fake_pool)
    await idx.compute_partition(tools, budget=500, tokenizer=_CharCountTokenizer())
    # Now raise the env budget so load can promote without eviction.
    monkeypatch.setenv("SACP_TOOL_LOADED_TOKEN_BUDGET", "100000")
    fake_conn.execute.reset_mock()

    target = idx.deferred_tool_names()[0]
    await idx.load_on_demand(target, all_tools=tools)

    actions = [call.args[3] for call in fake_conn.execute.await_args_list]
    assert "tool_loaded_on_demand" in actions
    assert "tool_re_deferred" not in actions


@pytest.mark.asyncio
async def test_loaded_on_demand_payload_sets_prompt_cache_invalidated(monkeypatch) -> None:
    """The audit payload always sets prompt_cache_invalidated=true per FR-009."""
    import json as _json

    monkeypatch.setenv("SACP_TOOL_LOADED_TOKEN_BUDGET", "500")
    fake_conn = AsyncMock()
    fake_conn.fetchrow = AsyncMock(return_value={"id": "fac-1"})
    fake_conn.execute = AsyncMock()
    fake_pool = _FakePool(fake_conn)
    tools = [_make_tool(f"t_{i}") for i in range(5)]
    idx = _LiveIndex("sess-1", "pid-A", pool=fake_pool)
    await idx.compute_partition(tools, budget=500, tokenizer=_CharCountTokenizer())
    fake_conn.execute.reset_mock()

    target = idx.deferred_tool_names()[0]
    await idx.load_on_demand(target, all_tools=tools)

    load_call = next(
        call
        for call in fake_conn.execute.await_args_list
        if call.args[3] == "tool_loaded_on_demand"
    )
    payload = _json.loads(load_call.args[6])
    assert payload["prompt_cache_invalidated"] is True
    assert payload["tool_name"] == target


# ── Discovery tools never eligible for eviction ─────────────────────


@pytest.mark.asyncio
async def test_discovery_tools_never_evicted(monkeypatch) -> None:
    """Even when budget exhausts, the two discovery tools survive LRU."""
    monkeypatch.setenv("SACP_TOOL_LOADED_TOKEN_BUDGET", "200")
    # Single participant tool plus a huge tool to force eviction.
    real_tool = _make_tool("real_tool", schema_bytes=100)
    big_tool = _make_tool("big_tool", schema_bytes=10_000)
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition([real_tool, big_tool], budget=200, tokenizer=_CharCountTokenizer())
    # real_tool fits (small); big_tool defers (huge).
    assert "real_tool" in _participant_loaded(idx)
    assert "big_tool" in idx.deferred_tool_names()
    # Force a load of big_tool that should evict real_tool to fit.
    await idx.load_on_demand("big_tool", all_tools=[real_tool, big_tool])
    loaded = set(idx.loaded_tool_names())
    # The two discovery tools survive every LRU eviction round (FR-011).
    assert DISCOVERY_TOOL_LIST in loaded
    assert DISCOVERY_TOOL_LOAD in loaded


# ── helpers ─────────────────────────────────────────────────────────


class _FakePoolContext:
    def __init__(self, conn) -> None:
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakePool:
    def __init__(self, conn) -> None:
        self._conn = conn
        self.acquire_count = 0

    def acquire(self):
        self.acquire_count += 1
        return _FakePoolContext(self._conn)
