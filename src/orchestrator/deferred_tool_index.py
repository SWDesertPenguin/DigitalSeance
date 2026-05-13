# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-participant deferred-tool partition state. Spec 018.

The partition module is the layered mechanism above the per-participant
MCP tool registry. It partitions each participant's tool set into a
loaded subset (full definitions in the per-turn dispatch payload) and a
deferred subset (compact index entries the model sees in lieu of the
full schema).

This file ships the Phase-1 design hooks: a stable `DeferredToolIndex`
Protocol, a no-op `_EmptyIndex` implementation that satisfies the
Protocol for the v1 default state (`SACP_TOOL_DEFER_ENABLED=false`),
and a resolver `get_deferred_index_for_participant` that returns the
no-op singleton. The working `_LiveIndex` class lands in Phase 2 once
the spec 017 freshness mechanism is on main.

Per-participant scoping (FR-006) is enforced by keying every state
lookup on `(session_id, participant_id)`. The two discovery MCP tools
(`tools.list_deferred`, `tools.load_deferred`) are always loaded
regardless of budget (FR-011) so the model has a path out of the
deferred state even under pathological partition.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

# Discovery tool names — match spec 030 domain.action snake_case convention.
DISCOVERY_TOOL_LIST = "tools.list_deferred"
DISCOVERY_TOOL_LOAD = "tools.load_deferred"
DISCOVERY_TOOL_NAMES = frozenset({DISCOVERY_TOOL_LIST, DISCOVERY_TOOL_LOAD})


@dataclass(frozen=True, slots=True)
class DeferredToolIndexEntry:
    """Compact per-deferred-tool record. No schema, no examples."""

    tool_name: str
    one_line_summary: str
    source_server: str | None = None


@runtime_checkable
class DeferredToolIndex(Protocol):
    """Per-participant deferred-tool partition state. Session-local.

    Phase-1 implementations (`_EmptyIndex`) satisfy this Protocol with
    empty state and no-op mutations. Phase-2 (`_LiveIndex`) fills the
    contract with working partition + LRU eviction + audit emission.
    """

    session_id: str
    participant_id: str

    def is_empty(self) -> bool:
        """True when no partition has been computed yet OR all tools loaded."""
        ...

    def loaded_tool_names(self) -> list[str]:
        """Loaded subset's tool names in registration order."""
        ...

    def deferred_tool_names(self) -> list[str]:
        """Deferred subset's tool names in registration order."""
        ...

    def loaded_token_count(self) -> int:
        """Total tokens of the loaded subset's full schemas."""
        ...

    def render_index_entries(self, max_tokens: int) -> tuple[list[str], bool]:
        """Render the deferred subset as compact index entries.

        Returns (entries, truncated). Each entry is a one-line string;
        ``truncated=True`` when the deferred subset did not fit in
        ``max_tokens`` and a pagination banner is appended.
        """
        ...

    async def compute_partition(
        self,
        tools: list[Any],
        budget: int,
        tokenizer: Any,
    ) -> None:
        """Partition `tools` into loaded/deferred under `budget`. Phase 2."""
        ...

    async def load_on_demand(
        self,
        tool_name: str,
        all_tools: list[Any],
    ) -> Any | None:
        """Promote `tool_name` from deferred to loaded. Phase 2."""
        ...

    async def recompute_on_freshness(
        self,
        new_tools: list[Any],
        budget: int,
        tokenizer: Any,
    ) -> None:
        """Recompute partition after a spec-017 freshness refresh. Phase 2."""
        ...


class _EmptyIndex:
    """No-op DeferredToolIndex used while spec 018 deferral is disabled.

    Satisfies the Protocol with zero state and no-op mutations. The
    Phase-1 cut returns this for every participant; the Phase-2 cut
    returns a working `_LiveIndex` when `SACP_TOOL_DEFER_ENABLED=true`.
    """

    __slots__ = ("session_id", "participant_id", "partition_decided_at")

    def __init__(self, session_id: str, participant_id: str) -> None:
        self.session_id = session_id
        self.participant_id = participant_id
        self.partition_decided_at = datetime.now(tz=UTC)

    def is_empty(self) -> bool:
        return True

    def loaded_tool_names(self) -> list[str]:
        return []

    def deferred_tool_names(self) -> list[str]:
        return []

    def loaded_token_count(self) -> int:
        return 0

    def render_index_entries(self, max_tokens: int) -> tuple[list[str], bool]:
        return ([], False)

    async def compute_partition(
        self,
        tools: list[Any],
        budget: int,
        tokenizer: Any,
    ) -> None:
        return None

    async def load_on_demand(
        self,
        tool_name: str,
        all_tools: list[Any],
    ) -> Any | None:
        return None

    async def recompute_on_freshness(
        self,
        new_tools: list[Any],
        budget: int,
        tokenizer: Any,
    ) -> None:
        return None


_EMPTY_INDEX_CACHE: dict[tuple[str, str], _EmptyIndex] = {}


def get_deferred_index_for_participant(
    session_id: str,
    participant_id: str,
) -> DeferredToolIndex:
    """Return the participant's index; create on first call.

    Phase 1: returns a per-`(session_id, participant_id)` cached
    `_EmptyIndex` when `SACP_TOOL_DEFER_ENABLED=false` (the v1 default).
    The cache is keyed by tuple to preserve per-participant identity —
    two participants in the same session get distinct instances per
    FR-006.

    Phase 2 (future): when `SACP_TOOL_DEFER_ENABLED=true`, returns a
    `_LiveIndex` with working partition logic. The contract stays
    stable across the transition; consumers don't need to know which
    implementation they're holding.
    """
    if _deferral_enabled():
        # Phase 2 hook point — _LiveIndex resolver lands here.
        pass
    key = (session_id, participant_id)
    cached = _EMPTY_INDEX_CACHE.get(key)
    if cached is None:
        cached = _EmptyIndex(session_id, participant_id)
        _EMPTY_INDEX_CACHE[key] = cached
    return cached


def _deferral_enabled() -> bool:
    """Read `SACP_TOOL_DEFER_ENABLED` at the v1 default of false."""
    val = os.environ.get("SACP_TOOL_DEFER_ENABLED", "false").strip().lower()
    return val == "true"


def evict_index(session_id: str, participant_id: str) -> None:
    """Drop the cached index for `(session_id, participant_id)`.

    Called when a session ends or a participant leaves. Phase-1
    `_EmptyIndex` carries no state to lose, but the eviction path is
    in place so Phase 2's `_LiveIndex` cleanup is wire-compatible.
    """
    _EMPTY_INDEX_CACHE.pop((session_id, participant_id), None)


def clear_index_cache() -> None:
    """Reset the process-scope index cache. Test isolation only."""
    _EMPTY_INDEX_CACHE.clear()
