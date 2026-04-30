# Feature Specification: MCP Server

**Feature Branch**: `006-mcp-server`
**Created**: 2026-04-11
**Status**: Draft
**Input**: User description: "MCP server with SSE transport, participant and facilitator tools, auth middleware, session lifecycle, and turn loop control"

## Clarifications

### Session 2026-04-14

- Q: SSE streaming reality check? → A: Keep spec as SSE; current code uses polling — this is a gap. Open follow-up work to implement real SSE streaming.
- Q: CORS policy? → A: Default to localhost + LAN (192.168.0.0/16, 10.0.0.0/8); operator sets SACP_CORS_ORIGINS env for production

### Session 2026-04-14 (fix/sse-streaming)

- SSE gap closed: `GET /sse/{session_id}` implemented via `StreamingResponse` (text/event-stream, no extra deps). `ConnectionManager` (per-session asyncio.Queue fan-out) added to `src/mcp_server/sse.py`. Each completed turn broadcasts `{turn, speaker_id, action, skipped: false}`. Keepalive comment sent every 30 s. Clients needing full message content call `GET /tools/participant/history`. The KNOWN GAP note in Assumptions is now resolved.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Authenticated SSE Connection (Priority: P1)

A participant connects to the MCP server via SSE on port 8750 by providing a bearer token. The server validates the token via the existing auth service, binds the connection to the participant's session, and begins streaming turn updates. Invalid or expired tokens are rejected before any connection is established.

**Why this priority**: No tools work without a connection. This is the entry point for all participant interaction.

**Independent Test**: Can be tested by connecting with valid and invalid tokens and verifying connection acceptance/rejection.

**Acceptance Scenarios**:

1. **Given** a valid bearer token, **When** a participant connects via SSE, **Then** the connection is established and bound to their session.
2. **Given** an invalid or expired token, **When** a connection attempt is made, **Then** it is rejected with a 401 status.
3. **Given** an authenticated connection, **When** a new turn completes in the session, **Then** the turn result is streamed to all connected participants.

---

### User Story 2 - Human Message Injection (Priority: P1)

An authenticated participant can inject a message into their session via the inject_message tool. The message is enqueued in the interrupt queue with the appropriate priority and delivered on the next turn cycle. This is how humans participate in the AI conversation.

**Why this priority**: Message injection is the primary human participation mechanism. Without it, humans can only observe.

**Independent Test**: Can be tested by injecting a message and verifying it appears in the interrupt queue with correct priority and speaker attribution.

**Acceptance Scenarios**:

1. **Given** an authenticated participant, **When** they call inject_message with content and priority, **Then** the message is enqueued in the interrupt queue.
2. **Given** an injected message, **When** the next turn cycle runs, **Then** the interjection is delivered before AI turns.
3. **Given** an unauthenticated caller, **When** they attempt to inject a message, **Then** the request is rejected.

---

### User Story 3 - Session Creation and Lifecycle (Priority: P1)

A facilitator can create new sessions, pause active sessions, resume paused sessions, and archive sessions via dedicated tools. Session creation atomically bootstraps the facilitator participant, main branch, and returns the session details including the facilitator's auth token.

**Why this priority**: Sessions must exist before anything else can happen. Lifecycle management is essential for operational use.

**Independent Test**: Can be tested by creating a session, then transitioning it through pause/resume/archive and verifying state changes.

**Acceptance Scenarios**:

1. **Given** a facilitator, **When** they create a session, **Then** a session is created with a facilitator participant, main branch, and auth token returned.
2. **Given** an active session, **When** the facilitator pauses it, **Then** the status changes to paused and new turns stop.
3. **Given** a paused session, **When** the facilitator resumes it, **Then** the status returns to active.
4. **Given** a session, **When** the facilitator archives it, **Then** it becomes read-only.

---

### User Story 4 - Facilitator Participant Management (Priority: P2)

The facilitator can invite new participants (generating invite links), approve pending participants, reject them, remove active participants, and revoke tokens. All actions are gated by facilitator role and logged to the admin audit log.

**Why this priority**: Multi-participant sessions require participant management. This enables the full join-to-departure lifecycle.

**Independent Test**: Can be tested by creating invites, approving/rejecting participants, and verifying role changes and audit logging.

**Acceptance Scenarios**:

1. **Given** a facilitator, **When** they create an invite, **Then** a single-use invite link is generated and returned.
2. **Given** a pending participant, **When** the facilitator approves them, **Then** their role changes to participant.
3. **Given** an active participant, **When** the facilitator removes them, **Then** the departure logic runs and the action is audit logged.
4. **Given** a non-facilitator, **When** they attempt any facilitator tool, **Then** the request is rejected with a permission error.

---

### User Story 5 - Participant Self-Service (Priority: P2)

Participants can view session status, get conversation history, retrieve summaries, set their routing preference, and rotate their own token. These operations do not require facilitator involvement.

**Why this priority**: Self-service reduces facilitator overhead and gives participants control over their own experience.

**Independent Test**: Can be tested by calling each self-service tool as an authenticated participant and verifying correct responses.

**Acceptance Scenarios**:

1. **Given** an authenticated participant, **When** they call get_status, **Then** they receive session status, participant count, and current turn.
2. **Given** an authenticated participant, **When** they call get_history with a limit, **Then** they receive the N most recent messages.
3. **Given** an authenticated participant, **When** they call set_routing_preference, **Then** their routing mode is updated.
4. **Given** an authenticated participant, **When** they call rotate_token, **Then** they receive a new token and the old one is invalidated.

---

### User Story 6 - Turn Loop Control (Priority: P2)

The facilitator can start and stop the conversation loop for a session. Starting the loop begins executing turns in sequence. Stopping the loop gracefully completes the current turn and halts. The loop state is visible via get_status.

**Why this priority**: The loop must be controllable. Without start/stop, conversations run indefinitely or not at all.

**Independent Test**: Can be tested by starting the loop, verifying turns execute, then stopping and verifying the loop halts.

**Acceptance Scenarios**:

1. **Given** an active session, **When** the facilitator starts the loop, **Then** turns begin executing in sequence.
2. **Given** a running loop, **When** the facilitator stops it, **Then** the current turn completes and the loop halts.
3. **Given** a stopped loop, **When** get_status is called, **Then** the loop state is reported as stopped.

---

### User Story 7 - Session Export (Priority: P3)

A participant can export the conversation transcript as markdown or JSON. The export includes all messages, summaries, and metadata. This is a read-only operation available to any authenticated participant.

**Why this priority**: Export is important for archival but not required for active conversation. Lower priority than real-time interaction.

**Independent Test**: Can be tested by exporting a session with messages and verifying the output format includes all content.

**Acceptance Scenarios**:

1. **Given** a session with messages, **When** a participant exports as markdown, **Then** they receive a formatted transcript with speaker labels and timestamps.
2. **Given** a session with messages, **When** a participant exports as JSON, **Then** they receive a structured JSON array of all messages.

---

### Edge Cases

- What happens when SSE connection drops? The participant can reconnect with the same token. Missed turns are available via get_history.
- What happens when the facilitator disconnects during an active loop? The loop continues running — it operates independently of connections.
- What happens when a tool is called for a session the participant isn't in? The request is rejected — tools are scoped to the participant's authenticated session.
- What happens when two facilitators try to manage the same session? Only one facilitator exists per session (transferred via transfer_facilitator). The second would fail auth.
- What happens when an SSE consumer stops reading? Per FR-013, their bounded queue fills and subsequent broadcasts are dropped silently for that consumer; other subscribers continue receiving events.
- What happens when an unhandled exception bubbles out of a route handler? Per FR-014, the response is a generic 500 JSON; the traceback is logged through the root-logger ScrubFilter so credentials don't leak.
- What happens when a participant rotates their token while an SSE stream is open? Per FR-017 the existing stream is NOT closed in Phase 1; it keeps streaming events until the connection terminates naturally. The new token is required for any subsequent reconnect.
- What happens when a tool returns a very large response (e.g., `get_history` with `limit=10000`)? Per-endpoint Pydantic limits cap input; response sizes are bounded by the underlying repository query limits (default 20 for `get_recent`, 1000 for `get_range`). Pagination is not formalized in Phase 1.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an SSE endpoint on a configurable port (default 8750) for participant connections.
- **FR-002**: System MUST validate bearer tokens via the existing auth service before accepting connections.
- **FR-003**: System MUST stream turn results to all connected participants in a session.
- **FR-004**: System MUST provide an inject_message tool for human message injection into the interrupt queue.
- **FR-005**: System MUST provide session lifecycle tools: create_session, pause_session, resume_session, archive_session.
- **FR-006**: System MUST provide facilitator tools: create_invite, approve_participant, reject_participant, remove_participant, revoke_token, transfer_facilitator.
- **FR-007**: System MUST provide participant self-service tools: get_status, get_history, get_summary, set_routing_preference, rotate_token.
- **FR-008**: System MUST provide turn loop control tools: start_loop, stop_loop (facilitator only).
- **FR-009**: System MUST gate facilitator-only tools by role — non-facilitators receive permission errors.
- **FR-010**: System MUST provide export tools: export_markdown, export_json (any authenticated participant).
- **FR-011**: System MUST reject all tool calls from unauthenticated connections.
- **FR-012**: System MUST scope all tool calls to the participant's authenticated session — no cross-session access.
- **FR-013**: SSE per-subscriber asyncio queues MUST be bounded (default 256 events, see `QUEUE_MAXSIZE` in `src/mcp_server/sse.py`). Broadcasts use `put_nowait` and silently DROP events for wedged consumers whose queues are full — the broadcast loop MUST NOT block on a slow client. Dropped consumers see stale state and re-sync on reconnect via `state_snapshot` (011 §FR-005). This defends against memory-exhaustion DoS via a slow / non-reading SSE client.
- **FR-014**: Unhandled server errors MUST surface as HTTP 500 with a generic JSON body (`{"detail": "Internal server error"}`). The traceback MUST be logged via the root logger (which routes through 007 §FR-012 ScrubFilter) — never returned in the response. FastAPI's default behavior of including the traceback in the response body is explicitly disabled via a global `Exception` handler in `src/mcp_server/app.py:_add_exception_handlers`.
- **FR-015**: OpenAPI / Swagger UI exposure (`/docs`, `/redoc`, `/openapi.json`) MUST be disabled in production. The schema is gated behind `SACP_ENABLE_DOCS=1` env var; default is OFF. Production deployments leave the env var unset so the schema isn't a free reconnaissance surface; dev / on-host troubleshooting opts in.
- **FR-016**: CORS allow-list regex MUST validate octets to the 0-255 range. Pre-fix the LAN regex matched `192.168.999.999` and similar invalid octets; the fixed regex uses `(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)` per octet. Operator overrides via `SACP_CORS_ORIGINS` (CSV of exact origins) bypass the regex entirely.
- **FR-017**: Per-participant SSE connection-count caps and forced-disconnect on token rotation are deferred to Phase 3. Phase 1+2 ship without enforcement: a single participant could open many SSE connections and a token rotation does NOT close existing streams (the new token must be used on the next reconnect; the old stream remains alive until the connection closes naturally or the server restarts). Trigger for Phase 3 work: any deployment that observes participants opening more than `SACP_MAX_SSE_PER_PARTICIPANT` (TBD) connections OR a security incident traceable to a stale-token SSE stream.
- **FR-018**: Per-tool latency MUST be captured into structured request logs (FastAPI access log extended with `tool_name`, `duration_ms`, `participant_id_hash`). Cheap tools (`get_status`, `set_routing_preference`) and expensive tools (`get_history`, `export_json`, `export_markdown`) are differentiated for SLO tracking — see SC-006.
- **FR-019**: SSE per-session subscriber count MUST be bounded by `SACP_MAX_SUBSCRIBERS_PER_SESSION` (default 64). When the cap is reached, additional SSE connection attempts MUST receive HTTP 503 with `{"detail": "subscriber_cap_reached"}` until existing connections drain. The cap × FR-013's 256-event queue × ~1KB-per-event ≈ 16MB/session memory ceiling makes capacity planning concrete. Combined with FR-017's deferred per-participant cap, this prevents a single session from exhausting server memory regardless of participant identity.
- **FR-020**: Request correlation: every API request MUST emit a `request_id` (UUID4) into structured logs. The `request_id` propagates to downstream calls (orchestrator, repositories) via `contextvars` and lands in `routing_log` (cross-ref 003 §FR-030 stage timings) so a single user-visible operation can be traced across MCP API → orchestrator → DB. Without this, multi-table forensics requires guesswork on timestamps.

### Key Entities

- **MCP Connection**: An authenticated SSE stream bound to a participant and session. Receives real-time turn updates.
- **Tool Call**: A request from a connected participant to execute a specific operation (inject, configure, manage).
- **Tool Response**: The result of a tool call, returned to the calling participant.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Authenticated participants can connect and receive turn updates within 2 seconds.
- **SC-002**: All facilitator tools are rejected when called by non-facilitators.
- **SC-003**: Injected messages appear in the interrupt queue within 1 second of the tool call.
- **SC-004**: Session lifecycle transitions (create/pause/resume/archive) complete within 1 second.
- **SC-005**: The server starts and accepts connections on the configured port.
- **SC-006**: Per-tool P95 latency targets: cheap-class tools (config reads, single-row lookups) ≤ 100ms; expensive-class tools (`get_history`, `export_*`) ≤ 1000ms typical-session (cross-ref 010 §SC-005). P99 ≤ 2× P95 for both classes; persistent breaches indicate either DB regression or unbounded data growth.
- **SC-007**: SSE-connection-establishment SLO: P95 connect-to-first-event ≤ 500ms (auth + session-bind + initial-state-snapshot). This decomposes SC-001's 2s aggregate, separating connection cost from steady-state event delivery.
- **SC-008**: Per-session subscriber-cap (FR-019) enforcement: synthetic-load test with 65 simultaneous SSE attempts on a single session MUST result in exactly 64 successful connections and 1 HTTP 503; the 503 response body MUST equal `{"detail": "subscriber_cap_reached"}` with no internal counter state leaked.

## Assumptions

- Phase 1 uses simple SSE streaming, not the full MCP protocol SDK. MCP protocol compliance is a future enhancement.
- The SSE endpoint serves as the connection mechanism. Tool calls are HTTP POST endpoints alongside the SSE stream.
- SSE stream endpoint implemented in fix/sse-streaming (2026-04-14). `GET /sse/{session_id}` streams `data: {turn, speaker_id, action, skipped}` events. Clients reconnect with the same token; missed turns available via `GET /tools/participant/history`.
- CORS wildcard replaced in fix/cors-restrict (2026-04-14). Default: localhost + RFC-1918 LAN ranges via `allow_origin_regex`. Override: `SACP_CORS_ORIGINS` env var (comma-separated exact origins).
- One SSE connection per participant per session is the *intended* deployment pattern; Phase 1+2 do NOT enforce it (see FR-017). Reconnection is supported with the same token.
- The turn loop runs in-process as an asyncio task. Not a separate process.
- Per-participant rate limiting is shipped per spec [009-rate-limiting](../009-rate-limiting/spec.md) §FR-006 — applied via `RateLimiter.check()` inside `get_current_participant` after authentication. The earlier "deferred to a later hardening pass" wording in this spec was retired when 009 landed.
- CORS defaults to localhost + LAN ranges (127.0.0.1, 192.168.0.0/16, 10.0.0.0/8) via `allow_origin_regex`, with octet validation per FR-016. Operators override via `SACP_CORS_ORIGINS` (comma-separated exact origins).
- CSP / HSTS / X-Content-Type-Options / X-Frame-Options / Referrer-Policy / Permissions-Policy headers are NOT applied to MCP API responses in Phase 1 — the Web UI app (port 8751, spec 011) sets those for HTML rendering. Adding parallel security-headers middleware to the MCP API is a Phase 3 hardening pass; trigger: any deployment exposing the MCP API directly to a browser (rather than through the Web UI proxy) OR a third-party security audit finding.
- Per-tool input validation (length caps, type enforcement) is per-endpoint via Pydantic `BaseModel` request bodies; lengths are codified at the endpoint (e.g., `MAX_MESSAGE_CONTENT_CHARS = 2_000` in `src/mcp_server/tools/participant.py`). There is no global request-body size limit beyond uvicorn defaults.

## Threat model traceability

| FR | Defends against | OWASP API / LLM | NIST SP 800-53 |
|----|-----------------|------------------|----------------|
| FR-001, FR-002 (SSE auth) | Unauthenticated session attachment | API1, API2 | AC-3, IA-2 |
| FR-003 (turn streaming) | Information disclosure via cross-session leak | API3 | AC-3, AC-21 |
| FR-004, FR-005 (inject + lifecycle tools) | Privilege escalation via tool invocation | API3 | AC-3 |
| FR-006, FR-009 (facilitator-only gating) | Privilege escalation | API3 | AC-3, AC-6 |
| FR-007 (self-service) | Cross-participant authority confusion | — | AC-3 |
| FR-008 (loop control) | Unauthorized session manipulation | API3 | AC-3 |
| FR-010 (export) | Confidentiality / data exfiltration | API3 | AC-21 |
| FR-011 (no anonymous tools) | Anonymous reconnaissance | API1 | AC-3 |
| FR-012 (session scoping) | Cross-session data access | API3 | AC-3 |
| FR-013 (bounded SSE queue + drop wedged) | Memory exhaustion DoS via slow consumer | API4, LLM04 | SC-5 |
| FR-014 (generic 500 + scrubbed log) | Stack-trace credential leak in error response | API3 | SI-15, AU-9 |
| FR-015 (docs gated) | Free schema reconnaissance | API1 | SC-7 |
| FR-016 (CORS octet validation) | Origin spoofing via crafted invalid IPs | API8 | SC-7 |
| FR-017 (per-participant SSE caps deferred) | (accepted residual: no per-participant limit Phase 1) | — | — |

Sister cross-references: token validation (FR-002) uses 002 §FR-001 + 002 §FR-022; rate limiting on tool calls is 009 §FR-006; output validation on AI responses runs in the turn loop, not the MCP layer (007); debug-export sensitive-field stripping is 010 §FR-4; security headers for HTML responses are 011 §SR-001 / SR-002 (Web UI only in Phase 1).

## Audit closeout (2026-04-29)

The security-requirements quality audit (`checklists/security.md`) raised 40 findings; resolution split:

**Code changes**:
- CHK029 (bounded SSE queue with drop-on-full — `ConnectionManager` now uses `asyncio.Queue(maxsize=256)` and `put_nowait` so wedged consumers can't memory-exhaust the broadcast loop).
- CHK010 (global `Exception` handler returns generic 500 + logs traceback through root-logger ScrubFilter — pre-fix FastAPI's default leaked tracebacks in the response body).
- CHK014 (`/docs`, `/redoc`, `/openapi.json` disabled by default; gated behind `SACP_ENABLE_DOCS=1` env var).
- CHK002 (CORS LAN regex octets validated 0-255; pre-fix regex matched `192.168.999.999`).

**Spec amendments (this commit)**: CHK002 / CHK016 (FR-016 octet validation), CHK010 / CHK014 (FR-014 generic-500 mandate), CHK013 / CHK029 (FR-013 bounded queue + drop semantics), CHK014 / CHK015 (FR-015 docs gating), CHK017 / CHK034 (FR-013 keepalive cadence + per-tool input validation reference), CHK031 / CHK037 (FR-017 codifies "no per-participant SSE caps Phase 1, no force-close on rotation Phase 1" as accepted residual + Phase 3 trigger), CHK032 (Threat-model traceability table), CHK035 (Assumption "rate limiting deferred" replaced with "shipped per 009").

**Closed as cross-reference / accepted residual**: CHK001 (token validated via Depends before stream opens — confirmed correct), CHK003 / CHK004 (security headers on MCP — accepted residual; Web UI is the HTML surface, MCP is JSON-only; Phase 3 trigger documented in Assumptions), CHK005 (WebSocket origin validation — Web UI's SR-004 is the authoritative requirement; MCP doesn't expose WebSockets), CHK006 (role-check at endpoint level via inline `participant.role` comparison or `_require_facilitator_or_inviter` helper), CHK007 (cross-session rejection via FR-012 + FR-022 of 002), CHK008 (per-tool Pydantic length caps — see Assumptions update), CHK009 (cross-session error shape — FR-012 + 401/403/404 conventions), CHK011 (uniform shape via `JSONResponse({"detail": ...})`), CHK012 (error-information leakage — accepted residual; "session not found" vs "not accessible" wording standardized in tools), CHK015 (debug export role-gated — confirmed at `debug.py` `participant.role != "facilitator"`), CHK018 (`_require_facilitator_or_inviter` is the SSOT for role check), CHK019 (pending access — 002 §FR-020 + §FR-021 are authoritative), CHK020 (CORS knob naming — `SACP_CORS_ORIGINS` is the canonical override), CHK021 (auth + WebUI error shape uniform via FastAPI `HTTPException`), CHK022 / CHK023 (per-endpoint vs aggregate testability — accepted; CI test_mcp_e2e covers both), CHK024 (negative-path SCs — implicit), CHK025 (SSE drop recovery — Edge Case + 011 §FR-005), CHK026 (concurrent tool calls per participant — covered by 009 rate limit), CHK027 (server restart — clients reconnect with same token), CHK028 (very-large response bodies — Edge Case clarifies; pagination Phase 3), CHK030 (HTTP smuggling / header injection — uvicorn defaults handle most; accepted residual), CHK033 (request-id / per-tool latency metrics — accepted residual; basic FastAPI logging covers it), CHK036 (uvicorn auth-header logging — disabled by default in uvicorn ≥0.30; accepted residual), CHK038 (login / invite-redemption are unauthenticated by definition; cross-ref 009 §FR-010 unauth-fallback deferred), CHK039 ("scope all tool calls" interpreted as match-token-session-id), CHK040 (URL session_id vs token session_id match enforced at `sse_router.py` — confirmed).

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): Topologies 1–6 (orchestrator-driven, participants connect via SSE). Topology 7 (MCP-to-MCP peer-to-peer) uses a different transport — peers running in desktop clients (Claude Desktop, ChatGPT app) via client-local MCP, not network SSE. Phase 1 ships 1–6; topology 7 integration is Phase 2+.

**Use cases** (per constitution §1): Serves all scenarios by providing the human-AI interface (message injection, routing preference, token rotation, loop control). Especially critical for zero-trust cross-org and consulting, where humans must actively steer the conversation in real-time.
