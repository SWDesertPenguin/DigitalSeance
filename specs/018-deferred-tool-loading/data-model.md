# Data Model: Deferred Tool Loading

**Branch**: `018-deferred-tool-loading` | **Date**: 2026-05-13 | **Plan**: [plan.md](./plan.md)

---

## In-Memory Entities (session-local, not persisted across restart)

### DeferredToolIndex

One instance per active `(session_id, participant_id)` tuple. Stored in a process-scope dict keyed on that tuple. Created on first partition-computation request (typically at session start when the participant joins and `SACP_TOOL_DEFER_ENABLED=true`).

```python
from typing import Protocol

class DeferredToolIndex(Protocol):
    """Per-participant deferred-tool partition state."""

    session_id: str
    participant_id: str
    loaded_tools: list[ToolDefinition]            # full schemas
    deferred_tools: list[DeferredToolIndexEntry]  # compact entries
    loaded_token_count: int                        # total tokens of loaded subset
    partition_decided_at: datetime                 # UTC, last partition timestamp
    selection_policy: str                          # 'registration_order' in v1
    pathological_partition: bool                   # True if no real tools fit budget
    tokenizer_name: str                            # from get_tokenizer_for_participant
    tokenizer_fallback_used: bool                  # True if _DefaultTokenizer

    async def compute_partition(
        self,
        tools: list[ToolDefinition],
        budget: int,
        tokenizer: TokenizerAdapter,
    ) -> None:
        """Partition `tools` into loaded/deferred under `budget`."""

    async def load_on_demand(
        self,
        tool_name: str,
        all_tools: list[ToolDefinition],
    ) -> ToolDefinition:
        """Promote `tool_name` from deferred to loaded; LRU-evict if needed."""

    def is_loaded(self, tool_name: str) -> bool:
        """True if `tool_name` is in the loaded subset."""
```

Field invariants:
- `len(loaded_tools) + len(deferred_tools) == len(participant_tools)` at all times (no tool exists in both subsets, none missing).
- `loaded_token_count == sum(tokenizer.count_tokens(t.full_schema) for t in loaded_tools)`.
- `pathological_partition == True` implies `len(loaded_tools) == 0` (or contains only the two discovery tools per FR-011 once those are registered).

### DeferredToolIndexEntry

One entry per deferred tool. Lightweight by design — no schema, no examples, no parameter details.

```python
@dataclass(frozen=True, slots=True)
class DeferredToolIndexEntry:
    tool_name: str                                 # full name including domain prefix
    one_line_summary: str                          # first ~80 chars of description, word-boundary truncated
    source_server: str | None                     # MCP server name if multi-server participant; else None
```

The entry's wire-format rendering in the system prompt / dispatch payload:
```text
- {tool_name}: {one_line_summary} [load_via: tools.load_deferred(name="{tool_name}")]
```
Approximately 12-15 tokens per entry. `SACP_TOOL_DEFER_INDEX_MAX_TOKENS` (default 256) holds ~20 entries before truncation.

### Discovery tool registrations

Two SACP-orchestrator-provided MCP tools always appear in every participant's loaded subset (never themselves deferred — FR-011):

| Tool Name              | Args             | Returns                                                                                |
|------------------------|------------------|----------------------------------------------------------------------------------------|
| `tools.list_deferred`  | (no args)        | `{deferred: [{name, summary}, ...], truncated: bool, next_page_token: str \| null}`    |
| `tools.load_deferred`  | `name: str`      | `{tool: ToolDefinition, evicted_for_this: str \| null}` OR `{error: str, reason: str}` |

Both tools enforce `ctx.participant_id == participant_id_of_deferred_set` and reject cross-participant calls with `{"error": "tool_not_in_caller_registry"}`.

---

## DB Audit Rows (existing `admin_audit_log` table — no schema change)

Three new `action_type` strings join the spec 002 catalog. The existing `admin_audit_log` table shape (per spec 002 §FR-014):

```sql
-- existing table; no migration needed
CREATE TABLE admin_audit_log (
    id           BIGSERIAL PRIMARY KEY,
    session_id   TEXT NOT NULL,
    participant_id TEXT,                       -- nullable for session-scope events
    action_type  TEXT NOT NULL,
    payload      JSONB NOT NULL,
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### action_type = "tool_partition_decided"

Emitted at session start AND on every partition recomputation (e.g., spec-017 `tool_list_changed` event).

```json
{
  "loaded_count": 5,
  "deferred_count": 15,
  "loaded_token_count": 1487,
  "decided_at": "2026-05-13T14:32:11Z",
  "selection_policy": "registration_order",
  "pathological_partition": false,
  "tokenizer_name": "anthropic:fallback-cl100k-x1.10",
  "tokenizer_fallback_used": false,
  "loaded_tool_names": ["search_docs", "edit_file", "list_files", "run_tests", "format_code"],
  "deferred_tool_names": ["git_log", "git_diff", "..."]
}
```

### action_type = "tool_loaded_on_demand"

Emitted on every successful `tools.load_deferred` invocation that promotes a deferred tool into the loaded subset.

```json
{
  "tool_name": "git_blame",
  "requested_at": "2026-05-13T14:35:20Z",
  "prompt_cache_invalidated": true,
  "evicted_tool_name": null
}
```

The `evicted_tool_name` field is non-null when the promotion triggered an LRU eviction (and a paired `tool_re_deferred` row is also emitted).

### action_type = "tool_re_deferred"

Emitted on every LRU eviction triggered by an on-demand load that exceeded the budget after promotion.

```json
{
  "tool_name": "format_code",
  "re_deferred_at": "2026-05-13T14:35:20Z",
  "reason": "lru_eviction_after_load",
  "evicted_for_tool_name": "git_blame"
}
```

The `evicted_for_tool_name` field references the tool whose promotion triggered this eviction. Together with the paired `tool_loaded_on_demand` row (same `requested_at` / `re_deferred_at` timestamp), the audit log reconstructs the full swap.

---

## conftest.py schema mirror

**No changes required.** The `admin_audit_log` table is already mirrored in `tests/conftest.py`'s raw schema from spec 002. No new tables, no new columns, no new mirror rows.

---

## Migration chain

**No migration.** Spec 018 introduces zero schema changes. The migration chain is unchanged. The next migration slot (024 or higher, depending on spec 030's actual revision number on main) is reserved for a future spec.

---

## Persistence decision

The `DeferredToolIndex` is **session-local and not persisted across restart**. On orchestrator restart, every participant's index is reconstructed from scratch via `compute_partition` at session resume. This matches the project stance from spec 015 (CircuitState) and spec 017 (ParticipantToolRegistry).

The audit tables provide the forensic record of partition decisions, on-demand loads, and LRU evictions. Operators can reconstruct any participant's partition history from the `admin_audit_log` rows alone (per SC-008).
