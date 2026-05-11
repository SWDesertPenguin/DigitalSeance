# Contract: `GET /tools/admin/detection_events`

**Branch**: `022-detection-event-history` | **Date**: 2026-05-10 (initial); **Amended 2026-05-11** (§1 reversal — single-table SELECT, integer event_id) | **Spec FR**: FR-001..FR-005, FR-011..FR-013, FR-015, FR-017 | **Data model**: [data-model.md](../data-model.md) | **Research**: [research.md §2, §4, §5, §8](../research.md)

## Endpoint

`GET /tools/admin/detection_events`

## Authentication

Facilitator-only. Reuses the spec 010 `/tools/admin/*` authentication pattern (session token validated, role check enforces `facilitator`). Non-facilitator callers MUST receive HTTP 403 with error code `facilitator_only` and a structured body matching spec 010 §FR-2.

## Master switch

When `SACP_DETECTION_HISTORY_ENABLED=false` (default), this endpoint MUST return HTTP 404 (per FR-016 / spec 029 FR-018 pattern). The route is not registered when the master switch is off; the SPA's admin-panel entry-point is also hidden.

## Query parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `session_id` | string | yes | — | Session whose detection events are requested. Facilitator MUST be authorized for this session (FR-003 session-bound check). Unauthorized cross-session access returns HTTP 403. |
| `max_events` | integer | no | `SACP_DETECTION_HISTORY_MAX_EVENTS` (default unbounded for active session) | Cap on returned rows; applied server-side via SQL `LIMIT`. Newest events kept when cap is hit. |
| `since` | ISO-8601 timestamp | no | (none) | Optional lower bound on `timestamp`; for retention-respecting fetches of archived sessions. The four client-side filter axes (FR-011) do NOT use this parameter — they apply over the loaded set. |

Filter axes (type, participant, time-range, disposition) are client-side per FR-011; the endpoint returns the full per-session event set (bounded by `max_events`) and the SPA filters in memory.

## Response (200 OK)

```json
{
  "session_id": "<session>",
  "events": [
    {
      "event_id": 1037,
      "event_class": "ai_question_opened",
      "event_class_label": "AI question opened",
      "participant_id": "<participant>",
      "trigger_snippet": "...",
      "detector_score": 0.87,
      "turn_number": 14,
      "timestamp": "2026-05-11T14:32:01.234Z",
      "disposition": "pending",
      "last_disposition_change_at": null
    }
  ],
  "count": 1,
  "max_events_applied": false,
  "as_of": "2026-05-11T14:35:00.000Z"
}
```

| Field | Notes |
|---|---|
| `events` | Array of `DetectionEvent` projections per [data-model.md](../data-model.md). Sorted newest-first; client can re-sort. |
| `count` | Number of returned events. |
| `max_events_applied` | True if the SQL `LIMIT` was hit (newer events kept, older events dropped — operator should consider raising the cap if this is true). |
| `as_of` | Server timestamp at query time. Useful for client-side reconciliation with subsequent WS pushes (FR-009). |

## Error responses

| Status | Code | When |
|---|---|---|
| 400 | `invalid_session_id` | `session_id` is missing or not a valid UUID/identifier shape. |
| 403 | `facilitator_only` | Caller is authenticated but not a facilitator. |
| 403 | `cross_session_access` | Facilitator is authenticated for a different session. |
| 404 | (no body) | Master switch off OR session does not exist. (Master-switch-off returns 404 with no distinguishing detail to avoid information disclosure.) |
| 500 | `internal_error` | Query failure; logged with full traceback server-side. |

## Read-only invariant

The GET endpoint MUST NOT issue any INSERT, UPDATE, or DELETE against `detection_events`, `routing_log`, `convergence_log`, `messages`, or any other source table. The two write paths spec 022 allows are:

1. INSERT on `detection_events` at the four detector emit sites (FR-017 dual-write, NOT this endpoint).
2. UPDATE on `detection_events.disposition` + INSERT on `admin_audit_log` from the disposition-transition handler (FR-010, NOT this endpoint).
3. INSERT on `admin_audit_log` at the FR-006 re-surface endpoint (separate contract).

The architectural test `tests/test_022_architectural.py` enforces this by asserting the endpoint module imports no write-side helpers.

## Performance budget (V14)

P95 ≤ 500ms for sessions with up to 1,000 detection events. The query is a single-table `WHERE session_id = $1 ORDER BY timestamp DESC LIMIT $2` against the indexed `detection_events_session_timestamp_idx`. No JOINs (disposition is denormalized into the row). Instrumentation per [research.md §15](../research.md).
