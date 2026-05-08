# Contract: ai-response-shaping audit events

Three new `action` strings written to `admin_audit_log`. No schema change — same pattern as spec 013/014 (cross-ref [data-model.md](../data-model.md#db-persistent-audit-shapes) for row-level field semantics).

## `session_register_changed`

**When**: facilitator sets the session-level slider via INSERT or UPDATE on `session_register`. Fires per change (FR-009: "each change is audit-logged").

**Row contract**:
- `action = "session_register_changed"`.
- `target_id` is the session ID.
- `previous_value` is JSON: `{"slider_value": <old_int_or_null>, "preset": "<old_preset_or_null>"}` (null on first-time set when no prior `session_register` row existed).
- `new_value` is JSON: `{"slider_value": <new_int>, "preset": "<new_preset>"}`.
- `facilitator_id` is the facilitator who set the value (mirrors `set_by_facilitator_id` in the table row).

**Effect on subsequent turns**: per FR-007, the next prompt assembly for any participant without a personal override uses the new preset's Tier 4 delta text. Participants with overrides remain on their override.

## `participant_register_override_set`

**When**: facilitator sets a per-participant override via INSERT or UPDATE on `participant_register_override`. Fires per change (FR-008: "Override changes MUST be recorded in `admin_audit_log` with actor, target participant, old value, new value, and timestamp.").

**Row contract**:
- `action = "participant_register_override_set"`.
- `target_id` is the participant ID (the audit row's subject is the participant; the session is captured in the row's standard `session_id` column).
- `previous_value` is JSON: `{"slider_value": <old_int_or_null>, "preset": "<old_preset_or_null>"}` (null on first-time set when no prior override row existed for this participant).
- `new_value` is JSON: `{"slider_value": <new_int>, "preset": "<new_preset>", "session_slider_at_time": <int>}`. The `session_slider_at_time` field captures what the override was overriding at the moment of set, useful for retroactive audit review.
- `facilitator_id` is the facilitator who set the override.

**Effect on subsequent turns**: per FR-008, only the override-targeted participant's prompt assembly uses the override's preset delta. Other participants are unaffected.

## `participant_register_override_cleared`

**When**: facilitator explicitly clears a per-participant override via DELETE on `participant_register_override`. Does NOT fire on cascade-delete (per [research.md §8](../research.md) — cascade events are bounded by the parent delete's audit row).

**Row contract**:
- `action = "participant_register_override_cleared"`.
- `target_id` is the participant ID.
- `previous_value` is JSON: `{"slider_value": <old_int>, "preset": "<old_preset>"}`.
- `new_value` is JSON: `{"slider_value": null, "fallback_to": "session"}`.
- `facilitator_id` is the facilitator who cleared the override.

**Effect on subsequent turns**: the participant falls back to the session-level register on the next prompt assembly. Their `/me` returns `register_source='session'` from that point forward.

**Distinction from cascade-delete**: when a participant leaves the session OR the session is deleted, the override row vanishes via `ON DELETE CASCADE` per FR-015 / SC-007. No `participant_register_override_cleared` row fires. The audit-visible action is the parent participant-removed or session-deleted event (existing schema). This avoids flooding the audit log on session delete (which can wipe many overrides at once).

## Cross-cutting

- All three events go through the existing append-only `admin_audit_log` path (V9 log integrity).
- `facilitator_id` on every row is the facilitator who made the change (not the session facilitator at large — these can differ if facilitator personnel changes mid-session, though that's outside the spec's scope).
- No Web UI surface in this spec's deliverable. The slider control widget lands in spec 011 (orchestrator-controls UI) per the spec 011 amendment forward-ref. Operators querying the audit log directly use:

```sql
SELECT timestamp, action, target_id, previous_value, new_value
FROM admin_audit_log
WHERE action IN (
    'session_register_changed',
    'participant_register_override_set',
    'participant_register_override_cleared'
)
ORDER BY timestamp DESC LIMIT 50;
```

- `routing_log` carries the per-shaping-decision audit (filler score, retry firing, retry-delta text, retry score, per-stage timings) per FR-011 — this is separate from the `admin_audit_log` register-change audit. The two audit surfaces serve different purposes (per-turn shaping decisions vs facilitator-action register changes).
