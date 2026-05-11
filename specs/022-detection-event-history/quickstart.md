# Quickstart: Detection Event History Surface

**Branch**: `022-detection-event-history` | **Date**: 2026-05-10 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

End-to-end smoke test for the detection event history panel. Runs against a live orchestrator. Validates US1 (panel open + chronological view + live-update), US2 (re-surface with audit trail), US3 (four-axis filtering), and SC-010 (cross-instance re-surface) in a single sweep.

## Prerequisites

- Local stack running per `docs/deployment.md`: `docker compose up` brings up Postgres + orchestrator + Web UI on ports 5432/8000.
- A facilitator account authenticated in a browser tab at `http://localhost:8000` (per spec 002 facilitator flow).
- `SACP_DETECTION_HISTORY_ENABLED=true` in the orchestrator's environment (default off; flip in `.env` and recompose).
- At least one AI participant configured (mock provider per spec 020 works; LiteLLM works for full fidelity).

## Step 1 — Open a session, fire detection events of each class

1. From the facilitator dashboard, click "New session" and configure with 2 AI participants + 1 human (facilitator). Mode: any.
2. Run the session for at least 5 turns. During those turns, you need at least one of each event class to fire. To force them deterministically:
   - **`ai_question_opened`**: have one AI ask a question that goes unresolved on the next turn (A2 tracker fires per spec 004).
   - **`ai_exit_requested`**: have one AI use a clear exit phrase like "I think we're done here" (A3 detector fires per spec 004).
   - **`density_anomaly`**: have one AI produce a high-word-count low-semantic-load response (FR-020).
   - **`mode_recommendation`**: cross the dynamic-mode-assignment threshold per spec 014 advisory mode.
   - **`mode_change`**: switch the session into auto-apply mode (spec 014) and cross the threshold again.

   For deterministic CI runs, the test harness uses `tests/test_022_quickstart_seed.py` which INSERTs synthetic rows directly into `routing_log`, `convergence_log`, and `admin_audit_log` (per [research.md §17](./research.md) fixture pattern).

3. **Expected**: Banners surface in the live UI as each event fires.

## Step 2 — Open the detection history panel and verify all five classes appear

1. In the session header, click "View detection history" (new affordance per spec 011 amendment).
2. The history panel opens at `/session/<session_id>/detection_events` (path settled in [contracts/detection-events-endpoint.md](./contracts/detection-events-endpoint.md)).
3. **Expected**: All five events appear in newest-first chronological order. Each row shows:
   - Event type label (e.g., "AI question opened")
   - Participant id / display name
   - Trigger snippet (truncated to 200 chars with `[expand]` link)
   - Detector score (or `—` for mode events / null-score detectors)
   - Timestamp in UTC ISO-8601
   - Disposition (`pending` for fresh, `banner_acknowledged` / `banner_dismissed` if acknowledged/dismissed during step 1)

## Step 3 — Filter by type, then add participant filter

1. Click the type-filter dropdown; select `density_anomaly`.
2. **Expected**: Only the density-anomaly event remains visible; the hidden-events badge on the type filter shows `(4 hidden)`.
3. Click the participant filter; select one of the two AI participants.
4. **Expected**: If the density-anomaly was for a different participant, the panel becomes empty with "No events match the active filters"; if same participant, the row remains visible.
5. Click "Clear filters".
6. **Expected**: All five events reappear.

## Step 4 — Filter by time range using a preset chip

1. Click the "5m" time-range chip.
2. **Expected**: Only events fired in the last 5 minutes remain visible. All five should remain if the session is fresh; only the most recent if more time has passed.
3. Click "Custom range" and set `from` to a future time.
4. **Expected**: Panel becomes empty with the filter-match empty-state.
5. Reset to `all`.

## Step 5 — Filter by disposition

1. Acknowledge one event from step 1's banner (if not already done) and dismiss another.
2. Click the disposition filter; select `banner_dismissed`.
3. **Expected**: Only the dismissed event remains.
4. Switch to `banner_acknowledged`; verify only the acknowledged event shows.
5. Reset to `all`.

## Step 6 — Re-surface a dismissed event

1. With the disposition filter set to `banner_dismissed`, click the dismissed event row to expand it.
2. Click "Re-surface banner".
3. **Expected**:
   - The original banner reappears in the live UI for re-evaluation.
   - An `admin_audit_log` row is appended with `action='detection_event_resurface'`, `actor_id=<facilitator>`, `target_event_id=<event_id>`.
   - The panel's row for that event remains visible; expanding the disposition timeline shows the original dismissal AND the new re-surface row.

4. Re-acknowledge or re-dismiss the re-surfaced banner.
5. **Expected**: A new disposition transition row appears in the timeline; the panel's row updates to reflect the new disposition.

## Step 7 — Verify archived-session behavior

1. Archive the session via the facilitator action ("End session" or equivalent per spec 011).
2. Reopen the detection history panel (archived sessions are accessible read-only).
3. **Expected**: All five events still visible. Click any event's row; the "Re-surface" button is disabled with tooltip "re-surface requires an active session."
4. Attempt the re-surface POST directly via curl or the browser dev tools:
   `curl -X POST http://localhost:8000/tools/admin/detection_events/<event_id>/resurface ...`
5. **Expected**: HTTP 409 `session_archived` with the explanatory error body.

## Step 8 — Cross-instance re-surface (multi-instance)

This step requires two orchestrator processes against a shared Postgres. Skip if running single-instance.

1. Start a second orchestrator process on port 8001 against the same DB: `PORT=8001 docker compose up -d orchestrator2` (or equivalent per multi-instance docs).
2. In a second browser tab, authenticate as the same facilitator against `http://localhost:8001`. Open the same session's detection history panel. The WS connection binds to port 8001.
3. In the original tab (port 8000), open the panel for the same session, click re-surface on a dismissed event.
4. **Expected**: The re-surfaced banner appears in the second tab (port 8001) within the cross-instance budget (P95 ≤ 500ms). The `admin_audit_log` re-surface row is durable (visible after page refresh on either port).
5. Check the orchestrator logs on port 8001 for `detection_events.resurface_cross_instance_ms` structured-log entries showing the routing latency.

## Step 9 — Verify master-switch behavior

1. Stop the orchestrator, set `SACP_DETECTION_HISTORY_ENABLED=false`, restart.
2. Reload the session page.
3. **Expected**: The "View detection history" entry-point is hidden.
4. Hit the endpoint directly: `curl http://localhost:8000/tools/admin/detection_events?session_id=...`
5. **Expected**: HTTP 404 with no body.

## Pass criteria

All 9 steps complete with expected results. Any deviation gets captured as a follow-up ticket (or, for steps 1-7, a fix on this branch before merge; step 8 is multi-instance and may need its own dev-stack scaffolding which can ride along with the cross-instance broadcast implementation).
