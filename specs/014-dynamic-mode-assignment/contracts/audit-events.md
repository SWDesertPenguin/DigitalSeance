# Contract: dynamic-mode-assignment audit events

Five new `action` strings written to `admin_audit_log`. No schema change — same pattern as spec 013 (cross-ref [data-model.md](../data-model.md#db-persistent-audit-shapes) for row-level field semantics).

## `mode_recommendation`

**When**: controller decision cycle produces an action that differs from `ControllerState.last_emitted_action`. Fires in BOTH advisory and auto-apply modes (FR-005).

**Row contract**:
- `action = "mode_recommendation"`.
- `target_id` is the session ID (the audit row's subject is the session, not a participant).
- `previous_value` is JSON: `{"action": "<previous_action>"}` or `null` for first emission.
- `new_value` is JSON: `{"action", "triggers", "signal_observations", "dwell_floor_at"}`.

**Multiple-trigger note**: `triggers[]` is alphabetically sorted by signal name (per spec acceptance scenario 3). The `signal_observations` array contains one entry per triggering signal in the same order.

## `mode_transition`

**When**: `SACP_AUTO_MODE_ENABLED=true` AND a recommendation fires AND the dwell floor permits it. The controller engages or disengages spec-013 mechanisms whose env vars are set.

**Row contract**:
- `action = "mode_transition"`.
- `target_id` is the session ID.
- `previous_value` is JSON: `{"action": "<previous_action>", "engaged_mechanisms": [...]}`.
- `new_value` is JSON: full `ModeTransition` shape — adds `engaged_mechanisms[]` and `skipped_mechanisms[]` (spec-013 mechanisms whose env vars are NOT set; controller skipped them silently per spec edge case).

**Pairing**: every transition pairs with a corresponding `mode_recommendation` row at the same `decision_at`. Operators can JOIN on `(target_id, decision_at)` to trace recommendation → transition.

## `mode_transition_suppressed`

**When**: auto-apply would have fired a transition but the dwell floor blocks it (FR-008).

**Row contract**:
- `action = "mode_transition_suppressed"`.
- `target_id` is the session ID.
- `previous_value` is JSON: `{"current_action": "<current_action>"}`.
- `new_value` is JSON: `{"would_have_fired", "reason": "dwell_floor_not_reached", "eligible_at"}`.

**Idempotency**: the controller MAY emit one suppressed-row per decision cycle while the dwell condition holds; consumers should treat this as informational. The dwell-floor `eligible_at` is the authoritative "when can the next transition fire" timestamp.

## `decision_cycle_throttled`

**When**: token-bucket budget rejects a decision-cycle attempt (rate cap exceeded). The cycle is dropped, not queued (FR-002).

**Row contract**:
- `action = "decision_cycle_throttled"`.
- `target_id` is the session ID.
- `previous_value` is JSON: `{"cap_per_minute": <int>, "last_cycle_at": "<iso>"}`.
- `new_value` is JSON: `{"reason": "rate_cap_exceeded", "next_eligible_at": "<iso>"}`.

**Rate limit**: at most one `decision_cycle_throttled` row per dwell window per session (FR-013). Suppressed throttle events DO NOT emit additional audit rows; they just decrement the bucket.

## `signal_source_unavailable`

**When**: a signal source's data feed is unavailable (e.g., convergence engine has not produced a similarity yet, or the density module reports no recent measurements).

**Row contract**:
- `action = "signal_source_unavailable"`.
- `target_id` is the session ID.
- `previous_value` is JSON: `{"signal": "<name>", "last_known_state": "<state>"}`.
- `new_value` is JSON: `{"signal": "<name>", "since": "<iso>", "rate_limited_until": "<iso>"}`.

**Rate limit**: at most one row per dwell window per signal per session (FR-013). The `rate_limited_until` field tells operators when the next emission is eligible if the source remains unavailable.

## Cross-cutting

- All five events go through the existing append-only `admin_audit_log` path (V9 log integrity).
- `facilitator_id` on every row is the session facilitator at the time of the event.
- No Web UI surface in initial Phase 3 delivery — operators query the audit log directly. UI rendering is a future amendment if requested.
