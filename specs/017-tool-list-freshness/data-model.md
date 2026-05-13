# Data Model: Tool-List Freshness

## In-Memory Entities

### `ParticipantToolRegistry`

Per-participant, session-local. Keyed by `(session_id, participant_id)` in the process-scope `_REGISTRIES` dict. Not persisted across restart.

```python
@dataclass
class ParticipantToolRegistry:
    session_id: str
    participant_id: str
    tools: list[dict]           # current cached tool list
    tool_set_hash: str          # stable SHA-256 of sorted tool list
    last_refreshed_at: datetime # UTC; used for poll-interval gate
    push_subscribed: bool       # True if push subscription succeeded
    consecutive_failures: int   # incremented on each refresh failure
    next_retry_at: datetime | None  # set after failure; None = retry anytime
```

### Session-scope registry dict

```python
_REGISTRIES: dict[tuple[str, str], ParticipantToolRegistry] = {}
```

Key: `(session_id, participant_id)`. Populated by `register_participant`; evicted by `evict_session`.

## Audit Entities (persisted in `admin_audit_log`)

No schema changes. All audit rows use the existing `admin_audit_log` table with `action = "tool_list_changed"`.

### `ToolListChangedRecord` (audit row shape)

Maps to `admin_audit_log` columns:
- `session_id`: the SACP session
- `facilitator_id`: the orchestrator's synthetic actor (uses session's `facilitator_id` from `sessions` table; falls back to `participant_id` if unavailable)
- `action`: `"tool_list_changed"`
- `target_id`: `participant_id`
- `previous_value`: `None` or prior tool-set hash (string)
- `new_value`: JSON object (stored as TEXT in the JSONB-compatible column)

`new_value` JSON shape:

```json
{
  "change_kind": "added | removed | description_changed | schema_changed | refresh_failed",
  "tool_name": "the_tool_name | null",
  "old_hash": "sha256hex | null",
  "new_hash": "sha256hex | null",
  "trigger_source": "poll | push | manual | registration",
  "prompt_cache_invalidated": true,
  "observed_at": "2026-05-13T00:00:00Z"
}
```

`change_kind` semantics:
- `added`: a tool present in new list was absent from old list
- `removed`: a tool present in old list is absent from new list
- `description_changed`: tool name unchanged but description text changed
- `schema_changed`: tool name unchanged but inputSchema changed (or tool re-added with different schema)
- `refresh_failed`: MCP server unreachable, timeout, or malformed response

`prompt_cache_invalidated` is True when `last_refreshed_at` is not the registration-time initial fetch (i.e., the system prompt was already dispatched to the provider at least once and this change invalidates the cached prefix).

### `ToolSubscriptionRecord` (audit row shape for push-subscription outcome)

Uses same `admin_audit_log` table with `action = "tool_subscription_attempted"`:
- `target_id`: `participant_id`
- `new_value`: `{"supported": true/false, "subscribed_at": "...", "failure_reason": null | "string"}`

## No Schema Changes

The existing `admin_audit_log` DDL is unchanged. The `new_value` TEXT column stores the JSON payload. The `facilitator_id` column is used for the orchestrator's actor identity (reuses session's facilitator_id or participant_id).
