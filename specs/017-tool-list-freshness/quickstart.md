# Quickstart: Tool-List Freshness

## Enable polling

Add to your `.env` (or Dockge compose environment):

```
SACP_TOOL_REFRESH_POLL_INTERVAL_S=60
```

Valid range: 15-3600. Unset disables polling entirely (pre-feature behavior).

Optionally tune the refresh timeout (default: inherit adapter timeout):

```
SACP_TOOL_REFRESH_TIMEOUT_S=10
```

## Observe audit log

Tool-set changes appear in `admin_audit_log` with `action = tool_list_changed`. Each row's `new_value` JSON carries:

- `change_kind`: `added`, `removed`, `description_changed`, `schema_changed`, or `refresh_failed`
- `tool_name`: the affected tool's name
- `old_hash` / `new_hash`: before/after SHA-256 of the full tool set
- `trigger_source`: `poll` (v1), `push` or `manual` (Phase 2)
- `prompt_cache_invalidated`: True when the change occurred after the first turn dispatch

Example query (psql):

```sql
SELECT timestamp, target_id, new_value
FROM admin_audit_log
WHERE session_id = '<your-session-id>'
  AND action = 'tool_list_changed'
ORDER BY timestamp DESC;
```

## Handle push subscription (Phase 2 stub)

To enable push subscription attempts at participant registration:

```
SACP_TOOL_REFRESH_PUSH_ENABLED=true
```

With `true`, the orchestrator sends a `notifications/tools/list_changed` subscription request to each participant's MCP server at registration. Servers that do not support push will receive the request and respond with a method-not-found error; the orchestrator falls back to polling silently. The subscription outcome is recorded in `admin_audit_log` with `action = tool_subscription_attempted`.

Push delivery (acting on received push notifications) is Phase 2 and requires a separate spec.

## Tune tool-list size cap

Default cap is 65536 bytes. To override:

```
SACP_TOOL_LIST_MAX_BYTES=131072
```

Valid range: 1024-1048576. When the tool list from an MCP server exceeds the cap, it is truncated to the first N tools that fit and a `tool_list_changed` audit row is emitted noting the truncation.

## Startup validation

All four vars are validated at startup. Invalid values exit with a clear error. Verify config without starting the server:

```
python -m src.run_apps --validate-config-only
```
