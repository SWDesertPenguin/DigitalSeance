# Contract: Discovery MCP Tools

**Branch**: `018-deferred-tool-loading` | **Date**: 2026-05-13

---

## Purpose

Two SACP-orchestrator-provided MCP tools let a model exit the deferred state on demand. They are registered against the SACP-native MCP surface (currently `src/mcp_server/tools/`, migrating to spec 030's `ToolRegistry` once that lands on main).

Both tools are **always in every participant's loaded subset** (FR-011). They are never themselves deferred.

## tools.list_deferred

**Purpose**: Return the participant's full deferred-tool index.

**Args**: `{page_token: str | null}` (optional, for pagination when the index exceeds `SACP_TOOL_DEFER_INDEX_MAX_TOKENS`).

**Caller scope**: Participant-callable on their own deferred set only. The dispatcher verifies `ctx.participant_id` equals the deferred set's owner before responding.

**Response (Phase-1 stub)**:
```json
{
  "status": "deferred_loading_disabled",
  "spec": "018",
  "documentation": "Deferred tool loading is disabled in this deployment (SACP_TOOL_DEFER_ENABLED=false). See spec 018 for activation details."
}
```

**Response (Phase-2 live)**:
```json
{
  "deferred": [
    {"name": "git_log", "summary": "Show commit log for a path"},
    {"name": "git_diff", "summary": "Show changes between commits"}
  ],
  "truncated": false,
  "next_page_token": null
}
```
When the deferred set exceeds the index budget, `truncated=true` and `next_page_token` is non-null. The caller pages by re-invoking with the token.

## tools.load_deferred

**Purpose**: Load one specific deferred tool's full definition and promote it into the loaded subset for the remainder of the session.

**Args**: `{name: str}` (the tool name to load).

**Caller scope**: Participant-callable on their own deferred set only. Cross-participant calls reject with `{"error": "tool_not_in_caller_registry"}` per US3 AS4.

**Response (Phase-1 stub)**:
```json
{
  "status": "deferred_loading_disabled",
  "spec": "018",
  "documentation": "Deferred tool loading is disabled in this deployment (SACP_TOOL_DEFER_ENABLED=false). See spec 018 for activation details."
}
```

**Response (Phase-2 live, success)**:
```json
{
  "tool": {
    "name": "git_blame",
    "description": "Show line-by-line authorship for a file at a commit",
    "input_schema": { ... full JSON Schema ... }
  },
  "evicted_for_this": null
}
```

When promotion triggered an LRU eviction to fit budget:
```json
{
  "tool": { ... },
  "evicted_for_this": "format_code"
}
```

**Response (Phase-2 live, error variants)**:

`tool not in caller's deferred set`:
```json
{"error": "tool_not_in_caller_registry", "tool_name": "git_blame"}
```

`tool not in any registry` (renamed away, deleted via freshness):
```json
{"error": "tool_not_found", "tool_name": "git_blame"}
```

`load timed out`:
```json
{"error": "load_timeout", "tool_name": "git_blame", "timeout_seconds": 30}
```

## Audit emission (Phase 2)

Each `tools.load_deferred` invocation that succeeds emits one `tool_loaded_on_demand` audit row (FR-008). If the load triggered an LRU eviction, a paired `tool_re_deferred` row also emits.

Both rows share the `requested_at` / `re_deferred_at` timestamp so an audit-log viewer can reconstruct the swap.

`tools.list_deferred` does NOT emit audit rows — it is a read-only operation.

## Cache invalidation (Phase 2)

A successful `tools.load_deferred` invalidates the participant's prompt-cache prefix exactly once (FR-009). The `tool_loaded_on_demand` audit row sets `prompt_cache_invalidated=true` so the cost is causally traceable.

## Forward-compatibility with spec 030 ToolRegistry

Phase 1 registers these handlers against the current `src/mcp_server/tools/` surface. When spec 030's `ToolRegistry` lands on main, the handlers migrate to:

```python
# Future: src/mcp_protocol/tools/deferred_tools.py
TOOL_DEFINITIONS = [
    ToolDefinition(
        name="tools.list_deferred",
        category="tools",
        action="list_deferred",
        ai_accessible=True,
        scopes=["participant"],
        ...
    ),
    ToolDefinition(
        name="tools.load_deferred",
        category="tools",
        action="load_deferred",
        ai_accessible=True,
        scopes=["participant"],
        ...
    ),
]
```

The migration is a renamed-import refactor, not a contract change.
