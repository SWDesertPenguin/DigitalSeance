# Contract: DeferredToolIndex

**Branch**: `018-deferred-tool-loading` | **Date**: 2026-05-13

---

## Purpose

The `DeferredToolIndex` interface is the **stable contract Phase 2 fills in**. Phase 1 ships a no-op implementation (`_EmptyIndex`) that satisfies the interface and returns empty partition state for every operation. Phase 2 replaces the no-op with the working partition logic.

This contract MUST remain stable across the Phase-1 → Phase-2 transition. Callers in `src/orchestrator/context.py` and `src/mcp_server/tools/deferred_tools.py` consume the interface only — they do not import the implementation directly.

## Interface

```python
# src/orchestrator/deferred_tool_index.py

from __future__ import annotations
from typing import Protocol, runtime_checkable
from datetime import datetime

from src.api_bridge.tokenizer import TokenizerAdapter


@runtime_checkable
class DeferredToolIndex(Protocol):
    """Per-participant deferred-tool partition state. Session-local."""

    session_id: str
    participant_id: str

    # ── Phase 1 + 2: read-side ─────────────────────────────────────

    def is_empty(self) -> bool:
        """True when no partition has been computed yet OR all tools loaded."""

    def loaded_tool_names(self) -> list[str]:
        """The current loaded subset's tool names in registration order."""

    def deferred_tool_names(self) -> list[str]:
        """The current deferred subset's tool names in registration order."""

    def loaded_token_count(self) -> int:
        """Total tokens of the loaded subset's full schemas."""

    def render_index_entries(self, max_tokens: int) -> tuple[list[str], bool]:
        """Render the deferred subset as compact index entries.

        Returns (entries, truncated). Each entry is a one-line string;
        `truncated=True` when the deferred subset did not fit in
        `max_tokens` and a pagination banner is appended.
        """

    # ── Phase 2 only: mutation paths ───────────────────────────────

    async def compute_partition(
        self,
        tools: list[ToolDefinition],
        budget: int,
        tokenizer: TokenizerAdapter,
    ) -> None:
        """Partition `tools` into loaded/deferred under `budget`.

        v1 policy: registration order. First N tools that fit `budget`
        land in loaded; the rest defer. The two discovery tools
        (tools.list_deferred, tools.load_deferred) are always loaded,
        regardless of budget (FR-011).

        Emits one `tool_partition_decided` audit row (FR-007).

        Phase-1 no-op implementation: returns immediately without
        side effects; index remains empty.
        """

    async def load_on_demand(
        self,
        tool_name: str,
        all_tools: list[ToolDefinition],
    ) -> ToolDefinition | None:
        """Promote `tool_name` from deferred to loaded.

        Returns the tool's full definition on success, None on
        `tool_not_found_in_deferred`.

        If promotion exceeds `budget`, evicts the LRU tool from the
        loaded subset (FR-008). The two discovery tools are never
        eligible for eviction.

        Emits one `tool_loaded_on_demand` audit row, plus one
        `tool_re_deferred` row when eviction occurs (FR-008).

        Phase-1 no-op implementation: returns None.
        """

    async def recompute_on_freshness(
        self,
        new_tools: list[ToolDefinition],
        budget: int,
        tokenizer: TokenizerAdapter,
    ) -> None:
        """Recompute the partition after a spec-017 freshness refresh.

        Promoted tools that still exist in `new_tools` remain promoted;
        promoted tools that disappeared are dropped. Then partition is
        re-run from registration order over `new_tools`.

        Emits one `tool_partition_decided` audit row.

        Phase-1 no-op implementation: returns immediately.
        """
```

## Resolver

The orchestrator resolves a `DeferredToolIndex` for a given `(session_id, participant_id)` via:

```python
def get_deferred_index_for_participant(
    session_id: str,
    participant_id: str,
) -> DeferredToolIndex:
    """Return the participant's index; create on first call.

    Phase-1 implementation: returns a process-scope-shared `_EmptyIndex`
    singleton when `SACP_TOOL_DEFER_ENABLED=false` (the v1 default).
    `_EmptyIndex` satisfies the Protocol with zero state and no-op
    mutations.

    Phase-2 implementation: when `SACP_TOOL_DEFER_ENABLED=true`,
    returns a per-`(session_id, participant_id)` cached instance of
    the working `_LiveIndex` class.
    """
```

## Consumers

Two call sites consume the contract:

1. **`src/orchestrator/context.py:build_full_context`** — calls `is_empty()` and `render_index_entries()` once per turn-prep. Phase-1 always sees an empty index and emits no index entries.
2. **`src/mcp_server/tools/deferred_tools.py:tools.load_deferred`** — calls `load_on_demand()` after verifying caller scope. Phase-1's no-op `load_on_demand` returns None, and the handler converts that to a `{"status": "deferred_loading_disabled"}` stub response.

## Tests

The contract has three test surfaces:

1. **Phase-1 regression contract** (`tests/test_018_phase1_hooks.py`): every consumer call site is exercised on every turn-prep / discovery call; the index returns empty / None and the system prompt is byte-identical to the pre-feature baseline.
2. **Phase-2 partition contract** (`tests/test_018_partition.py`): `compute_partition` produces the expected loaded/deferred split for known inputs; `recompute_on_freshness` correctly merges promoted-and-still-present tools.
3. **Phase-2 discovery contract** (`tests/test_018_discovery.py`): `load_on_demand` promotes correctly and triggers LRU eviction at budget; per-participant scoping rejects cross-participant calls.
