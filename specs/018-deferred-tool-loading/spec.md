# Feature Specification: Deferred Tool Loading for Large MCP Tool Sets

**Feature Branch**: `018-deferred-tool-loading`
**Created**: 2026-05-06
**Status**: Implemented 2026-05-13 (Phase 1 + Phase 2 — design hooks + working partition + discovery capability + audit emission. Live wiring of the partition to a participant tool-list source is the spec 017 integration point; the `set_tool_list_provider` hook is in place awaiting spec 017's `ParticipantToolRegistry` reaching main.)
**Input**: User description: "Deferred tool loading for participants with large MCP tool counts. When a participant registers multiple MCP servers each exposing several tools, the combined tool definitions can dominate the system prompt budget, crowding out conversation history and current-turn content. This is a different problem from the [NEED:] proxy mechanism (which addresses low-capability models that cannot do tool calling at all): deferred loading addresses high-capability models that can do tool calling but should not have to carry every tool definition in every turn. The mechanism should defer tool definitions above a measured threshold and provide a discovery capability the model invokes when it needs an unloaded tool. Per-participant scoping is required — each participant's deferred set is private. The loaded subset participates in the cached prefix for that participant, so tool-set changes interact with the freshness mechanism. Phase 2 scope for the working implementation. Phase 1 ships only the design hooks (system-prompt assembly knows about deferral, the index interface is defined, no-op default). Cross-references the MCP tool-list freshness feature."

## Overview

A participant's tool capabilities live in their MCP server(s) and
flow into the orchestrator's per-turn context payload via the
participant's system prompt (`sacp-design.md` §4.2 step 6, "Build
context payload"). For participants with one or two MCP servers
exposing a handful of tools each, the combined definitions fit
comfortably alongside the rest of the prompt tier (Constitution
§6.1, ~250–1,730-token system-prompt budget across the four
tiers).

For participants with **multiple MCP servers each exposing several
tools** — increasingly common as the MCP ecosystem matures —
combined tool definitions can dominate the system prompt budget.
Tool descriptions, parameter schemas, and example payloads add up:
20 tools × ~150 tokens of definition each ≈ 3,000 tokens, exceeding
the entire core-tier budget before any conversation history or
current-turn content is added. Research on context length sensitivity
(`sacp-design.md` §6.1: "LLM reasoning performance starts degrading
at roughly 3,000 system prompt tokens", "lost in the middle" effect
with 20–30% accuracy drops for mid-context information) makes this
not just a budget concern but a quality concern.

This is a **different problem from the `[NEED:]` proxy** mechanism in
§6.3. The `[NEED:]` proxy addresses LOW-capability models that
cannot do native function calling at all — it gives them a
text-based interface for requesting context. Deferred tool loading
addresses HIGH-capability models that CAN do native function calling
but should not have to carry every tool definition in every turn.
The two mechanisms are complementary, not redundant.

This spec defines **deferred tool loading** as a partitioning
mechanism layered above the participant tool registry. The
mechanism:

1. **Partitions** each participant's tool set into a *loaded subset*
   (full definitions in every turn's system prompt) and a
   *deferred subset* (a compact index entry per tool — name +
   one-line summary + invocation hint, no full schema).
2. **Selects** the loaded subset based on a measured threshold
   (system-prompt budget allocated to tools, recency, or
   relevance — final policy decided in `/speckit.plan`).
3. **Discovers** deferred tools when the model needs them, via a
   discovery capability the model invokes (an MCP-native tool
   like `sacp_load_tool(name)` or equivalent) that returns the
   full definition and adds the tool to the loaded subset for
   that turn — and possibly subsequent turns.
4. **Audits** every deferred-set transition (tool deferred, tool
   loaded on demand, tool re-deferred) into `admin_audit_log` so
   operators can see capability changes after the fact and tune
   the threshold.
5. **Coordinates** with spec 017 freshness: the loaded subset
   participates in the participant's prompt-cache prefix, so any
   tool-set change must invalidate the cache and re-partition.

The deferred set is **strictly per-participant**. A participant's
deferred set is part of their sovereignty surface — other
participants MUST NOT see another participant's loaded vs.
deferred partition. This is consistent with §7.2 participant
privacy (tool capabilities are participant-private state) and
spec 017's per-participant registry rule.

This spec is layered over **two phases**:

- **Phase 1 deliverable** (this spec ships): design hooks only.
  The system-prompt assembly pipeline KNOWS about a deferred set
  but always sees an empty deferred set in v1. The index interface
  is defined as a stable contract. The discovery tool exists but
  is registered as a no-op stub. No behavioral change occurs;
  every existing test passes byte-identically.
- **Phase 2 deliverable** (separate spec or follow-up phase of
  this spec): the working partition mechanism, the live discovery
  capability, the threshold-driven selection policy, and the
  audit-log entries. The design hooks shipped in Phase 1 are the
  contract Phase 2 fills in.

## Clarifications

### Session 2026-05-13

All seven open questions resolved per operator direction:

- **Phase split structure**: Single spec, three user stories.
  US1 = Phase-1 design hooks (no-op default, ships in this spec's
  initial PR). US2 = Phase-2 partition (working implementation,
  ships in a follow-up PR cut of this same spec). US3 = Phase-2
  discovery capability (working impl, same follow-up PR or
  immediately after US2). Phase 1 and Phase 2 here refer to the
  deliverable cuts of this spec, NOT the SACP project phases.
- **Threshold metric**: Token budget is the primary partition
  metric. `SACP_TOOL_LOADED_TOKEN_BUDGET` caps the loaded subset
  in tokens. Count-based or hybrid policies are deferred to a
  future spec; the v1 partition algorithm is deterministically
  driven by token consumption.
- **Selection policy**: Registration order for v1. Tools are
  partitioned in the order they appear in the participant's
  registry (which itself is ordered by tool-list freshness arrival
  per spec 017). First N tools that fit the budget land in the
  loaded subset; the rest are deferred. Recency- and
  relevance-based policies are deferred to a future spec.
- **Discovery tool naming**: The two discovery tools follow the
  spec 030 tool-registry naming convention (domain.action
  snake_case): `tools.list_deferred` (returns the deferred index)
  and `tools.load_deferred` (loads one specific deferred tool by
  name). Both are SACP-orchestrator-provided (NOT
  participant-MCP-server-provided), are participant-callable on
  their own deferred set only, and always sit in the loaded subset
  (never themselves deferred — per FR-011).
- **Sticky vs. per-turn loading**: Sticky-within-session. One
  successful `tools.load_deferred` call promotes the tool into
  the loaded subset for the remainder of the session. State is
  not persisted across session restart (session-local model
  matches spec 015 and spec 017 stance). On restart, the
  partition recomputes from scratch with the registration-order
  policy.
- **Single-tool-exceeds-budget pathology**: Graceful degradation.
  If a single tool's full definition exceeds
  `SACP_TOOL_LOADED_TOKEN_BUDGET` on its own, the loaded subset
  may be empty (or contain only the two discovery tools per
  FR-011); ALL participant tools are deferred. The
  `tool_partition_decided` audit entry MUST set a
  `pathological_partition=true` flag so operators see this state
  in the audit log. The model is forced through discovery for
  every tool call. No fail-closed (refusing to start the session
  on this pathology would be worse — the operator has chosen the
  budget and the participant has chosen the tools; deferral
  graceful-degrades).
- **Tokenizer**: At partition time, the orchestrator uses the
  participant-model-specific tokenizer if one is available
  through the existing `src/api_bridge/` adapter (e.g., per
  provider, tiktoken for OpenAI-family, model-specific for
  Anthropic, etc.). If no model-specific tokenizer is available,
  the orchestrator falls back to a coarse character-based estimate
  (`len(s) / 4` rounded up, matching the estimate used elsewhere
  for budget enforcement). The fallback case MUST be logged at
  partition time at WARN level so operators can investigate.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Phase 1 design hooks ship without behavior change (Priority: P1)

A participant registers two MCP servers exposing 20 tools combined.
With Phase 1 design hooks shipped (this spec), the orchestrator's
system-prompt assembly pipeline goes through the deferral-aware code
path: it consults the deferred-tool index, sees it's empty (the v1
default), and emits the same system prompt it would have emitted
before this spec landed. The discovery MCP tools are registered but
return a "deferred loading not enabled in this deployment" stub.
Phase 2 (later spec) plugs the live partition policy into the
already-shipped hooks without touching the assembly pipeline.

**Why this priority**: P1 because shipping the hooks WITHOUT the
working partition is the entire point of the Phase 1 cut. The
contract Phase 2 will fill must exist and be tested — otherwise
Phase 2 lands as a big-bang change that the Phase 1 cut explicitly
exists to prevent. The no-op default also lets us regression-test
"deferral disabled produces identical output to pre-feature
behavior."

**Independent Test**: Run the full pre-feature acceptance suite
with this spec's code merged. Verify every existing test passes
byte-identically. Separately, verify the deferred-tool index
interface exists, returns an empty set on every call, and is
covered by a unit test asserting "always empty in v1". Verify the
discovery MCP tools are registered but return the documented stub
response.

**Acceptance Scenarios**:

1. **Given** a participant with 20 registered tools and
   `SACP_TOOL_DEFER_ENABLED=false` (default in v1), **When** the
   orchestrator builds the participant's per-turn system prompt,
   **Then** the prompt MUST contain all 20 tool definitions
   (full schemas) byte-identically to the pre-feature baseline.
2. **Given** the deferral-aware system-prompt assembly path,
   **When** the assembly path consults the deferred-tool index,
   **Then** the index MUST be defined as a stable interface
   (return type, methods documented) and MUST return an empty
   set in v1 regardless of input.
3. **Given** a model invokes the discovery MCP tool
   (`sacp_list_deferred_tools` or `sacp_load_tool`), **When**
   `SACP_TOOL_DEFER_ENABLED=false`, **Then** the tool MUST return
   a documented stub response (`{"status": "deferred_loading_disabled"}`
   or equivalent) and MUST NOT alter any participant state.
4. **Given** the full pre-feature acceptance suite, **When** this
   spec's code is merged, **Then** every test in the suite MUST
   pass unmodified — no test changes, no fixture changes, no
   golden-output changes (regression contract).

---

### User Story 2 - Phase 2 partitioning keeps the system prompt within the budget (Priority: P2)

The same participant with 20 registered tools enters a session
where `SACP_TOOL_DEFER_ENABLED=true` and
`SACP_TOOL_LOADED_TOKEN_BUDGET=1500`. The orchestrator partitions
the tool set: full definitions for the first M tools that fit
within 1500 tokens of system prompt budget; compact index entries
(name + one-line summary) for the remaining 20 - M tools. The
system prompt now stays within budget; conversation history and
current-turn content have room to breathe.

**Why this priority**: P2 because this is the Phase-2 working
implementation that delivers the actual benefit. P1 hooks without
P2 give zero behavioral improvement; P2 without P1 hooks lands as
a risky big-bang. With both shipped, behavior changes only when
the operator opts in.

**Independent Test**: Configure a session with
`SACP_TOOL_DEFER_ENABLED=true` and `SACP_TOOL_LOADED_TOKEN_BUDGET=1500`.
Register a participant with 20 tools whose combined full definitions
exceed 1500 tokens. Drive 5 turns. Measure the system-prompt
token count on each turn and verify it stays at or below the
budget. Verify deferred tools appear as index entries (compact
form) in the system prompt, not full schemas.

**Acceptance Scenarios**:

1. **Given** a participant with 20 tools whose combined full
   definitions exceed `SACP_TOOL_LOADED_TOKEN_BUDGET` and
   `SACP_TOOL_DEFER_ENABLED=true`, **When** the orchestrator
   builds the per-turn system prompt, **Then** the system prompt
   MUST contain full definitions for the loaded subset and
   compact index entries for the deferred subset, and the total
   tool-section token count MUST stay at or below the budget.
2. **Given** the same configuration, **When** the partition is
   computed, **Then** an `admin_audit_log` entry of action type
   `tool_partition_decided` MUST be emitted at session start
   with payload fields
   `(session_id, participant_id, loaded_count, deferred_count,
   loaded_token_count, decided_at, selection_policy)`.
3. **Given** another participant B in the same session, **When**
   participant A's partition is computed, **Then** participant
   B's partition MUST be computed independently (per-participant
   scoping) and B's system prompt MUST NOT reflect A's
   loaded/deferred decision.
4. **Given** participant A's tool set changes mid-session via
   spec 017's freshness mechanism, **When** the freshness
   refresh applies, **Then** the partition MUST be recomputed,
   the prompt-cache prefix MUST invalidate (per spec 017
   `prompt_cache_invalidated`), and a new
   `tool_partition_decided` entry MUST be audited.

---

### User Story 3 - Phase 2 discovery capability lets the model load deferred tools on demand (Priority: P3)

A model needs a deferred tool. Without discovery, the model is
stuck — the tool's full schema is not in the system prompt, so the
model cannot produce a syntactically valid call. With discovery,
the model invokes `sacp_load_tool(name)` (or equivalent), the
orchestrator returns the full definition and promotes the tool
into the loaded subset for the rest of the session, and the
participant's next turn carries the full definition in the
system prompt — re-enabling the model's native function calling
on that tool.

**Why this priority**: P3 because the partition itself (US2) is
useful even without discovery — if the operator picks the
threshold well, the loaded subset is "the tools the model uses";
discovery is the safety valve when the partition picks wrong.
But discovery is a Phase-2 deliverable on the same critical
path as US2.

**Independent Test**: Configure US2's setup. Drive a turn where
the model needs a deferred tool. Verify the model can invoke
`sacp_load_tool(deferred_tool_name)`, that the response contains
the full definition, that the tool appears in the loaded subset
on the next turn, and that the prompt-cache prefix invalidates
exactly once for the load (not twice — load is a single
invalidation event).

**Acceptance Scenarios**:

1. **Given** a deferred tool `T` is in participant A's index,
   **When** A's model invokes `sacp_load_tool("T")`, **Then** the
   orchestrator MUST return T's full definition in the response
   AND MUST promote T into A's loaded subset for the remainder
   of the session.
2. **Given** T is now in the loaded subset, **When** the next
   turn-prep occurs, **Then** A's system prompt MUST include T's
   full schema, the prompt-cache prefix MUST invalidate exactly
   once for this load (per spec 017 audit semantics), and a
   `tool_loaded_on_demand` audit entry MUST be emitted with
   payload `(session_id, participant_id, tool_name, requested_at,
   prompt_cache_invalidated)`.
3. **Given** the loaded subset would exceed
   `SACP_TOOL_LOADED_TOKEN_BUDGET` after promoting T, **When** T
   is loaded, **Then** the orchestrator MUST evict the
   least-recently-used tool from the loaded subset to fit T,
   MUST audit the eviction with `tool_re_deferred`, and MUST NOT
   reject the load (the model already needs T; the budget is a
   soft target the discovery path takes priority over).
4. **Given** participant B invokes `sacp_load_tool("T_in_A_set")`
   for a tool only in A's registry, **When** the call is
   processed, **Then** the orchestrator MUST reject the call
   with `{"error": "tool_not_in_caller_registry"}` and MUST NOT
   alter A's state (per-participant scoping enforcement).

---

### Edge Cases

- **All tools fit under the budget.** `deferred_count = 0` is a
  valid partition outcome — the participant's behavior is
  identical to v1. No audit entries other than the initial
  `tool_partition_decided` (with `deferred_count=0`).
- **Single tool exceeds the entire budget.** Pathological case;
  the loaded subset contains only the two discovery tools (or is
  empty if discovery is not yet registered) and EVERY participant
  tool is deferred. The audit entry MUST flag this state for
  operator visibility (`pathological_partition=true` per Session
  2026-05-13). The model is forced to use discovery for any tool
  call. Graceful-degradation per Session 2026-05-13 clarification;
  no fail-closed.
- **Tool removed from the registry while in the loaded subset.**
  Spec 017's freshness mechanism removes the tool from the
  registry; the partition recomputes and the loaded/deferred
  partition reflects the post-removal set.
- **Tool removed from the registry while loaded on demand.**
  Same as above — the on-demand promotion is meaningless once
  the tool is gone; the next partition computation drops the
  tool from both subsets.
- **Discovery tool itself is registered as a tool.** The two
  discovery MCP tools (`sacp_list_deferred_tools`,
  `sacp_load_tool`) are SACP-orchestrator-provided, NOT
  participant-MCP-server-provided. They MUST appear in every
  participant's loaded subset always (not subject to deferral)
  because they are how the model exits the deferred state.
- **Index entry size.** Each deferred-tool index entry consumes
  some tokens. The orchestrator MUST cap the index size so a
  pathological 200-tool deferred set doesn't itself blow out
  the budget. `SACP_TOOL_DEFER_INDEX_MAX_TOKENS` bounds the
  index; if exceeded, the index is truncated and a banner entry
  is added pointing the model at `sacp_list_deferred_tools` to
  paginate.
- **Concurrent partition recomputation.** A spec-017 refresh and
  a discovery-driven load arriving in close succession MUST not
  produce a torn partition state. Recomputation MUST be
  serialized per participant.
- **Provider does not support tool calling natively.** This
  participant should be using the `[NEED:]` proxy per §6.3, not
  deferred loading. The orchestrator MUST detect the
  no-tool-calling case at registration and disable deferred
  loading for that participant (it would be meaningless — the
  proxy already handles the case).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The orchestrator MUST partition each participant's
  tool set into a loaded subset (full definitions) and a
  deferred subset (compact index entries) when
  `SACP_TOOL_DEFER_ENABLED=true`.
- **FR-002**: The loaded subset MUST be selected to fit within
  `SACP_TOOL_LOADED_TOKEN_BUDGET` total tokens of system-prompt
  budget. Selection policy in v1 is registration order
  (deterministic, no embedding cost on hot path); recency- and
  relevance-based policies are deferred to a future spec.
- **FR-003**: Each deferred-subset entry in the system prompt
  MUST be a compact index line containing tool name, one-line
  summary, and an invocation hint pointing the model at
  `sacp_load_tool(name)` to retrieve the full definition.
- **FR-004**: The total index size MUST stay within
  `SACP_TOOL_DEFER_INDEX_MAX_TOKENS`. If the deferred set is
  larger than this allows, the index MUST be truncated with a
  pagination banner pointing the model at
  `sacp_list_deferred_tools` for the full list.
- **FR-005**: The orchestrator MUST register two MCP tools on the
  participant-callable tool set:
  - `sacp_list_deferred_tools()` — returns the participant's
    full deferred-tool index (paginated if needed).
  - `sacp_load_tool(name)` — loads one specific deferred tool
    and promotes it into the loaded subset for the rest of the
    session.
- **FR-006**: Deferred sets are per-participant private. No
  participant's loaded/deferred partition, on-demand loads, or
  index contents may appear in another participant's context,
  audit-log view, system prompt, or metric surface. The
  facilitator MAY view all participants' partitions per the
  §7.2 facilitator-visible field model.
- **FR-007**: The orchestrator MUST emit an `admin_audit_log`
  entry of action type `tool_partition_decided` at session start
  AND on every partition recomputation (e.g., spec-017-driven
  refresh).
- **FR-008**: The orchestrator MUST emit an `admin_audit_log`
  entry of action type `tool_loaded_on_demand` for every
  successful discovery-driven load AND `tool_re_deferred` for
  every LRU eviction triggered by an on-demand load.
- **FR-009**: A discovery-driven load MUST invalidate the
  participant's prompt-cache prefix exactly once, and the audit
  entry MUST set `prompt_cache_invalidated=true` so the cost is
  causally traceable (consistent with spec 017 FR-012).
- **FR-010**: A spec-017 freshness refresh MUST trigger a
  partition recomputation for the affected participant. The
  recomputation MUST emit a `tool_partition_decided` audit
  entry; the underlying spec-017 `tool_list_changed` entry is
  emitted separately. Both entries together describe the
  cause-and-effect (registry changed → partition recomputed).
- **FR-011**: The two discovery MCP tools
  (`sacp_list_deferred_tools`, `sacp_load_tool`) MUST always
  appear in every participant's loaded subset (never deferred),
  because they are the mechanism by which the model exits the
  deferred state.
- **FR-012**: When a participant is registered with a model that
  does not support native function calling, deferred loading
  MUST be disabled for that participant — they use the §6.3
  `[NEED:]` proxy instead. The disabling MUST be audited at
  registration time.
- **FR-013**: All four new `SACP_TOOL_DEFER_*` env vars MUST have
  validator functions in `src/config/validators.py` registered in
  the `VALIDATORS` tuple, and corresponding sections in
  `docs/env-vars.md` with the six standard fields BEFORE
  `/speckit.tasks` is run for the working-implementation cut
  (V16 deliverable gate).
- **FR-014**: The Phase-1 design-hooks cut MUST satisfy three
  contracts:
  - The deferral-aware system-prompt assembly path is exercised
    on every turn and consults the deferred-tool index.
  - The deferred-tool index interface is defined and returns an
    empty set in v1 regardless of input.
  - The two discovery MCP tools are registered and return the
    documented stub response.
- **FR-015**: When `SACP_TOOL_DEFER_ENABLED=false` (the v1 default
  and the Phase-1 cut state), every aspect of behavior MUST be
  byte-identical to the pre-feature baseline — system prompts,
  audit-log content, metric values, routing-log timing. The
  Phase-1 hooks MUST be additive and observable only via the
  deferred-tool index returning an empty set.

### Key Entities

- **DeferredToolIndex** (per-participant, session-local) —
  holds the partition state:
  `(session_id, participant_id, loaded_tools[], deferred_tools[],
  loaded_token_count, partition_decided_at, selection_policy)`.
  Cached for session lifetime; not persisted across restart.
- **DeferredToolIndexEntry** — compact per-deferred-tool record:
  `(tool_name, one_line_summary, source_server)`. Contains no
  schema and no examples.
- **ToolPartitionDecidedRecord** (audit) — captures the partition
  outcome at session start and on every recomputation.
- **ToolLoadedOnDemandRecord** (audit) — captures every
  discovery-driven load with `prompt_cache_invalidated` flag.
- **ToolReDeferredRecord** (audit) — captures every LRU eviction
  triggered by an on-demand load that exceeded the budget.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With `SACP_TOOL_DEFER_ENABLED=false` (v1 default and
  Phase-1 cut state), the full pre-feature acceptance suite
  passes byte-identically — verified in CI on the Phase-1 cut
  PR.
- **SC-002**: With `SACP_TOOL_DEFER_ENABLED=true` and a 20-tool
  participant exceeding the budget, system-prompt total tokens
  for that participant stay at or below
  `SACP_TOOL_LOADED_TOKEN_BUDGET + SACP_TOOL_DEFER_INDEX_MAX_TOKENS`
  on every turn — verified by a contract test capturing
  per-turn token counts.
- **SC-003**: A discovery-driven load completes within the
  participant's existing per-turn timeout (`turn_timeout_seconds`)
  and adds the loaded tool to the next turn's system prompt —
  verified by an integration test driving the load path.
- **SC-004**: Per-participant scoping is enforced — a contract
  test with two participants A and B verifies that loads/evictions
  on A's deferred set produce zero state changes on B (loaded
  subset, system prompt, audit-log row count, metric series).
- **SC-005**: Spec-017 freshness coordination is correct — when
  participant A's tool registry changes via freshness, the
  partition recomputes within one turn-prep cycle and the
  prompt-cache prefix invalidates exactly once for the
  combined event (registry change + repartition), not twice.
- **SC-006**: With any `SACP_TOOL_DEFER_*` env var set to an
  invalid value, the orchestrator process exits at startup with
  a clear error message naming the offending var (V16
  fail-closed gate observed in CI).
- **SC-007**: A participant whose model does not support native
  function calling has deferred loading disabled at
  registration; the participant uses `[NEED:]` proxy as before.
  Verified by a registration test with a no-tool-calling model
  that asserts the deferral path is bypassed.
- **SC-008**: An operator can observe which tools are loaded vs.
  deferred per session per participant via the audit log alone,
  without inspecting the system-prompt body — verified by
  asserting `tool_partition_decided` entries contain the loaded
  and deferred tool name lists.

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** (orchestrator-driven
topologies). The orchestrator owns the per-participant system-prompt
assembly and the discovery MCP tools; both the partition policy and
the load-on-demand mechanism live there.

This feature is **NOT applicable to topology 7 (MCP-to-MCP, Phase
3+)**. In topology 7, each participant's client builds its own
context and the orchestrator is not in the system-prompt-assembly
path. Tool deferral in topology 7 becomes the participant's
client's responsibility (Claude Desktop, ChatGPT app, etc.). Per
V12: any topology-7 deployment MUST recognize that this spec's
mechanism does not apply.

### V13 — Use Case Coverage

This feature serves all four use cases that involve participants
with multiple MCP servers:

- §1 Distributed Software Collaboration: developers register
  per-toolchain MCP servers (build, test, deploy, lint, search)
  whose combined tool set frequently exceeds budget.
- §2 Research Co-authorship: researchers register
  domain-specific MCP servers (citation, dataset, statistical
  package) with rich per-domain tool sets.
- §3 Consulting Engagement: consultants register
  client-specific MCP servers per engagement; aggregate tool
  count grows over time.
- §4 Open Source Coordination: contributors with diverse MCP
  setups need the budget protection without leaking their
  personal toolchain to other contributors.

No use case is the priority driver — this is foundational
context-budget protection.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts. This
spec contributes three budgets:

- **Partition computation at session start**: One-time per
  participant per session. MUST stay within the existing session-
  start budget. With registration-order policy in v1, computation
  is `O(tools)` and well under any latency-relevant threshold.
- **Partition recomputation on tool-set change**: Triggered by
  spec 017 freshness. MUST stay within the existing turn-prep
  budget tolerance. Recomputation is `O(tools)`; the budget is
  the §4.2 line 446 "under 50ms per turn cycle" target.
- **Discovery load latency**: Out-of-band from the turn loop;
  MUST NOT block any other participant's dispatch. Discovery
  request handling MUST complete within `SACP_TOOL_DEFER_LOAD_TIMEOUT_S`
  or fail with a documented error.

## Configuration (V16) — New Env Vars

Four new `SACP_TOOL_DEFER_*` env vars are introduced. Each MUST
have type, valid range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for the
working-implementation cut (per V16 deliverable gate).

### `SACP_TOOL_DEFER_ENABLED`

- **Intended type**: boolean
- **Intended valid range**: `true` / `false` (case-insensitive)
- **Fail-closed semantics**: unset means `false` — the v1 default
  and the Phase-1 cut state. With `false`, deferral is inactive
  and pre-feature behavior holds. Unparseable values MUST cause
  startup exit per V16.

### `SACP_TOOL_LOADED_TOKEN_BUDGET`

- **Intended type**: positive integer, tokens
- **Intended valid range**: `512 <= value <= 8192` (512 tokens
  minimum to ensure at least one realistic tool fits; 8192
  maximum to bound system-prompt budget commitment).
- **Fail-closed semantics**: unset means a default settled in
  `/speckit.plan` (likely 1500 tokens — leaves room for the
  rest of the prompt-tier budget). Out-of-range values MUST
  cause startup exit per V16.

### `SACP_TOOL_DEFER_INDEX_MAX_TOKENS`

- **Intended type**: positive integer, tokens
- **Intended valid range**: `64 <= value <= 1024`.
- **Fail-closed semantics**: unset means a default settled in
  `/speckit.plan` (likely 256 tokens — enough for ~30 deferred
  tools at 8-token index entries each). Out-of-range values
  MUST cause startup exit per V16.

### `SACP_TOOL_DEFER_LOAD_TIMEOUT_S`

- **Intended type**: positive integer, seconds
- **Intended valid range**: `1 <= value <= 30`.
- **Fail-closed semantics**: unset means load inherits the
  configured MCP client request timeout. Out-of-range values
  MUST cause startup exit per V16.

## Cross-References to Existing Specs and Design Docs

- **`sacp-design.md` §4.2 (Conversation Loop Engine)** — step 6
  ("Build context payload") is the integration point for the
  partition-aware system-prompt assembly. The §4.2 line 446
  latency-optimization budget binds V14 partition-recomputation.
- **`sacp-design.md` §6.1 (System Prompt Architecture)** — the
  ~1,730-token system-prompt budget across the four tiers is
  the target this spec protects. Tool definitions consume part
  of this budget.
- **`sacp-design.md` §6.3 (Tool Access Asymmetry)** — the
  `[NEED:]` proxy is for low-capability models; THIS spec is
  for high-capability models with large tool counts. FR-012
  enforces the disjoint scoping.
- **`sacp-design.md` §7.2 (Participant Privacy)** — bounds FR-006
  per-participant scoping.
- **Constitution §3 (Sovereignty)** — V1 sovereignty guarantees
  bind FR-006: a participant's loaded/deferred partition is part
  of their sovereignty surface.
- **Spec 002 (mcp-server)** — participant registration; FR-012
  detects no-tool-calling-capability at this point.
- **Spec 003 (turn-loop-engine) §FR-030** — `routing_log`
  per-stage timing capture; partition recomputation events
  surface through this channel.
- **Spec 015 (provider-failure-detection)** — the discovery
  tools (`sacp_list_deferred_tools`, `sacp_load_tool`) are
  internal MCP tools and MUST NOT trip the provider failure
  breaker even if the underlying MCP server is degraded.
- **Spec 016 (prometheus-metrics)** — partition statistics
  (loaded vs. deferred counts, on-demand load rate, eviction
  rate) SHOULD surface through spec 016's metrics surface.
  Cross-reference; not a hard dependency for the Phase-1 cut.
- **Spec 017 (tool-list-freshness)** — partition recomputation
  is triggered by freshness refreshes; the
  `prompt_cache_invalidated` field on spec-017 audit entries
  pairs with this spec's `tool_loaded_on_demand` invalidations.
  This is the deepest cross-spec coupling.

## Assumptions

- The MCP tool definition format (name, description, parameter
  schema) is stable and uniformly representable. Cross-server
  tool definition variation does not require per-server custom
  serialization.
- Token counting against the budget uses the same tokenizer as
  the participant's model — resolved via
  `src.api_bridge.tokenizer.get_tokenizer_for_participant` per
  Session 2026-05-13. Fallback to the `_DefaultTokenizer`
  (cl100k_base) when no model-specific adapter exists; fallback
  emits a WARN log and sets `tokenizer_fallback_used=true` in the
  partition audit row.
- The Phase-1 design-hooks cut and the Phase-2 working-
  implementation cut share a single SACP_TOOL_DEFER_* env-var
  namespace (not separate namespaces). Phase 1 ships with all
  vars defaulting to "deferral disabled." Phase 2 enables the
  policy.
- The `sacp_list_deferred_tools` and `sacp_load_tool` discovery
  tool names are working titles. Final naming is settled in
  `/speckit.plan` against MCP naming conventions and any
  facilitator-tool-namespace policies.
- Tool descriptions and one-line summaries used in the index
  are generated from the existing tool description text by
  truncation, not by an LLM call (no per-partition LLM cost
  on the hot path).
- "Phase 2 scope for the working implementation. Phase 1 ships
  only the design hooks." in the user description is interpreted
  as: this spec ships the Phase-1 hooks; the Phase-2 working
  implementation is a follow-up cut of this same spec OR a
  separate spec. Confirmation pending per Clarifications §"Phase
  split structure".
- Status remains Draft until the five flagged clarifications
  resolve and the user accepts the scaffolding.
