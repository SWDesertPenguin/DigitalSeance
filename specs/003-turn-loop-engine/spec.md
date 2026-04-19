# Feature Specification: Turn Loop Engine

**Feature Branch**: `003-turn-loop-engine`
**Created**: 2026-04-11
**Status**: Draft
**Input**: User description: "Turn loop engine — serialized conversation execution with context assembly, 8-mode routing, LiteLLM provider dispatch, budget enforcement, circuit breaker, and interrupt processing"

## Clarifications

### Session 2026-04-14

- Q: Default turn timeout? → A: 180 seconds (matches migration 003; originally 60s proved insufficient for local models like llama3.2:3b on CPU)
- Q: Late response grace window? → A: None — drop late responses; removed [LATE] aspirational tagging from spec

### Session 2026-04-15

- Q: When an interjection arrives while an AI turn is already in flight, how should its position in the transcript be ordered relative to that AI turn? → A: By **arrival time**, not processing time. Interjections are persisted to the transcript at the moment `inject_message` is received, so their `turn_number` reflects when the human asked the question (before the in-flight AI reply), not when the loop later drained the interrupt queue. The interrupt queue is still used as a routing/cadence signal; it no longer owns transcript persistence.
- Q: How do we avoid `turn_number` collisions between the concurrent inject write and the AI-turn persist? → A: A transaction-scoped PostgreSQL advisory lock on `hashtext(branch_id)` serializes `SELECT MAX(turn_number) + 1` + `INSERT` within `MessageRepository.append_message`.
- Q: On small/CPU-hosted models, prompt-eval latency grew every turn because history kept accumulating. What's the bound? → A: `_fill_history` now reads `SACP_CONTEXT_MAX_TURNS` (default 20, clamped to at least `MVC_FLOOR_TURNS=3`) and passes it as the limit to `MessageRepository.get_recent`. Token budget still applies; this is a secondary cap that protects latency when the token window is too generous for the actual model hardware.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Single Turn Execution (Priority: P1)

The orchestrator executes a single conversation turn: selects the next speaker via round-robin rotation, builds a context payload, dispatches it to the speaker's AI provider, receives the response, persists it as an immutable message, and logs both the routing decision and token usage. This is the atomic unit of the entire conversation system.

**Why this priority**: Nothing works without turn execution. Every other story builds on this fundamental loop iteration.

**Independent Test**: Can be tested by executing a single turn with two participants, verifying the response is persisted, routing is logged, and usage is recorded.

**Acceptance Scenarios**:

1. **Given** an active session with two participants, **When** a turn executes, **Then** the next speaker is selected via round-robin, a context payload is built, the AI provider is called, and the response is persisted as an immutable message.
2. **Given** a completed turn, **When** the response is persisted, **Then** a routing log entry records who was intended, who responded, the action taken, and the reason.
3. **Given** a completed turn, **When** usage is logged, **Then** input tokens, output tokens, and cost are recorded against the responding participant.
4. **Given** a turn with a provider timeout, **When** the timeout expires, **Then** the turn is skipped, the skip is logged, and the loop advances to the next turn without halting.

---

### User Story 2 - Context Assembly (Priority: P1)

The orchestrator builds a context payload for each turn using a strict priority order and a token budget. Human interjections come first (highest priority), followed by active proposals, then the minimum viable context floor (system prompt + last 3 turns), then the latest summarization checkpoint, then additional history filling the remaining budget. The payload never exceeds the participant's context window.

**Why this priority**: The AI provider receives exactly this payload — its quality directly determines response quality. Without proper context assembly, responses are incoherent or miss critical information.

**Independent Test**: Can be tested by assembling context for a session with interjections, proposals, messages, and a summary, verifying priority order is respected and token budget is not exceeded.

**Acceptance Scenarios**:

1. **Given** pending interjections, active proposals, recent messages, and a summary checkpoint, **When** context is assembled, **Then** interjections appear first, proposals second, MVC floor third, summary fourth, and additional history fills the remainder.
2. **Given** a participant with a limited context window, **When** context is assembled, **Then** the total token count does not exceed the available budget (context_window minus system prompt minus response reserve).
3. **Given** more history than fits in the budget, **When** context is assembled, **Then** history is truncated at turn boundaries (never mid-turn), newest-first.
4. **Given** an MVC floor that exceeds the participant's context window, **When** context is assembled, **Then** the system reports that the participant's context is too small for active participation.

---

### User Story 3 - LiteLLM Provider Dispatch (Priority: P1)

The orchestrator sends the assembled context to the participant's AI provider via LiteLLM, handles streaming responses, extracts the final text, counts tokens, and computes cost. The participant's API key is decrypted only at the moment of dispatch and discarded immediately after. Provider-specific message format translation is handled transparently.

**Why this priority**: Provider dispatch is the external call that produces AI responses. Without it, the loop has no output.

**Independent Test**: Can be tested by dispatching a payload to a provider (or mock), verifying the response is extracted with correct token count, cost is computed, and the API key is not retained after dispatch.

**Acceptance Scenarios**:

1. **Given** a context payload and a participant's encrypted API key, **When** the payload is dispatched, **Then** the key is decrypted in memory, the provider is called, and the key is discarded immediately after the call completes.
2. **Given** a streaming response, **When** tokens arrive, **Then** they are accumulated into the final response text with correct token counting.
3. **Given** a provider-specific format requirement, **When** the payload is sent, **Then** it is translated to the correct format (messages array structure) for that provider.
4. **Given** a provider rate limit response, **When** the response includes a Retry-After header, **Then** the system backs off for the specified duration before retrying (up to 3 retries).

---

### User Story 4 - Turn Routing with 8 Modes (Priority: P2)

Each participant has a routing preference that determines when and how they engage. The turn router evaluates the preference before each turn and takes the appropriate action: proceed normally (always), stage for review (review_gate), delegate to cheaper model (delegate_low), filter by domain (domain_gated), batch responses (burst), read on interval (observer), activate on name mention (addressed_only), or respond only to humans (human_only).

**Why this priority**: Routing modes are what make SACP a collaboration protocol rather than a simple round-robin chat. They enable cost control, oversight, and flexible engagement patterns.

**Independent Test**: Can be tested by setting each routing mode on a participant and verifying the correct routing action is taken and logged.

**Acceptance Scenarios**:

1. **Given** a participant with mode 'always', **When** their turn comes, **Then** they respond to every turn with no additional checks.
2. **Given** a participant with mode 'review_gate', **When** their AI generates a response, **Then** the response is staged as a draft for human review rather than entering the transcript directly.
3. **Given** a participant with mode 'delegate_low' and a low-complexity turn, **When** routing is evaluated, **Then** the turn is delegated to the cheapest active model and the original participant is recorded in delegated_from.
4. **Given** a participant with mode 'burst' who has accumulated enough turns, **When** the burst interval is reached, **Then** they produce one comprehensive response covering the accumulated period.
5. **Given** a participant with mode 'observer', **When** their observer interval is reached, **Then** they receive context and decide whether to respond.
6. **Given** a participant with mode 'addressed_only', **When** they are not mentioned by name in recent turns, **Then** they are skipped.
7. **Given** a participant with mode 'human_only', **When** no human interjection is pending, **Then** they are skipped.
8. **Given** any routing decision, **When** it completes, **Then** the decision is logged with intended participant, actual participant, action, complexity, domain match, and reason.

---

### User Story 5 - Interrupt Queue Processing (Priority: P2)

Human interjections take absolute priority over AI turns. When pending interjections exist in the queue, the orchestrator delivers them before any AI turn, ordered by priority (high before normal) then creation time (FIFO within priority). Delivered interjections are marked with a delivery timestamp.

**Why this priority**: Human authority over AI autonomy is a constitutional principle (§4.2). The interrupt queue is the mechanism that enforces it in the turn loop.

**Independent Test**: Can be tested by enqueuing interjections with different priorities during an active loop and verifying they are delivered before AI turns in correct order.

**Acceptance Scenarios**:

1. **Given** pending interjections, **When** the loop checks for interrupts at the start of a turn, **Then** all pending interjections are delivered before the AI turn proceeds.
2. **Given** interjections of different priorities, **When** they are delivered, **Then** high-priority interjections come before normal ones, and within the same priority they are delivered in creation order.
3. **Given** a delivered interjection, **When** delivery completes, **Then** its status is updated to 'delivered' with a delivery timestamp.
4. **Given** interjections from multiple humans, **When** they are delivered, **Then** each is included in the context payload with speaker attribution.

---

### User Story 6 - Budget Enforcement (Priority: P2)

The orchestrator tracks each participant's token usage and cost per turn. Before dispatching a turn, it checks whether the participant's hourly or daily budget ceiling would be exceeded. If the ceiling is hit, the turn is skipped, the skip is logged, and the participant's human is notified. Budget tracking is per-participant and never pooled.

**Why this priority**: Budget autonomy is a sovereignty guarantee (constitution §3). Without enforcement, a runaway conversation could drain a participant's API credits.

**Independent Test**: Can be tested by setting a low budget ceiling, executing turns until the budget is hit, and verifying the participant is skipped with appropriate logging.

**Acceptance Scenarios**:

1. **Given** a participant with a daily budget of $1.00 who has used $0.95, **When** a turn would cost $0.10, **Then** the turn is skipped because it would exceed the budget.
2. **Given** a budget-exceeded participant, **When** the skip occurs, **Then** a routing log entry records the skip with reason 'budget_exceeded'.
3. **Given** a budget-exceeded participant, **When** their AI stops, **Then** they can still inject human messages via the interrupt queue.
4. **Given** multiple participants with different budgets, **When** one hits their ceiling, **Then** the other participant continues normally — budgets are never pooled.

---

### User Story 7 - Circuit Breaker (Priority: P3)

When a participant's AI provider fails repeatedly (timeout, error, rate limit), the circuit breaker tracks consecutive failures. After a configurable number of consecutive failures (default 3), the participant is automatically paused and their human is notified. The circuit resets to zero on any successful response.

**Why this priority**: Graceful degradation is a constitutional principle (§4.3). The circuit breaker prevents one failing provider from halting the entire session.

**Independent Test**: Can be tested by simulating consecutive provider failures and verifying the participant is auto-paused after the threshold, then resumes correctly after a successful response.

**Acceptance Scenarios**:

1. **Given** a participant whose provider times out 3 consecutive times, **When** the threshold is reached, **Then** the participant's status changes to 'paused' and the pause is logged.
2. **Given** a paused participant, **When** their human resumes them, **Then** the consecutive timeout counter resets to zero.
3. **Given** a participant with 2 consecutive timeouts, **When** the next turn succeeds, **Then** the counter resets to zero (circuit closes).
4. **Given** one participant is circuit-broken, **When** the loop continues, **Then** the remaining participant(s) continue conversing normally.

---

### User Story 8 - Error Detection and Recovery (Priority: P3)

The orchestrator inspects each AI response for quality problems: empty responses, responses that repeat the same content as the previous turn, or responses with excessive n-gram repetition. Detected problems trigger a retry (up to 3 attempts). If all retries fail, the turn is skipped with logging.

**Why this priority**: Quality checks prevent degraded responses from polluting the transcript. Without them, broken outputs accumulate and confuse subsequent turns.

**Independent Test**: Can be tested by providing mock responses with known problems (empty, identical, repetitive) and verifying retries are attempted and bad responses are rejected.

**Acceptance Scenarios**:

1. **Given** an empty response from a provider, **When** the error is detected, **Then** the system retries (up to 3 times) before skipping the turn.
2. **Given** a response identical to the previous turn's content, **When** the duplicate is detected, **Then** it is rejected and retried.
3. **Given** 3 consecutive failed retries for the same turn, **When** all retries are exhausted, **Then** the turn is skipped and the failure is logged.
4. **Given** a valid response after a retry, **When** the retry succeeds, **Then** the response is persisted normally and the retry count resets.

---

### User Story 9 - Complexity Classifier (Priority: P3)

Before routing each turn, the orchestrator classifies the conversation's current complexity as 'low' or 'high' using pattern-matching heuristics. Low-complexity turns include restatements, confirmations, and acknowledgments. High-complexity turns include tradeoffs, novel proposals, and flaw identification. The classification feeds into routing decisions (delegate_low and domain_gated modes).

**Why this priority**: The classifier enables cost-saving routing modes but the loop works without it (defaulting to 'high' for all turns).

**Independent Test**: Can be tested by providing sample conversation contexts and verifying the classifier labels them correctly as low or high complexity.

**Acceptance Scenarios**:

1. **Given** a conversation context containing mostly confirmations and agreements, **When** complexity is classified, **Then** it is labeled 'low'.
2. **Given** a conversation context containing a novel proposal with tradeoff analysis, **When** complexity is classified, **Then** it is labeled 'high'.
3. **Given** a classified turn, **When** routing occurs, **Then** the complexity score is included in the routing log and available to routing mode logic.

---

### User Story 10 - Review Gate Integration (Priority: P3)

When a participant uses review_gate mode, their AI's response is staged as a draft rather than entering the transcript. The loop pauses new dispatches while drafts are pending; the pause scope is facilitator-configurable — `"session"` (all participants pause, default) or `"participant"` (only the gated participant pauses). When the facilitator approves, edits, or rejects the draft via the MCP endpoints, the resolved content enters (or doesn't enter) the transcript and dispatching resumes.

**Why this priority**: Review gate is one of the 8 routing modes and provides human oversight of AI responses. It works through the existing review gate draft staging from feature 001.

**Independent Test**: Can be tested by executing a turn for a review-gated participant and verifying the response is staged as a draft (not in the transcript) with pending status.

**Acceptance Scenarios**:

1. **Given** a review-gated participant's turn, **When** their AI generates a response, **Then** the response is stored as a review gate draft with 'pending' status, not as a transcript message.
2. **Given** a pending draft and session-scope pause (default), **When** the loop advances, **Then** no participant is dispatched until the draft is resolved.
3. **Given** a pending draft and participant-scope pause, **When** the loop advances, **Then** only the gated participant is skipped; other participants continue normally.
4. **Given** a staged draft, **When** the routing decision is logged, **Then** the action is recorded as 'review_gated' and subsequent skips are logged as 'review_gate_pending'.

---

### Edge Cases

- What happens when all participants are skipped (budget, paused, circuit-broken)? The loop pauses the session and notifies connected humans.
- What happens when a provider returns a response after the timeout? The response is dropped — once a turn times out, the request is cancelled and any late reply is discarded. No grace window, no [LATE] tagging.
- What happens when the API key decryption fails at dispatch time? The turn is skipped with an error log; the participant is not auto-paused (encryption failure is an infrastructure problem, not a provider problem).
- What happens when a burst participant's interval is reached but no turns have occurred? The burst fires with whatever history is available.
- What happens when an observer chooses not to respond? The observation is logged as 'observer_read' (not 'observer_inject') and consumes zero output tokens.
- What happens when delegate_low tries to delegate but no cheaper model is active? The turn proceeds with the original participant's model.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST execute turns in a serialized loop — one turn at a time, no concurrent turns on the same session.
- **FR-002**: System MUST select the next speaker via round-robin rotation through active participants, skipping paused or over-budget participants.
- **FR-003**: System MUST build context payloads using a strict 5-priority allocation order: interjections → proposals → MVC floor → latest summary → additional history.
- **FR-004**: System MUST enforce a token budget per turn that does not exceed the participant's context window minus system prompt and response reserve.
- **FR-005**: System MUST truncate history at turn boundaries (never mid-turn) when the token budget is exceeded.
- **FR-006**: System MUST dispatch context payloads to AI providers via a provider abstraction layer, translating message format to each provider's expected structure.
- **FR-007**: System MUST decrypt participant API keys only at the moment of provider dispatch and discard plaintext immediately after the call completes.
- **FR-008**: System MUST handle streaming responses by accumulating tokens into the final response text.
- **FR-009**: System MUST count input and output tokens per turn and compute cost based on the participant's configured rates.
- **FR-010**: System MUST persist every AI response as an immutable message with speaker attribution, token count, cost, and complexity score.
- **FR-011**: System MUST log every routing decision with intended participant, actual participant, action, complexity, domain match, and reason.
- **FR-012**: System MUST implement all 8 routing modes: always, review_gate, delegate_low, domain_gated, burst, observer, addressed_only, human_only.
- **FR-013**: System MUST process pending interrupt queue entries before each AI turn, delivering them in priority-then-creation order.
- **FR-014**: System MUST enforce per-participant budget ceilings (hourly and daily), skipping turns that would exceed the budget.
- **FR-015**: System MUST track consecutive provider failures per participant and auto-pause after a configurable threshold (default 3).
- **FR-016**: System MUST detect empty, duplicate, and excessively repetitive responses and retry up to 3 times before skipping the turn.
- **FR-017**: System MUST classify turn complexity as 'low' or 'high' using pattern-matching heuristics before routing decisions.
- **FR-018**: System MUST stage review-gated participant responses as drafts rather than transcript messages.
- **FR-019**: System MUST respect per-turn timeouts (configurable per participant, default 180 seconds as of migration 003) and skip the turn on timeout.
- **FR-020**: System MUST retry provider calls on rate-limit responses with exponential backoff respecting Retry-After headers.
- **FR-021**: System MUST never halt the session due to a single participant's provider failure — the loop skips and continues.

### Key Entities

- **Turn**: A single iteration of the conversation loop — route, build context, dispatch, persist, log.
- **Context Payload**: The assembled set of messages, interjections, proposals, and history sent to an AI provider, bounded by a token budget.
- **Routing Decision**: The determination of what action to take for a given turn based on the participant's routing mode and the current conversation state.
- **Provider Response**: The AI-generated text returned from a provider call, with associated token counts and cost.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A complete turn (route → assemble → dispatch → persist → log) executes end-to-end with all artifacts persisted correctly.
- **SC-002**: Context payloads respect priority order — interjections always appear before proposals, proposals before MVC floor, in every assembled payload.
- **SC-003**: No context payload exceeds the participant's available token budget.
- **SC-004**: All 8 routing modes produce the correct routing action when evaluated with appropriate inputs.
- **SC-005**: Budget-exceeded participants are skipped 100% of the time with appropriate logging.
- **SC-006**: Circuit breaker auto-pauses participants after exactly the configured threshold of consecutive failures.
- **SC-007**: Human interjections are delivered before AI turns in every turn cycle where they exist.
- **SC-008**: Provider API keys never appear in any log output, error trace, or persisted record.
- **SC-009**: The turn loop continues operating when one participant's provider fails — no single failure halts the session.

## Assumptions

- Phase 1 uses round-robin rotation only. Relevance-based and broadcast rotation modes are deferred to Phase 3.
- The complexity classifier uses pattern-matching heuristics only (no embeddings, no model calls) per constitution §10.
- Convergence detection, adaptive cadence, and adversarial rotation are deferred to feature 004. The loop runs at a fixed cadence in this feature.
- Summarization checkpoint triggering is deferred to feature 005. The loop reads existing summaries for context assembly but does not generate new ones.
- LiteLLM is the primary provider abstraction. Direct SDK fallbacks (anthropic, openai) are deferred to a later hardening pass.
- Token counting uses LiteLLM's built-in token estimation. Exact tiktoken counting is a future optimization.
- The MCP server (feature 006) will expose the loop's start/stop controls. This feature provides the engine; the interface comes later.
- The system prompt tier content is a separate deliverable. This feature assembles whatever prompt text is configured on the participant record.
- Late responses are dropped — once the turn timeout expires, the request is cancelled and no response is accepted from that dispatch.

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): Topologies 1–6 only (orchestrator-driven). The turn loop engine assumes the orchestrator drives turn selection, context assembly, and provider dispatch. Topology 7 (MCP-to-MCP, client-side AI execution) requires peer routing — no orchestrator turn loop. Phase 2+ will implement peer-to-peer coordination for topology 7.

**Use cases** (per constitution §1): Serves all seven equally within orchestrator-driven topologies (1–6). Routing modes (always, review_gate, delegate_low, etc.) and budget enforcement enable the flexible participation patterns needed for consulting, asymmetric expertise, and zero-trust scenarios.
