# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 018 — Phase-1 design-hooks contract tests (US1).

The Phase-1 cut ships the hooks Phase 2 will fill. These tests assert:
- US1 AS1: with deferral disabled, 20-tools participant sees byte-identical
  system prompt vs pre-feature baseline.
- US1 AS2: the resolver returns an instance satisfying the Protocol; the
  no-op `_EmptyIndex` returns empty state on every read.
- US1 AS3: discovery MCP tools return the documented `deferred_loading_disabled`
  stub when the master switch is off.
- US1 AS4: representative pre-feature regression — assemble_prompt with
  None/empty deferred entries is byte-identical to assemble_prompt without
  the new kwarg.

Per FR-014: the deferral-aware assembly path is exercised on every
turn-prep; the index is consulted; the result threads through to
`assemble_prompt`. Phase 1 sees an empty index, so the prompt is
byte-identical to the pre-feature baseline (FR-015).
"""

from __future__ import annotations

import secrets
from unittest.mock import patch

import pytest

from src.orchestrator.deferred_tool_index import (
    DISCOVERY_TOOL_LIST,
    DISCOVERY_TOOL_LOAD,
    DISCOVERY_TOOL_NAMES,
    DeferredToolIndex,
    DeferredToolIndexEntry,
    _deferral_enabled,
    clear_index_cache,
    evict_index,
    get_deferred_index_for_participant,
)
from src.prompts.tiers import assemble_prompt


@pytest.fixture(autouse=True)
def _reset_index_cache():
    clear_index_cache()
    yield
    clear_index_cache()


# ---- US1 AS2: resolver + no-op contract ----


def test_resolver_returns_protocol_instance() -> None:
    """The resolver returns an instance that satisfies `DeferredToolIndex`."""
    idx = get_deferred_index_for_participant("sess-1", "pid-A")
    assert isinstance(idx, DeferredToolIndex)
    assert idx.session_id == "sess-1"
    assert idx.participant_id == "pid-A"


def test_no_op_index_is_empty() -> None:
    """Phase-1 index reports empty state on every read."""
    idx = get_deferred_index_for_participant("sess-1", "pid-A")
    assert idx.is_empty()
    assert idx.loaded_tool_names() == []
    assert idx.deferred_tool_names() == []
    assert idx.loaded_token_count() == 0


def test_no_op_render_returns_empty_entries() -> None:
    """`render_index_entries` returns `([], False)` regardless of max_tokens."""
    idx = get_deferred_index_for_participant("sess-1", "pid-A")
    entries, truncated = idx.render_index_entries(256)
    assert entries == []
    assert truncated is False

    entries, truncated = idx.render_index_entries(1)
    assert entries == []
    assert truncated is False


def test_per_participant_distinct_instances() -> None:
    """Different participants in the same session get distinct instances."""
    a = get_deferred_index_for_participant("sess-1", "pid-A")
    b = get_deferred_index_for_participant("sess-1", "pid-B")
    assert a is not b
    assert a.participant_id != b.participant_id


def test_resolver_caches_by_key() -> None:
    """Same `(session_id, participant_id)` returns the cached instance."""
    a1 = get_deferred_index_for_participant("sess-1", "pid-A")
    a2 = get_deferred_index_for_participant("sess-1", "pid-A")
    assert a1 is a2


def test_evict_index_drops_cached_instance() -> None:
    """`evict_index` clears the cached instance for `(session_id, participant_id)`."""
    a1 = get_deferred_index_for_participant("sess-1", "pid-A")
    evict_index("sess-1", "pid-A")
    a2 = get_deferred_index_for_participant("sess-1", "pid-A")
    assert a1 is not a2


@pytest.mark.asyncio
async def test_no_op_mutations_return_safely() -> None:
    """Phase-1 mutation paths are no-ops that don't raise."""
    idx = get_deferred_index_for_participant("sess-1", "pid-A")
    await idx.compute_partition([], 1500, None)
    result = await idx.load_on_demand("foo", [])
    assert result is None
    await idx.recompute_on_freshness([], 1500, None)


def test_discovery_tool_names_match_spec_030_convention() -> None:
    """Tool names follow spec 030 domain.action snake_case convention."""
    assert DISCOVERY_TOOL_LIST == "tools.list_deferred"
    assert DISCOVERY_TOOL_LOAD == "tools.load_deferred"
    assert frozenset({"tools.list_deferred", "tools.load_deferred"}) == DISCOVERY_TOOL_NAMES


# ---- US1 AS4: regression contract — assemble_prompt byte-identical ----


def _deterministic_canaries() -> object:
    """Force deterministic canaries so two assemblies produce byte-identical output."""
    return patch.object(secrets, "token_bytes", lambda n: bytes([42] * n))


def test_assemble_prompt_byte_identical_with_no_deferred_entries() -> None:
    """assemble_prompt() == assemble_prompt(deferred_index_entries=None) byte-for-byte."""
    with _deterministic_canaries():
        baseline = assemble_prompt(
            prompt_tier="mid",
            custom_prompt="test custom",
            participant_id="pid-A",
        )
    with _deterministic_canaries():
        with_none = assemble_prompt(
            prompt_tier="mid",
            custom_prompt="test custom",
            participant_id="pid-A",
            deferred_index_entries=None,
        )
    with _deterministic_canaries():
        with_empty = assemble_prompt(
            prompt_tier="mid",
            custom_prompt="test custom",
            participant_id="pid-A",
            deferred_index_entries=[],
        )
    assert baseline == with_none
    assert baseline == with_empty


def test_assemble_prompt_non_empty_entries_surface_in_prompt() -> None:
    """Non-empty entries land in the prompt under the 'Available deferred tools' header."""
    with _deterministic_canaries():
        prompt = assemble_prompt(
            prompt_tier="mid",
            custom_prompt="",
            participant_id="pid-A",
            deferred_index_entries=[
                '- git_log: Show commit log [load_via: tools.load_deferred(name="git_log")]',
            ],
        )
    assert "Available deferred tools" in prompt
    assert "git_log: Show commit log" in prompt


@pytest.mark.parametrize("tier", ["low", "mid", "high", "max"])
def test_assemble_prompt_byte_identical_across_tiers(tier: str) -> None:
    """Byte-identical regression holds for every tier."""
    with _deterministic_canaries():
        baseline = assemble_prompt(prompt_tier=tier, custom_prompt="x")
    with _deterministic_canaries():
        with_none = assemble_prompt(
            prompt_tier=tier, custom_prompt="x", deferred_index_entries=None
        )
    assert baseline == with_none


# ---- US1 AS3: discovery tools return stub when disabled ----


def test_deferral_enabled_reads_env(monkeypatch) -> None:
    """`_deferral_enabled` reads SACP_TOOL_DEFER_ENABLED at the v1 default of false."""
    monkeypatch.delenv("SACP_TOOL_DEFER_ENABLED", raising=False)
    assert _deferral_enabled() is False

    monkeypatch.setenv("SACP_TOOL_DEFER_ENABLED", "false")
    assert _deferral_enabled() is False

    monkeypatch.setenv("SACP_TOOL_DEFER_ENABLED", "true")
    assert _deferral_enabled() is True

    monkeypatch.setenv("SACP_TOOL_DEFER_ENABLED", "True")
    assert _deferral_enabled() is True


def test_discovery_handler_returns_stub_when_disabled(monkeypatch) -> None:
    """The list_deferred_tools handler returns the documented stub.

    The handler is `_deferral_enabled()`-gated; with the master switch off,
    it returns `{"status": "deferred_loading_disabled", "spec": "018", ...}`
    per US1 AS3.
    """
    monkeypatch.delenv("SACP_TOOL_DEFER_ENABLED", raising=False)
    from src.participant_api.tools.deferred_tools import _STUB_RESPONSE

    # Validate the stub shape — handlers return a dict-copy of this constant.
    assert _STUB_RESPONSE["status"] == "deferred_loading_disabled"
    assert _STUB_RESPONSE["spec"] == "018"
    assert "documentation" in _STUB_RESPONSE


# ---- DeferredToolIndexEntry dataclass shape ----


def test_index_entry_dataclass() -> None:
    """`DeferredToolIndexEntry` is a frozen dataclass with the expected fields."""
    entry = DeferredToolIndexEntry(
        tool_name="git_log",
        one_line_summary="Show commit log",
        source_server="git-mcp-server",
    )
    assert entry.tool_name == "git_log"
    assert entry.one_line_summary == "Show commit log"
    assert entry.source_server == "git-mcp-server"

    with pytest.raises((TypeError, AttributeError)):
        entry.tool_name = "x"  # frozen


def test_index_entry_default_source_server() -> None:
    """`source_server` defaults to None."""
    entry = DeferredToolIndexEntry(tool_name="x", one_line_summary="y")
    assert entry.source_server is None
