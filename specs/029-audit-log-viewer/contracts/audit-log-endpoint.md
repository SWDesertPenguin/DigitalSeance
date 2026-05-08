# Contract: `GET /tools/admin/audit_log`

**Spec**: [../spec.md](../spec.md) §FR-001 / FR-002 / FR-003 / FR-004 / FR-005 / FR-014 / FR-015 / FR-016 / FR-017 / FR-018
**Plan**: [../plan.md](../plan.md)
**Status**: Phase 1 contract draft

## Authorization

- **Caller MUST be a facilitator of the requested session.** Non-facilitator callers receive `HTTP 403`. (FR-002)
- **Caller MUST belong to the requested session.** A facilitator from session A requesting session B's audit log receives `HTTP 403`. (FR-003)
- **Master switch.** When `SACP_AUDIT_VIEWER_ENABLED=false` (default), the route is unmounted and ALL callers receive `HTTP 404`. (FR-018)

## Request

```
GET /tools/admin/audit_log?session_id=<uuid>&offset=<int>&limit=<int>
```

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `session_id` | UUID | Yes | — | Caller MUST be a facilitator of this session |
| `offset` | non-negative int | No | `0` | Offset-based pagination |
| `limit` | int 1..500 | No | `SACP_AUDIT_VIEWER_PAGE_SIZE` (default 50) | Bounded by the env var; out-of-range rejected with `HTTP 400` |

## Response: 200 OK

```json
{
  "rows": [
    {
      "id": "uuid",
      "timestamp": "2026-05-08T14:30:00.000Z",
      "actor_id": "uuid-or-null",
      "actor_display_name": "Alice (or 'Orchestrator' or '<deleted-participant 1234abcd>')",
      "action": "remove_participant",
      "action_label": "Facilitator removed participant",
      "target_id": "uuid-or-null",
      "target_display_name": "Bob (or null for session-scoped actions)",
      "previous_value": "string-or-null-or-[scrubbed]",
      "new_value": "string-or-null-or-[scrubbed]",
      "summary": "string-or-null"
    }
  ],
  "total_count": 142,
  "next_offset": 50
}
```

- `rows` is reverse-chronological (`ORDER BY timestamp DESC`).
- `previous_value` / `new_value` ship as `"[scrubbed]"` when the action's registry entry has `scrub_value=true` per FR-014. The unscrubbed values are NOT returned by this endpoint (server-side scrub).
- `action_label` ships as `"[unregistered: <raw_action>]"` if the row's action isn't in the registry per FR-015. The orchestrator emits a WARN log in that case.
- `total_count` reflects the COUNT of rows matching `WHERE session_id = $1 AND <retention_clause>` — i.e., the same scope as the rows page.
- `next_offset` is `null` when no more pages remain; otherwise `offset + len(rows)`.

## Response: 403 Forbidden

```json
{ "error": "facilitator_only", "message": "audit log access requires facilitator role" }
```

Returned when the caller is authenticated but not the facilitator of the requested session.

## Response: 404 Not Found

```json
{ "error": "audit_viewer_disabled", "message": "audit viewer is disabled" }
```

Returned when `SACP_AUDIT_VIEWER_ENABLED=false`. The message is identical for any caller — the master switch hides the existence of the surface.

## Response: 400 Bad Request

```json
{ "error": "invalid_params", "message": "limit must be between 1 and 500" }
```

For `offset < 0`, `limit < 1`, or `limit > 500` (or the env-var-configured max if lower).

## Retention cap behavior

- When `SACP_AUDIT_VIEWER_RETENTION_DAYS` is empty (default), no retention WHERE clause is applied.
- When set to a positive integer N, the query becomes `WHERE timestamp >= NOW() - INTERVAL '{N} days'`.
- Retention applies to viewer DISPLAY only — the underlying `admin_audit_log` table is untouched and remains queryable via spec 010 debug-export (subject to its own retention sweep).

## Side effects

**None.** Per FR-004, the endpoint is read-only. No `admin_audit_log` mutation occurs as a side effect — including no audit-of-the-audit (the act of viewing the log is not itself an audit event).

## Performance contract

Per V14 (plan.md Performance Goals):
- P95 latency ≤ 500ms for sessions with up to 1,000 audit events at default pagination (50 rows/page).
- The query is traced with stage `audit_log_query` into `routing_log` per V14 instrumentation rule.

## Error semantics

- DB query failure → `HTTP 500` with structured error; row count contract violation never silently degrades.
- Registry lookup failure (action not in `LABELS`) → emits WARN log, returns `[unregistered: ...]` label, NOT a 5xx.
- Display-name JOIN miss (deleted participant) → returns the `<deleted-participant ...>` substitute, NOT a 5xx.

## Test surface

Tests in `tests/test_029_audit_log_endpoint.py`:
- T-001: 403 for non-facilitator
- T-002: 403 for facilitator of different session
- T-003: 404 when master switch disabled
- T-004: 200 returns rows in reverse-chronological order
- T-005: 200 includes pagination metadata (next_offset, total_count)
- T-006: scrub_value action returns `[scrubbed]` (cross-ref test_029_scrub.py)
- T-007: unregistered action returns `[unregistered: ...]` (cross-ref test_029_unregistered_action.py)
- T-008: orchestrator-actor row returns `actor_display_name = "Orchestrator"`
- T-009: deleted-participant row returns substitute display name
- T-010: retention cap excludes rows older than the configured days
- T-011: out-of-range `limit` returns 400
