# Feature Specification: Tool-List Freshness for Participant-Registered MCP Servers

**Feature Branch**: `017-tool-list-freshness`
**Created**: 2026-05-06
**Status**: Implemented 2026-05-13
**Input**: User description: "Tool-list freshness for participant-registered MCP servers. Participants register their own MCP servers as part of their sovereignty surface. MCP servers may add, remove, or modify tools between session start and any subsequent turn (server restart, capability update, version bump). Without a freshness mechanism, the orchestrator caches stale tool definitions and the participant operates on out-of-date capabilities — which can cause failed tool calls, missing functionality, or silent behavior changes. The mechanism must keep each participant's tool registry private to that participant, integrate cleanly with the adaptive context assembly (§4.2) so system-prompt rebuilds happen at the right moments, and produce audit-log entries for every tool-set change. Provider-native prompt caching makes the system prompt the highest-value cache target on participating providers, so tool-set changes carry a real cost that the spec must address. Phase 1 minimum (polling-only) is acceptable if the push-notification path is non-trivial; the full push + poll + manual-refresh design lands in Phase 2."

## Overview

Participants in SACP register their own MCP servers as part of their
sovereignty surface — a participant brings not just their model and
API key but also the tool capabilities they've chosen to expose to
the conversation (Constitution §3, `sacp-design.md` §6.3 Tool
Access Asymmetry). Once registered, the orchestrator caches each
participant's tool list and includes it in their per-turn context
payload (`sacp-design.md` §4.2 step 6, "Build context payload").

The cached list goes stale. MCP servers add tools when their
maintainer ships a feature; remove tools during a deprecation cycle;
modify tool descriptions or schemas during a version bump; and
disappear briefly during restarts. Without a freshness mechanism,
the orchestrator continues to advertise the cached tools to the
participant's AI — and the AI generates tool calls against a
schema that no longer matches reality. Three concrete failure
modes:

1. **Failed tool call.** AI invokes a tool that has been removed.
   Server returns "tool not found"; the orchestrator surfaces the
   error to the AI, the AI retries, and the participant burns
   tokens on a tool call that cannot succeed regardless of how
   well-formed the request is.
2. **Missing functionality.** AI is unaware of a newly-added tool
   because the cached list is stale. The participant has the
   capability but cannot use it; behavior degrades silently.
3. **Silent behavior change.** A tool's description or schema
   shifts (e.g., a parameter became required, a return shape
   changed) and the AI's calls succeed syntactically but return
   results that no longer match what the AI expected. This is
   the most insidious failure because there is no error event;
   only the conversation quality degrades.

This spec defines **tool-list freshness** as the mechanism keeping
each participant's cached tool registry in sync with their
registered MCP server. The mechanism:

1. **Detects** tool-set changes via polling at a configurable
   cadence (Phase 1 MVP) and via MCP `notifications/tools/list_changed`
   push notifications (Phase 2 extension).
2. **Refreshes** the per-participant cached registry, computing a
   stable hash of the tool set so every change is observable.
3. **Coordinates** with §4.2 context assembly so that a tool-set
   change triggers a system-prompt rebuild at the right turn
   boundary, NOT mid-context-assembly.
4. **Audits** every tool-set change into `admin_audit_log` with the
   diff (tools added / removed / modified) so the operator and the
   participant's human can see capability changes after the fact.
5. **Respects** provider-native prompt caching: tool-set changes
   invalidate the system-prompt cache prefix and the spec MUST
   surface this cost rather than mask it.

The tool registry is **strictly per-participant**. A participant's
tool list is part of their sovereignty surface — other participants
MUST NOT see another participant's tool catalogue, change events,
or refresh state. This is consistent with §7.2 participant privacy
(system prompts and tool capabilities are participant-private state).

This spec also activates the **deferred Phase 1+2 "tool description
hashing" hardening item** noted in Constitution §6/§7 ("Tool description
hashing — Phase 1+2 status: deferred (tool descriptions are static
at registration time; rug-pull threat surface is small until external
MCP integration lands). Trigger: any external MCP server integration"
). Participant-registered MCP servers ARE the external MCP integration
that triggers that deferred work — and this spec delivers it.

## Clarifications

### Initial draft assumptions requiring confirmation

- **Polling-only Phase 1.** User input says "Phase 1 minimum
  (polling-only) is acceptable if the push-notification path is
  non-trivial." Drafted with three user stories: P1 polling, P2
  context-assembly coordination, P3 push + manual-refresh as
  Phase-2 hooks. The push path is feasible (MCP spec defines
  `notifications/tools/list_changed` and SACP's MCP client can
  subscribe), but participant-side support varies — some MCP
  servers don't emit the notification, so polling is the
  always-correct floor. [NEEDS CLARIFICATION: confirm Phase 1
  ships polling-only with push capability stubs gated behind a
  feature flag, OR ships a polling-only implementation with
  push left as a fully separate Phase-2 spec.]
- **Refresh on what trigger relative to §4.2.** §4.2 step 6
  ("Build context payload") includes the system prompt as part of
  the per-turn payload. Drafted as: tool-set hash is checked at
  step 6's start; if changed, the system prompt is rebuilt and
  the change audited before the payload is sent (step 8). This
  means a refresh can extend a single turn's prep latency, but
  never crosses turn boundaries with a stale list. [NEEDS
  CLARIFICATION: confirm the at-turn-boundary check point is
  acceptable vs. a between-turn background refresh.]
- **Prompt cache cost surfacing.** Provider-native prompt caching
  (Anthropic, OpenAI, Google) caches the system prompt prefix
  with a 5-minute TTL — a tool-set change invalidates the prefix
  and the next call pays the full cache-miss cost. Drafted as:
  the audit entry for a tool-set change records the
  cache-invalidation event so an operator reviewing token-spend
  spikes can correlate them to capability changes. [NEEDS
  CLARIFICATION: confirm we surface this cost in the metrics
  surface (spec 016) as well as the audit log, or audit-log only
  in v1.]
- **Tool-set change semantics.** Tool description text changes
  versus tool schema (parameter shape) changes versus tool
  add/remove are all changes, but they have different blast
  radii. Drafted as a single change event with a `change_kind`
  enum (`added`, `removed`, `description_changed`, `schema_changed`).
  [NEEDS CLARIFICATION: confirm we collapse these into a single
  audit-event family vs. emit four distinct event types.]

### Session 2026-05-13

1. **Polling-only v1 confirmed.** Phase 1 ships polling-only with push-subscription stubs gated by `SACP_TOOL_REFRESH_PUSH_ENABLED=false`. The stub attempts `notifications/tools/list_changed` subscription at participant registration when the flag is true and audits the outcome; the delivery path (push-driven refresh) is a Phase-2 spec. This means the flag is wired and testable in v1 but the push-delivery loop ships later. Polling is the always-correct floor.

2. **At-turn-boundary check confirmed.** The hash check runs at `_assemble_and_dispatch` entry (before `assembler.assemble(...)` is called in loop.py), which is the §4.2 step-6 equivalent. The hash is sealed at that point; any refresh completing mid-assembly uses the sealed hash (no torn reads). If a change is detected, the registry is updated in-place and the assembler picks up the fresh tool list on this same turn (the system prompt is rebuilt on this turn, not deferred). This is acceptable because the assembler always reads from the live registry at assembly time.

3. **Audit-log only in v1 confirmed.** `prompt_cache_invalidated` is recorded in the `admin_audit_log` entry (FR-012). Spec 016 metrics surface is a SHOULD cross-reference, not a hard dependency — v1 ships the audit row only. The `prompt_cache_invalidated` boolean is set True when the registry's `last_refreshed_at` indicates the tool list was already sent to the provider at least once (i.e., it is not the first turn for this participant).

4. **Single `change_kind` enum confirmed.** The five values are `added`, `removed`, `description_changed`, `schema_changed`, `refresh_failed`. All five reuse the single `tool_list_changed` action type in `admin_audit_log` (one action family, multiple `change_kind` discriminators in the JSONB payload). This is consistent with the existing pattern (e.g., spec 014 reuses `admin_audit_log` with multiple action types but a single table).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Polling detects a tool removed mid-session before the AI calls it (Priority: P1)

A participant's MCP server is updated mid-session — a tool that was
present at session start is deprecated and removed in a server
restart. Today, the orchestrator's cached tool list still advertises
the removed tool to the AI; the AI tries to call it; the call fails
at the server with "tool not found"; the participant pays for a
turn that cannot produce the intended outcome.

With polling-based freshness, the orchestrator re-fetches the tool
list at a configurable cadence; when the next refresh detects the
tool is gone, the cache is updated and the next system-prompt
rebuild reflects reality. The AI's next turn no longer sees the
removed tool.

**Why this priority**: This is the core failure mode. Polling
delivers correctness (the cache is eventually consistent) at
acceptable cost (one MCP `tools/list` call per refresh interval per
participant). Push notifications and manual refresh (US3) layer on
top to reduce the staleness window further, but polling is the
always-available floor.

**Independent Test**: Register a participant whose MCP server
exposes 3 tools. Drive the session through 5 turns. Restart the
server with 2 tools (one removed). Wait one refresh interval.
Verify the cached list reflects the removal, the
`tool_list_changed` audit entry is present with the removed tool's
metadata, and the participant's next turn's system-prompt no longer
mentions the removed tool.

**Acceptance Scenarios**:

1. **Given** participant A's MCP server lists tools `{T1, T2, T3}`
   at session start and `SACP_TOOL_REFRESH_POLL_INTERVAL_S=30`,
   **When** the server begins listing only `{T1, T2}` and 30+
   seconds elapse, **Then** participant A's cached registry MUST
   be updated to `{T1, T2}` on the next refresh and an
   `admin_audit_log` entry of action type `tool_list_changed`
   MUST be emitted with payload fields
   `(session_id, participant_id, change_kind, tool_name,
   old_hash, new_hash, observed_at)`.
2. **Given** participant A's cached registry is updated, **When**
   the next turn-prep step occurs (per §4.2 step 6), **Then** the
   system prompt MUST be rebuilt against the fresh list and MUST
   NOT include the removed tool.
3. **Given** another participant B is in the same session, **When**
   the refresh for A detects the change, **Then** participant B's
   cached registry, audit-log visibility, and turn-prep state
   MUST be unaffected (per-participant isolation per Constitution
   §3 sovereignty).
4. **Given** the freshness env var is unset, **When** any session
   runs, **Then** the orchestrator MUST behave byte-identically
   to the pre-feature baseline (tool lists captured once at
   registration, no polling, no audit events for freshness)
   and dispatch behavior MUST remain unchanged.

---

### User Story 2 - Tool-set change rebuilds the system prompt and surfaces the prompt-cache cost (Priority: P2)

Provider-native prompt caching (Anthropic, OpenAI, Google) caches
the system prompt prefix on a 5-minute TTL on the provider side.
Tool definitions are part of the system prompt, so a tool-set
change invalidates the cache: the next call pays the cache-miss
cost (the full prompt is re-billed instead of the cache-hit fraction).

A participant whose MCP server changes tool descriptions every few
minutes will see their per-turn cost rise meaningfully — and
without visibility, an operator cannot tell whether the cost spike
is from prompt growth, a model change, or tool churn.

**Why this priority**: P2 because correctness (US1) is the floor;
P2 makes the cost of correctness observable. Without this,
operators see only the symptom (token spend up) and the audit log
but no causal link.

**Independent Test**: Run a session with a participant whose MCP
server cycles tool descriptions every 60 seconds. Drive 10 turns.
Verify the audit-log entries capture each cache-invalidation
event AND that the next-turn token cost reflects the cache-miss
penalty consistent with the participating provider's documented
prompt-caching behavior.

**Acceptance Scenarios**:

1. **Given** a tool-set change for participant A, **When** the
   `tool_list_changed` audit entry is written, **Then** the entry
   MUST include a `prompt_cache_invalidated` boolean field
   indicating whether this change invalidated the participant's
   prompt-cache prefix on their configured provider.
2. **Given** a tool-set change has invalidated the prompt cache,
   **When** participant A's next turn dispatches, **Then** the
   provider-side cache miss MUST be observable in the cost
   tracker (full prompt re-billed) and MUST appear in the spec
   016 metrics surface if `SACP_METRICS_ENABLED=true`.
3. **Given** the §4.2 step-6 context assembly is in progress for
   participant A, **When** a refresh completes mid-assembly,
   **Then** the assembly MUST complete with whichever tool-set
   was sealed at step-6 start (no torn reads). The fresh list
   takes effect on the NEXT turn-prep, with the audit entry
   noting the deferred application.
4. **Given** §4.2's latency-optimization patterns (line 446) require
   orchestrator overhead under 50ms per turn, **When** a refresh
   is performed at a turn boundary, **Then** the refresh-induced
   overhead on that turn MUST stay within the V14 turn-prep
   budget tolerance — refreshes that exceed the budget MUST run
   asynchronously between turns rather than blocking turn-prep.

---

### User Story 3 - Push notifications and manual refresh land as Phase-2 extensions (Priority: P3)

The polling-only Phase 1 floor leaves a staleness window equal to
the poll interval. Two improvements close that gap:

- **Push notifications (MCP `notifications/tools/list_changed`).**
  The MCP server pushes a notification when its tool list changes;
  the orchestrator refreshes immediately. Reduces staleness from
  `poll_interval` to `network_RTT`.
- **Manual refresh.** The participant's human (via their MCP
  client) or the facilitator (via an admin tool) can trigger an
  immediate refresh for that participant. Useful when the human
  knows they just deployed a change and doesn't want to wait for
  the next poll.

**Why this priority**: P3 because both are improvements layered on
US1's correctness floor — neither changes whether the cache
eventually catches up; they change how fast. The Phase 2 spec will
own the full push + manual-refresh design; this spec defines the
interfaces and event shapes so Phase 2 plugs in cleanly.

**Independent Test**: Phase 1 — verify the orchestrator's MCP
client subscribes to `notifications/tools/list_changed` (or
gracefully no-ops if the server doesn't advertise it) and that the
subscription state is captured in the audit log at session start.
Phase 2 (separate spec) — verify push-driven refreshes complete
within network RTT and that manual-refresh tools are exposed.

**Acceptance Scenarios**:

1. **Given** a participant's MCP server advertises support for
   `notifications/tools/list_changed`, **When** the participant
   registers, **Then** the orchestrator MUST attempt to subscribe
   to the notification stream and MUST audit the subscription
   outcome (subscribed / not_supported / failed).
2. **Given** a participant's MCP server does NOT advertise push
   support, **When** the participant registers, **Then** the
   orchestrator MUST fall back to polling-only for that
   participant and MUST NOT block registration on push
   subscription failure.
3. **Given** Phase 2 lands, **When** a push notification arrives,
   **Then** the orchestrator MUST refresh the participant's cache
   on receipt and MUST emit the same `tool_list_changed` audit
   entry as the polling path (single audit-event shape, multiple
   trigger sources).
4. **Given** a participant's human triggers a manual refresh
   (Phase 2), **When** the refresh completes, **Then** the audit
   entry MUST include `trigger_source="manual"` so the audit log
   distinguishes operator-initiated refreshes from automatic
   ones.

---

### Edge Cases

- **MCP server is unreachable at refresh time.** The refresh MUST
  fail gracefully — the cached list is preserved, an audit entry
  with `change_kind=refresh_failed` is emitted, and the next
  refresh interval is attempted. Repeated failures interact with
  spec 015 provider-failure-detection: an unreachable MCP server
  is functionally equivalent to a failed dispatch attempt and
  MAY trip a separate breaker. [NEEDS CLARIFICATION: confirm we
  reuse spec 015's breaker abstraction or define a parallel
  MCP-server breaker.]
- **Tool list larger than the configured size cap.** §7.5
  hardening caps tool-call content at 2000 tokens; an analogous
  cap should apply to tool-list size to prevent a misbehaving
  MCP server from blowing out the context. Drafted: total tool
  list size capped at `SACP_TOOL_LIST_MAX_BYTES` with overflow
  truncating to the first N tools and emitting an audit entry.
- **Tool description contains content that would invalidate
  privacy invariants.** Tool descriptions are participant-controlled
  text and could in principle leak content from another session.
  Drafted: tool description text is treated as participant-private
  (§7.2) and never appears in cross-participant logs or metrics.
- **Refresh races a turn-prep on the same participant.** Two
  refreshes initiated concurrently MUST not produce two audit
  entries for the same change — the second observer MUST detect
  the refresh-in-progress lock and either wait or no-op.
- **Tool added with the same name as a previously-removed tool
  but different schema.** Treated as a `(schema_changed)` event,
  not a re-add — the orchestrator compares hashes, and a
  previously-evicted name reappearing with a fresh schema is a
  schema change.
- **Server returns the same tool set with reordered entries.**
  Hash MUST be order-independent; no audit entry emitted.
- **Server returns a tool list during the refresh that includes
  duplicate tool names.** Treated as malformed; the orchestrator
  logs the malformed response and preserves the previous cache
  rather than ingesting ambiguous state.
- **Long-running session crosses the prompt-cache TTL window
  multiple times without tool changes.** Cache misses caused by
  TTL expiry are NOT this spec's concern (provider behavior, not
  SACP behavior); only changes-driven invalidations are audited.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The orchestrator MUST maintain a per-participant
  cached tool registry, keyed on `(session_id, participant_id)`.
- **FR-002**: The orchestrator MUST poll each participant's MCP
  server at the configured interval (`SACP_TOOL_REFRESH_POLL_INTERVAL_S`)
  and refresh the cached registry on every poll.
- **FR-003**: The orchestrator MUST compute a stable, order-independent
  hash of the tool set on every refresh and MUST detect change by
  hash comparison.
- **FR-004**: When a change is detected, the orchestrator MUST emit
  an `admin_audit_log` entry of action type `tool_list_changed`
  with payload fields
  `(session_id, participant_id, change_kind, tool_name,
  old_hash, new_hash, observed_at, trigger_source,
  prompt_cache_invalidated)`. `trigger_source ∈ {poll, push,
  manual}`. `change_kind ∈ {added, removed, description_changed,
  schema_changed, refresh_failed}` per the Clarifications
  resolution.
- **FR-005**: A tool-set change MUST trigger a system-prompt
  rebuild on the affected participant's NEXT turn-prep boundary
  (per §4.2 step 6). The rebuild MUST NOT happen mid-payload
  assembly for a turn already in progress.
- **FR-006**: Tool registries are per-participant private. No
  participant's tool list, change events, or refresh state may
  appear in another participant's context, audit-log view, or
  metrics surface. The facilitator MAY view all participants'
  tool-set changes per the §7.2 facilitator-visible field model.
- **FR-007**: When a participant's MCP server advertises support
  for `notifications/tools/list_changed`, the orchestrator MUST
  attempt to subscribe at participant registration and MUST audit
  the subscription outcome.
- **FR-008**: When push notifications arrive (Phase 2), the
  orchestrator MUST refresh the cache immediately and MUST emit
  the same `tool_list_changed` audit entry as the polling path
  with `trigger_source="push"`.
- **FR-009**: A manual refresh tool (Phase 2 — interface stub in
  v1) MUST exist for the participant's human and the facilitator
  to trigger an immediate refresh, with `trigger_source="manual"`
  audit entry.
- **FR-010**: The orchestrator MUST cap the total tool-list size
  at `SACP_TOOL_LIST_MAX_BYTES`. Overflow MUST truncate the list
  and emit an `admin_audit_log` entry with the truncation event.
- **FR-011**: When a refresh fails (MCP server unreachable, malformed
  response, timeout), the cached list MUST be preserved, the
  failure MUST be audited with `change_kind=refresh_failed`, and
  the next refresh interval MUST proceed. Repeated failures MAY
  interact with spec 015's provider-failure-detection per the
  edge-case clarification.
- **FR-012**: When a tool-set change invalidates the participant's
  provider-native prompt-cache prefix, the audit entry MUST
  set `prompt_cache_invalidated=true` so token-spend spikes are
  causally traceable.
- **FR-013**: All four new `SACP_TOOL_*` env vars MUST have
  validator functions in `src/config/validators.py` registered in
  the `VALIDATORS` tuple, and corresponding sections in
  `docs/env-vars.md` with the six standard fields BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable gate).
- **FR-014**: When all four env vars are unset, the orchestrator's
  pre-feature behavior MUST be byte-identical: tool lists captured
  once at registration, no polling, no audit events for freshness,
  no system-prompt rebuilds for tool changes (matches current
  behavior). When any env var is set to an invalid value, the
  orchestrator MUST exit at startup with a clear error.

### Key Entities

- **ParticipantToolRegistry** (per-participant, session-local) —
  captures the current tool set:
  `(session_id, participant_id, tools[], tool_set_hash,
  last_refreshed_at, push_subscribed)`. Cached for session
  lifetime; not persisted across restart.
- **ToolListChangedRecord** (audit) — captures every change with
  the FR-004 field set.
- **ToolRefreshFailureRecord** (audit) — captures failed refresh
  attempts:
  `(session_id, participant_id, attempted_at, failure_kind,
  retry_in_s)`.
- **ToolSubscriptionRecord** (audit) — captures push-subscription
  outcome at registration:
  `(session_id, participant_id, supported, subscribed_at_or_null,
  failure_reason_or_null)`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Polling-driven staleness window for any participant's
  tool registry MUST stay at or below
  `SACP_TOOL_REFRESH_POLL_INTERVAL_S + 1 turn` in the worst case
  (the worst case being a change occurring just after one poll
  completed). Verified by a contract test injecting a change and
  measuring time-to-cache-update.
- **SC-002**: System-prompt rebuilds following a tool-set change
  reflect the new tool set on the affected participant's next
  turn — verified by a contract test that asserts the new
  system prompt's tool definitions match the post-change set
  byte-for-byte (modulo whitespace).
- **SC-003**: A tool-set change for participant A produces zero
  observable side effects on participant B's cached registry,
  audit-log visibility, system-prompt content, and metric
  surface — verified by a contract test that runs A and B in
  parallel and asserts B's state is unchanged across A's churn.
- **SC-004**: Refresh-induced overhead on a turn-boundary refresh
  stays within the V14 turn-prep budget tolerance versus a
  no-refresh baseline turn — verified by a load test capturing
  per-turn timing in the routing log.
- **SC-005**: With all four env vars unset, the full pre-feature
  acceptance suite passes unmodified (regression contract — no
  observable behavior change).
- **SC-006**: With any env var set to an invalid value, the
  orchestrator process exits at startup with a clear error
  message naming the offending var (V16 fail-closed gate
  observed in CI).
- **SC-007**: Every tool-set change of every kind (`added`,
  `removed`, `description_changed`, `schema_changed`,
  `refresh_failed`) is auditable — verified by a contract test
  that drives each change kind and asserts the audit entry.
- **SC-008**: Prompt-cache invalidation events caused by tool-set
  changes are causally traceable from the audit log to the
  next-turn token cost spike — verified by a test that
  correlates `prompt_cache_invalidated=true` entries with the
  cost tracker's per-turn delta.

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** (orchestrator-driven
topologies). The orchestrator is the cache holder and the only
component that builds the per-turn context payload (§4.2 step 6),
so it is also the only component that needs the freshness
mechanism.

This feature is **NOT directly applicable to topology 7
(MCP-to-MCP, Phase 3+)** because the orchestrator does not
mediate provider dispatch in topology 7 — each participant's
client builds its own context. Tool-list freshness in topology 7
becomes the participant's client's responsibility (Claude Desktop,
ChatGPT app, etc.). Per V12: any topology-7 deployment MUST
recognize that this spec's mechanism does not apply and that
freshness is delegated to the client. A separate spec MAY define
a topology-7 freshness contract.

### V13 — Use Case Coverage

This feature serves all four use cases from `docs/sacp-use-cases.md`
because every use case involves participants registering MCP
servers with tool capabilities:

- §1 Distributed Software Collaboration: developers iterate on
  their own tooling mid-session; a freshness mechanism prevents
  the orchestrator from advertising tools that have just been
  removed.
- §2 Research Co-authorship: research-tooling MCP servers (search,
  citation, dataset access) get added/removed as the research
  evolves; freshness keeps the AIs synchronized with current
  capability.
- §3 Consulting Engagement: consultants frequently update their
  domain-specific MCP server during an engagement; without
  freshness, every update requires a session restart.
- §4 Open Source Coordination: contributors with different MCP
  setups need their tool changes to be visible only to their own
  sessions, not leaked to other contributors.

No use case is the priority driver — this is foundational
correctness for participant-registered MCP integration.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts. This
spec contributes three budgets:

- **Cache hash check on every turn-prep**: Constant-time (`O(tools)`
  amortized — typically O(10) for realistic tool counts). The
  check is a hash comparison against the previously cached hash,
  not a re-fetch. Budget enforcement: routing log MUST NOT show
  a per-turn freshness-check stage exceeding O(tools) cost.
- **Polling refresh latency**: Refresh is OUT-OF-BAND from the turn
  loop and MUST NOT block any other participant's dispatch.
  Budget enforcement: refresh duration captured in the
  refresh-event audit record; refreshes exceeding
  `SACP_TOOL_REFRESH_TIMEOUT_S` count as failed and trigger the
  retry path.
- **System-prompt rebuild on change**: Rebuild MUST stay within the
  existing §4.2 latency-optimization budget (line 446: "under 50ms
  per turn cycle" for orchestrator overhead). Budget enforcement:
  rebuild duration captured in the routing log per spec 003
  §FR-030.

## Configuration (V16) — New Env Vars

Four new `SACP_TOOL_*` env vars are introduced. Each MUST have type,
valid range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this spec
(per V16 deliverable gate).

### `SACP_TOOL_REFRESH_POLL_INTERVAL_S`

- **Intended type**: positive integer, seconds
- **Intended valid range**: `15 <= value <= 3600` (15s minimum
  to bound MCP server load; 1 hour maximum to bound staleness
  in the worst case).
- **Fail-closed semantics**: unset means polling is disabled
  (current pre-feature behavior — tool list captured once at
  registration). Out-of-range values MUST cause startup exit
  per V16.

### `SACP_TOOL_REFRESH_TIMEOUT_S`

- **Intended type**: positive integer, seconds
- **Intended valid range**: `1 <= value <= 30`.
- **Fail-closed semantics**: unset means refresh inherits the
  configured MCP client request timeout. Out-of-range values
  MUST cause startup exit per V16.

### `SACP_TOOL_LIST_MAX_BYTES`

- **Intended type**: positive integer, bytes
- **Intended valid range**: `1024 <= value <= 1048576` (1 KiB
  to 1 MiB).
- **Fail-closed semantics**: unset means a default settled in
  `/speckit.plan` (likely 64 KiB to align with tool-call content
  caps in §7.5). Out-of-range values MUST cause startup exit per
  V16.

### `SACP_TOOL_REFRESH_PUSH_ENABLED`

- **Intended type**: boolean
- **Intended valid range**: `true` / `false` (case-insensitive)
- **Fail-closed semantics**: unset means `false` (Phase 1 polling-only
  default). When `true` (Phase 2), the orchestrator attempts to
  subscribe to `notifications/tools/list_changed` for every
  participant whose server advertises support. Unparseable values
  MUST cause startup exit.

## Cross-References to Existing Specs and Design Docs

- **`sacp-design.md` §4.2 (Conversation Loop Engine)** — step 6
  ("Build context payload") is the integration point for the
  system-prompt rebuild on tool-set change (FR-005); the
  latency-optimization patterns (§4.2 line 446) bind the V14
  rebuild budget.
- **`sacp-design.md` §6.3 (Tool Access Asymmetry)** — the
  participant-registered MCP servers and per-participant tool
  capability registry that this spec keeps fresh.
- **`sacp-design.md` §7.2 (Participant Privacy)** — tool
  capabilities and registries are participant-private state per
  the public/private/facilitator-visible field model. Bounds
  FR-006 (per-participant isolation).
- **`sacp-design.md` §7.5 (Hardening) — "Tool description hashing"
  deferred item** — this spec activates the deferred Phase 1+2
  hardening trigger ("any external MCP server integration").
- **Constitution §3 (Sovereignty)** — V1 sovereignty guarantees
  bind FR-006: a participant's tool registry is part of their
  sovereignty surface.
- **Spec 002 (mcp-server)** — participant registration flow; this
  spec adds the tool-list subscription step at registration time
  (FR-007).
- **Spec 003 (turn-loop-engine) §FR-030** — `routing_log`
  per-stage timing capture; refresh and rebuild events surface
  through this channel.
- **Spec 015 (provider-failure-detection)** — repeated MCP server
  unreachability MAY interact with the provider-failure breaker;
  scope of overlap settled in `/speckit.plan`.
- **Spec 016 (prometheus-metrics)** — `prompt_cache_invalidated`
  events from FR-012 SHOULD surface through spec 016's
  per-participant cost counters so cache-miss penalties are
  observable in dashboards. Cross-reference; not a hard
  dependency for v1.

## Assumptions

- The MCP `notifications/tools/list_changed` notification is the
  only push channel considered. Custom MCP extensions for tool-list
  push are out of scope.
- The poll cadence (`SACP_TOOL_REFRESH_POLL_INTERVAL_S`) is the
  same for every participant in v1. Per-participant cadence
  override is a follow-up.
- Provider-native prompt caching is assumed to be enabled by the
  participant's provider configuration. SACP does not opt the
  participant in or out; it merely observes whether a tool-set
  change invalidated the cache prefix.
- Tool description text is treated as opaque participant-private
  content. SACP does not parse, summarize, or transform tool
  descriptions; it stores and forwards them.
- The Phase-2 push + manual-refresh design is a separate spec that
  consumes this spec's audit-event shape and registry interface.
  This spec defines the interface; Phase 2 implements push
  delivery and the manual-refresh MCP tool.
- "Phase 1 minimum (polling-only) is acceptable" in the user
  description is interpreted as: ship polling + Phase-2 stub
  interfaces in this spec; Phase-2 push completion is a separate
  spec. Confirmation pending per Clarifications §"Polling-only
  Phase 1".
- Status remains Draft until the four flagged clarifications
  resolve and the user accepts the scaffolding.
