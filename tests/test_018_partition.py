# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 018 — Phase-2 partition + recomputation tests (US2).

These tests exercise the `_LiveIndex` working partition logic, the
spec-017 freshness coordination, the per-participant scoping
guarantee, and the pathological-partition graceful-degradation
clarified at Session 2026-05-13.
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
    get_deferred_index_for_participant,
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
    """Token estimator: 1 token per 4 chars. Deterministic for tests."""

    def count_tokens(self, content: str) -> int:
        if not content:
            return 0
        return max(len(content) // 4, 1)

    def get_tokenizer_name(self) -> str:
        return "test:char_count"


class _FallbackTokenizer(_CharCountTokenizer):
    def get_tokenizer_name(self) -> str:
        return "default:cl100k"


def _make_tool(name: str, description: str = "", schema_bytes: int = 600) -> ToolDefinition:
    """Tool definition sized to ~150 tokens by default (large schema padding).

    At schema_bytes=600 the rendered schema string is ~620 chars + tiny header,
    which the char-count tokenizer estimates at ~155 tokens. Tests pick budgets
    that produce known loaded/deferred splits given that cost.
    """
    return ToolDefinition(
        name=name,
        description=description or f"tool {name}",
        input_schema={"_pad": "x" * schema_bytes},
    )


def _participant_loaded(idx: _LiveIndex) -> list[str]:
    """Loaded tool names with the two always-loaded discovery tools excluded."""
    return [n for n in idx.loaded_tool_names() if n not in DISCOVERY_TOOL_NAMES]


# ── US2 AS1: budget respected ───────────────────────────────────────


@pytest.mark.asyncio
async def test_us2_as1_partition_fits_budget() -> None:
    """20-tool participant with budget 500 — only some fit; rest defer."""
    tools = [_make_tool(f"tool_{i}") for i in range(20)]
    idx = _LiveIndex(session_id="sess-1", participant_id="pid-A")
    await idx.compute_partition(tools, budget=500, tokenizer=_CharCountTokenizer())
    assert idx.loaded_token_count() <= 500
    assert idx.loaded_token_count() > 0
    # All 20 participant tools appear in either loaded or deferred (discovery
    # tools are infrastructure overhead, excluded from this accounting).
    participant_loaded = _participant_loaded(idx)
    assert len(participant_loaded) + len(idx.deferred_tool_names()) == 20
    # Budget binds: at this cost, not all fit.
    assert len(idx.deferred_tool_names()) > 0


@pytest.mark.asyncio
async def test_us2_as1_partition_uses_registration_order() -> None:
    """Loaded subset is the first-N tools in input order (v1 policy)."""
    tools = [_make_tool(f"tool_{i:02d}") for i in range(10)]
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition(tools, budget=500, tokenizer=_CharCountTokenizer())
    loaded_participants = _participant_loaded(idx)
    # The loaded participants are the prefix of the input in registration order.
    expected_prefix = [f"tool_{i:02d}" for i in range(len(loaded_participants))]
    assert loaded_participants == expected_prefix


@pytest.mark.asyncio
async def test_us2_as1_all_tools_fit_under_budget() -> None:
    """When the full set fits, deferred is empty."""
    tools = [_make_tool(f"t_{i}", schema_bytes=50) for i in range(3)]
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition(tools, budget=10_000, tokenizer=_CharCountTokenizer())
    assert idx.deferred_tool_names() == []
    assert len(_participant_loaded(idx)) == 3


# ── US2 AS3: per-participant scoping ───────────────────────────────


@pytest.mark.asyncio
async def test_us2_as3_per_participant_independence() -> None:
    """Two participants compute partitions independently; A's state doesn't reach B."""
    tools_a = [_make_tool(f"a_{i}") for i in range(8)]
    tools_b = [_make_tool(f"b_{i}", schema_bytes=50) for i in range(3)]
    idx_a = _LiveIndex("sess-1", "pid-A")
    idx_b = _LiveIndex("sess-1", "pid-B")
    await idx_a.compute_partition(tools_a, budget=300, tokenizer=_CharCountTokenizer())
    await idx_b.compute_partition(tools_b, budget=10_000, tokenizer=_CharCountTokenizer())
    assert all(n.startswith("a_") for n in _participant_loaded(idx_a) + idx_a.deferred_tool_names())
    assert all(n.startswith("b_") for n in _participant_loaded(idx_b) + idx_b.deferred_tool_names())
    assert idx_b.deferred_tool_names() == []


@pytest.mark.asyncio
async def test_resolver_returns_live_index_when_enabled() -> None:
    """With SACP_TOOL_DEFER_ENABLED=true, resolver returns a _LiveIndex."""
    idx = get_deferred_index_for_participant("sess-1", "pid-A")
    assert isinstance(idx, _LiveIndex)


# ── US2 AS4: freshness coordination ─────────────────────────────────


@pytest.mark.asyncio
async def test_us2_as4_freshness_preserves_promoted_tools() -> None:
    """recompute_on_freshness keeps a previously-promoted tool in the loaded subset."""
    tools = [_make_tool(f"t_{i}") for i in range(10)]
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition(tools, budget=500, tokenizer=_CharCountTokenizer())
    deferred_before = idx.deferred_tool_names()
    assert deferred_before, "test setup expects some deferred"
    promoted_name = deferred_before[0]
    await idx.load_on_demand(promoted_name, all_tools=tools)
    assert idx.is_loaded(promoted_name)

    # Freshness refresh delivers the same list — promoted tool stays loaded.
    await idx.recompute_on_freshness(tools, budget=500, tokenizer=_CharCountTokenizer())
    assert idx.is_loaded(promoted_name), (
        f"promoted tool {promoted_name} dropped from loaded after freshness refresh; "
        f"loaded={idx.loaded_tool_names()}"
    )


@pytest.mark.asyncio
async def test_freshness_drops_removed_tools() -> None:
    """Tools removed from registry vanish from both subsets after freshness."""
    tools = [_make_tool(f"t_{i}") for i in range(6)]
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition(tools, budget=500, tokenizer=_CharCountTokenizer())
    new_tools = tools[:3]  # last 3 removed
    await idx.recompute_on_freshness(new_tools, budget=500, tokenizer=_CharCountTokenizer())
    all_names = _participant_loaded(idx) + idx.deferred_tool_names()
    assert set(all_names) == {"t_0", "t_1", "t_2"}


# ── Pathological partition ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_pathological_partition_single_tool_exceeds_budget() -> None:
    """When no real tool fits, pathological_partition=True; participant subset is empty.

    The two discovery tools always appear in `loaded_tool_names()` per FR-011 —
    they're infrastructure overhead, not subject to the partition budget. The
    pathological-partition signal lives in the participant-scoped accounting.
    """
    tool = _make_tool("huge", schema_bytes=10_000)
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition([tool], budget=100, tokenizer=_CharCountTokenizer())
    assert _participant_loaded(idx) == []
    assert idx.deferred_tool_names() == ["huge"]
    assert idx._state.pathological_partition is True  # noqa: SLF001
    # Discovery tools still surface in the loaded subset (FR-011).
    assert DISCOVERY_TOOL_LIST in idx.loaded_tool_names()
    assert DISCOVERY_TOOL_LOAD in idx.loaded_tool_names()


@pytest.mark.asyncio
async def test_tokenizer_fallback_used_flag(caplog) -> None:
    """Fallback tokenizer triggers a WARN log and sets the flag in state."""
    tools = [_make_tool("t_1")]
    idx = _LiveIndex("sess-1", "pid-A")
    import logging

    with caplog.at_level(logging.WARNING):
        await idx.compute_partition(tools, budget=1500, tokenizer=_FallbackTokenizer())
    assert idx._state.tokenizer_fallback_used is True  # noqa: SLF001
    assert any("tokenizer_fallback_used" in rec.message for rec in caplog.records), [
        r.message for r in caplog.records
    ]


# ── render_index_entries ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_render_index_entries_fits_max_tokens() -> None:
    tools = [_make_tool(f"t_{i}", description=f"description for tool {i}") for i in range(10)]
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition(tools, budget=500, tokenizer=_CharCountTokenizer())
    entries, truncated = idx.render_index_entries(max_tokens=2000)
    assert len(entries) >= 1
    for e in entries:
        assert "tools.load_deferred" in e


@pytest.mark.asyncio
async def test_render_index_entries_truncates_with_banner() -> None:
    """When the deferred set exceeds max_tokens, a pagination banner appends."""
    tools = [
        _make_tool(f"t_{i:02d}", description=f"longer description for tool {i:02d} " * 3)
        for i in range(30)
    ]
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition(tools, budget=500, tokenizer=_CharCountTokenizer())
    entries, truncated = idx.render_index_entries(max_tokens=32)
    assert truncated is True
    assert any("tools.list_deferred" in e for e in entries)


# ── Discovery tools always loaded (FR-011) ──────────────────────────


@pytest.mark.asyncio
async def test_discovery_tools_always_appear_in_loaded_even_pathological() -> None:
    """Even with the worst possible budget, the two discovery tools surface."""
    huge = _make_tool("huge", schema_bytes=10_000)
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition([huge], budget=10, tokenizer=_CharCountTokenizer())
    loaded = set(idx.loaded_tool_names())
    assert DISCOVERY_TOOL_LIST in loaded
    assert DISCOVERY_TOOL_LOAD in loaded


@pytest.mark.asyncio
async def test_discovery_tools_excluded_from_deferred() -> None:
    """If discovery tools appear in input, they never end up deferred."""
    list_tool = _make_tool(DISCOVERY_TOOL_LIST, schema_bytes=50)
    load_tool = _make_tool(DISCOVERY_TOOL_LOAD, schema_bytes=50)
    huge = _make_tool("huge", schema_bytes=10_000)
    idx = _LiveIndex("sess-1", "pid-A")
    await idx.compute_partition(
        [list_tool, huge, load_tool],
        budget=10,
        tokenizer=_CharCountTokenizer(),
    )
    assert DISCOVERY_TOOL_LIST not in idx.deferred_tool_names()
    assert DISCOVERY_TOOL_LOAD not in idx.deferred_tool_names()


# ── Audit emission via injected pool ────────────────────────────────


@pytest.mark.asyncio
async def test_partition_decided_audit_emitted() -> None:
    """compute_partition writes a tool_partition_decided row to the pool."""
    fake_conn = AsyncMock()
    fake_conn.fetchrow = AsyncMock(return_value={"id": "fac-1"})
    fake_conn.execute = AsyncMock()
    fake_pool = _FakePool(fake_conn)
    tools = [_make_tool("t_1")]
    idx = _LiveIndex("sess-1", "pid-A", pool=fake_pool)
    await idx.compute_partition(tools, budget=1500, tokenizer=_CharCountTokenizer())
    assert fake_pool.acquire_count >= 1
    assert fake_conn.execute.await_count == 1, fake_conn.execute.await_args_list
    args = fake_conn.execute.await_args.args
    # _INSERT_AUDIT_SQL is positional:
    # (sql, session_id, facilitator_id, action, target_id, prev, new)
    assert args[1] == "sess-1"
    assert args[3] == "tool_partition_decided"
    assert args[4] == "pid-A"
    import json as _json

    payload = _json.loads(args[6])
    assert payload["loaded_count"] == 1
    assert payload["selection_policy"] == "registration_order"


@pytest.mark.asyncio
async def test_freshness_audit_payload_marks_reason() -> None:
    """recompute_on_freshness audit row records reason=freshness_refresh."""
    fake_conn = AsyncMock()
    fake_conn.fetchrow = AsyncMock(return_value={"id": "fac-1"})
    fake_conn.execute = AsyncMock()
    fake_pool = _FakePool(fake_conn)
    tools = [_make_tool("t_1")]
    idx = _LiveIndex("sess-1", "pid-A", pool=fake_pool)
    await idx.compute_partition(tools, budget=1500, tokenizer=_CharCountTokenizer())
    fake_conn.execute.reset_mock()
    await idx.recompute_on_freshness(tools, budget=1500, tokenizer=_CharCountTokenizer())
    args = fake_conn.execute.await_args.args
    import json as _json

    payload = _json.loads(args[6])
    assert payload["reason"] == "freshness_refresh"


# ── helpers ─────────────────────────────────────────────────────────


class _FakePoolContext:
    def __init__(self, conn) -> None:
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakePool:
    """Test-only stand-in for asyncpg.Pool that yields a single shared conn."""

    def __init__(self, conn) -> None:
        self._conn = conn
        self.acquire_count = 0

    def acquire(self):
        self.acquire_count += 1
        return _FakePoolContext(self._conn)
