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

## Assumptions

- Phase 1 uses simple SSE streaming, not the full MCP protocol SDK. MCP protocol compliance is a future enhancement.
- The SSE endpoint serves as the connection mechanism. Tool calls are HTTP POST endpoints alongside the SSE stream.
- SSE stream endpoint implemented in fix/sse-streaming (2026-04-14). `GET /sse/{session_id}` streams `data: {turn, speaker_id, action, skipped}` events. Clients reconnect with the same token; missed turns available via `GET /tools/participant/history`.
- CORS wildcard replaced in fix/cors-restrict (2026-04-14). Default: localhost + RFC-1918 LAN ranges via `allow_origin_regex`. Override: `SACP_CORS_ORIGINS` env var (comma-separated exact origins).
- One SSE connection per participant per session. Reconnection is supported with the same token.
- The turn loop runs in-process as an asyncio task. Not a separate process.
- Rate limiting per participant is deferred to a later hardening pass.
- CORS defaults to localhost + LAN ranges (127.0.0.1, 192.168.0.0/16, 10.0.0.0/8) via `allow_origin_regex`. Operators override via `SACP_CORS_ORIGINS` (comma-separated exact origins). CSP headers are minimally configured for Phase 1.

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): Topologies 1–6 (orchestrator-driven, participants connect via SSE). Topology 7 (MCP-to-MCP peer-to-peer) uses a different transport — peers running in desktop clients (Claude Desktop, ChatGPT app) via client-local MCP, not network SSE. Phase 1 ships 1–6; topology 7 integration is Phase 2+.

**Use cases** (per constitution §1): Serves all scenarios by providing the human-AI interface (message injection, routing preference, token rotation, loop control). Especially critical for zero-trust cross-org and consulting, where humans must actively steer the conversation in real-time.
