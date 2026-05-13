# Feature Specification: MCP Build — Codebase Restructure, Protocol Implementation, Tool Mapping, OAuth 2.1, and Participant Onboarding Documentation

**Feature Branch**: `030-mcp-build`
**Created**: 2026-05-13
**Status**: Draft (Phase 3 prerequisite — five-phase build correcting the misnamed `src/mcp_server/` module and shipping actual MCP protocol support; phases A→B+C→D→E sequence with B+C co-designed)
**Input**: User description: "The repo's `src/mcp_server/` is misnamed — it does not implement the Model Context Protocol. It is SACP's participant-facing FastAPI surface plus a `/sse/{session_id}` SACP turn-event stream. This build is a five-phase sequence that (1) renames the misnamed module to `src/participant_api/` and reserves `src/mcp_protocol/` for the actual MCP layer; (2) implements the MCP protocol over Streamable HTTP per MCP spec revision 2025-11-25 (SSE intentionally skipped — the revision deprecates it); (3) defines the tool surface mapping every public `participant_api` capability to a named, JSON-Schema'd, error-contracted MCP tool with scope binding; (4) layers OAuth 2.1 + PKCE on the MCP endpoint per Constitution §10 Phase 3 roadmap with per-participant token isolation, refresh rotation, discovery metadata, Client ID Metadata Documents, scope binding to phase 3's vocabulary, step-up for destructive actions, and a controlled migration off static tokens; (5) ships participant onboarding documentation deliverables covering the cross-platform overview, Windows-specific gotchas (8.3 short paths, env-var workarounds, PowerShell vs cmd.exe, Defender stall, CRLF vs LF), and macOS-specific gotchas (config-file path, xattr quarantine handling). Phase 1 is pure refactor with no behavior change. Phases 2 and 3 are co-designed. Phase 4 layers OAuth onto phases 2+3. Phase 5 documentation can ship earlier as the SACP participant API docs surface."

## Overview

The directory `src/mcp_server/` in this repo does not implement the Model Context Protocol. A scan for the canonical MCP imports (`from mcp`, `import mcp`, `SseServerTransport`, `FastMCP`) returns no hits across `src/`. The routers under `src/mcp_server/tools/` (`admin`, `debug`, `detection_events`, `facilitator`, `participant`, `proposal`, `provider`, `session`, plus the scratch surface introduced by spec 024 when it lands) are FastAPI HTTP routers serving SACP's participant-facing API. The module's only `sse` surface, `/sse/{session_id}`, streams SACP turn events of the shape `{turn, speaker_id, action, skipped}` — not the MCP `endpoint` event MCP clients expect from a Streamable HTTP or SSE transport handshake. The name is historical noise: spec 006 (mcp-server) shipped this module under a label that anticipated a future MCP layer, the layer never landed, and the surface evolved into SACP's native API instead. The divergence was identified during a 2026-05-12 debug session that attempted to connect Claude Desktop on Windows to a running orchestrator instance via `mcp-remote`; the session walked through several layers (network reachability, route existence, bearer authentication, session-id match) before stalling on the misnamed-module discovery AND exposing significant cross-platform onboarding friction along the way.

This build is the five-phase sequence that corrects the misnaming AND lands actual MCP protocol support AND documents the participant flow. Phase 1 (codebase restructure) is a behavior-preserving rename: every file moves from `src/mcp_server/` to `src/participant_api/` via `git mv` so blame history is preserved, the factory function `create_mcp_app` is renamed to `create_participant_api_app`, all internal/test/migration/docs/deployment references are updated, and an empty `src/mcp_protocol/` namespace is reserved for Phase 2. Phase 2 (MCP protocol over Streamable HTTP) populates `src/mcp_protocol/` with the wire-format transport, the dispatcher, session lifecycle, error model, and protocol-version negotiation pinned to the 2025-11-25 spec revision (SSE intentionally skipped per the revision's deprecation). Phase 3 (SACP-to-MCP tool mapping) populates the `ToolRegistry` Phase 2's dispatcher reads — every public `participant_api` capability surfaces as a named tool with JSON Schema params and returns, error contract, scope requirement, AI-accessibility flag, idempotency and pagination support, and V14 budget. Phase 4 (OAuth 2.1 + PKCE) layers the authorization server surface onto the MCP endpoint with per-participant token isolation, refresh rotation, discovery metadata, Client ID Metadata Documents, scope binding to Phase 3's vocabulary, step-up for destructive actions, AI-participant exclusion (BYOK stays), and a controlled migration off static tokens. Phase 5 (participant onboarding docs) ships `docs/participant-onboarding.md` (cross-platform overview), `docs/participant-onboarding-windows.md` (Windows gotchas), and `docs/participant-onboarding-macos.md` (macOS content); Phase 5 v1 documents the current SACP participant API surface and reserves a Phase-3-OAuth migration section that content-fills when Phase 4 lands.

The phase ordering is A → B+C (co-designed; may merge in either order so long as registry-shape contracts hold) → D (depends on B+C stable AND on sovereignty remediation completing) → E (documentation deliverable that can ship in parallel with the others, but content-evolves as each phase lands). Phase 1 blocks Phases 2/3/4: none can begin until the namespace rename is on main. Phase 5 doc surface depends on Phases 1-4 for the eventual updates but ships v1 against the existing SACP-native surface and updates via versioned cross-references as each phase lands.

This build re-uses three established patterns from the existing spec base: the cross-instance routing pattern from spec 022 (Postgres LISTEN/NOTIFY or Redis pub/sub per 022's research-resolved choice) for MCP request routing when an MCP client connected to instance A targets a SACP session bound to instance B; the spec 019 rate-limiter middleware applied uniformly across MCP and participant_api surfaces with a shared per-bearer/per-account bucket; and the spec 023 Fernet API-key encryption pattern for refresh-token at-rest storage in Phase 4. The build also depends on the spec 023 sponsor model for the `sponsor` scope value in Phase 3's vocabulary AND for the email-plus-password authentication step in Phase 4's authorization flow.

The Constitution §10 Phase 3 roadmap names "OAuth 2.1 with PKCE replaces static tokens" as the auth migration deliverable. Phase 4 of this build is the work item that satisfies §10. The migration is scoped to the MCP protocol endpoint specifically; the SACP participant API (the renamed `src/participant_api/` router surface, used by the Web UI) stays on static bearers indefinitely for backward compatibility — its scope-of-use is the single-tenant Web UI within an operator's own deployment, where static bearers behind a session cookie are appropriate. AI participants joining via the BYOK provider flow continue using orchestrator-issued API credentials at every phase; the OAuth flow is human-facing.

## User Scenarios & Testing *(mandatory)*

### Phase 1 — Codebase Restructure

#### US1 (P1) — Developer reads `src/` and the module names match the code

**As a** new contributor cloning the repo, **I want** the `src/` directory names to match the modules' contents **so that** I do not pay the cognitive tax of a `mcp_server/` directory that contains no MCP-protocol code.

- **Given** the refactor has landed, **When** any contributor runs `ls src/`, **Then** they MUST see `participant_api/` and `mcp_protocol/` AND MUST NOT see `mcp_server/`.
- **Given** the refactor has landed, **When** any contributor opens `src/participant_api/tools/`, **Then** they MUST see the prior router files with their git blame history preserved (moves are via `git mv`).
- **Given** the refactor has landed, **When** any contributor opens `src/mcp_protocol/__init__.py`, **Then** they MUST see a placeholder docstring indicating Phase 2 will populate the module AND no other code.

#### US2 (P1) — Deployment config is updated; the running stack loads the renamed module without breakage

**As an** operator applying the refactor PR, **I want** the TrueNAS Dockge stack to pull AND both ASGI apps to come up successfully **so that** the rename is invisible to running clients and no log errors reference the old `mcp_server` path.

- **Given** the refactor has landed AND the deployment config has been updated, **When** the orchestrator process starts, **Then** both ASGI apps MUST come up AND emit no import errors related to the old `mcp_server` path.
- **Given** the post-refactor orchestrator is running, **When** any participant client connects to port 8750, **Then** the connection MUST succeed with the same behavior as pre-refactor (auth, routes, SSE stream shape).
- **Given** the post-refactor orchestrator is running, **When** any Web UI client connects to port 8751, **Then** the connection MUST succeed with the same behavior as pre-refactor.

#### US3 (P2) — Phase 2 unblocks; it can land additively under `src/mcp_protocol/` without rename collisions

**As the** Phase 2 implementer, **I want** the `src/mcp_protocol/` namespace to exist empty after Phase 1 **so that** I can create `src/mcp_protocol/transport.py`, `src/mcp_protocol/session.py`, and other Phase 2 files without name-collision dances or simultaneous mega-rename PRs.

- **Given** Phase 1 has landed, **When** the Phase 2 author creates new files under `src/mcp_protocol/`, **Then** the files MUST land without name collisions against `src/participant_api/` or any other `src/` module.
- **Given** Phase 1 has landed, **When** the Phase 2 author imports `from src.mcp_protocol import ...`, **Then** the import path MUST resolve to the new empty namespace AND MUST NOT shadow or conflict with any participant_api import.

### Phase 2 — MCP Protocol over Streamable HTTP

#### US4 (P1) — `mcp-remote` bridge user connects Claude Desktop to a SACP session

**As a** Claude Desktop user who wants to participate in a SACP session, **I want** the `mcp-remote` bridge to connect Claude Desktop's stdio to the SACP MCP endpoint **so that** I can invoke SACP tools through Claude Desktop's native tool-calling UI.

- **Given** `SACP_MCP_PROTOCOL_ENABLED=true` AND a valid bearer token, **When** an `mcp-remote` bridge invokes `initialize` against the MCP endpoint, **Then** the response MUST carry the negotiated protocol version (2025-11-25) AND a fresh `Mcp-Session-Id` header AND the server capabilities advertisement.
- **Given** an established MCP session, **When** the bridge invokes `tools/list`, **Then** the response MUST enumerate the tools registered per Phase 3 with their JSON schemas.
- **Given** an established MCP session, **When** the bridge invokes `tools/call` for a specific tool with valid params, **Then** the dispatcher MUST route to the corresponding participant_api router AND return the result in the MCP `call_tool` response envelope.
- **Given** an established MCP session, **When** the bridge invokes `tools/call` with invalid params, **Then** the response MUST be a JSON-RPC 2.0 error envelope with code -32602 (invalid params) AND the SACP-native error code in `data`.

#### US5 (P1) — Claude Desktop Pro+ Custom Connector connects directly

**As a** Claude Desktop Pro+ user, **I want** to configure the Custom Connector with the SACP MCP endpoint URL and a bearer token **so that** I can use SACP via MCP without the `mcp-remote` bridge.

- **Given** Custom Connector configured with the MCP endpoint URL, **When** Claude Desktop establishes the connection, **Then** the handshake MUST complete over Streamable HTTP only AND MUST NOT attempt SSE fallback.
- **Given** an established Custom Connector session, **When** the user invokes a SACP tool, **Then** the dispatch path MUST be identical to the `mcp-remote` bridge case AND the response shape MUST be identical.

#### US6 (P2) — claude code MCP-server registration via `claude mcp add`

**As a** claude code user, **I want** to register the SACP MCP server via `claude mcp add sacp <url> --token <bearer>` **so that** the SACP tool registry surfaces alongside my other MCP servers in claude code's agent loop.

- **Given** `claude mcp add sacp <url> --token <bearer>` succeeds, **When** a new claude code session starts, **Then** the SACP tools MUST appear in the available-tools list.
- **Given** the SACP tools are registered, **When** the agent invokes a SACP tool, **Then** the invocation MUST follow the standard MCP `call_tool` path AND the response MUST surface to the agent loop.

#### US7 (P1) — MCP protocol error model verification

**As an** MCP-protocol-compliance test driver, **I want** every invalid-request case to return the correct JSON-RPC 2.0 error envelope shape **so that** MCP clients can do useful retry / fallback / user-message work against documented error codes.

- **Given** any malformed JSON-RPC request, **When** the server responds, **Then** the response MUST be a JSON-RPC 2.0 error envelope with code -32700 (parse error).
- **Given** any well-formed request to a non-existent method, **When** the server responds, **Then** the response MUST carry code -32601 (method not found).
- **Given** any tools/call invocation with schema-invalid params, **When** the server responds, **Then** the response MUST carry code -32602 (invalid params) AND `data` MUST include schema validation details AND the SACP-native error code.
- **Given** any request without a valid bearer token, **When** the server responds, **Then** the response MUST carry code -32001 (auth failed) per the Phase 2 mapping table.

### Phase 3 — SACP-to-MCP Tool Mapping

#### US8 (P1) — Facilitator uses Claude Desktop to create a session

**As a** facilitator, **I want** to ask Claude Desktop in natural language to create a SACP session **so that** Claude Desktop calls `session.create` via the MCP protocol AND the orchestrator creates the session record AND emits the audit-log row.

- **Given** the orchestrator is running with MCP enabled, **When** an MCP client issues `list_tools`, **Then** the response MUST include `session.create` with a complete `paramsSchema` and `returnSchema`.
- **Given** an MCP client with facilitator scope, **When** the client issues `call_tool` for `session.create` with valid params, **Then** the orchestrator MUST create the session AND return the record matching the `returnSchema` AND emit one `admin_audit_log` row with `action='mcp_tool_session.create'`.
- **Given** an MCP client without facilitator scope, **When** the client issues `call_tool` for `session.create`, **Then** the dispatch MUST reject with the scope-violation error code AND no session row MUST be created.
- **Given** an MCP client issues `call_tool` for `session.create` with params violating the schema, **Then** the dispatch MUST reject with the validation error code AND no session row MUST be created AND no audit row MUST be emitted.

#### US9 (P1) — Participant uses Cursor to call inject_message into an active session

**As a** human participant on an active session, **I want** to inject a message via Cursor's MCP client **so that** my message persists to the `messages` table AND the orchestrator's turn loop processes it on its next iteration.

- **Given** an MCP client with participant scope on session S and participant P, **When** the client invokes `participant.inject_message` with valid content, **Then** a `messages` row MUST persist AND the audit log MUST record the invocation.
- **Given** an MCP client with participant scope on session S participant P, **When** the client invokes `participant.inject_message` targeting a different participant id, **Then** the dispatch MUST reject with scope-violation error.
- **Given** an MCP client invokes `participant.inject_message` on an archived session, **Then** the dispatch MUST reject with the session-state error code.

#### US10 (P2) — AI participant agent uses proposal_create on its own behalf

**As an** AI participant running in an external agent harness, **I want** to formalize a proposal for the session to vote on **so that** the proposal row persists AND other participants receive notification on their next dispatch.

- **Given** an AI participant authenticated via MCP, **When** the participant invokes `proposal.create`, **Then** the proposal MUST persist AND audit log MUST record the action.
- **Given** an AI participant on session S, **When** the AI invokes `proposal.vote` on a proposal belonging to session S, **Then** the vote MUST persist.
- **Given** an AI participant invokes `proposal.create` with malformed params, **Then** the dispatch MUST reject with validation error.

#### US11 (P2) — Audit consumer uses get_audit_log to surface session history

**As a** facilitator reviewing a long-running session, **I want** to invoke `admin.get_audit_log` with the session id and a time range **so that** the response returns a paginated audit-log slice matching spec 029's retention and pagination semantics.

- **Given** an MCP client with facilitator scope, **When** the client invokes `admin.get_audit_log` with valid params, **Then** the tool MUST return rows matching the spec 029 read-side query.
- **Given** the audit log has more rows than one page, **When** the client requests subsequent pages via the returned cursor, **Then** each page MUST return the next chunk in stable order.
- **Given** the requested range falls outside the spec 029 retention window, **When** the client invokes the tool, **Then** the response MUST return only rows within the retention window.

#### US12 (P3) — AI dispatches set_routing_preference on itself

**As an** AI participant operating in long-running advisory mode, **I want** to shift my own `routing_scope` to `observer` for a stretch **so that** I can listen rather than emit when the discussion moves outside my expertise.

- **Given** an MCP client with participant scope on participant P, **When** the client invokes `participant.set_routing_preference` on participant P, **Then** the routing scope MUST update AND the audit log MUST record the change.
- **Given** an MCP client with participant scope on participant P, **When** the client invokes the tool on a different participant id, **Then** the dispatch MUST reject with scope violation.

### Phase 4 — OAuth 2.1 + PKCE

#### US13 (P1) — Claude Desktop user completes initial OAuth flow

**As a** human installing Claude Desktop, **I want** to complete the OAuth Authorization Code flow with PKCE against the orchestrator's authorization endpoint **so that** Claude Desktop obtains an access token + refresh token bound to my participant scope.

- **Given** the orchestrator is running with `SACP_OAUTH_ENABLED=true`, **When** an MCP client fetches `/.well-known/oauth-protected-resource`, **Then** the response MUST include the authorization endpoint URL, token endpoint URL, supported scopes, and CIMD submission URL per the MCP authorization spec.
- **Given** a client submits a valid CIMD, **When** the orchestrator validates it, **Then** the client MUST register with a generated client_id AND the registration MUST emit an `admin_audit_log` row.
- **Given** a registered client begins an authorization flow with a PKCE code_challenge, **When** the human completes authentication, **Then** the redirect MUST include an authorization code AND the code MUST be single-use within its 60-second TTL.
- **Given** a client exchanges an authorization code with the matching PKCE code_verifier, **When** the token endpoint processes the request, **Then** the response MUST include an access token and a refresh token AND the issuance MUST emit an `admin_audit_log` row.
- **Given** a client presents a code without the matching PKCE verifier, **When** the token endpoint processes the request, **Then** the request MUST be rejected with the PKCE-mismatch error code.
- **Given** a client presents a code with `code_challenge_method=plain`, **When** the authorization endpoint processes the request, **Then** the request MUST be rejected — only `S256` is accepted.

#### US14 (P1) — Client refreshes an expired access token

**As an** MCP client with an expired access token, **I want** to present the refresh token at the token endpoint **so that** the orchestrator atomically issues new tokens AND revokes the presented refresh token AND a replay revokes the entire token family.

- **Given** an expired access token, **When** an MCP client presents it, **Then** the dispatcher MUST reject with the token-expired error code.
- **Given** a valid refresh token, **When** the client presents it at the token endpoint, **Then** the orchestrator MUST issue new access and refresh tokens atomically AND invalidate the presented refresh token.
- **Given** a refresh token already used once, **When** the client presents the same refresh token again, **Then** the orchestrator MUST revoke the entire token family AND emit a security-event audit row.
- **Given** a refresh token issued more than `SACP_OAUTH_REFRESH_TOKEN_TTL_DAYS` ago, **When** the client presents it, **Then** the request MUST be rejected with refresh-token-expired AND the client MUST re-authenticate.

#### US15 (P2) — User revokes a compromised token

**As a** participant who believes a device session may be compromised, **I want** to revoke that session's token via the management endpoint **so that** the dispatcher rejects subsequent MCP calls AND in-flight connections close within the propagation SLA.

- **Given** an active access token, **When** the user revokes it via the management endpoint, **Then** the token's status MUST update to revoked AND `admin_audit_log` MUST record the action.
- **Given** a revoked token, **When** an MCP client presents it, **Then** the dispatcher MUST reject AND no tool call MUST execute.
- **Given** a revoked token has an open MCP transport connection, **When** revocation propagates, **Then** the connection MUST close within `SACP_OAUTH_REVOCATION_PROPAGATION_SECONDS` (default 5).
- **Given** a revoked refresh token, **When** the client attempts to refresh using it, **Then** the token endpoint MUST reject AND the entire token family MUST remain revoked.

#### US16 (P2) — Facilitator views per-participant token issuance audit

**As a** facilitator suspecting a security event, **I want** to review token issuance, refresh, and revocation events filtered by `token_*` actions **so that** I can reconstruct the full token lifecycle per participant.

- **Given** several token lifecycle events occurred, **When** the facilitator invokes the audit-log read filtered by token actions, **Then** the response MUST include one row per event ordered by timestamp.
- **Given** the response includes refresh events, **When** the facilitator drills into a refresh row, **Then** the row MUST include both old and new token identifiers with token values scrubbed.
- **Given** an event includes scope data, **When** the row renders, **Then** the scope claims MUST appear in human-readable form for forensic review.

#### US17 (P1) — AI participant continues on orchestrator-issued credentials

**As an** AI participant joined via the BYOK provider flow, **I want** to keep using my orchestrator-issued credentials **so that** Phase 4 OAuth ship does not require my external agent to complete a browser-based OAuth flow AND any attempt to obtain a token for my participant id is structurally refused.

- **Given** an AI participant on an active session, **When** the orchestrator dispatches their turn, **Then** the AI's BYOK credentials MUST be used AND no OAuth token MUST be required.
- **Given** an authorization endpoint request naming an AI participant subject, **When** the orchestrator processes it, **Then** the request MUST be rejected with the AI-participant-excluded error code.
- **Given** an existing static-token AI participant from before Phase 4, **When** Phase 4 ships, **Then** the AI MUST continue working unchanged AND no migration prompt MUST appear to the AI's external agent.

### Phase 5 — Participant Onboarding Documentation

#### US18 (P1) — Facilitator creates a session, issues a participant token, generates the onboarding bundle

**As a** facilitator onboarding a new participant, **I want** documented steps to create a session, issue a token (returned once on creation), and produce a four-field onboarding bundle **so that** the participant receives the bundle via side channel and can begin onboarding.

- **Given** a facilitator follows the documented session-creation flow, **When** the session is created, **Then** the session_id MUST be the documented 12-char hex shape AND the doc MUST cover how to retrieve it again if the facilitator loses the value.
- **Given** a facilitator follows the documented token-issue flow, **When** the participant token is issued, **Then** the token MUST be returned once (on creation) AND the doc MUST cover the rotation flow if the token is lost.
- **Given** a facilitator follows the documented bundle-format template, **When** the bundle is produced, **Then** the bundle MUST contain exactly the four fields named (session_id, participant_id, bearer token, endpoint URL) in the documented order.
- **Given** a facilitator wants to verify the participant has received the bundle correctly, **When** the documented masked-display copy-paste block is used, **Then** the displayed bundle MUST hide all but the last 4 chars of the token so the two parties can confirm the same token value over a low-trust side channel without exposing it.
- **Given** a facilitator hands the bundle to a participant, **When** the participant follows the documented endpoint URL format, **Then** the URL MUST resolve to the SACP turn-event stream AND the doc MUST cover the URL shape for both current SACP-native (`/sse/{session_id}`) and future MCP (`/mcp`) surfaces.

#### US19 (P1) — Windows participant first connection via Claude Desktop / mcp-remote

**As a** non-Spike Windows participant receiving an onboarding bundle, **I want** the documented Windows-specific gotchas (8.3 short paths, env-var workaround, PowerShell vs cmd.exe, Defender stall, CRLF vs LF) so that I can onboard end-to-end in ≤ 15 minutes without operator support.

- **Given** a Windows participant follows the documented 8.3 short-path requirement, **When** their `claude_desktop_config.json` is inspected, **Then** the `npx` invocation MUST use the 8.3 short-path form (e.g., `C:\\PROGRA~1\\nodejs\\npx.cmd`) AND the doc MUST cover the `dir /x` command AND the cmd.exe /C space-handling bug that motivates the workaround.
- **Given** a Windows participant follows the documented env-var workaround, **When** their config is inspected, **Then** the `--header` argument MUST NOT contain a literal space-after-colon AND the env var MUST be defined in the config's `env` block per the documented pattern.
- **Given** a Windows participant invokes `mcp-remote` manually for diagnostics, **Then** the doc MUST cover the quoting differences between PowerShell and cmd.exe AND MUST provide working invocation examples for both.
- **Given** a Windows participant encounters a first-run Windows Defender scan delay, **Then** the doc MUST cover both the wait-it-out option (with expected window) AND the antivirus exclusion path (with the exact directory AND the risk note).
- **Given** a Windows participant saves `claude_desktop_config.json` with CRLF line endings, **Then** the doc MUST cover both the failure mode AND the LF-save fix (with editor-specific instructions for VS Code, Notepad++, Notepad).
- **Given** a Windows participant follows the entire documented flow, **When** their stopwatch reads total elapsed time, **Then** the target MUST be ≤ 15 minutes.

#### US20 (P1) — macOS participant first connection via Claude Desktop / mcp-remote

**As a** non-Spike macOS participant, **I want** the documented macOS-specific content (config-file path, Gatekeeper quarantine handling, first-run permission prompts, Apple Silicon notes) **so that** I can onboard end-to-end in ≤ 15 minutes following the docs.

- **Given** a macOS participant follows the documented config-file location, **When** they navigate to `~/Library/Application Support/Claude/`, **Then** the doc MUST cover the path AND the visibility-toggle for the hidden `Library` folder.
- **Given** a macOS participant encounters a Gatekeeper quarantine, **When** they follow the documented `xattr -d com.apple.quarantine` path, **Then** the doc MUST cover the exact invocation AND the risk note.
- **Given** a macOS participant encounters first-run permission prompts, **Then** the doc MUST cover each prompt the participant is likely to see AND the correct response for each.
- **Given** a macOS participant on Apple Silicon, **Then** the doc MUST cover any ARM-specific notes inline (Rosetta, native-binary preference, path differences) AND MUST NOT silently assume Intel.
- **Given** a macOS participant follows the entire documented flow, **When** their stopwatch reads total elapsed time, **Then** the target MUST be ≤ 15 minutes.

#### US21 (P2) — Token rotation mid-session

**As a** participant whose bearer token has been compromised or lost, **I want** the facilitator to invoke the documented rotation flow AND for me to update only the token env var in my config **so that** the new bundle replaces the lost token without losing per-session state.

- **Given** a facilitator invokes the documented rotation flow, **When** the new token is issued, **Then** the doc MUST cover the once-returned semantics AND the grace-window semantics per spec 002 §FR-007.
- **Given** a participant receives the new bundle, **When** they follow the documented config update path, **Then** the doc MUST cover updating ONLY the token env var so the participant does not accidentally re-introduce stale values.
- **Given** a Windows participant updates the config, **When** the env var is set, **Then** the doc MUST cover the Windows-specific env-var pattern.
- **Given** a participant restarts Claude Desktop with the new token, **When** the connection re-establishes, **Then** the doc MUST cover expected behavior AND the 401-troubleshooting path.

#### US22 (P2) — Disconnect and reconnect after laptop sleep / network blip

**As a** participant whose laptop slept overnight or whose WiFi blipped, **I want** the doc to cover the stateless-on-reconnect behavior of the SACP turn-event stream AND the catch-up path via the orchestrator's session transcript **so that** my expectations match the no-replay reality.

- **Given** a participant's connection drops mid-session, **When** the client reconnects, **Then** the doc MUST cover that the SACP turn-event stream is stateless on reconnect (no replay; next turn arrives).
- **Given** a participant wants to catch up on missed turns, **Then** the doc MUST cover the orchestrator's session transcript export endpoint (per spec 010) AND the read-only nature of the catch-up surface.
- **Given** a participant's reconnect fails, **Then** the doc MUST cover the common reconnect-only failure modes separately from initial-connect failures.
- **Given** a Windows participant's reconnect is blocked by Defender re-scanning the bridge after a sleep wake, **Then** the doc MUST cover this case AND the antivirus exclusion guidance.

### Edge Cases (cross-phase)

- **Phase 1 backward-compat alias.** `prime_from_mcp_app()` retains for one release as an alias for `prime_from_participant_api_app()`; the release notes call out the upcoming removal so any external operator script can update before the alias is dropped. No deprecation warning at import time (noise on an internal helper).
- **Phase 1 deployment-side `compose.yaml` update.** The repo-side `compose.yaml` is updated in the refactor PR; the running TrueNAS Dockge stack at `/mnt/.ix-apps/app_mounts/dockge/stacks/sacp/compose.yaml` requires a separate manual update per the deployment runbook — repo-side changes do not propagate automatically.
- **Phase 2 master switch off — endpoint returns 404.** With `SACP_MCP_PROTOCOL_ENABLED=false`, any request to `/mcp` returns HTTP 404 with no protocol-layer side effects; the SACP participant_api routes on the same port 8750 continue to serve normally.
- **Phase 2 cross-instance dispatch via spec 022's binding registry.** An MCP client connected to instance A invoking `call_tool` for a SACP session bound to instance B is routed cross-instance transparently per spec 022's mechanism.
- **Phase 2 concurrent-session cap reached.** A new `initialize` arriving when 100 sessions are active returns HTTP 503 + Retry-After.
- **Phase 2 idle session expires.** The server responds with a 404-class error indicating the session is unknown; the client re-handshakes with `initialize`.
- **Phase 2 rate-limit hit on `call_tool`.** The spec 019 middleware applies; the response is a JSON-RPC 2.0 error with code -32002 AND `data` includes the Retry-After hint.
- **Phase 2 `prompts` or `resources` request when out of v1 scope.** The server responds with code -32601 (method not found); `initialize` does not advertise these capabilities.
- **Phase 3 schema drift between registry and protocol layer.** A tool's schema in `ToolRegistry` evolves but a cached client copy is stale. The protocol layer's `list_tools` is the source of truth; clients re-query when they encounter validation errors on previously-valid params.
- **Phase 3 tool dispatch race during registry reload.** Hot-reload mid-dispatch: an in-flight `call_tool` completes against the old registry entry; subsequent calls see the new entry. No in-flight call is aborted.
- **Phase 3 long-running tool call.** A tool whose dispatch exceeds the V14 budget returns a partial result with continuation cursor, or returns the timeout error per the MCP spec. Tool declarations note budget-sensitive tools.
- **Phase 3 tool with no registered dispatch.** A tool definition exists but its dispatch callable raises ImportError at startup. The orchestrator fails startup (V15 fail-closed).
- **Phase 3 audit log emission failure during a successful dispatch.** The dispatcher returns success to the client and logs a high-severity warning about the missing audit row; the daily audit-reconciliation runbook covers investigation.
- **Phase 4 authorization endpoint under denial-of-service load.** Spec 019's per-IP rate limiter applies; the orchestrator also tracks failed-PKCE-verification counts per client and temporarily blocks clients exceeding `SACP_OAUTH_FAILED_PKCE_THRESHOLD`.
- **Phase 4 CIMD submission fetches a hostile URL.** The orchestrator fetches with timeouts (network + size) and validates against the MCP authorization spec schema; hostile responses (oversized, malformed, redirect chains) are rejected.
- **Phase 4 token claims tampered with.** Access tokens are signed JWTs; signature verification at the dispatcher rejects tampered tokens. Opaque refresh tokens stored hashed; mismatched presentations are rejected.
- **Phase 4 step-up authorization mid-flow.** A facilitator invokes `admin.archive_session` with an access token older than the step-up freshness threshold; the dispatcher rejects with `step_up_required`; the client redirects through a fresh authorization flow; on completion, the user retries.
- **Phase 4 cross-instance race on revocation.** Instance A revokes a token; instance B's per-instance cache holds it valid until the TTL expires. The dispatcher's check goes to DB on cache miss; revocation is honored within the cache TTL (≤ 30s).
- **Phase 5 participant pastes the session_id into the bearer-token slot, or vice versa.** Both are 12-char hex; the participant gets 403. The troubleshooting matrix elevates this as the top 403 cause.
- **Phase 5 facilitator gives wrong session_id.** The participant gets 404; the troubleshooting matrix names "check the bundle's session_id" as the resolution.
- **Phase 5 `claude_desktop_config.json` already contains entries for other MCP servers.** The doc covers JSON-merge: `mcpServers` is a dictionary; adding a SACP entry is one key-value pair; existing entries are untouched.
- **Phase 5 Gatekeeper prompt on macOS the doc did not anticipate.** The doc covers the general principle (`xattr -d com.apple.quarantine`) but cannot enumerate every binary or version; the doc states this scope limit explicitly.

## Requirements *(mandatory)*

### Functional Requirements

#### Phase 1 — Codebase Restructure

- **FR-001**: All files currently under `src/mcp_server/` MUST be moved to `src/participant_api/` via `git mv` (not via copy + delete). Blame history MUST be preserved. CI MUST confirm via a post-rename `git log --follow` spot-check on at least three randomly-selected moved files.
- **FR-002**: Every Python import under `src/` referencing `src.mcp_server` or `from mcp_server` MUST be updated to `src.participant_api` / `from participant_api`. CI MUST run `grep -rn "mcp_server" src/` post-refactor and assert zero hits.
- **FR-003**: The factory function `create_mcp_app` in `src/run_apps.py` MUST be renamed to `create_participant_api_app`. The orchestrator's entry point MUST call the new name. Port assignments (8750 for participant API, 8751 for Web UI) MUST be unchanged.
- **FR-004**: The `prime_from_mcp_app()` helper MUST be renamed to `prime_from_participant_api_app()`. A backward-compat alias `prime_from_mcp_app = prime_from_participant_api_app` MUST be retained for one release in `src/participant_api/__init__.py` AND MUST be flagged for removal in the next release's notes. All internal callers MUST use the new name.
- **FR-005**: All alembic migration files under `alembic/versions/` MUST be audited for imports from `src.mcp_server`. Any hits MUST be updated. The migration revision chain MUST NOT change — only import lines. CI MUST run `grep -rn "mcp_server" alembic/` post-refactor and assert zero hits.
- **FR-006**: The TrueNAS Dockge deployment config (repo-side `compose.yaml` + `.env`, plus any related scripts under `scripts/` or `docker/`) MUST be audited for `mcp_server` path references. Any hits MUST be updated. The operator MUST be informed via the PR description that the running-deployment file requires a separate manual update.
- **FR-007**: The `/sse/{session_id}` SACP turn-event stream MUST be moved to `src/participant_api/sse.py` and `src/participant_api/sse_router.py` with NO behavior change. The event payload shape (`{turn, speaker_id, action, skipped}`), transport semantics, auth posture, and route binding MUST be identical post-refactor.
- **FR-008**: All test files under `tests/` MUST be audited for `mcp_server` imports and updated. No test logic changes are permitted; only import paths. CI MUST run `grep -rn "mcp_server" tests/` post-refactor and assert zero hits.
- **FR-009**: `src/mcp_protocol/` MUST ship as an empty package containing only `__init__.py` with a placeholder docstring indicating Phase 2 will populate the module. The directory MUST exist post-refactor to reserve the namespace.
- **FR-010**: All committed documentation under `docs/` MUST be audited for `mcp_server` path references and updated. CI MUST run `grep -rn "mcp_server" docs/` post-refactor and assert zero hits.
- **FR-011**: The refactor MUST be accompanied by a discovery-context note in the spec body acknowledging the misnaming was identified during the 2026-05-12 debug session. The note MUST anchor the rename to the audit finding without citing any local-only artifact path.
- **FR-012**: The full pytest suite MUST pass identically before AND after the refactor — same test count, same passing assertions, same execution path. CI MUST emit a baseline (pre-refactor) test count and a post-refactor test count to the merge-PR status comment; the two counts MUST be equal.
- **FR-013**: Ruff lint MUST pass post-refactor with the same rule configuration as pre-refactor. The seven closeout preflights (traceability, doc-deliverables, audit-label parity, detection-taxonomy parity, migration chain, plus the two newer preflights) MUST be green on the refactor PR before merge.

#### Phase 2 — MCP Protocol over Streamable HTTP

- **FR-014**: The MCP endpoint MUST implement Streamable HTTP transport per the MCP spec revision 2025-11-25. SSE transport MUST NOT be implemented.
- **FR-015**: The `initialize` handshake MUST negotiate protocol version, exchange capability advertisements, and issue a fresh `Mcp-Session-Id` header. The negotiated version MUST be 2025-11-25 (per pin in clarifications) or be rejected with a clear error.
- **FR-016**: The `tools/list` method MUST return the tool registry populated by Phase 3. Each tool entry MUST include name, JSON Schema for params, JSON Schema for return, description, and the documented error contract.
- **FR-017**: The `tools/call` method MUST dispatch to the corresponding participant_api router per the Phase 3 mapping. The dispatch path MUST flow through the same auth, rate-limit, and audit hooks the participant API uses today.
- **FR-018**: The `ping` method MUST be implemented as a keepalive. The response is a minimal JSON-RPC 2.0 success envelope; no body data beyond the protocol-required fields.
- **FR-019**: The error model MUST conform to JSON-RPC 2.0. Errors MUST use the documented code-mapping table (parse error -32700, method not found -32601, invalid params -32602, plus server-defined codes -32001 auth / -32002 rate-limit / -32003 SACP state). SACP-native error codes MUST be preserved in the error envelope's `data` field for forensic continuity.
- **FR-020**: The `Mcp-Session-Id` header MUST be a cryptographically-secure 256-bit token issued at `initialize` time, generated via the OS cryptographic random source. Tokens MUST be opaque to the client.
- **FR-021**: On protocol-violation (malformed envelope, missing required fields, unexpected method sequence), the server MUST close the connection. For Streamable HTTP, the server returns the JSON-RPC 2.0 error and does not accept further requests on that session id until the client re-handshakes.
- **FR-022**: Static bearer-token auth MUST be required on every MCP request. The `Authorization: Bearer <token>` header MUST be validated against the same token store the participant API uses. OAuth is deferred to Phase 4.
- **FR-023**: Cross-instance routing MUST re-use the spec 022 binding registry (the `session_instance_bindings` table or its Redis pub/sub variant, per spec 022's research-resolved choice). MCP requests for a SACP session bound to a different instance MUST be routed cross-instance transparently.
- **FR-024**: The discovery metadata endpoint `/.well-known/mcp-server` MUST be served on the same host:port as the MCP endpoint. The response MUST include protocol version (2025-11-25), auth scheme (bearer-token in v1), endpoint URL, and server name. The endpoint MUST be available even when `SACP_MCP_PROTOCOL_ENABLED=false`, responding with an `enabled: false` flag.
- **FR-025**: A master switch `SACP_MCP_PROTOCOL_ENABLED` (V16 env var, default `false`) MUST gate the MCP endpoint. When false, the `/mcp` route MUST return HTTP 404 AND the SACP participant_api on the same port MUST be unaffected.
- **FR-026**: The MCP endpoint MUST be mounted at `/mcp` on the existing port 8750 service (per clarification resolution, default option). If clarification resolves to a third ASGI app, the path / port adjusts accordingly.
- **FR-027**: A concurrent-session cap per orchestrator instance MUST be enforced. Default `SACP_MCP_MAX_CONCURRENT_SESSIONS=100`. Beyond the cap, `initialize` MUST return HTTP 503 with a Retry-After header.
- **FR-028**: Rate limiting MUST re-use the spec 019 network-rate-limiting middleware. MCP requests share the same rate-limit budgets as participant_api requests (the bucket key is the bearer token / participant id). Rate-limit responses use JSON-RPC 2.0 error code -32002.
- **FR-029**: Audit logging MUST emit an `admin_audit_log` row for every `tools/call` invocation. The row MUST carry `action='mcp_tool_called'`, the tool name, the MCP session id, the SACP session id (if resolvable), the participant id (if resolvable), and the dispatch result.
- **FR-030**: Performance budgets MUST be enforced: `initialize` P95 ≤ 500ms, `tools/list` P95 ≤ 100ms, `tools/call` round-trip P95 ≤ 5s, `ping` P95 ≤ 50ms.
- **FR-031**: V15 fail-closed. Invalid values for the new env vars (`SACP_MCP_PROTOCOL_ENABLED`, `SACP_MCP_SESSION_IDLE_TIMEOUT_SECONDS`, `SACP_MCP_SESSION_MAX_LIFETIME_SECONDS`, `SACP_MCP_MAX_CONCURRENT_SESSIONS`) MUST cause the orchestrator process to exit at startup with a clear error naming the offending var. The startup validator MUST run before any ASGI app is mounted.
- **FR-032**: The MCP `prompts` and `resources` capability families are **out of v1 scope**. The `initialize` server-capabilities advertisement MUST NOT claim `prompts` or `resources` support. Any client request for `prompts/list` or `resources/list` MUST return code -32601.
- **FR-033**: V13 use-case coverage. Primary use cases benefitting from MCP-client interop are §3 Consulting Engagement, §5 Technical Review and Audit, and §1 Distributed Software Collaboration.
- **FR-034**: The four new env vars from Phase 2 MUST have validator functions in `src/config/validators.py` registered in the `VALIDATORS` tuple, AND corresponding sections in `docs/env-vars.md` with the six standard fields, BEFORE `/speckit.tasks` is run for this spec (V16 deliverable gate).
- **FR-035**: V11 supply chain. The MCP protocol implementation likely adds the Python `mcp` SDK as a dependency. The dependency MUST be pinned per Constitution §6.3 (pin to a specific version, not a range). If the team chooses to implement the wire protocol directly without the SDK, this FR is satisfied trivially. The choice is settled in `/speckit.plan`.
- **FR-036**: The MCP `Mcp-Session-Id` MUST be structurally distinct from the SACP `session_id`. A binding registry maps MCP-session-id → (SACP-session-id, participant-id, bearer-token-issued-to), established at `initialize` time. Subsequent `tools/call` invocations on this MCP session id MUST route to the bound SACP session.
- **FR-037**: The SACP turn-event SSE stream at `/sse/{session_id}` (post-Phase-1 path: `src/participant_api/sse_router.py`) MUST remain structurally separate from any MCP transport. Documentation under `docs/` MUST call out the distinction explicitly. The MCP endpoint is `/mcp`; the SACP-native stream is `/sse/{session_id}`; both are on port 8750 but serve different protocols.

#### Phase 3 — SACP-to-MCP Tool Mapping

- **FR-038**: Tool names MUST follow `domain.action` convention with snake_case segments (e.g., `session.create`, `participant.inject_message`, `proposal.cast_vote`). The full enumeration of names lands at `/speckit.plan` time per the clarifications.
- **FR-039**: A `ToolRegistry` MUST be loaded at orchestrator startup, populated from a registration module under `src/mcp_protocol/tools/`. Each registry entry MUST contain a `ToolDefinition` (name + description + paramsSchema + returnSchema + errorContract + scopeRequirement) and a `ToolDispatch` callable.
- **FR-040**: The tool surface MUST cover session lifecycle: session.create, session.update_settings, session.archive, session.delete, session.list. Scope: facilitator.
- **FR-041**: The tool surface MUST cover participant lifecycle: participant.create, participant.update, participant.remove, participant.rotate_token, participant.list. Scope: facilitator for most; participant.rotate_token follows spec 002 (facilitator or the participant themselves on their own token).
- **FR-042**: The tool surface MUST cover message injection: participant.inject_message. Scope: participant on their own behalf, with facilitator-on-behalf-of variants explicitly enumerated.
- **FR-043**: The tool surface MUST cover proposal flow: proposal.create, proposal.cast_vote, proposal.close, proposal.list. Scope: participant (creation, voting); facilitator (close).
- **FR-044**: The tool surface MUST cover review-gate flow: review_gate.list_pending, review_gate.approve, review_gate.reject, review_gate.edit_and_approve. Scope: facilitator.
- **FR-045**: The tool surface MUST cover routing/budget config: participant.set_routing_preference, participant.set_budget. Scope: participant on own behalf (routing); sponsor on sponsored AI (budget); facilitator overrides.
- **FR-046**: The tool surface MUST cover debug-export: debug.export_session, debug.export_participant_view. Scope: facilitator. Returns may be paginated/chunked per FR-052.
- **FR-047**: The tool surface MUST cover audit-log read: admin.get_audit_log. Scope: facilitator. Backed by spec 029 read-side query.
- **FR-048**: The tool surface MUST cover detection-event history read: detection_events.list, detection_events.detail. Scope: facilitator. Backed by spec 022 read-side query.
- **FR-049**: The tool surface MUST cover facilitator scratch operations: scratch.list_notes, scratch.create_note, scratch.update_note, scratch.delete_note, scratch.promote_to_transcript. Scope: facilitator. Backed by spec 024.
- **FR-050**: The tool surface MUST cover provider configuration: provider.list, provider.test_credentials. Scope: facilitator or participant on own BYOK credentials.
- **FR-051**: The tool surface MUST cover admin lifecycle: admin.list_sessions, admin.list_participants, admin.transfer_facilitator. Scope: facilitator.
- **FR-052**: The tool surface SHOULD provide convenience read endpoints: session.get, participant.get, message.list. Scope: participant on own session.
- **FR-053**: Parameter validation MUST run against each tool's `paramsSchema` at the dispatch boundary BEFORE the dispatch callable is invoked. Validation failures MUST return the `SACP_E_VALIDATION` error code with the JSON-Pointer to the offending field.
- **FR-054**: Return validation MUST run against each tool's `returnSchema` BEFORE serialization to the client. Return-validation failures indicate an internal bug and MUST return `SACP_E_INTERNAL` to the client while logging the full validation error at error severity.
- **FR-055**: Each tool MUST declare its error contract — the set of error codes it can return outside the universal ones (`SACP_E_FORBIDDEN`, `SACP_E_NOT_FOUND`, `SACP_E_VALIDATION`, `SACP_E_INTERNAL`). The protocol layer (Phase 2) maps each code to its JSON-RPC error envelope.
- **FR-056**: Scope enforcement MUST happen at the dispatch boundary. Each tool declares its required scope via `scopeRequirement`. The dispatcher reads the caller's effective scope (from the bearer token in Phase 2's static phase; from the OAuth token in Phase 4) and rejects with `SACP_E_FORBIDDEN` when the caller lacks the scope.
- **FR-057**: Audit logging MUST emit one `admin_audit_log` row per successful tool dispatch with `action='mcp_tool_<name>'`, the caller's participant id, the dispatch params (with secrets scrubbed per spec 002 ScrubFilter), and the dispatch result identifier. Failed dispatches due to validation, scope, or business-rule errors MUST also be logged.
- **FR-058**: Mutating write tools MUST support optional client-provided idempotency keys via a `_idempotency_key` parameter (UUID string). Re-submission within the retention window MUST return the original result without re-executing the dispatch. Read tools MUST NOT accept idempotency keys.
- **FR-059**: Read tools returning list results MUST support pagination via opaque cursors. The `paramsSchema` MUST include optional `cursor` and `page_size` fields. The `returnSchema` MUST include `items` array, `next_cursor` (nullable), and `has_more` boolean.
- **FR-060**: Per-tool V14 performance budgets MUST be declared in tool metadata: most tools P95 ≤ 1s; debug-export and audit-log paged reads P95 ≤ 5s; session.create and participant.create P95 ≤ 500ms. The dispatcher timing path records actual latency per dispatch.
- **FR-061**: Granular V16 master switches per tool category MUST be supported via env vars (`SACP_MCP_TOOL_SESSION_ENABLED`, `SACP_MCP_TOOL_PROPOSAL_ENABLED`, etc.). Default `true` when the master `SACP_MCP_PROTOCOL_ENABLED` is `true`. When a category switch is `false`, the affected tools MUST NOT appear in `list_tools` AND `call_tool` invocations against them MUST return `SACP_E_NOT_FOUND`.
- **FR-062**: Tool deprecation MUST follow a versioned-name policy: a breaking schema change ships a new tool name with a version suffix (`session.create.v2`); the old name remains in the registry for one minor-version cycle returning the same result, then sunsets returning `SACP_E_DEPRECATED` pointing to the replacement. The cycle length is env-tunable.
- **FR-063**: AI participant access MUST be enumerated per tool — each `ToolDefinition` MUST declare whether AI-side clients can invoke it. The enumeration distinguishes between tools an AI invokes on its own behalf (`participant.inject_message`, `proposal.cast_vote`, `participant.set_routing_preference` on self) and tools structurally inaccessible to AIs (`participant.rotate_token` on others, `admin.transfer_facilitator`, debug-export).
- **FR-064**: Cross-cutting concerns from specs 022 / 024 / 029 MUST be reflected: detection-event-history tools (spec 022), facilitator scratch tools (spec 024), and audit-log viewer tools (spec 029) become MCP tools when this phase ships. Tool definitions cross-reference the source specs for behavior pinning.
- **FR-065**: Sponsor-scoped tools MUST be enumerated: the sponsor scope (spec 023 sponsorship model) grants invocation rights on `participant.set_budget` and `participant.rotate_token` for the sponsored AI, AND on read-side tools to inspect the sponsored AI's state. The sponsor scope does NOT grant message-injection on behalf of the sponsored AI.
- **FR-066**: Pre/post hooks at the dispatch boundary MUST be available for request/response logging and V14 instrumentation. Phase 2's dispatcher exposes the hook points; all dispatches flow through them.
- **FR-067**: Every tool MUST have at least one happy-path test and one error-path test in `tests/test_mcp_tools_*.py`. The happy-path test exercises a valid call returning the expected schema-conformant result. The error-path test exercises a validation, scope, or business-rule failure returning the expected error code.
- **FR-068**: An architectural test MUST assert that every public `participant_api` router endpoint has at least one corresponding MCP tool in the registry (or is explicitly excluded with a documented rationale). CI fails if a new endpoint ships without a tool counterpart.
- **FR-069**: The new env vars introduced by Phase 3 (`SACP_MCP_TOOL_<CATEGORY>_ENABLED` for each category; `SACP_MCP_TOOL_IDEMPOTENCY_RETENTION_HOURS`; `SACP_MCP_TOOL_DEPRECATION_HORIZON_DAYS`; `SACP_MCP_TOOL_PAGINATION_DEFAULT_SIZE`; `SACP_MCP_TOOL_PAGINATION_MAX_SIZE`) MUST have validator functions in `src/config/validators.py` registered in the `VALIDATORS` tuple, AND corresponding sections in `docs/env-vars.md` with the six standard fields, BEFORE `/speckit.tasks` is run.

#### Phase 4 — OAuth 2.1 + PKCE

- **FR-070**: The MCP protocol endpoint MUST be OAuth 2.1 compliant. The Resource Owner Password Credentials Grant MUST NOT be supported. The Implicit Grant MUST NOT be supported. The Authorization Code Grant with PKCE MUST be the only flow.
- **FR-071**: PKCE MUST be required for all authorization flows. Only `code_challenge_method=S256` MUST be accepted; `plain` MUST be rejected with the standard OAuth `unsupported_challenge_method` error.
- **FR-072**: An authorization endpoint MUST be provided at a discoverable path (specific path pinned in `/speckit.plan`). The endpoint MUST validate the `client_id`, `redirect_uri`, `code_challenge`, `code_challenge_method`, `scope`, and `state` parameters per RFC 6749 + RFC 7636.
- **FR-073**: A token endpoint MUST be provided at a discoverable path. The endpoint MUST support the `authorization_code` and `refresh_token` grant types. Other grant types MUST be refused.
- **FR-074**: A revocation endpoint MUST be provided at a discoverable path per RFC 7009. The endpoint MUST accept either an access token or a refresh token; presenting a refresh token MUST revoke the entire token family.
- **FR-075**: Discovery metadata MUST be served at `/.well-known/oauth-protected-resource` per the MCP authorization spec (revision 2025-11-25). The metadata MUST include the authorization endpoint, token endpoint, revocation endpoint, supported scopes, supported grant types, supported code challenge methods, and the CIMD submission URL.
- **FR-076**: Client ID Metadata Documents MUST be supported. A client submits its CIMD URL on first contact; the orchestrator fetches the document with bounded timeout and size, validates against the schema, and registers the client. The registration mode (`open` / `allowlist` / `closed`) is controlled via `SACP_OAUTH_CLIENT_REGISTRATION_MODE`.
- **FR-077**: The scope vocabulary MUST be the union of (a) role scopes from Phase 3 (`facilitator` / `participant` / `pending` / `sponsor`) and (b) tool-category scopes from Phase 3 (`tool:session`, `tool:participant`, `tool:proposal`, `tool:review_gate`, `tool:debug_export`, `tool:audit_log`, `tool:detection_events`, `tool:scratch`, `tool:provider`, `tool:admin`). A token request lists requested scopes; the orchestrator issues the intersection of (requested, grantable-to-this-user).
- **FR-078**: Access token TTL MUST default to 60 minutes; refresh token TTL MUST default to 30 days. Both MUST be env-tunable via `SACP_OAUTH_ACCESS_TOKEN_TTL_MINUTES` and `SACP_OAUTH_REFRESH_TOKEN_TTL_DAYS`.
- **FR-079**: Refresh tokens MUST rotate on every use. The token endpoint MUST atomically issue a new refresh token AND revoke the presented one in the same DB transaction. A re-use of a previously-used refresh token MUST revoke the entire token family AND emit a `token_family_revoked_replay_attempt` security event.
- **FR-080**: Issued tokens MUST carry a `participant_id` claim AND a `session_id` claim where applicable. The dispatcher MUST refuse to dispatch tool calls whose target session does not match the token's `session_id` claim, and whose target participant does not match the token's `participant_id` claim (with explicit exceptions for facilitator-scope cross-participant tools).
- **FR-081**: Refresh tokens MUST be encrypted at rest using the existing Phase 1 Fernet pattern (spec 023). The cleartext refresh token is presented to the client once at issuance; the orchestrator stores only the Fernet-encrypted form. Token lookup at the token endpoint uses a per-token hash for indexing.
- **FR-082**: A migration path MUST be provided for existing static-token participants on the MCP endpoint. The first MCP request from a static-token participant after Phase 4 ships MUST return a migration prompt in the error response pointing the user to the OAuth onboarding flow. The static token MUST continue working during the grace period.
- **FR-083**: After `SACP_OAUTH_STATIC_TOKEN_GRACE_DAYS` elapse from Phase 4 ship date (or from the per-participant first-prompted date — pin in `/speckit.plan`), static tokens on the MCP endpoint MUST stop validating; requests MUST be rejected with `migration_required`. The SACP participant API (the renamed `src/participant_api/` routers used by the Web UI) MUST continue accepting static tokens regardless of the MCP grace period.
- **FR-084**: The facilitator scope MUST grant session-governance authority but MUST NOT grant access to participant API keys, wallets, or sponsored-AI credentials owned by other participants. Specifically: `tool:provider` for the facilitator scope MUST NOT include `participant.test_credentials` on a non-self participant's BYOK record. `tool:participant.set_budget` for the facilitator scope MUST NOT include non-sponsored participants' budgets. The sovereignty remediation completes before this phase's `/speckit.tasks` and codifies the exclusions in the scope claim semantics.
- **FR-085**: Every token issuance, refresh, and revocation event MUST emit an `admin_audit_log` row with `action='token_issued'` / `action='token_refreshed'` / `action='token_revoked'`, the participant id, the client id, the scopes granted, and the token identifier (with the token value scrubbed). Failed events (PKCE mismatch, scope rejection, family-replay) MUST also be logged with a `security_event` row.
- **FR-086**: Step-up authorization MUST be required for destructive facilitator actions: `admin.transfer_facilitator`, `admin.archive_session`, `admin.mass_revoke_tokens`, `session.delete`. The dispatcher checks the access token's `auth_time` claim against the current time; if the difference exceeds `SACP_OAUTH_STEP_UP_FRESHNESS_SECONDS`, the dispatch returns `step_up_required` and the client must complete a fresh authorization flow.
- **FR-087**: The orchestrator process MUST exit at startup on invalid OAuth env-var values — invalid TTLs, malformed signing keys, missing required configuration. V15 fail-closed gate observed in CI.
- **FR-088**: The new env vars introduced by Phase 4 (`SACP_OAUTH_ENABLED`, `SACP_OAUTH_ACCESS_TOKEN_TTL_MINUTES`, `SACP_OAUTH_REFRESH_TOKEN_TTL_DAYS`, `SACP_OAUTH_AUTH_CODE_TTL_SECONDS`, `SACP_OAUTH_CLIENT_REGISTRATION_MODE`, `SACP_OAUTH_STATIC_TOKEN_GRACE_DAYS`, `SACP_OAUTH_STEP_UP_FRESHNESS_SECONDS`, `SACP_OAUTH_REVOCATION_PROPAGATION_SECONDS`, `SACP_OAUTH_SIGNING_KEY_PATH`, `SACP_OAUTH_FAILED_PKCE_THRESHOLD`, `SACP_OAUTH_CIMD_ALLOWED_HOSTS`) MUST have validator functions in `src/config/validators.py` registered in the `VALIDATORS` tuple, AND corresponding sections in `docs/env-vars.md` with the six standard fields, BEFORE `/speckit.tasks` is run.
- **FR-089**: AI participants registered via the BYOK provider flow (`kind='ai'` on their participant record) MUST NOT obtain OAuth tokens. The authorization endpoint MUST refuse to start a flow naming an AI participant as the subject AND emit a `security_event` row. The check is at issuance, not at dispatch.
- **FR-090**: WebAuthn / passkey support is OUT OF SCOPE for v1. The authorization endpoint completes with email + password authentication per spec 023.
- **FR-091**: One OAuth subject (one human) MUST be able to participate in multiple SACP sessions concurrently. Each session has its own participant record; tokens issued for each are independent and isolated.
- **FR-092**: Token revocation MUST close existing MCP transport connections within `SACP_OAUTH_REVOCATION_PROPAGATION_SECONDS` (default 5). The dispatcher boundary check on every call enforces this; if the dispatcher detects the token is revoked, it returns the close-required error per Phase 2 FR-021.
- **FR-093**: Per-IP rate limiting MUST apply to the authorization endpoint and token endpoint per spec 019. The OAuth flow is the primary credential-stuffing surface; both endpoints are protected.
- **FR-094**: Token state MUST be persisted in the DB (not in-memory) so multiple orchestrator instances share the issuance and revocation state. Per-instance caches MUST have a TTL ≤ 30 seconds so revocations propagate within bounded latency.
- **FR-095**: Authorization endpoint and token endpoint P95 latency MUST be ≤ 200ms under representative load. Slower paths indicate either DB contention or signing-key issues; both surface in V14 budget enforcement.
- **FR-096**: OAuth flow events (authorization request, code issuance, code redemption, token issuance, refresh, revocation) MUST go to `admin_audit_log` AND `security_events`. They MUST NOT enter the message transcript — they are forensic, not conversational (V17 transcript canonicity).
- **FR-097**: Every issued token MUST carry enough claims to trace back to the canonical participant record AND the canonical scope-grant decision (V18 derived-artifacts traceability). Claims include: `sub` (participant_id), `client_id`, `scope`, `auth_time`, `iat`, `exp`, `jti` (token identifier).
- **FR-098**: The CIMD fetcher MUST run with a bounded network timeout (default 10 seconds) AND a bounded document size (default 256 KiB). Documents exceeding either bound MUST be rejected. The list of allowed CIMD hosts MUST be controlled via `SACP_OAUTH_CIMD_ALLOWED_HOSTS` (default empty — all hosts allowed; operators with egress controls scope the list).
- **FR-099**: An architectural test MUST assert that no code path under `src/` outside `src/mcp_protocol/auth/` accepts an OAuth token directly; tokens are exclusively validated at the protocol-layer middleware (V18 traceability of the auth boundary).

#### Phase 5 — Participant Onboarding Documentation

- **FR-100**: The facilitator-creates-session step MUST be documented with the exact tool call. Pre-Phase-3 (current state), this is the existing REST endpoint with the documented request shape and response shape. Post-Phase-3, this is the `session.create` MCP tool with its JSON Schema parameter contract. The doc carries both forms so participants reading during the transition can resolve their version.
- **FR-101**: The facilitator-issues-participant-token step MUST be documented with the exact tool call. Pre-Phase-3, this is the existing REST endpoint that issues `participant.create` semantics. Post-Phase-3, this is the `participant.create` MCP tool. The doc MUST cover the token-shown-once contract (token value returned once on creation; subsequent reads return only metadata). The doc MUST cover the rotation path as the recovery flow for lost tokens.
- **FR-102**: The onboarding bundle format MUST be a markdown template with exactly four fields in this order: (a) session_id (12-char hex), (b) participant_id (12-char hex), (c) bearer token (opaque 32+ char string), (d) endpoint URL. The template MUST include a masked-display copy-paste block that hides all but the last 4 chars of the token, for visual confirmation during side-channel transfer over low-trust channels.
- **FR-103**: The endpoint URL format MUST be documented as `http://<host>:8750/sse/<session_id>` for the SACP turn-event stream (current state, Phase 1+ surface). The doc MUST include a forward-looking note that once Phase 2 ships, the endpoint shifts to `http://<host>:8750/mcp` for the Streamable HTTP transport. Both forms are documented; the version header signals which is current.
- **FR-104**: The bearer token format MUST be documented as an opaque string of 32 or more characters, carried in the `Authorization: Bearer <token>` HTTP header. The doc MUST cover that the token is the per-session credential (the security primitive), separate from the session_id (the routing primitive); both are required for the connection to succeed.
- **FR-105**: The session_id vs participant_id distinction MUST be documented explicitly. Both are 12-char hex strings; the shape is identical. The SSE endpoint is keyed by session_id; the bearer token validation is keyed by participant_id. A mismatch produces 403 (token-doesn't-match-session). The doc MUST include a troubleshooting entry mapping the 403 symptom to the id-vs-token-swap root cause as the most-likely first cause.
- **FR-106**: Token rotation policy MUST be documented. The `participant.rotate_my_token` tool (or REST equivalent) issues a new token; the old token is invalidated after a configurable grace window per spec 002 §FR-007. The doc covers the rotation flow end-to-end: facilitator invokes, new bundle generated, participant updates env var, restart Claude Desktop. The doc covers the grace-window semantics explicitly.
- **FR-107**: Disconnect-and-reconnect behaviour MUST be documented. The SACP turn-event stream is stateless on reconnect; the client re-subscribes and receives the next turn. Missed turns are NOT replayed to the reconnecting client. The doc covers the no-replay assumption explicitly AND covers the catch-up path (the orchestrator's session transcript export per spec 010). The doc covers reconnect-specific failure modes separately from initial-connect failure modes.
- **FR-108**: The Windows 8.3 short-path requirement MUST be documented for `npx.cmd` in `claude_desktop_config.json`. The cmd.exe /C space bug means paths with spaces fail. The doc MUST cover the 8.3 short-path form (`C:\\PROGRA~1\\nodejs\\npx.cmd`), the `dir /x` command that generates 8.3 names on the participant's specific machine, and the cmd.exe /C space-handling reason the workaround exists.
- **FR-109**: The Windows env-var workaround for spaces in `--header` values MUST be documented. The `--header "Authorization: Bearer ${VAR}"` form fails on Windows because of the space-after-colon. The doc covers the working form: `Authorization:${VAR}` with no space around the colon, with the actual token value set in the config's `env` block as a separate variable. The doc covers both the failure mode (silent failure or 401) and the working pattern, with a complete sample config block.
- **FR-110**: PowerShell vs cmd.exe differences for the manual `mcp-remote` invocation MUST be documented. When a participant needs to invoke `mcp-remote` directly for diagnostic purposes, the quoting rules differ between the two shells. The doc MUST cover working invocations for both shells with explicit notes on which quoting form goes where.
- **FR-111**: The Windows Defender first-run scan stall MUST be documented. On first invocation of `npx mcp-remote ...`, Windows Defender's real-time scanner may stall the process for an extended window (observed up to several minutes). The doc MUST cover both the wait-it-out option (with the typical wait window) AND the antivirus exclusion path (with the exact directory to exclude AND a risk note explaining why exclusion is acceptable).
- **FR-112**: The CRLF vs LF subtlety in `claude_desktop_config.json` MUST be documented. Claude Desktop reads the config file strictly; on some installs, CRLF line endings cause parse failures that surface as "config not loading" rather than a JSON error. The doc MUST cover the symptom, the verification step (open in an editor that displays line endings), and the fix (save as LF, with editor-specific instructions for VS Code, Notepad++, and Notepad).
- **FR-113**: The macOS `claude_desktop_config.json` location MUST be documented as `~/Library/Application Support/Claude/`. The doc MUST cover the hidden-`Library`-folder convention so a participant unfamiliar with macOS does not get stranded by Finder's default-hidden behaviour.
- **FR-114**: The macOS first-run permission prompts and `xattr -d com.apple.quarantine` handling MUST be documented. The doc MUST cover (a) network-access prompt that Claude Desktop may surface, (b) the `xattr -d com.apple.quarantine <path>` invocation for binaries quarantined by Gatekeeper, (c) a risk note explaining why quarantine removal is acceptable for this scenario.
- **FR-115**: CSRF and origin-header requirements MUST be documented. The current SACP participant API does NOT require Origin or Referer headers on the SSE endpoint; the Web UI's X-SACP-Request CSRF middleware is scoped to Web UI routes and does NOT apply to participant API routes. The doc covers the current state explicitly AND flags that Phase 4 will tighten this; the OAuth migration section covers the eventual change.
- **FR-116**: A troubleshooting matrix MUST be documented covering at minimum four HTTP status codes: 401 (authentication failure — wrong token / token expired / token in wrong field), 403 (authorization failure — token-doesn't-match-session / id-vs-token swap), 404 (route not found — wrong endpoint URL / wrong session_id / orchestrator on different port), and timeout (connection established but no response — orchestrator unreachable / firewall / proxy interception). Each entry maps the symptom to a root-cause list (most-likely first) and a fix path. The matrix is in the cross-platform overview doc; platform-specific docs link to the matrix rather than duplicating it.
- **FR-117**: The doc-versioning header MUST be present at the top of each of the three docs, immediately under the title. The header carries (a) the SACP phase the doc was written against (Phase 1, Phase 2, Phase 3 — citing Constitution §10 phase numbering), (b) the last-updated date (YYYY-MM-DD), (c) the version of Claude Desktop the doc was tested against. Updates to the doc bump the relevant fields. The header is the first thing a participant reads; a stale doc declares itself.
- **FR-118**: The Phase-3 OAuth migration section MUST be reserved in `docs/participant-onboarding.md`. The section is structurally present at v1 ship (a heading + a placeholder one-sentence note that says the section is reserved for the Phase 4 OAuth flow) but the content is empty until Phase 4's tasks schedule. When Phase 4 ships, this section is content-filled with the OAuth onboarding flow + the migration path for existing static-token participants.
- **FR-119**: Known-good sample `claude_desktop_config.json` blocks MUST be included in the platform-specific docs. The Windows sample uses the 8.3 short-path pattern from FR-108, the env-var pattern from FR-109, and LF line endings per FR-112. The macOS sample uses the standard `npx` path (no 8.3 equivalent needed). Both samples use placeholder values per the FR-121 redaction policy. Both samples carry inline comments (in adjacent prose, since JSON does not support comments) explaining what each field does and what to substitute.
- **FR-120**: Cross-references to Phases 1-4 MUST be present in the docs. Phase 1 (codebase restructure) explains why `src/mcp_server/` is renamed; the doc cites the rename as a forward-looking note. Phase 2 (MCP protocol over Streamable HTTP) is the eventual home of the `/mcp` endpoint. Phase 3 (tool mapping) is the eventual home of the tool definitions referenced in FR-100 / FR-101 / FR-106. Phase 4 (OAuth) is the eventual home of the FR-118 OAuth migration section. The cross-references are forward-looking; the docs do NOT require any phase to be Implemented before v1 ships, but the docs DO require the cross-references to be present so the v1 reader knows what is changing and when.
- **FR-121**: Sample configuration redaction policy MUST be documented. Placeholder tokens use the form `SACP_DOC_EXAMPLE_<32-char alphanumeric>` so the value is recognizable as a placeholder AND the secret scanner does not flag the doc. The session_id placeholder uses the fixed value `000000000000` (12 zeros) recognizable as not-real. The endpoint URL placeholder uses `http://orchestrator.example:8750`. The doc MUST cover the substitution step explicitly.
- **FR-122**: Linux client onboarding MUST be explicitly out-of-scope for v1, with a one-sentence note in the cross-platform overview acknowledging the deferral so a Linux reader is not stranded. The note cites that Linux MCP-client onboarding is unscoped because no current request and no debug-session data; the deferral is a Phase-3-or-later follow-up if MCP clients on Linux become a use case.
- **FR-123**: Mobile (iOS / Android) client onboarding MUST be out-of-scope for v1 AND MUST NOT be mentioned in the cross-platform overview to avoid implying a roadmap commitment. The omission is deliberate; if a mobile MCP client becomes a use case, that work scopes its own doc.

### Key Entities

- **`src/participant_api/`** — the renamed module containing SACP's participant-facing API surface. Holds the routers (`admin.py`, `debug.py`, `detection_events.py`, `facilitator.py`, `participant.py`, `proposal.py`, `provider.py`, `session.py`), the SACP SSE turn-event stream (`sse.py`, `sse_router.py`), the FastAPI app factory (`app.py`), middleware (`middleware.py`), and the rate limiter (`rate_limiter.py`).
- **`src/mcp_protocol/`** — the new module reserved by Phase 1 (empty) and populated by Phase 2 (transport, dispatcher, session lifecycle) and Phases 3-4 (tool registry, OAuth surface under `src/mcp_protocol/auth/`).
- **`src/run_apps.py`** — the wiring entry point. The factory functions `create_participant_api_app` (renamed from `create_mcp_app`) and the existing `create_web_ui_app` build the two ASGI apps that run in one process.
- **`prime_from_participant_api_app()`** — the renamed helper that primes the Web UI's service references from the participant_api's app instance. A backward-compat alias `prime_from_mcp_app` is retained for one release.
- **MCPSession** — a session_id-scoped MCP-protocol session. Carries `mcp_session_id` (256-bit opaque token), `created_at`, `last_activity_at`, bound `sacp_session_id`, bound `participant_id`, advertised capabilities, negotiated protocol version. Distinct from but bound to the SACP session.
- **ProtocolMessage** — the MCP wire-format envelope. JSON-RPC 2.0 shape with `jsonrpc`, `method`, `params`, `id` for requests; `jsonrpc`, `result` OR `error`, `id` for responses. Server-initiated notifications follow the same shape minus the id.
- **TransportConnection** — the Streamable HTTP connection state. Carries request/response cycle metadata, bearer-token-validated identity, rate-limit bucket reference. No SSE; the connection is request-scoped per Streamable HTTP semantics.
- **MCPErrorEnvelope** — the JSON-RPC 2.0 error structure. `code` (numeric, per the documented mapping table), `message` (human-readable), `data` (structured details including the SACP-native error code for forensic continuity).
- **MCPToolDispatcher** — the orchestrator-side dispatcher that consults the tool registry on `tools/call`, validates params against the registered JSON Schema, routes to the corresponding participant_api router, captures the response, marshals it back into the MCP envelope, and emits the audit-log row.
- **ToolDefinition** — the public-facing tool record. Fields: `name` (domain.action), `description` (natural-language hint for client AIs), `paramsSchema` (JSON Schema for the call parameters), `returnSchema` (JSON Schema for the success result), `errorContract` (enumerated error codes the tool may return), `scopeRequirement` (facilitator / participant / pending / sponsor / any), `aiAccessible` (boolean), `idempotencySupported` (boolean — write tools only), `paginationSupported` (boolean — list-return tools), `v14BudgetMs` (P95 latency budget). Phase 2 and Phase 3 co-design this shape.
- **ToolRegistry** — the in-memory registry loaded at orchestrator startup. Maps tool name → (ToolDefinition, ToolDispatch). The source of truth Phase 2's dispatcher reads. Mutation outside startup is not supported in v1.
- **ToolDispatch** — the boundary callable bridging the protocol layer to the participant_api router function. Signature: `async def dispatch(caller_context, params) -> result`. The dispatcher applies parameter validation BEFORE the call, scope enforcement BEFORE the call, return validation AFTER the call, and audit-log emission AFTER the call.
- **ScopeRequirement** — the auth-scope each tool needs. Values: `facilitator`, `participant`, `pending`, `sponsor`, `any`. Binds to Phase 4's OAuth scope vocabulary.
- **ErrorContract** — per-tool enumeration of error codes the tool may return beyond the universal `SACP_E_FORBIDDEN`, `SACP_E_NOT_FOUND`, `SACP_E_VALIDATION`, `SACP_E_INTERNAL`.
- **IdempotencyKey** — UUID string provided by the client via `_idempotency_key` param on mutating writes. Stored in DB with the dispatch result for the env-tunable retention window. Re-submission within the window returns the original result.
- **AuthorizationServer** — the SACP-side OAuth surface comprising the authorization endpoint, token endpoint, revocation endpoint, and discovery metadata endpoint. Implemented in `src/mcp_protocol/auth/`.
- **ClientRegistration** — per-MCP-client metadata. Includes client_id (orchestrator-generated), CIMD URL, validated CIMD content, redirect URIs, allowed scopes, registration timestamp, status.
- **AccessToken** — short-lived JWT-signed token with claims `sub` (participant_id), `client_id`, `scope`, `auth_time`, `iat`, `exp`, `jti`. Lifetime governed by `SACP_OAUTH_ACCESS_TOKEN_TTL_MINUTES`.
- **RefreshToken** — longer-lived opaque token, Fernet-encrypted at rest, indexed by hash. Lifetime governed by `SACP_OAUTH_REFRESH_TOKEN_TTL_DAYS`. Rotated atomically on every use; family tracking for replay detection.
- **AuthorizationCode** — single-use, short-lived (default 60-second TTL via `SACP_OAUTH_AUTH_CODE_TTL_SECONDS`). PKCE-bound — the code redemption requires the matching code_verifier.
- **PKCEVerifier** — the server-side hash stored at authorization-request time (the `code_challenge`) and the client-side `code_verifier` presented at code redemption. Only `S256` method is accepted.
- **TokenFamily** — the chain of refresh tokens descending from a single authorization flow. The family is tracked so a replay attempt revokes all descendants AND the family root atomically.
- **OnboardingBundle** — the four-field markdown structure handed from facilitator to participant. Fields: session_id (12-char hex), participant_id (12-char hex), bearer token (opaque 32+ chars), endpoint URL. Includes a masked-display copy-paste block for low-trust side-channel verification.
- **ParticipantClientConfig** — the platform-specific config file: `claude_desktop_config.json` at `%APPDATA%\Claude\` on Windows and at `~/Library/Application Support/Claude/` on macOS. Holds the `mcpServers` dictionary entry for the SACP orchestrator: command, args, env. Subject to platform-specific gotchas.
- **IdentityDistinction** — the documentation concept that session_id and participant_id have the same shape but different roles. The SSE endpoint requires session_id; the bearer token's validation binds to participant_id; a swap produces 403.
- **TroubleshootingMatrix** — the documentation table mapping HTTP status codes (401, 403, 404, timeout) to root-cause lists and fix paths. Lives in `docs/participant-onboarding.md`; platform-specific docs link to it.
- **VersionHeader** — the three-field block (SACP phase, last-updated date, tested-against Claude Desktop / `mcp-remote` versions) at the top of each onboarding doc.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Post-Phase-1, `grep -rn "mcp_server" src/ tests/ docs/ alembic/` MUST return zero hits. Verified by a CI grep guard.
- **SC-002**: Post-Phase-1, the full pytest suite MUST pass with the same test count and same passing assertions as the pre-refactor baseline. Verified by a baseline-capture step in CI.
- **SC-003**: Post-Phase-1, `ls src/` MUST show `participant_api/` and `mcp_protocol/` AND MUST NOT show `mcp_server/`. Verified by a CI directory-listing assertion.
- **SC-004**: Post-Phase-1, a `git log --follow src/participant_api/app.py` invocation MUST return commit history pre-dating the refactor. Verified by a CI follow-history spot-check on at least three randomly-selected moved files.
- **SC-005**: Post-Phase-1, both ASGI apps MUST start successfully via `run_apps.py` AND respond on their existing ports (8750 + 8751) with the same behavior as pre-refactor. Verified by a smoke test.
- **SC-006**: Post-Phase-1, the `/sse/{session_id}` SACP turn-event stream MUST produce the same `{turn, speaker_id, action, skipped}` event shape as pre-refactor for an identical input session. Verified by a regression test.
- **SC-007**: Post-Phase-1, ruff lint MUST pass with zero new findings vs. the pre-refactor baseline.
- **SC-008**: Phase 2's first stub commit (e.g., `src/mcp_protocol/transport.py`) MUST land without name collisions and the test suite MUST remain green. Verified at Phase 2 start time.
- **SC-009**: The deployment-side audit MUST document every `mcp_server` reference in `compose.yaml` + `.env` + any related script files and confirm each is updated. The operator MUST be informed via the PR description of the separate manual update needed on TrueNAS.
- **SC-010**: With `SACP_MCP_PROTOCOL_ENABLED=true`, an `mcp-remote` bridge MUST complete the full handshake (initialize → tools/list → tools/call) against the SACP MCP endpoint using a valid bearer token. Verified by an end-to-end test.
- **SC-011**: With `SACP_MCP_PROTOCOL_ENABLED=true`, a Claude Desktop Pro+ Custom Connector configuration pointed at the SACP MCP endpoint MUST complete the same handshake. Verified by a manual smoke test per release.
- **SC-012**: With `SACP_MCP_PROTOCOL_ENABLED=true`, `claude mcp add sacp <url> --token <bearer>` MUST register successfully AND the SACP tools MUST surface in claude code's tool list. Verified by a manual smoke test.
- **SC-013**: `initialize` P95 latency MUST be ≤ 500ms under normal load. Verified by a perf-test harness exercising 100 concurrent handshakes.
- **SC-014**: `tools/list` P95 latency MUST be ≤ 100ms. Verified by the same perf-test harness.
- **SC-015**: `tools/call` round-trip P95 latency MUST be ≤ 5s for the canonical test tool. Verified by the same perf-test harness.
- **SC-016**: With `SACP_MCP_PROTOCOL_ENABLED=false`, the `/mcp` endpoint MUST return HTTP 404 AND the SACP participant_api MUST be unaffected. Verified by an endpoint-availability test.
- **SC-017**: The MCP error model MUST conform to JSON-RPC 2.0. Verified by a protocol-compliance test harness driving each documented error path.
- **SC-018**: Every `tools/call` invocation MUST emit one `admin_audit_log` row with `action='mcp_tool_called'`. Verified by an integration test.
- **SC-019**: Cross-instance dispatch via spec 022's binding registry MUST work transparently to the MCP client. Verified by a multi-instance integration test.
- **SC-020**: The concurrent-session cap MUST be enforced. With the cap set to 5 (test config), the 6th `initialize` MUST return HTTP 503 with Retry-After.
- **SC-021**: The `prompts/list` and `resources/list` methods MUST return code -32601 (method not found) in v1.
- **SC-022**: The `Mcp-Session-Id` token MUST be 256-bit, cryptographically generated. Verified by inspecting the token-generation code path.
- **SC-023**: The `/.well-known/mcp-server` endpoint MUST respond even when `SACP_MCP_PROTOCOL_ENABLED=false`, with the `enabled: false` flag.
- **SC-024**: Every public `participant_api` endpoint MUST be reachable via at least one MCP tool. Verified by an architectural test enumerating endpoints and tools.
- **SC-025**: JSON Schema coverage for tool params and returns MUST be 100% — every field declared with its type, every error path enumerated. Verified by a registry-validation test at startup.
- **SC-026**: Zero behavior drift between a REST endpoint and its MCP tool counterpart. Verified by a side-by-side test asserting equivalent persisted-state outcomes.
- **SC-027**: Every successful MCP tool dispatch MUST emit exactly one `admin_audit_log` row. Verified by an audit-log invariant test.
- **SC-028**: Scope enforcement MUST reject every cross-scope invocation. Verified by a parameterized test cycling through scope/tool combinations.
- **SC-029**: Idempotency on mutating writes MUST return the same result on key re-submission within the retention window.
- **SC-030**: Pagination on list-returning tools MUST traverse the full result set across pages in stable order.
- **SC-031**: Per-tool V14 P95 budgets MUST be met under representative load. Verified by a perf-test suite.
- **SC-032**: Granular master switches MUST hide their tools from `list_tools` AND reject `call_tool` with `SACP_E_NOT_FOUND`.
- **SC-033**: Tool versioning MUST allow `session.create.v1` and `session.create.v2` to coexist for one minor-version cycle without conflict.
- **SC-034**: AI participant access MUST be enforced per the per-tool `aiAccessible` flag. Verified by a parameterized test cycling AI vs. human callers.
- **SC-035**: Sponsor-scoped tools MUST be reachable only by sponsors of the target participant. Verified by a sponsor-scope test.
- **SC-036**: An architectural test MUST assert every public participant_api endpoint has a corresponding MCP tool. CI fails on drift.
- **SC-037**: Tool dispatch through the registry MUST be O(1) on registry size for lookup. Verified by a microbenchmark comparing registry lookup time across 10, 100, and 1000 entries.
- **SC-038**: Claude Desktop's OAuth flow against the orchestrator MUST complete end-to-end without manual intervention beyond standard browser interaction. Verified by an end-to-end test using a headless OAuth client.
- **SC-039**: Existing static-token participants on the MCP endpoint MUST receive the migration prompt on first post-Phase-4 request AND continue working during the grace period.
- **SC-040**: Per-participant token isolation MUST hold under concurrent-participant load — one participant's token compromise MUST NOT affect another participant's tokens.
- **SC-041**: Refresh-token rotation MUST atomically issue new tokens AND revoke the presented one; a replay MUST revoke the entire family.
- **SC-042**: PKCE MUST be required and MUST reject non-S256 challenges. Verified by an OAuth conformance test.
- **SC-043**: Discovery metadata at `/.well-known/oauth-protected-resource` MUST match the MCP authorization spec shape.
- **SC-044**: CIMD submission MUST validate against the schema AND reject hostile documents. Verified by a CIMD fuzz test with oversized, malformed, and redirect-chain inputs.
- **SC-045**: Token revocation MUST propagate to existing MCP connections within the configured SLA.
- **SC-046**: AI participants MUST NOT obtain OAuth tokens. Verified by an enforcement test attempting to start an OAuth flow naming an AI participant.
- **SC-047**: Step-up authorization MUST be required for destructive facilitator actions. Verified by a step-up test invoking each destructive tool with a stale token.
- **SC-048**: Authorization endpoint and token endpoint P95 latency MUST be ≤ 200ms under representative load.
- **SC-049**: Cross-instance token state consistency MUST hold within the cache TTL — a revocation on one instance MUST be visible on another instance within 30 seconds.
- **SC-050**: With any of the new env vars (across all phases) set to an invalid value, the orchestrator process MUST exit at startup with a clear error naming the offending var (V15 fail-closed gate observed in CI).
- **SC-051**: An architectural test MUST assert no code path outside `src/mcp_protocol/auth/` validates OAuth tokens. CI fails on drift.
- **SC-052**: Every token lifecycle event MUST emit the corresponding audit row. Verified by an audit-invariant test driving each token state transition.
- **SC-053**: A non-Spike Windows participant MUST be able to onboard end-to-end following ONLY the docs (no operator support, no chat support) in ≤ 15 minutes total including config edits. Verified by a documented walk-through with stopwatch data recorded in the doc's commit history.
- **SC-054**: A non-Spike macOS participant MUST be able to onboard end-to-end following ONLY the docs in ≤ 15 minutes total including config edits.
- **SC-055**: Zero unresolved 401 / 403 / 404 / timeout errors MUST remain at the end of the Windows onboarding walk-through.
- **SC-056**: Zero unresolved 401 / 403 / 404 / timeout errors MUST remain at the end of the macOS onboarding walk-through.
- **SC-057**: The four troubleshooting matrix entries (401, 403, 404, timeout) MUST each carry at least one evidenced root cause (each entry's root-cause list cites at least one observed-in-practice case, dated rather than memory-cited). Verified by reviewing each entry against the V19 evidence-and-judgment marker policy.
- **SC-058**: Each of the three onboarding docs MUST carry a version header per FR-117 (SACP phase, last-updated date, tested-against versions). Verified by a structural check at commit time.
- **SC-059**: The Phase 4 OAuth migration section MUST be structurally present in `docs/participant-onboarding.md` even when content-empty. Verified by a structural check at v1 ship time.
- **SC-060**: Known-good sample `claude_desktop_config.json` blocks MUST be present in both platform-specific docs and MUST validate as JSON (parseable). Verified by a JSON-parse check at doc-commit time.
- **SC-061**: Cross-references to Phases 1-4 MUST be present in the docs and MUST resolve correctly when the phases are present under the spec directory.
- **SC-062**: The redaction policy from FR-121 MUST be observed throughout the docs; no real bearer-token-shaped value MUST appear in any sample. Verified by a secret-scanner pass on the doc files.
- **SC-063**: All seven closeout preflights MUST be green on each phase's merge PR before merge.

## Out of Scope

- **Phase 1 — Behavior changes of any kind.** Pure refactor. No new endpoints, no new env vars, no new dependencies. The `/sse/{session_id}` SACP turn-event stream stays exactly as-is in shape, payload, transport semantics, and auth posture; only its module path changes.
- **Phase 2 — `prompts` and `resources` capability families.** The MCP protocol has `tools`, `prompts`, and `resources` as the three first-class capability families. v1 implements `tools` only. `prompts` and `resources` are deferred to a Phase 2 follow-up amendment, gated on demand from the target clients.
- **Phase 2 — MCP SDK selection lock-in.** The choice between the Python `mcp` SDK and a direct wire-protocol implementation is settled in `/speckit.plan`, not in this spec.
- **Phase 3 — Per-tool enumeration of names, schemas, and error contracts.** This spec lists FAMILIES of tools and the FR families that constrain each. The exact tool names, parameter schemas, return schemas, and error contracts pin in `/speckit.plan`'s artifacts (one per tool category).
- **Phase 3 — Hot-reload of the tool registry.** The registry is in-memory and loaded at startup. Adding a new tool requires a deploy.
- **Phase 4 — WebAuthn / passkey support.** Out of scope for v1. The OAuth 2.1 surface is extensible to passkeys later without breaking changes.
- **Phase 4 — Migration of the SACP participant API off static tokens.** The migration is MCP-scoped. The participant_api routers used by the Web UI stay on static bearers indefinitely.
- **Phase 4 — Cross-orchestrator OAuth federation.** Phase 4 federation work may define cross-orchestrator OAuth flows; out of scope for this build.
- **Phase 5 — Linux MCP-client onboarding.** Explicitly deferred. The cross-platform overview acknowledges the deferral so Linux readers are not stranded.
- **Phase 5 — Mobile (iOS / Android) MCP-client onboarding.** Out of scope and explicitly not mentioned in the cross-platform overview to avoid implying a roadmap commitment.
- **Phase 5 — Account-flow onboarding.** Token-flow-first; account-flow onboarding (login-based identity, persistent session history per spec 023) is a separate doc when spec 023's tasks schedule.
- **All phases — Topology 7 (MCP-to-MCP peer).** Each phase explicitly carves topology 7 out. Phase 4 federation work may define peer-to-peer OAuth flows; topology 7 onboarding gets its own doc when federation work scopes.

## Cross-References to Existing Specs and Design Docs

- **Internal phase sequence (A → B+C → D → E)**: Phase 1 (codebase restructure) blocks Phases 2/3/4. Phase 2 (MCP protocol) and Phase 3 (tool mapping) are co-designed; B's dispatcher signature MUST match C's `ToolDispatch` shape; they may merge in either order so long as registry-shape contracts hold. Phase 4 (OAuth) requires Phases 2 and 3 stable AND sovereignty remediation completing. Phase 5 (onboarding docs) ships v1 against the existing SACP-native surface and updates as each phase lands.
- **Spec 006 (mcp-server, the original misnamed spec)** — historically misnamed; Phase 1 retroactively corrects the module name. Spec 006 itself is not edited (historical record stays intact); future readers should be directed to this spec for the rename context.
- **Spec 002 (participant-auth)** — provides the static-bearer model carried into Phase 2 and migrated off in Phase 4 (MCP-scoped). The token-store contract, the ScrubFilter pattern, and the rotation grace window (§FR-007) are re-used across phases.
- **Spec 003 (turn-loop-engine) §FR-030** — MCP-specific stage timings register within the existing `routing_log` per-stage timing infrastructure.
- **Spec 007 (ai-security-pipeline)** — MCP `tools/call` invocations that route to participant_api endpoints emitting AI-side content flow through the `_validate_and_persist` pipeline at the participant_api layer; the MCP protocol layer does NOT bypass security.
- **Spec 010 (debug-export)** — wrapped by Phase 3's `debug.export_session` and `debug.export_participant_view` tools. Phase 5's catch-up-after-reconnect path (FR-107) cites spec 010's session transcript export endpoint.
- **Spec 011 (web-ui)** — alternative onboarding path for participants who connect via the Web UI instead of an MCP client. The Web UI's `prime_from_*` integration boundary is renamed (`prime_from_participant_api_app`) but the semantic contract is unchanged. No spec 011 amendment required at scaffold time; the cross-link from the onboarding docs to the Web UI flow arrives at this spec's implementation time.
- **Spec 013 (high-traffic-mode)** — provides the routing-mode setting endpoint wrapped by Phase 3's `participant.set_routing_preference`.
- **Spec 014 (dynamic-mode-assignment)** — provides the signal-driven routing controller `participant.set_routing_preference` interacts with per spec 014's signal vocabulary.
- **Spec 019 (network-rate-limiting)** — re-used by Phase 2 (`FR-028`) and Phase 4 (`FR-093`). MCP requests, authorization-endpoint requests, and token-endpoint requests all share rate-limit budgets with participant_api requests per the spec 019 contract.
- **Spec 022 (detection-event-history)** — provides (a) the cross-instance binding registry re-used by Phase 2 for MCP request routing per `FR-023`, and (b) the read-side surface wrapped by Phase 3's `detection_events.list` and `detection_events.detail` tools.
- **Spec 023 (user-accounts)** — provides (a) the sponsor scope model (Phase 3 `FR-065`, Phase 4 `FR-077`), (b) the Fernet API-key encryption pattern re-used by Phase 4 for refresh-token at-rest storage (`FR-081`), and (c) the email + password authentication used at Phase 4's authorization endpoint.
- **Spec 024 (facilitator-scratch)** — provides the scratch tool surface wrapped by Phase 3's `scratch.*` tools.
- **Spec 029 (audit-log-viewer)** — provides the read-side surface wrapped by Phase 3's `admin.get_audit_log` tool AND surfaced via Phase 5's docs as the audit forensic path AND filtered by `token_*` actions for Phase 4's per-participant token issuance audit.
- **Constitution §10 Phase 3 OAuth roadmap** — Phase 4 of this build satisfies the §10 deliverable "OAuth 2.1 with PKCE replaces static tokens" scoped to the MCP protocol endpoint.
- **Constitution §14.1** — Feature work workflow. This spec scaffolds via the numbered branch convention.
- **Constitution V6** — graceful degradation. Phase 5's troubleshooting matrix (FR-116) is the explicit graceful-degradation surface for the participant-facing flow.
- **Constitution V11** — supply chain. Phase 2's possible `mcp` SDK pin and Phase 4's signing-key handling both fall under V11; the Phase 1 refactor introduces no new deps.
- **Constitution V12** — topology applicability. All phases apply to topologies 1-6 and are NOT applicable to topology 7.
- **Constitution V13** — primary use cases. Every V13 use case has at least one tool surface (Phase 3), one onboarding path (Phase 5), AND benefits from OAuth on the MCP endpoint where applicable (Phase 4).
- **Constitution V14** — per-stage timing budgets. Phases 2, 3, and 4 contribute V14 budgets; Phase 5 contributes documentation-driven onboarding-time budgets (SC-053/054).
- **Constitution V15** — fail-closed. All new env vars across phases fail closed at startup.
- **Constitution V16** — env-var validation at startup. Phases 2, 3, and 4 each introduce env vars subject to the V16 deliverable gate; Phase 1 and Phase 5 introduce zero new env vars.
- **Constitution V17** — transcript canonicity. OAuth flow events and MCP audit rows go to `admin_audit_log` and `security_events`, NOT the message transcript.
- **Constitution V18** — derived-artifacts traceability. Phase 4 tokens carry claims sufficient to trace back to the canonical participant record AND the scope-grant decision (FR-097). Phase 3 tool dispatch results that denormalize from canonical source rows carry source-range metadata where the source allows it.
- **Constitution V19** — evidence + judgment markers. Phase 5 troubleshooting matrix entries (FR-116) cite evidence from real debug sessions — the 2026-05-12 debug session is one such source, cited by date.

## Clarifications

### Phase 1 clarifications

- **Target module name `participant_api` vs. alternatives.** Drafted as `src/participant_api/` because the routers ARE the participant-facing API surface for SACP. The name avoids overloading "api" alone (the Web UI under port 8751 also serves API endpoints) and avoids "sacp" (every module in `src/` is SACP). [NEEDS CLARIFICATION: confirm `participant_api` vs. `sacp_api` vs. `orchestrator_api` vs. `core_api`. Stakeholder concern: the name must read naturally to a contributor scanning `src/` for the first time and must not collide with later module additions.]
- **Namespace for the future MCP module.** Drafted as `src/mcp_protocol/` to make the intent explicit. Alternatives: `src/mcp/` (shortest; collides cognitively with the old `mcp_server` for a release cycle), `src/protocol/mcp/` (nested; cleaner if more protocols land later — e.g., A2A — but speculative). [NEEDS CLARIFICATION: confirm `src/mcp_protocol/` over `src/mcp/` or `src/protocol/mcp/`.]
- **Backward-compat alias retention duration.** Drafted: `prime_from_mcp_app()` retained as an alias for one release after rename, then removed. [NEEDS CLARIFICATION: confirm one-release retention vs. immediate removal vs. permanent alias. Internal audit: are there any external callers at all? If none, immediate removal is cleaner.]
- **Deployment config path audit.** The TrueNAS Dockge stack may reference `src/mcp_server/` paths in volume mounts, entrypoint scripts, or env-var defaults. Drafted: audit both the repo-side `compose.yaml` AND the running-deployment file on TrueNAS. [NEEDS CLARIFICATION: confirm both paths are audited; confirm who applies the deployment-side update.]
- **Alembic migration impact.** Drafted: alembic revision IDs are not affected. However, any migration that imports from `src.mcp_server` (e.g., for shared constants or enum mirrors) must be updated. [NEEDS CLARIFICATION: confirm migrations contain no module-path references in `down_revision` or related metadata fields; spot-check expected zero hits.]
- **CI lane parity.** Drafted: the pre-refactor test suite establishes a baseline; the post-refactor suite must match exactly. [NEEDS CLARIFICATION: confirm baseline-capture mechanism (CI run pre-refactor, post-refactor, diff the outputs) vs. trust-the-greens approach.]

### Phase 2 clarifications

- **Protocol version pin.** Drafted: pin to MCP spec revision **2025-11-25** as the v1 target. The `initialize` handshake advertises this version; clients negotiating older versions are rejected. [NEEDS CLARIFICATION: confirm 2025-11-25 pin vs. supporting a version range; confirm rejection-on-mismatch vs. graceful-downgrade.]
- **Transport binding — mount on port 8750 vs. third ASGI app.** Drafted: mount at `/mcp` on the existing port 8750 service. Alternative: a third ASGI app on its own port (e.g., 8752) co-running in `src/run_apps.py`. [NEEDS CLARIFICATION: confirm port 8750 mount at `/mcp` vs. third ASGI app on 8752; if 8750, confirm `/mcp` path vs. `/mcp/v1/` vs. another prefix.]
- **Prompts and resources protocol surfaces — v1 scope.** Drafted: out-of-scope for v1. The MCP protocol has `tools`, `prompts`, and `resources` as the three first-class capability families. v1 implements `tools` only. [NEEDS CLARIFICATION: confirm tools-only v1 vs. tools+prompts v1 vs. tools+prompts+resources v1.]
- **AI participant access via MCP.** Drafted: yes, AI participants in a SACP session MAY connect via MCP. The provider-side exclusion (humans must be excluded from LiteLLM dispatch paths) does NOT apply in reverse — MCP-as-client-side is fine for either humans or AIs. [NEEDS CLARIFICATION: confirm AI-via-MCP allowed vs. human-only-via-MCP; confirm interaction with the existing provider-exclusion invariant.]
- **Session timeout semantics.** Drafted: idle timeout 30 minutes since last request (configurable; default 1800). Hard cap: 24 hours per session id regardless of activity. [NEEDS CLARIFICATION: confirm 30-minute idle / 24-hour hard cap vs. other values; confirm idle-expiry behavior (404 vs. 401 vs. 410).]
- **Concurrent-session cap value.** Drafted: 100 concurrent MCP sessions per orchestrator instance, default 100. [NEEDS CLARIFICATION: confirm 100-session cap value; the right number depends on per-session memory footprint, which is unknown until prototyping lands.]
- **Integration with the existing `/sse/{session_id}` SACP stream.** Drafted: structurally distinct from any MCP transport mechanism. The SACP stream's `{turn, speaker_id, action, skipped}` payload is NOT an MCP envelope. [NEEDS CLARIFICATION: confirm structural-separation stance vs. exposing the SACP turn stream through an MCP `resources` subscription in a future amendment.]
- **Error-code mapping from MCP to existing SACP error codes.** Drafted: validation → -32602; auth → -32001; rate-limit → -32002; SACP state → -32003. SACP-native error codes preserved in `data`. [NEEDS CLARIFICATION: confirm preserved-in-data approach vs. silent translation; confirm the four server-defined code reservations vs. other values within the JSON-RPC server-error range.]
- **Discovery metadata endpoint binding.** Drafted: `/.well-known/mcp-server` returns minimal metadata. [NEEDS CLARIFICATION: confirm `/.well-known/mcp-server` path vs. alternative; confirm what fields are mandatory per the MCP spec revision 2025-11-25 and which are optional.]

### Phase 3 clarifications

- **Tool naming convention final pin.** Drafted as `domain.action` with snake_case actions. MCP spec is silent on naming convention; community examples vary. [NEEDS CLARIFICATION: confirm `domain.action` snake_case versus camelCase versus flat snake_case (`session_create`).]
- **AI participant tool access list.** Drafted as: AI participants registered via the BYOK provider flow can invoke a subset of tools — message injection on their own behalf, proposal voting, scratch read where extended to it, detection-event read. [NEEDS CLARIFICATION: enumerate the AI-accessible tool list versus deny-list approach.]
- **Sponsor scope mapping.** Spec 023 introduces account-level sponsorship. Drafted as: tools that touch the sponsored AI's budget are reachable by the sponsor's scope; tools that emit on the sponsored AI's behalf are not. [NEEDS CLARIFICATION: enumerate sponsor-scope tool list; confirm sponsor cannot impersonate the sponsored AI.]
- **Versioning policy.** Drafted as: tool names carry an implicit v1; a breaking schema change requires a new tool name (`session.create.v2`). [NEEDS CLARIFICATION: confirm version-as-name-suffix versus version-as-protocol-header versus version-as-tool-metadata.]
- **Pagination cursor encoding.** Drafted as: cursor is an opaque base64-encoded JSON object with `{last_id, sort_key_value}`. [NEEDS CLARIFICATION: confirm opaque-base64 versus server-side-token; affects horizontal-scaling story.]
- **Idempotency-key expiration.** Drafted as: 24 hours retention; re-submitted key within the window returns the original result. [NEEDS CLARIFICATION: confirm 24h expiration versus session-lifetime retention versus no expiration.]
- **Error-code consolidation.** Drafted as: every tool defines its error codes locally; a shared catalog lives in `src/mcp_protocol/errors.py`. [NEEDS CLARIFICATION: confirm shared catalog plus per-tool extension versus fully per-tool.]
- **Debug-export tool scope binding.** Spec 010's `/tools/debug/export` is facilitator-scoped today. Drafted as: same scope on the MCP tool variant; chunked-return mode for large exports. [NEEDS CLARIFICATION: confirm chunked-return mechanism versus single-shot with size cap.]
- **Deprecated-tool sunset horizon.** Drafted as: one minor-version cycle. [NEEDS CLARIFICATION: confirm one-minor-cycle versus six-month versus operator-tunable.]
- **Granular master switches.** Drafted as: one master switch plus optional per-category switches defaulting `true` when the master is `true`. [NEEDS CLARIFICATION: confirm one-per-category versus one-per-tool versus master-only.]
- **Cross-spec tool surfaces (022, 024, 029).** Specs 022, 024, and 029 ship read-side surfaces that become MCP tools. Drafted as: Phase 3 declares those tools and depends on the source specs being Implemented. [NEEDS CLARIFICATION: confirm dependency direction; if 022/024/029 ship before C, do they expose MCP tools themselves or wait for C?]
- **Tool description language scope.** Drafted as: each tool's `description` string is in English; localization is out of scope for v1. [NEEDS CLARIFICATION: confirm English-only versus locale-aware via MCP protocol extension.]

### Phase 4 clarifications

- **Token format pin.** Drafted as opaque random tokens stored in DB (refresh tokens) with short-lived JWT access tokens carrying signed claims. [NEEDS CLARIFICATION: confirm JWT-access + opaque-refresh versus fully-opaque versus fully-JWT.]
- **Refresh-rotation timing.** Drafted as: every refresh-token use rotates the token. [NEEDS CLARIFICATION: confirm strict-rotation-on-every-use versus rotation-on-near-expiry versus no-rotation.]
- **Scope vocabulary granularity.** Drafted as: role-level scopes plus per-tool-category scopes. [NEEDS CLARIFICATION: confirm role-plus-tool-category versus role-only versus per-tool granularity.]
- **Static-token grace duration.** Drafted as: env-tunable, default `90` (one quarter). [NEEDS CLARIFICATION: confirm 90-day default versus 30-day default versus no-default-must-be-set.]
- **WebAuthn / passkey scope.** Drafted as: out of scope for v1. [NEEDS CLARIFICATION: confirm v1 password-only versus v1 password-or-passkey.]
- **Multi-session-concurrent-participant model.** Drafted as: yes — one OAuth subject can participate in multiple SACP sessions concurrently. [NEEDS CLARIFICATION: confirm subject-scoped-many-participants versus subject-equals-one-participant.]
- **Step-up freshness threshold.** Drafted as: 5 minutes (configurable). [NEEDS CLARIFICATION: confirm 5-minute default versus 60-second default versus operator-set.]
- **Client-registration mode.** Drafted as: env-controlled (`open` / `allowlist` / `closed`); default `allowlist`. [NEEDS CLARIFICATION: confirm allowlist-default versus open-default.]
- **Revocation propagation latency.** Drafted as: token revocation closes existing MCP transport connections within 5 seconds. [NEEDS CLARIFICATION: confirm 5-second revocation-to-disconnect SLA versus immediate-disconnect-via-push.]
- **Cross-instance token-store consistency model.** Drafted as: DB as source-of-truth; per-instance LRU with TTL ≤ 30s. [NEEDS CLARIFICATION: confirm DB-as-source-of-truth versus DB-plus-pub-sub-broadcast.]
- **Sovereignty boundary specifics.** The sovereignty remediation clarifies that facilitator scope grants session-governance authority but NOT access to participant API keys, wallets, or sponsored-AI credentials. [NEEDS CLARIFICATION: confirm exclusions enumerated in the scope claim semantics.]
- **AI participant exclusion enforcement mechanism.** Drafted as: AI participants registered via the BYOK flow are structurally excluded from OAuth issuance. [NEEDS CLARIFICATION: confirm exclusion-at-issuance versus exclusion-at-dispatch versus both.]

### Phase 5 clarifications

- **Document location convention.** Drafted as: three files at `docs/` root, NOT nested in `docs/onboarding/`. [NEEDS CLARIFICATION: confirm flat `docs/` placement vs. `docs/onboarding/` subdirectory.]
- **Versioning convention.** Drafted as: each doc carries a header `**SACP Phase**: <phase>` and `**Last Updated**: <date>`. [NEEDS CLARIFICATION: confirm phase-and-date dual fields vs. a single doc-version semver vs. relying on git history.]
- **Sample config redaction policy.** Drafted as: placeholder tokens use the prefix `SACP_DOC_EXAMPLE_` (32+ alphanumeric chars); session_id placeholder is `000000000000`. [NEEDS CLARIFICATION: confirm prefix-marked placeholder shape vs. generic `<your-token-here>` angle-bracket markers vs. real-format example tokens that would need allowlist entries.]
- **Troubleshooting matrix scope.** Drafted as: the matrix covers four HTTP status codes (401, 403, 404, timeout) at minimum. [NEEDS CLARIFICATION: confirm four-code minimum vs. broader coverage from spec inception.]
- **Linux deferral confirmation.** Drafted as: Linux client onboarding is explicitly out-of-scope for v1. [NEEDS CLARIFICATION: confirm Linux deferral with no-stub-page approach vs. minimal Linux stub page that says "deferred".]
- **macOS Apple Silicon vs Intel differences.** Drafted as: the macOS doc treats both architectures together; ARM-specific notes appear inline. [NEEDS CLARIFICATION: confirm unified-macOS-doc with inline arch notes vs. preemptive split into `participant-onboarding-macos-arm.md` and `participant-onboarding-macos-intel.md`.]
- **Mobile client roadmap.** Drafted as: mobile MCP clients are out-of-scope for v1; not mentioned in the cross-platform overview. [NEEDS CLARIFICATION: confirm complete-omission vs. one-sentence acknowledgement that mobile is deferred.]
- **Pre-MCP-shipping docs surface.** Drafted as: the docs ship as v1 today describing the existing SACP participant API surface, and gain a Phase 4 amendment section when Phase 2 / Phase 4 ship. [NEEDS CLARIFICATION: confirm ship-now-with-reserved-amendment vs. wait-for-Phase-2-to-ship vs. ship-now-with-two-versions-side-by-side.]

## Constitution Constraints (V12-V20)

### V12 — Topology Applicability

All five phases apply to **topologies 1-6** (orchestrator-mediated). Each phase's surfaces are orchestrator-side: Phase 1's renamed module continues to serve the same routes for the same topologies; Phase 2's MCP endpoint is orchestrator-side with clients connecting to the orchestrator and invoking tools the orchestrator dispatches; Phase 3's tool surface is a server-side capability of the orchestrator; Phase 4's authorization server is an orchestrator-side surface; Phase 5's docs describe the orchestrator-connection flow from the participant's perspective. **Topology 7 (MCP-to-MCP peer)** is NOT applicable to any phase in v1. In topology 7 each participant's MCP client and server are themselves peers; there is no central orchestrator hosting a tool registry or authorization server. Phase 4 federation work may define cross-orchestrator OAuth flows; that is out of scope for this build. Topology-7 deployments will need their own onboarding doc that describes the MCP-to-MCP credential model.

Cross-instance routing within topologies 1-6 is supported via the spec 022 binding registry (`FR-023`). MCP clients can connect to any orchestrator instance; their requests route to the instance owning the target SACP session.

### V13 — Use Case Coverage

Every V13 primary use case has at least one tool surface (Phase 3), one onboarding path (Phase 5), AND benefits from OAuth on the MCP endpoint where applicable (Phase 4). The use cases that especially benefit from the build:

- §1 Distributed Software Collaboration — multi-tool AI workflows where SACP is one tool among many; session lifecycle + message injection + proposal flow tools cover the engineering interactions.
- §2 Research Paper Co-authorship — long-running session + scratch + audit-log read tools for retrospective review; weeks-long sessions where token rotation across days matters AND the documented rotation path covers lost-token recovery.
- §3 Consulting Engagement — an external consulting AI's host process speaks MCP to many servers; SACP becomes one. The 15-minute onboarding target (SC-053 / SC-054) reflects consulting-engagement onboarding budgets. Multiple devices per consultant motivate per-device OAuth tokens.
- §4 Open Source Project Coordination — proposal flow + audit-log read tools; documented bundle accommodates contributors on either Windows or macOS.
- §5 Technical Review and Audit — a review AI's host process invokes SACP tools for audit-trail inspection (read-only). The audit-log read tool surface is OAuth-scope-gated. The troubleshooting matrix covers common credential-confusion cases.
- §6 Decision-Making Under Asymmetric Expertise — routing-preference + proposal vote tools; domain experts join via Claude Desktop or Cursor with the OAuth flow as their entry point. The rotation path covers experts returning across multiple engagement windows.
- §7 Zero-Trust Cross-Organization Collaboration — scope enforcement + audit-log read tools. Per-participant token isolation prevents cross-organization token leakage. The masked-display copy-paste block supports low-trust side-channel verification between organizations.

Phase 1 is topology-agnostic and use-case-agnostic: it serves all use cases identically pre/post refactor.

### V14 — Performance Budgets

Phase 1 contributes zero new budgets — it is a pure refactor with no behavior change; all existing budgets carry through unchanged because the code paths are byte-identical after the move. Refactor-specific operational budget: the refactor PR's test-suite execution time MUST be within ±5% of the pre-refactor baseline (informational, not blocking).

Phase 2 contributes: `initialize` P95 ≤ 500ms; `tools/list` P95 ≤ 100ms; `tools/call` P95 ≤ 5s; `ping` P95 ≤ 50ms; `/.well-known/mcp-server` discovery P95 ≤ 20ms. Per-stage timings emit to `routing_log` per spec 003 §FR-030 with new timing labels (`mcp_initialize`, `mcp_tools_list`, `mcp_tools_call`, `mcp_ping`).

Phase 3 contributes per-tool budgets recorded in tool metadata: read tools (single-record) P95 ≤ 200ms; read tools (list with pagination) P95 ≤ 1s per page at default page size; write tools (single-record) P95 ≤ 500ms; write tools (multi-step) P95 ≤ 1s; debug-export tools P95 ≤ 5s; dispatch overhead P95 ≤ 5ms per call for the protocol → dispatcher → registry-lookup → scope-check path, excluding the actual dispatch callable execution.

Phase 4 contributes: authorization endpoint P95 ≤ 200ms; token endpoint P95 ≤ 200ms; revocation endpoint P95 ≤ 100ms; discovery metadata P95 ≤ 50ms; per-dispatch token validation P95 ≤ 5ms (cache-hit path; within the dispatch-overhead budget from Phase 3); revocation propagation SLA ≤ 5 seconds end-to-end.

Phase 5 contributes documentation-driven onboarding-time budgets: Windows onboarding time ≤ 15 minutes from bundle receipt to first message sent (SC-053); macOS onboarding time ≤ 15 minutes (SC-054). These are doc-quality budgets, not runtime budgets — verified by walk-through measurement at doc-update time, recorded in the doc's commit history.

### V15 — Fail-Closed

All new env vars across phases fail closed. Invalid values for any of the env vars introduced in Phases 2, 3, and 4 MUST cause the orchestrator process to exit at startup with a clear error naming the offending var; the startup validator runs before any ASGI app is mounted. Phase 1 introduces zero new env vars; existing fail-closed semantics carry through unchanged. Phase 5 introduces zero new env vars; the V15 surface is unchanged.

### V16 — Env-Var Validation at Startup

Phase 1 introduces zero new env vars; the V16 deliverable gate is trivially satisfied. Phase 2 introduces four env vars (`SACP_MCP_PROTOCOL_ENABLED`, `SACP_MCP_SESSION_IDLE_TIMEOUT_SECONDS`, `SACP_MCP_SESSION_MAX_LIFETIME_SECONDS`, `SACP_MCP_MAX_CONCURRENT_SESSIONS`). Phase 3 introduces per-category enables (`SACP_MCP_TOOL_SESSION_ENABLED`, `SACP_MCP_TOOL_PARTICIPANT_ENABLED`, `SACP_MCP_TOOL_PROPOSAL_ENABLED`, `SACP_MCP_TOOL_REVIEW_GATE_ENABLED`, `SACP_MCP_TOOL_DEBUG_EXPORT_ENABLED`, `SACP_MCP_TOOL_AUDIT_LOG_ENABLED`, `SACP_MCP_TOOL_DETECTION_EVENTS_ENABLED`, `SACP_MCP_TOOL_SCRATCH_ENABLED`, `SACP_MCP_TOOL_PROVIDER_ENABLED`, `SACP_MCP_TOOL_ADMIN_ENABLED`) plus `SACP_MCP_TOOL_IDEMPOTENCY_RETENTION_HOURS`, `SACP_MCP_TOOL_DEPRECATION_HORIZON_DAYS`, `SACP_MCP_TOOL_PAGINATION_DEFAULT_SIZE`, `SACP_MCP_TOOL_PAGINATION_MAX_SIZE`. Phase 4 introduces eleven (`SACP_OAUTH_ENABLED`, `SACP_OAUTH_ACCESS_TOKEN_TTL_MINUTES`, `SACP_OAUTH_REFRESH_TOKEN_TTL_DAYS`, `SACP_OAUTH_AUTH_CODE_TTL_SECONDS`, `SACP_OAUTH_CLIENT_REGISTRATION_MODE`, `SACP_OAUTH_STATIC_TOKEN_GRACE_DAYS`, `SACP_OAUTH_STEP_UP_FRESHNESS_SECONDS`, `SACP_OAUTH_REVOCATION_PROPAGATION_SECONDS`, `SACP_OAUTH_SIGNING_KEY_PATH`, `SACP_OAUTH_FAILED_PKCE_THRESHOLD`, `SACP_OAUTH_CIMD_ALLOWED_HOSTS`). Each MUST have a validator function in `src/config/validators.py` registered in the `VALIDATORS` tuple AND a corresponding section in `docs/env-vars.md` with the six standard fields BEFORE `/speckit.tasks` is run for the relevant phase. Phase 5 introduces zero new env vars; the docs MAY reference existing env vars by linking to their `docs/env-vars.md` entry rather than restating the V16 type-range-fail-closed semantics.

### V17 — Transcript Canonicity

OAuth flow events (authorization request, code issuance, code redemption, token issuance, refresh, revocation) and MCP audit rows (every `tools/call` invocation; every token lifecycle event) go to `admin_audit_log` AND `security_events`. They MUST NOT enter the message transcript — they are forensic, not conversational. The transcript is the SACP session messages, not the protocol-layer invocation log. When an MCP `tools/call` results in a turn being posted to a session, the participant_api side writes the transcript content separately from the MCP audit row. Phase 1 does not touch the transcript or any audit-log row shape; the refactor is at the module-organization layer.

### V18 — Derived-Artifacts Traceability

Phase 3 tool dispatch results that denormalize from canonical source rows (e.g., audit-log read views) carry source-range metadata in their return schema where the source allows it. Phase 4 issued tokens carry claims sufficient to trace back to the canonical participant record AND the canonical scope-grant decision (`sub`, `client_id`, `scope`, `auth_time`, `iat`, `exp`, `jti`). The architectural test in FR-099 asserts the auth-validation boundary is exclusively in `src/mcp_protocol/auth/`, preserving traceability of the auth boundary itself. Phase 1, Phase 2, and Phase 5 do not introduce derived artifacts subject to V18.

### V11 — Supply Chain

Phase 1 introduces zero new dependencies. Phase 2 likely adds the Python `mcp` SDK as a dependency; if so, the dependency MUST be pinned per Constitution §6.3 (pin to a specific version, not a range). If the team chooses to implement the wire protocol directly without the SDK (to minimize dependency surface), V11 is satisfied trivially. The choice is settled in `/speckit.plan`. Phase 3 introduces zero new third-party dependencies (the tool registry is internal). Phase 4 introduces signing-key handling via the existing `cryptography` library (already a project dependency for Phase 1 Fernet usage per spec 023) plus a JWT library if not already present; both follow §6.3 pinning. Phase 5 introduces zero new dependencies — it is a documentation deliverable.

### V19 — Evidence + Judgment Markers

Phase 5 troubleshooting matrix entries (FR-116) cite evidence from real debug sessions — the 2026-05-12 debug session that exposed the Windows-specific friction is one such source, cited by date. The doc does NOT cite memory-file paths; evidence citation is by date and observed behaviour only. The five Windows-specific gotchas (FR-108 through FR-112) are the gotchas surfaced by the 2026-05-12 session; the two macOS-specific gotchas (FR-113, FR-114) rely on convention rather than observed-in-practice evidence for v1, with SC-054 walk-through verification at doc-update time producing the missing observation set. Phases 1-4 are evidence-rooted in the 2026-05-12 misnamed-module discovery, with the rename, the protocol implementation, the tool mapping, and the OAuth migration all flowing from that single anchored finding.
