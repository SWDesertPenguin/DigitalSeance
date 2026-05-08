# Contract: `audit_log_appended` WebSocket event

**Spec**: [../spec.md](../spec.md) §FR-010 / FR-014
**Plan**: [../plan.md](../plan.md)
**Status**: Phase 1 contract draft

## Event name

`audit_log_appended`

Mirrors the `<entity>_<verb>` naming convention used by spec 022's `detection_event` and the existing spec 011 events (`participant_update`, `convergence_update`, `review_gate_staged`).

## Trigger

Emitted immediately after every successful `INSERT` into `admin_audit_log` for the active session. The emitter is invoked from `src/repositories/log_repo.py:append_audit_event(...)` when the function is called with a non-null `broadcast_session_id` parameter (per [research.md §7](../research.md)).

## Delivery scope (role-filtered)

Per clarify Q1 (Session 2026-05-08): the event is broadcast **only to facilitator subscribers** via:

```python
broadcast_to_session_roles(
    session_id=session_id,
    roles=["facilitator"],
    event="audit_log_appended",
    payload=decorated_row,
)
```

Non-facilitator participants subscribed to the session WS channel never receive the event. This mirrors spec 011 SR-010's filtered-broadcast pattern and closes the WS leak that would otherwise contradict FR-002's HTTP-side facilitator-only guarantee.

## Payload

Identical to one row from the `GET /tools/admin/audit_log` response (see [audit-log-endpoint.md](./audit-log-endpoint.md)):

```json
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
```

The WS layer wraps this payload in the existing event envelope (handled by `src/web_ui/websocket.py`):

```json
{ "type": "audit_log_appended", "payload": { ... } }
```

### Server-side scrubbing applied to payload

The decorated row goes through `log_repo`'s scrub pass before broadcast — `previous_value` / `new_value` ship as `"[scrubbed]"` when the registry entry's `scrub_value` is `true`. This is defense-in-depth: even if the role-filter ever fails open in a future deployment misconfiguration, the scrub still applies and raw content does not reach a non-facilitator client.

## SPA handling

- The SPA's WS event handler (in `frontend/app.jsx`) routes `audit_log_appended` to the active `AuditLogPanel` instance if mounted; otherwise the event is silently dropped (the panel re-fetches on open per FR-005, so missed pushes are not data loss — the audit log is the durable source of truth).
- The handler renders WS-pushed rows through the same render path as API-fetched rows.
- Deduplication: the panel keeps a `Set<row.id>` and ignores any event whose id is already rendered. This prevents double-render when an HTTP refetch races with a WS push.
- Active filters (FR-027 in spec 011 amendment): if the WS-pushed row doesn't match the active filter, the row is NOT added to the visible set; the filter-control badge increments per FR-013.

## Performance contract

- P95 latency ≤ 2s from `admin_audit_log` INSERT commit to facilitator-client render. Matches spec 022 SC-002.
- Stage timing captured into `routing_log` with stage `audit_log_broadcast` per V14.

## Error semantics

- Decoration failure (registry lookup error, JOIN failure) → log WARN with the action + session_id, fall back to a row with `action_label = "[unregistered: <raw>]"`. The event is still broadcast — partial information is more useful than nothing for the live viewer.
- Broadcast failure (WS layer error) → log ERROR; the underlying `admin_audit_log` INSERT is already committed, so the SPA picks up the row on next panel-open or refresh.
- The WS-broadcast path MUST NOT raise back into the audit-write call site — failures here cannot be allowed to abort or roll back the audit-log INSERT (the durable record is authoritative).

## Test surface

Tests in `tests/test_029_ws_event.py`:
- T-001: emission fires within 2s of an `admin_audit_log` INSERT
- T-002: payload shape matches the FR-001 row schema verbatim
- T-003: role-filtered — facilitator client receives, non-facilitator client does not
- T-004: `scrub_value` action ships `[scrubbed]` over WS (cross-ref test_029_scrub.py T-004)
- T-005: dedupe — SPA receives the event but doesn't double-render if the row was already API-fetched
- T-006: broadcast failure does not abort the underlying INSERT (durability invariant)

## Cross-references

- Existing pattern for role-filtered broadcast: spec 011 SR-010 (`broadcast_to_session_roles` in `src/web_ui/websocket.py`).
- Naming convention parallel: spec 022's `detection_event` (Phase 3+, not yet implemented but the shape is committed in 022's spec).
- Subscriber cap: spec 006 §FR-019 per-session subscriber cap applies — the audit-event broadcast respects the existing cap and does not require independent rate-limiting.
