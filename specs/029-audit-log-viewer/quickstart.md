# Quickstart: Human-Readable Audit Log Viewer

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Phase**: 1 (Design & Contracts)
**Date**: 2026-05-08

This walkthrough exercises the end-to-end flow once the spec is implemented. It serves as both an operator-facing onboarding doc and the target shape for the SC-001 Playwright e2e test.

## Prerequisites

- Orchestrator running with the new env vars set:
  - `SACP_AUDIT_VIEWER_ENABLED=true`
  - `SACP_AUDIT_VIEWER_PAGE_SIZE=50` (default; override for high-event sessions)
  - `SACP_AUDIT_VIEWER_RETENTION_DAYS=` (empty default; set for time-bounded views)
- A facilitator account in an active session (any of topologies 1-6).
- At least one non-facilitator participant joined to the session (for the role-filter check).

## Walkthrough

### Step 1 — Open the audit log panel

1. As facilitator, log into the SPA (`/login`).
2. Navigate to your session.
3. Open the facilitator admin panel.
4. Click **"View audit log"** (a new button alongside "Pending approvals", "Invite generation", etc.).
5. The SPA navigates to `/session/{id}/audit`.

**What you should see:** A table with columns `timestamp | actor | action | target | summary`, in reverse-chronological order. Pagination controls at the bottom show page 1 of N.

If you see a "facilitator-only" notice or HTTP 404, check:
- Are you the facilitator of this session? (Non-facilitators get 403 per FR-002.)
- Is `SACP_AUDIT_VIEWER_ENABLED=true`? (`false` returns 404 per FR-018.)

### Step 2 — Verify human-readable labels

The action labels render in English: e.g., `"Facilitator removed participant"` rather than the raw `remove_participant` string. Hover any timestamp — a tooltip shows the same instant in your browser locale + a relative time string ("3 minutes ago").

### Step 3 — Expand a `review_gate_edit` row to see a diff

1. Drive a review-gate edit: as facilitator, edit a draft response from the review-gate queue.
2. The audit log panel updates within ~2 seconds via WebSocket push (`audit_log_appended` event). A new row appears at the top.
3. Click the expand affordance on the new `review_gate_edit` row.
4. The DiffRenderer mounts, showing a side-by-side diff: original draft on the left, edited content on the right. Line-level differences are highlighted.
5. Click the per-row **"show word-level diff"** toggle to drop into word granularity. Click again to return to line mode.

**What you should see:**
- Text values: line-by-line Myers diff with side-by-side rendering.
- JSON values (e.g., a `session_config_change` row): structured key-by-key diff.

For payloads ≥ 50KB, you'll see a brief "computing diff" placeholder while the Web Worker runs. For payloads > 500KB, the renderer falls back to raw values side-by-side without a computed diff.

### Step 4 — Expand a value-less row

Click the expand affordance on an `add_participant` row (no `previous_value` / `new_value`). The expansion shows the row's metadata only — no DiffRenderer is invoked, no empty diff pane appears.

### Step 5 — Apply filters

1. Open the filter controls in the panel header.
2. Select **Action type → "Review gate: draft edited"**. Only rows of that action display.
3. Add **Actor → <a specific facilitator>**. The intersection narrows further.
4. Add **Time range → last 1 hour**. Older rows drop out.

**What you should see:** Filtered set narrows immediately (client-side filter; no network round-trip). Cleared filter restores the full loaded page.

### Step 6 — Watch a WS push arrive while a filter is active

1. With an action-type filter active for `review_gate_edit`:
2. Drive an `add_participant` action (different action type).
3. Watch the filter-control badge increment to `(1 hidden)`. The row is NOT added to the visible set because it doesn't match the filter; the badge tells you something happened outside the filter.
4. Clear the filter — the previously-hidden row appears in the now-unfiltered view. Badge resets.

### Step 7 — Verify scrub-display on `rotate_token`

1. As facilitator, rotate a participant's auth token (`/tools/participant/rotate_token`).
2. A new row appears with action `"Auth token rotated"` (registry label for `rotate_token`).
3. Click expand. The `previous_value` and `new_value` fields render as `[scrubbed]` placeholders — NOT the raw token-hash references.
4. To retrieve the full content, run `GET /tools/debug/export?session_id=<id>` (spec 010 debug-export). The raw values appear in the JSON output (separate authorization, separate audit trail).

### Step 8 — Verify the role-filter

1. Open a second SPA session as a non-facilitator participant in the same session.
2. With the developer console open, watch the WebSocket frames.
3. Drive an audit-emitting action (e.g., facilitator removes a Haiku participant).
4. The non-facilitator client does NOT receive the `audit_log_appended` event — the role-filter at `broadcast_to_session_roles` excludes them.
5. The facilitator client DOES receive the event and renders the new row within 2s.

### Step 9 — Verify the master-switch behavior

1. Set `SACP_AUDIT_VIEWER_ENABLED=false` and restart the orchestrator.
2. Reload the SPA as facilitator.
3. The "View audit log" button is hidden from the admin panel.
4. Direct navigation to `/session/{id}/audit` returns HTTP 404.
5. Existing audit-log writes continue (the `admin_audit_log` table is unaffected — this is a viewer surface, not a writer surface).

## Smoke test summary

A 5-minute smoke test exercising the contract:

```
1. Login as facilitator → /session/{id}/audit
   ✓ Panel renders rows in reverse-chrono with English labels
2. Drive a review_gate_edit
   ✓ New row appears within 2s via WS push
   ✓ Expand → side-by-side diff renders
3. Toggle word-level on the diff
   ✓ Diff recomputes at word granularity
4. Apply action-type filter for "review_gate_edit"
   ✓ Set narrows to matching rows
5. Drive an add_participant
   ✓ Filter-control badge shows (1 hidden); row not in visible set
6. Clear filter
   ✓ Hidden row appears
7. Rotate a token
   ✓ Row appears with [scrubbed] values
8. Open as non-facilitator
   ✓ /session/{id}/audit returns 403
   ✓ WS does not deliver audit_log_appended
9. Set SACP_AUDIT_VIEWER_ENABLED=false, restart
   ✓ Button hidden, route 404
```

## Verification commands

```bash
# CI parity gates (must pass on every PR touching audit_labels or time_format)
python scripts/check_audit_label_parity.py
python scripts/check_time_format_parity.py

# Architectural test (FR-020 — no parallel mappings outside 029)
pytest tests/test_029_architectural.py

# Endpoint contract
pytest tests/test_029_audit_log_endpoint.py

# Server-side scrub
pytest tests/test_029_scrub.py

# Role-filtered WS broadcast
pytest tests/test_029_ws_event.py

# Frontend pure-logic modules (Node-runnable per frontend_polish_module_pattern)
node tests/frontend/test_audit_labels.js
node tests/frontend/test_time_format.js
node tests/frontend/test_diff_engine.js

# End-to-end via Playwright (browser-required; Phase F testability framework)
pytest tests/test_029_e2e.py  # (created when Playwright suite lands per Phase F roadmap)
```

## Operator runbook hooks

When investigating a security incident:
1. Open the audit panel as facilitator (Steps 1-2 above).
2. Filter by actor + time range to scope the review.
3. Expand suspicious rows to inspect diffs.
4. For `[scrubbed]` rows, escalate to a debug-export run (spec 010) for raw value retrieval — note that debug-export has separate authorization and is itself audit-logged.
5. If the panel shows `[unregistered: <action>]` rows, file a registry-update PR — the action exists in code but not in `audit_labels.py`. The orchestrator's WARN log surfaces these too.

## Out of scope (deferred to future enhancements)

- Server-side filter pushdown (Phase 3+ trigger: any operator complaint about filter scope on > 500-event sessions).
- i18n / locale-specific action labels (default-acceptable English-only at v1).
- Diff renderer with semantic-cleanup post-processing (current default is mechanical Myers).
- Audit-export (markdown/CSV download) — debug-export covers JSON export today.
- Filter persistence across page reloads.
- Unread-count badge on the admin-panel "View audit log" button (silent-consume on unmounted panel is the v1 behavior).
