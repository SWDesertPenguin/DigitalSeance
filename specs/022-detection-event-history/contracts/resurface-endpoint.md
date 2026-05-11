# Contract: `POST /tools/admin/detection_events/<event_id>/resurface`

**Branch**: `022-detection-event-history` | **Date**: 2026-05-10 | **Spec FR**: FR-006..FR-008, FR-016 | **Data model**: [data-model.md](../data-model.md) | **Research**: [research.md §1, §7, §10, §11](../research.md)

## Endpoint

`POST /tools/admin/detection_events/<event_id>/resurface`

## Authentication

Facilitator-only. Same gate as the GET endpoint ([detection-events-endpoint.md](./detection-events-endpoint.md)). Non-facilitator callers receive HTTP 403 `facilitator_only`.

## Master switch

When `SACP_DETECTION_HISTORY_ENABLED=false`, this endpoint MUST return HTTP 404. The route is not registered when the master switch is off.

## Path parameter

`event_id` — synthesized identifier of the shape `<source_table>:<source_row_id>` per [data-model.md](../data-model.md). Examples: `routing_log:42`, `convergence_log:17`, `admin_audit_log:91`. Malformed identifiers return HTTP 400 `invalid_event_id`.

## Request body

Empty (no body required). The action's actor is the authenticated facilitator from the session token; the target is `event_id` from the path. Future enhancements (e.g., re-surface with annotation) would add a JSON body; v1 ships without.

## Server-side flow

1. Validate `event_id` shape (`<table>:<integer>` regex).
2. Authenticate facilitator + session-bind check (FR-007).
3. Verify session is active (FR-008). If archived, return HTTP 409 `session_archived` with body explaining "re-surface requires an active session."
4. Lookup the source row by `event_id` to verify it exists. If not found (e.g., source row purged per retention policy), return HTTP 404 `event_not_found`.
5. Compose the banner payload from the source row.
6. INSERT one row into `admin_audit_log` per [data-model.md](../data-model.md) "Re-surface action row" — action `detection_event_resurface`, actor_id, target_event_id, timestamp.
7. Emit a WS broadcast on the facilitator's per-session channel with the payload — via `src/web_ui/cross_instance_broadcast.py::broadcast_session_event(session_id, payload, kind='resurfaced')`. The broadcast is role-filtered to facilitator subscribers; participant AIs are NOT addressees (per Clarifications §2).
8. Return HTTP 200 with the broadcast envelope and the new audit-row id.

## Response (200 OK)

```json
{
  "event_id": "routing_log:42",
  "audit_row_id": 1037,
  "broadcast": {
    "kind": "resurfaced",
    "event_id": "routing_log:42",
    "event_class": "ai_question_opened",
    "event_class_label": "AI question opened",
    "participant_id": "<participant>",
    "trigger_snippet": "...",
    "detector_score": 0.87,
    "timestamp": "2026-05-10T14:32:01.234Z",
    "disposition": "banner_dismissed"
  },
  "broadcast_path": "same_instance" | "cross_instance"
}
```

| Field | Notes |
|---|---|
| `audit_row_id` | The id of the new `admin_audit_log` row. Useful for follow-up audit-log queries and for the disposition-timeline click-expand view. |
| `broadcast.disposition` | The disposition at the moment of re-surface (NOT mutated by the re-surface — typically `banner_dismissed` since that's the common re-surface trigger). |
| `broadcast_path` | Diagnostic: which path the broadcast took. Useful for the V14 cross-instance budget instrumentation. |

## Error responses

| Status | Code | When |
|---|---|---|
| 400 | `invalid_event_id` | Path `event_id` doesn't match the `<source_table>:<source_row_id>` shape, or `source_table` is not one of `routing_log`/`convergence_log`/`admin_audit_log`. |
| 403 | `facilitator_only` | Caller is authenticated but not a facilitator. |
| 403 | `cross_session_access` | Facilitator is authenticated for a different session than the event's. |
| 404 | (no body) | Master switch off OR session does not exist. |
| 404 | `event_not_found` | Event id is well-formed but the source row no longer exists (purged or never existed). |
| 409 | `session_archived` | Re-surface is disallowed on archived sessions (FR-008). |
| 500 | `internal_error` | Audit INSERT failure or cross-instance broadcast failure (NOT a silent fallback to same-instance-only; failures fail-closed per V15). |

## Cross-instance routing (research §1)

The endpoint MAY be hit on an orchestrator process different from the one holding the facilitator's WS. The broadcast layer (`cross_instance_broadcast.py`) MUST resolve the routing per [research.md §1](../research.md):

- **Same-instance fast path**: if the facilitator's WS connection is in the receiving process's in-memory map, the broadcast emits in-process directly. P95 ≤ 200ms.
- **Cross-instance path**: if the facilitator's WS is not in the local map, emit `NOTIFY detection_events_{session_id}, '<payload>'`. All instances LISTENing on that channel receive the payload; only the instance holding the facilitator's WS rebroadcasts to it. P95 ≤ 500ms (per V14 cross-instance budget).

The endpoint MUST return after the NOTIFY emit, NOT after the receiving instance confirms delivery (which would require a round-trip). Client-side confirmation arrives via the WS payload landing on the facilitator's browser.

## Append-only invariant

The endpoint writes EXACTLY ONE row to `admin_audit_log`. No source-row mutations. No deletes. Spec 001 §FR-008 append-only invariant is preserved.

## Audit trail completeness

Each re-surface action is fully traceable: the new audit row records the facilitator (`actor_id`), the target event (`target_event_id`), and the time (`timestamp`). Subsequent operator actions on the re-surfaced banner (re-acknowledge, re-dismiss) write further `detection_event_*` rows that are visible in the disposition timeline (click-expand fetch).
