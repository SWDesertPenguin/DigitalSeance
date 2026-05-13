# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-participant deferred-tool partition state. Spec 018.

The partition module is the layered mechanism above the per-participant
MCP tool registry. It partitions each participant's tool set into a
loaded subset (full definitions in the per-turn dispatch payload) and a
deferred subset (compact index entries the model sees in lieu of the
full schema).

Phase 1 ships a stable `DeferredToolIndex` Protocol + no-op
`_EmptyIndex` (used while `SACP_TOOL_DEFER_ENABLED=false`).
Phase 2 ships the working `_LiveIndex` (activated when the master
switch flips to true) with registration-order partition, LRU eviction
on discovery-driven promotion, freshness-refresh recomputation, and
compact index entry rendering.

Per-participant scoping (FR-006) is enforced by keying every state
lookup on `(session_id, participant_id)`. The two discovery MCP tools
(`tools.list_deferred`, `tools.load_deferred`) are always loaded
regardless of budget (FR-011) so the model has a path out of the
deferred state even under pathological partition.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

log = logging.getLogger(__name__)

# Discovery tool names — match spec 030 domain.action snake_case convention.
DISCOVERY_TOOL_LIST = "tools.list_deferred"
DISCOVERY_TOOL_LOAD = "tools.load_deferred"
DISCOVERY_TOOL_NAMES = frozenset({DISCOVERY_TOOL_LIST, DISCOVERY_TOOL_LOAD})

SELECTION_POLICY_REGISTRATION_ORDER = "registration_order"


def _build_discovery_tool_defs() -> list[ToolDefinition]:
    """Synthesize the two always-loaded discovery tool definitions (FR-011)."""
    return [
        ToolDefinition(
            name=DISCOVERY_TOOL_LIST,
            description=(
                "Return the participant's deferred-tool index " "(name + summary per tool)."
            ),
            input_schema={"type": "object", "properties": {}},
        ),
        ToolDefinition(
            name=DISCOVERY_TOOL_LOAD,
            description=(
                "Load one deferred tool's full definition by name; "
                "promotes the tool sticky-within-session."
            ),
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        ),
    ]


@dataclass(frozen=True, slots=True)
class DeferredToolIndexEntry:
    """Compact per-deferred-tool record. No schema, no examples."""

    tool_name: str
    one_line_summary: str
    source_server: str | None = None


@dataclass
class ToolDefinition:
    """Minimal tool-definition shape consumed by the partition module.

    Spec 018 ships this as a duck-typed alias for the spec 017
    `ParticipantToolRegistry` entries (which aren't on main yet) and
    the spec 030 `ToolDefinition` (also not on main yet). The fields
    here are the intersection both sources agree on. Phase-2 callers
    can pass `dict` literals too — the partition module reads via
    `getattr` so any duck-type works.
    """

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    source_server: str | None = None


@runtime_checkable
class DeferredToolIndex(Protocol):
    """Per-participant deferred-tool partition state. Session-local."""

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

    def is_loaded(self, tool_name: str) -> bool:
        """True if `tool_name` is in the loaded subset."""
        ...

    def render_index_entries(self, max_tokens: int) -> tuple[list[str], bool]:
        """Render the deferred subset as compact index entries."""
        ...

    async def compute_partition(
        self,
        tools: list[Any],
        budget: int,
        tokenizer: Any,
    ) -> None:
        """Partition `tools` into loaded/deferred under `budget`."""
        ...

    async def load_on_demand(
        self,
        tool_name: str,
        all_tools: list[Any],
    ) -> Any | None:
        """Promote `tool_name` from deferred to loaded."""
        ...

    async def recompute_on_freshness(
        self,
        new_tools: list[Any],
        budget: int,
        tokenizer: Any,
    ) -> None:
        """Recompute partition after a spec-017 freshness refresh."""
        ...


# ── No-op implementation (Phase 1 default) ──────────────────────────


class _EmptyIndex:
    """No-op DeferredToolIndex used while spec 018 deferral is disabled."""

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

    def is_loaded(self, tool_name: str) -> bool:
        return False

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


# ── Working implementation (Phase 2) ────────────────────────────────


@dataclass
class _PartitionState:
    """Internal mutable state for `_LiveIndex` — broken out for testability."""

    loaded_tools: list[Any] = field(default_factory=list)
    deferred_entries: list[DeferredToolIndexEntry] = field(default_factory=list)
    loaded_token_count: int = 0
    promoted_tool_names: set[str] = field(default_factory=set)
    pathological_partition: bool = False
    tokenizer_name: str = ""
    tokenizer_fallback_used: bool = False
    partition_decided_at: datetime | None = None
    selection_policy: str = SELECTION_POLICY_REGISTRATION_ORDER


class _LiveIndex:
    """Working partition + LRU + recompute. Activated when SACP_TOOL_DEFER_ENABLED=true."""

    def __init__(
        self,
        session_id: str,
        participant_id: str,
        *,
        pool: Any = None,
    ) -> None:
        self.session_id = session_id
        self.participant_id = participant_id
        self._state = _PartitionState()
        self._lock = asyncio.Lock()
        self._pool = pool
        self._partition_ever_computed = False

    # ── read-side ───────────────────────────────────────────────────

    def is_empty(self) -> bool:
        return not self._partition_ever_computed or (
            not self._state.loaded_tools and not self._state.deferred_entries
        )

    def loaded_tool_names(self) -> list[str]:
        return [_tool_name(t) for t in self._state.loaded_tools]

    def deferred_tool_names(self) -> list[str]:
        return [e.tool_name for e in self._state.deferred_entries]

    def loaded_token_count(self) -> int:
        return self._state.loaded_token_count

    def is_loaded(self, tool_name: str) -> bool:
        return any(_tool_name(t) == tool_name for t in self._state.loaded_tools)

    def render_index_entries(self, max_tokens: int) -> tuple[list[str], bool]:
        if not self._state.deferred_entries:
            return ([], False)
        return _render_with_banner(self._state.deferred_entries, max_tokens)

    # ── mutation paths ──────────────────────────────────────────────

    async def compute_partition(
        self,
        tools: list[Any],
        budget: int,
        tokenizer: Any,
    ) -> None:
        async with self._lock:
            self._apply_partition(tools, budget, tokenizer)
        await self._emit_partition_decided_audit(reason="initial")

    async def recompute_on_freshness(
        self,
        new_tools: list[Any],
        budget: int,
        tokenizer: Any,
    ) -> None:
        async with self._lock:
            previously_promoted = set(self._state.promoted_tool_names)
            self._apply_partition(
                new_tools,
                budget,
                tokenizer,
                preserve_promoted=previously_promoted,
            )
        await self._emit_partition_decided_audit(reason="freshness_refresh")

    async def load_on_demand(
        self,
        tool_name: str,
        all_tools: list[Any],
    ) -> Any | None:
        async with self._lock:
            if self.is_loaded(tool_name):
                return _find_tool(all_tools, tool_name)
            target = _find_tool(all_tools, tool_name)
            if target is None:
                return None
            cost = _tokenize_schema(target, _tokenizer_or_default())
            evicted: str | None = None
            budget = _read_loaded_budget()
            while self._state.loaded_token_count + cost > budget and self._has_evictable_tool():
                evicted_tool = self._evict_lru()
                if evicted_tool is None:
                    break
                evicted = _tool_name(evicted_tool)
            self._state.loaded_tools.append(target)
            self._state.loaded_token_count += cost
            self._state.promoted_tool_names.add(tool_name)
            self._state.deferred_entries = [
                e for e in self._state.deferred_entries if e.tool_name != tool_name
            ]
            self._state.pathological_partition = self._compute_pathological_flag()
        await self._emit_loaded_on_demand_audit(tool_name=tool_name, evicted=evicted)
        if evicted is not None:
            await self._emit_re_deferred_audit(re_deferred_tool=evicted, for_tool=tool_name)
        return target

    # ── internal helpers ────────────────────────────────────────────

    def _apply_partition(
        self,
        tools: list[Any],
        budget: int,
        tokenizer: Any,
        *,
        preserve_promoted: set[str] | None = None,
    ) -> None:
        preserve_promoted = preserve_promoted or set()
        tokenizer = tokenizer or _tokenizer_or_default()
        self._record_tokenizer(tokenizer)
        non_discovery_tools = [t for t in tools if _tool_name(t) not in DISCOVERY_TOOL_NAMES]
        loaded, deferred, token_count, new_promoted = self._build_partition(
            non_discovery_tools, budget, tokenizer, preserve_promoted
        )
        self._state.loaded_tools = loaded
        self._state.deferred_entries = deferred
        self._state.loaded_token_count = token_count
        self._state.promoted_tool_names = new_promoted
        self._state.pathological_partition = self._compute_pathological_flag(
            non_discovery_tools=non_discovery_tools, loaded=loaded
        )
        self._state.partition_decided_at = datetime.now(tz=UTC)
        self._partition_ever_computed = True

    def _record_tokenizer(self, tokenizer: Any) -> None:
        self._state.tokenizer_name = _tokenizer_name(tokenizer)
        self._state.tokenizer_fallback_used = _is_fallback_tokenizer(tokenizer)
        if self._state.tokenizer_fallback_used:
            log.warning(
                "deferred_tool_index: tokenizer_fallback_used "
                "session=%s participant=%s using=%s",
                self.session_id,
                self.participant_id,
                self._state.tokenizer_name,
            )

    def _build_partition(
        self,
        non_discovery_tools: list[Any],
        budget: int,
        tokenizer: Any,
        preserve_promoted: set[str],
    ) -> tuple[list[Any], list[DeferredToolIndexEntry], int, set[str]]:
        # Discovery tools always land in loaded (FR-011); they're
        # orchestrator-provided overhead so token cost is not charged
        # against the participant's loaded budget.
        loaded: list[Any] = list(_build_discovery_tool_defs())
        deferred: list[DeferredToolIndexEntry] = []
        token_count = 0
        new_promoted: set[str] = set()
        # Pass 1: skip-the-queue priority for previously-promoted tools.
        for tool in non_discovery_tools:
            if _tool_name(tool) not in preserve_promoted:
                continue
            loaded.append(tool)
            token_count += _tokenize_schema(tool, tokenizer)
            new_promoted.add(_tool_name(tool))
        # Pass 2: fill remaining budget with registration-order tools.
        for tool in non_discovery_tools:
            if _tool_name(tool) in preserve_promoted:
                continue
            cost = _tokenize_schema(tool, tokenizer)
            if token_count + cost <= budget:
                loaded.append(tool)
                token_count += cost
            else:
                deferred.append(_to_entry(tool))
        return loaded, deferred, token_count, new_promoted

    def _compute_pathological_flag(
        self,
        *,
        non_discovery_tools: list[Any] | None = None,
        loaded: list[Any] | None = None,
    ) -> bool:
        loaded_list = loaded if loaded is not None else self._state.loaded_tools
        non_disc = (
            non_discovery_tools
            if non_discovery_tools is not None
            else loaded_list + [_entry_to_tool(e) for e in self._state.deferred_entries]
        )
        non_disc_loaded = [t for t in loaded_list if _tool_name(t) not in DISCOVERY_TOOL_NAMES]
        return bool(non_disc) and not non_disc_loaded

    def _has_evictable_tool(self) -> bool:
        for tool in self._state.loaded_tools:
            if _tool_name(tool) not in DISCOVERY_TOOL_NAMES:
                return True
        return False

    def _evict_lru(self) -> Any | None:
        for i, tool in enumerate(self._state.loaded_tools):
            name = _tool_name(tool)
            if name in DISCOVERY_TOOL_NAMES:
                continue
            evicted = self._state.loaded_tools.pop(i)
            self._state.deferred_entries.append(_to_entry(evicted))
            self._state.promoted_tool_names.discard(name)
            tokenizer = _tokenizer_or_default()
            self._state.loaded_token_count -= _tokenize_schema(evicted, tokenizer)
            self._state.loaded_token_count = max(self._state.loaded_token_count, 0)
            return evicted
        return None

    # ── audit emission ──────────────────────────────────────────────

    async def _emit_partition_decided_audit(self, *, reason: str) -> None:
        if self._pool is None:
            return
        from src.orchestrator.deferred_tool_audit import emit_partition_decided

        # Operator-facing counts are scoped to participant tools — the
        # two discovery tools are infrastructure overhead, not partition
        # outcomes worth reporting (per data-model.md).
        participant_loaded = [n for n in self.loaded_tool_names() if n not in DISCOVERY_TOOL_NAMES]
        await emit_partition_decided(
            pool=self._pool,
            session_id=self.session_id,
            participant_id=self.participant_id,
            loaded_tool_names=participant_loaded,
            deferred_tool_names=self.deferred_tool_names(),
            loaded_token_count=self._state.loaded_token_count,
            pathological_partition=self._state.pathological_partition,
            tokenizer_name=self._state.tokenizer_name,
            tokenizer_fallback_used=self._state.tokenizer_fallback_used,
            selection_policy=self._state.selection_policy,
            decided_at=self._state.partition_decided_at,
            reason=reason,
        )

    async def _emit_loaded_on_demand_audit(self, *, tool_name: str, evicted: str | None) -> None:
        if self._pool is None:
            return
        from src.orchestrator.deferred_tool_audit import emit_loaded_on_demand

        await emit_loaded_on_demand(
            pool=self._pool,
            session_id=self.session_id,
            participant_id=self.participant_id,
            tool_name=tool_name,
            evicted_tool_name=evicted,
        )

    async def _emit_re_deferred_audit(self, *, re_deferred_tool: str, for_tool: str) -> None:
        if self._pool is None:
            return
        from src.orchestrator.deferred_tool_audit import emit_re_deferred

        await emit_re_deferred(
            pool=self._pool,
            session_id=self.session_id,
            participant_id=self.participant_id,
            re_deferred_tool=re_deferred_tool,
            evicted_for_tool=for_tool,
        )


# ── Resolver + cache ────────────────────────────────────────────────


_INDEX_CACHE: dict[tuple[str, str], DeferredToolIndex] = {}
_DB_POOL_PROVIDER: Any | None = None
_TOOL_LIST_PROVIDER: Any | None = None


def set_db_pool_provider(provider: Any) -> None:
    """Inject the asyncpg pool used by audit emissions.

    Set once at application startup. The audit helpers acquire from this
    pool to write `admin_audit_log` rows. When unset (tests, dev shells),
    audit emission silently no-ops — the partition state remains correct
    but no row reaches the DB.
    """
    global _DB_POOL_PROVIDER
    _DB_POOL_PROVIDER = provider


def _resolve_pool() -> Any | None:
    return _DB_POOL_PROVIDER


def set_tool_list_provider(provider: Any) -> None:
    """Inject the spec-017-style tool-list provider.

    Signature: ``async (session_id, participant_id) -> list[ToolDefinition]``.
    The orchestrator's context-assembly path calls this on first turn-prep
    to seed `compute_partition` with the participant's tools. Spec 017's
    `ParticipantToolRegistry` wires this once it lands on main; in the
    meantime, the provider is unset and the partition computes a
    zero-tools decision (observable as `deferred_count=0, loaded_count=0`
    in the audit log).
    """
    global _TOOL_LIST_PROVIDER
    _TOOL_LIST_PROVIDER = provider


def get_tool_list_provider() -> Any | None:
    """Return the registered tool-list provider, or None if unset."""
    return _TOOL_LIST_PROVIDER


def get_deferred_index_for_participant(
    session_id: str,
    participant_id: str,
) -> DeferredToolIndex:
    """Return the participant's index; create on first call.

    Returns the cached instance for `(session_id, participant_id)` when
    one exists. Otherwise creates `_LiveIndex` (when
    `SACP_TOOL_DEFER_ENABLED=true`) or `_EmptyIndex` (the v1 default).
    """
    key = (session_id, participant_id)
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    if _deferral_enabled():
        idx: DeferredToolIndex = _LiveIndex(session_id, participant_id, pool=_resolve_pool())
    else:
        idx = _EmptyIndex(session_id, participant_id)
    _INDEX_CACHE[key] = idx
    return idx


def _deferral_enabled() -> bool:
    """Read `SACP_TOOL_DEFER_ENABLED` at the v1 default of false."""
    val = os.environ.get("SACP_TOOL_DEFER_ENABLED", "false").strip().lower()
    return val == "true"


def evict_index(session_id: str, participant_id: str) -> None:
    """Drop the cached index for `(session_id, participant_id)`.

    Called when a session ends or a participant leaves. Phase-2
    `_LiveIndex` releases its partition state and lock; Phase-1
    `_EmptyIndex` carries no state to lose.
    """
    _INDEX_CACHE.pop((session_id, participant_id), None)


def clear_index_cache() -> None:
    """Reset the process-scope index cache. Test isolation only."""
    _INDEX_CACHE.clear()


# ── Module-level helpers ────────────────────────────────────────────


def _tool_name(tool: Any) -> str:
    if hasattr(tool, "name"):
        return tool.name
    if isinstance(tool, dict):
        return tool.get("name", "")
    return str(tool)


def _tool_description(tool: Any) -> str:
    if hasattr(tool, "description"):
        return tool.description or ""
    if isinstance(tool, dict):
        return tool.get("description", "") or ""
    return ""


def _tool_source_server(tool: Any) -> str | None:
    if hasattr(tool, "source_server"):
        return tool.source_server
    if isinstance(tool, dict):
        return tool.get("source_server")
    return None


def _tool_schema_str(tool: Any) -> str:
    """Render the tool's full schema as a string for token counting."""
    if hasattr(tool, "input_schema"):
        schema = tool.input_schema
    elif isinstance(tool, dict):
        schema = tool.get("input_schema", {})
    else:
        schema = {}
    return f"{_tool_name(tool)}\n{_tool_description(tool)}\n{json.dumps(schema)}"


def _tokenize_schema(tool: Any, tokenizer: Any) -> int:
    return tokenizer.count_tokens(_tool_schema_str(tool))


def _to_entry(tool: Any) -> DeferredToolIndexEntry:
    desc = _tool_description(tool).strip().replace("\n", " ")
    summary = _truncate_at_word_boundary(desc, max_chars=80)
    return DeferredToolIndexEntry(
        tool_name=_tool_name(tool),
        one_line_summary=summary,
        source_server=_tool_source_server(tool),
    )


def _entry_to_tool(entry: DeferredToolIndexEntry) -> ToolDefinition:
    return ToolDefinition(
        name=entry.tool_name,
        description=entry.one_line_summary,
        source_server=entry.source_server,
    )


def _find_tool(tools: list[Any], name: str) -> Any | None:
    for tool in tools:
        if _tool_name(tool) == name:
            return tool
    return None


def _truncate_at_word_boundary(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    return cut.rstrip() + "..."


def _render_one_entry(entry: DeferredToolIndexEntry) -> str:
    return (
        f"- {entry.tool_name}: {entry.one_line_summary} "
        f'[load_via: tools.load_deferred(name="{entry.tool_name}")]'
    )


_INDEX_BANNER = (
    "- ...more deferred tools available. Call tools.list_deferred " "to retrieve the full index."
)


def _render_with_banner(
    entries: list[DeferredToolIndexEntry], max_tokens: int
) -> tuple[list[str], bool]:
    """Render entries one-per-line; append pagination banner on truncation."""
    banner_cost = _approx_tokens(_INDEX_BANNER)
    out: list[str] = []
    used = 0
    total = len(entries)
    for i, entry in enumerate(entries):
        rendered = _render_one_entry(entry)
        cost = _approx_tokens(rendered)
        remaining_after = max_tokens - banner_cost - used - cost
        more_after = total - i - 1
        if (more_after > 0 and remaining_after < 0) or used + cost > max_tokens:
            if banner_cost <= max_tokens - used:
                out.append(_INDEX_BANNER)
            return (out, True)
        out.append(rendered)
        used += cost
    return (out, False)


def _approx_tokens(text: str) -> int:
    """Coarse token estimate for index entries (~4 chars/token)."""
    if not text:
        return 0
    return max(len(text) // 4, 1)


def _tokenizer_or_default() -> Any:
    """Resolve a process-default tokenizer when one isn't passed in."""
    from src.api_bridge.tokenizer import default_estimator

    return default_estimator()


def _tokenizer_name(tokenizer: Any) -> str:
    if hasattr(tokenizer, "get_tokenizer_name"):
        try:
            return tokenizer.get_tokenizer_name()
        except Exception:  # noqa: BLE001
            return "unknown"
    return "unknown"


def _is_fallback_tokenizer(tokenizer: Any) -> bool:
    name = _tokenizer_name(tokenizer)
    return name.startswith("default:")


def _read_loaded_budget() -> int:
    """Read SACP_TOOL_LOADED_TOKEN_BUDGET at the default of 1500."""
    raw = os.environ.get("SACP_TOOL_LOADED_TOKEN_BUDGET", "").strip()
    if not raw:
        return 1500
    try:
        return int(raw)
    except ValueError:
        return 1500
