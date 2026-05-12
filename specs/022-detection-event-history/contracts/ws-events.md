# Contract: WebSocket events — `detection_event_appended` and `detection_event_resurfaced`

**Branch**: `022-detection-event-history` | **Date**: 2026-05-10 (initial); **Amended 2026-05-11** (event_id is now integer; emission gated on detection_events INSERT commit) | **Spec FR**: FR-006, FR-009 | **Data model**: [data-model.md](../data-model.md) | **Research**: [research.md §1, §10, §11](../research.md)

Spec 022 introduces two new WebSocket events on the existing spec 011 per-session WS channel. Both events are role-filtered to facilitator subscribers via `broadcast_to_session_roles(session_id, ['facilitator'], payload)` (the pattern established in spec 029 for `audit_log_appended`).

## Event: `detection_event_appended`

Emitted when a new `detection_events` row is INSERTed for an active session — i.e., after one of the four detector emit sites successfully dual-writes per FR-017.

### Emission point

The emitter sits in `src/web_ui/events.py::emit_detection_event_appended(session_id, detection_event_id)`. Called immediately after the `detection_events` INSERT commits (the call-site sweep covers the four emit sites: question/exit in loop.py, density-anomaly in density.py, mode events in the spec 014 emit sites). If the INSERT fails, this emitter is NOT called — the existing per-class WS broadcast (e.g., `ai_question_opened`) still fires per the FR-017 dual-write fail-soft contract.

### Payload

```json
{
  "type": "detection_event_appended",
  "session_id": "<session>",
  "event": {
    "event_id": 1037,
    "event_class": "ai_question_opened",
    "event_class_label": "AI question opened",
    "participant_id": "<participant>",
    "trigger_snippet": "...",
    "trigger_snippet_truncated": false,
    "detector_score": 0.87,
    "turn_number": 14,
    "timestamp": "2026-05-11T14:32:01.234Z",
    "disposition": "pending"
  }
}
```

| Field | Notes |
|---|---|
| `type` | Fixed literal `detection_event_appended`. |
| `event` | Identical shape to the GET endpoint's event row, with the addition of `trigger_snippet_truncated`. |
| `event.trigger_snippet` | Truncated to 1000 chars server-side BEFORE emission to stay under the Postgres NOTIFY 8000-byte limit per [data-model.md](../data-model.md). |
| `event.trigger_snippet_truncated` | True if truncation occurred. Client refetches full snippet via the REST GET endpoint on click-expand. |
| `event.disposition` | Always `pending` for a fresh event (no transition rows exist yet). |

### Role filter

Recipients are facilitator WS subscribers on the session's channel. Participant subscribers do NOT receive this event. The role filter is enforced server-side in `broadcast_to_session_roles`; clients cannot opt in.

### Cross-instance contract

Per [research.md §1](../research.md), the broadcast MUST reach the facilitator's WS regardless of which orchestrator process holds the connection:

- **Same-instance**: broadcast in-process directly. P95 ≤ 100ms server-to-client (matches V14 budget).
- **Cross-instance**: emit `NOTIFY detection_events_{session_id}, '<payload>'`; the instance holding the facilitator's WS receives the NOTIFY via its LISTEN connection and rebroadcasts in-process. Cross-instance budget absorbed by V14 cross-instance Re-surface budget (P95 ≤ 500ms — same routing path used).

## Event: `detection_event_resurfaced`

Emitted when an operator clicks the re-surface button on a previously-dispositioned event. Re-broadcasts the banner shape so the facilitator's live UI re-renders the banner for re-evaluation.

### Emission point

The emitter is `cross_instance_broadcast.broadcast_session_event(session_id, payload, kind='resurfaced')` called from the FR-006 POST handler in `src/web_ui/detection_events.py`. Emission happens AFTER the `admin_audit_log` re-surface row is INSERTed (so the audit trail is durable before the broadcast).

### Payload

```json
{
  "type": "detection_event_resurfaced",
  "session_id": "<session>",
  "event": {
    "event_id": 1037,
    "event_class": "ai_question_opened",
    "event_class_label": "AI question opened",
    "participant_id": "<participant>",
    "trigger_snippet": "...",
    "trigger_snippet_truncated": false,
    "detector_score": 0.87,
    "turn_number": 14,
    "timestamp": "2026-05-11T14:32:01.234Z",
    "disposition": "banner_dismissed"
  },
  "resurface_audit_row_id": 2491
}
```

| Field | Notes |
|---|---|
| `type` | Fixed literal `detection_event_resurfaced`. |
| `event` | Identical shape to `detection_event_appended.event`, with `event.disposition` carrying the disposition at the moment of re-surface (NOT mutated by re-surface). |
| `resurface_audit_row_id` | The id of the audit row written by FR-006. Useful for the SPA to cross-reference the disposition timeline. |

### Role filter

Same as `detection_event_appended`: facilitator subscribers only. Participant AIs do NOT see this event (per Clarifications §2; FR-006 corrected wording).

### Cross-instance contract

Same as `detection_event_appended` — Postgres LISTEN/NOTIFY for cross-instance, in-process for same-instance.

## Client-side handling (frontend/app.jsx)

The SPA's `DetectionHistoryPanel` React component subscribes to both events via the existing spec 011 WS connection. On `detection_event_appended`:

1. Insert the event row at the top of the panel (newest-first default per [research.md §12](../research.md)).
2. If the active filter set excludes the event, increment the hidden-events badge and skip the insertion (per US3 acceptance scenario 3).
3. Update the disposition timeline if the panel is currently rendering one for the same event id.

On `detection_event_resurfaced`:

1. Trigger the spec 011 banner-rendering pipeline with the `event` payload (same code path as a fresh banner from `detection_event_appended` would trigger).
2. Update the disposition timeline (if open) with the new `detection_event_resurface` row.
3. The panel's row for the re-surfaced event stays in place — disposition remains the same (re-surface does NOT mutate it).

## Event identity and idempotency

Both events carry `event.event_id` (the synthesized `<source_table>:<source_row_id>` identifier). Clients MAY use this for idempotency — if a network blip causes a duplicate WS delivery, the client compares `event_id` against the rendered set and de-dupes. This is best-effort; the server does NOT guarantee at-most-once delivery for the WS layer.

## V14 budget alignment

- `detection_event_appended` P95 ≤ 100ms (live-update budget).
- `detection_event_resurfaced` P95 ≤ 200ms same-instance / ≤ 500ms cross-instance (re-surface budgets).
- The cross-instance routing path is shared between live-update and re-surface; one instrumentation hook in `cross_instance_broadcast.py` covers both.
