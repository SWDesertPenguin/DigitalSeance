# Contract: Scratch Endpoints

**Spec**: [../spec.md](../spec.md) §FR-002..FR-008, §FR-019, §FR-021
**Plan**: [../plan.md](../plan.md)
**Status**: Phase 1 contract draft

Six new HTTP endpoints under the `/tools/facilitator/scratch/` prefix. All endpoints are gated by:

1. `SACP_SCRATCH_ENABLED=1` — returns HTTP 404 when off (FR-019).
2. Facilitator role check via the existing `get_current_participant` dependency (HTTP 403 for non-facilitators per FR-021).
3. Session-bound: the participant''s `session_id` MUST match the request''s session context.

## §1 — GET /tools/facilitator/scratch?session_id=<id>

Return the full scratch payload for the active session.

Response 200:

```json
{
  "scope": "account",
  "account_id": "<uuid-or-null>",
  "session_id": "<uuid>",
  "notes": [{"id": "<uuid>", "content": "<markdown>", "version": 3, "created_at": "<iso>", "updated_at": "<iso>", "promoted_at": null, "promoted_message_id": null}],
  "summaries": {"items": [{"id": "<msg-uuid>", "turn_range": {"first": 47, "last": 96}, "content_preview": "<200 chars>", "created_at": "<iso>"}], "page": 0, "page_size": 20, "total": 12},
  "review_gate_events": [{"id": "<audit-row-uuid>", "action": "review_gate_edit", "action_label": "Review gate: draft edited", "actor_participant_id": "<uuid>", "actor_display_name": "Alice", "previous_value": "<original>", "new_value": "<edited>", "timestamp": "<iso>"}]
}
```

Errors: 401 (unauth), 403 (non-facilitator), 404 (master switch off OR session not found OR cross-tenant).

## §2 — POST /tools/facilitator/scratch/notes

Create a new note. Request: `{"content": "<markdown>"}`. Response 201: `{"id": "<uuid>", "version": 1, "created_at": "<iso>", "updated_at": "<iso>", "scope": "account", "account_id": "<uuid-or-null>"}`.

Errors: 401 / 403 / 404; 413 over `SACP_SCRATCH_NOTE_MAX_KB`; 422 empty content.

## §3 — PUT /tools/facilitator/scratch/notes/<note_id>

Update an existing note. OCC on `version`. Request: `{"content": "<markdown>", "version": 3}`. Response 200: `{"id": "<uuid>", "version": 4, "updated_at": "<iso>"}`.

Errors: 401 / 403 / 404 / 413; 409 stale write (response body includes current row).

## §4 — DELETE /tools/facilitator/scratch/notes/<note_id>

Soft-delete a note. Response 204.

Errors: 401 / 403 / 404.

## §5 — POST /tools/facilitator/scratch/notes/<note_id>/promote

Promote a note to the transcript. Reuses the existing `inject_message` dispatch path; runs through `_validate_and_persist` (spec 007 §FR-013). Emits one `admin_audit_log` row with `action=''facilitator_promoted_note''`.

Response 200: `{"note_id": "<uuid>", "message_id": "<uuid>", "promoted_at": "<iso>", "audit_row_id": "<uuid>", "status": "promoted"}`. The `status` reflects the security pipeline outcome: `promoted` when content cleared all validators; `review_gate_staged` when content triggered the review-gate threshold.

Errors: 401 / 403 / 404 / 422 (empty); 409 archived session (body: `{"error": "session_archived", "message": "promote-to-transcript requires an active session"}`).

## §6 — GET /tools/facilitator/scratch/summaries?session_id=<id>&page=<n>

Paginated summary archive (FR-011, FR-012). Same shape as the `summaries` block from §1 with offset pagination.

Errors: 401 / 403 / 404; 422 negative page.

## Performance contracts (V14)

| Endpoint | P95 Budget |
|---|---|
| GET /tools/facilitator/scratch | <= 1s |
| POST /tools/facilitator/scratch/notes | <= 200ms |
| PUT /tools/facilitator/scratch/notes/<id> | <= 200ms |
| DELETE /tools/facilitator/scratch/notes/<id> | <= 200ms |
| POST /tools/facilitator/scratch/notes/<id>/promote | <= 500ms |
| GET /tools/facilitator/scratch/summaries | <= 500ms |
