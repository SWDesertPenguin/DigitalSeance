# Contract: observer-downgrade audit events

Three new `action` strings written to `admin_audit_log` (no schema change). Cross-ref [data-model.md](../data-model.md#db-persistent-audit-shapes) for the row-level field semantics.

## `observer_downgrade`

**When**: turn-prep evaluator decides to downgrade an active participant to observer because configured thresholds tripped AND the candidate is not the last remaining human.

**Row contract**:
- `action = "observer_downgrade"` (literal string).
- `target_id` is the downgraded participant's ID.
- `previous_value` is a JSON object with keys `role`, `model_tier`, `consecutive_timeouts`, `last_seen` (ISO 8601).
- `new_value` is a JSON object with keys `role` (always `"observer"`), `trigger_threshold` (`"participants"` or `"tpm"`), `observed` (int), `configured` (int).

**Sequencing**: written BEFORE the participant role state mutates in-process. If the audit write fails the role mutation aborts (transactional consistency).

## `observer_restore`

**When**: a previously-downgraded participant has had `tpm` below the threshold for `restore_window_s` sustained, and the evaluator restores them to active.

**Row contract**:
- `action = "observer_restore"`.
- `target_id` is the restored participant's ID.
- `previous_value` is a JSON object with keys `role` (always `"observer"`), `downgraded_at` (ISO 8601 from the matching `observer_downgrade` row).
- `new_value` is a JSON object with keys `role` (the role they had before downgrade), `tpm_observed`, `tpm_threshold`, `sustained_window_s`.

**Pairing**: every `observer_restore` row pairs with exactly one prior `observer_downgrade` row for the same `(session_id, target_id)`. Operators can JOIN on these to compute downgrade duration. Phase 3+ may add a query helper.

## `observer_downgrade_suppressed`

**When**: thresholds tripped and the lowest-priority active candidate is the only remaining human in the session. The downgrade is suppressed (no role mutation). Spec FR-011 / spec edge-case "last human protection".

**Row contract**:
- `action = "observer_downgrade_suppressed"`.
- `target_id` is the participant who would have been downgraded.
- `previous_value` is a JSON object with keys `role`, `model_tier`.
- `new_value` is a JSON object with keys `reason` (always `"last_human_protection"`), `trigger_threshold`, `observed`, `configured`.

**Idempotency**: the evaluator MAY emit one suppressed-row per evaluation cycle while the suppression condition holds; consumers should treat this as informational, not a deduplication burden.

## Cross-cutting

- All three events are append-only via the existing admin_audit_log path (V9 log integrity).
- All three are visible in operator-facing log queries; no separate UI surface in Phase 3 initial delivery (Web UI rendering is a follow-up if operators ask for it).
- `facilitator_id` on every row is the session facilitator at the time of the event (orchestrator acts on their behalf).
