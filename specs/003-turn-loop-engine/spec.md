# Feature Specification: Turn Loop Engine

**Feature Branch**: `003-turn-loop-engine`
**Created**: 2026-04-11
**Status**: Draft
**Spec Version**: 1.3.0 | **Last Amended**: 2026-05-03 | **Amended In**: fix/context-window-clamp (FR-035 catalog-clamped budget + ContextWindowOverflowError)
**Input**: User description: "Turn loop engine — serialized conversation execution with context assembly, 8-mode routing, LiteLLM provider dispatch, budget enforcement, circuit breaker, and interrupt processing"

## Clarifications

### Session 2026-04-14

- Q: Default turn timeout? → A: 180 seconds (matches migration 003; originally 60s proved insufficient for local models like llama3.2:3b on CPU)
- Q: Late response grace window? → A: None — drop late responses; removed [LATE] aspirational tagging from spec

### Session 2026-04-15

- Q: When an interjection arrives while an AI turn is already in flight, how should its position in the transcript be ordered relative to that AI turn? → A: By **arrival time**, not processing time. Interjections are persisted to the transcript at the moment `inject_message` is received, so their `turn_number` reflects when the human asked the question (before the in-flight AI reply), not when the loop later drained the interrupt queue. The interrupt queue is still used as a routing/cadence signal; it no longer owns transcript persistence.
- Q: How do we avoid `turn_number` collisions between the concurrent inject write and the AI-turn persist? → A: A transaction-scoped PostgreSQL advisory lock on `hashtext(branch_id)` serializes `SELECT MAX(turn_number) + 1` + `INSERT` within `MessageRepository.append_message`.
- Q: On small/CPU-hosted models, prompt-eval latency grew every turn because history kept accumulating. What's the bound? → A: `_fill_history` now reads `SACP_CONTEXT_MAX_TURNS` (default 20, clamped to at least `MVC_FLOOR_TURNS=3`) and passes it as the limit to `MessageRepository.get_recent`. Token budget still applies; this is a secondary cap that protects latency when the token window is too generous for the actual model hardware.

### Session 2026-05-02 (audit fix/003-ops-reliability — Phase E)

- Q: What's the operator-override surface for a stuck loop? → A: Phase 1: pause via facilitator API or DB UPDATE on the session row. No dedicated kill-switch CLI in Phase 1. Process-level restart abandons in-flight turns across ALL sessions (RPO=0 for committed turns). Phase 3 trigger: any deployment where individual sessions can wedge without affecting others — implementation: a `/tools/admin/kill_loop?session_id=...` endpoint that cancels the session's loop task without process-restart.

- Q: How does the orchestrator behave on SIGTERM? → A: In-flight turns are abandoned (uvicorn graceful shutdown cancels the loop task; transactional rollback ensures no partial state). On startup, no per-turn resumption — the next dispatch uses persisted state as the source of truth. RTO ~5–10 seconds; see `docs/operational-runbook.md` §10.4.

- Q: What's the threshold for advisory-lock contention alerting? → A: FR-032 captures `routing_log.advisory_lock_wait_ms` per acquisition. Operator alert threshold: rolling-window mean > 100 ms over 5 minutes indicates cross-session lock pressure (single-instance Phase 1 deployments shouldn't normally exhibit this). Implementation: operator-side query / alerting infrastructure; SACP supplies the raw column.

- Q: What's the alert escalation for FR-031 compound-retry events? → A: `compound_retry_warn` (turn elapsed > 2× per-attempt timeout, default 360 s) is informational — operator monitors trend. `compound_retry_exhausted` (turn skipped at hard cap, default 600 s) is actionable — investigate the participant's provider health. See runbook §6.4.

- FR-031 compound-retry cap implemented in fix/003-compound-retry-cap (2026-05-05): `dispatch_with_retry` tracks elapsed via `time.monotonic()`; `_check_retry_budget` runs before every attempt and (a) raises `CompoundRetryExhaustedError` when elapsed >= `SACP_COMPOUND_RETRY_TOTAL_MAX_SECONDS` (default 600s) and (b) emits one `compound_retry_warn` log line when elapsed first crosses `SACP_COMPOUND_RETRY_WARN_FACTOR × timeout` (default 2.0 × per-attempt). The new exception subclasses `ProviderDispatchError` so existing catches keep working; `_assemble_and_dispatch` in `src/orchestrator/loop.py` catches it specifically and surfaces `routing_log.reason='compound_retry_exhausted'` ahead of the generic `provider_error` reason.

- Q: Does the budget-enforcement window handle 23:59:59 turn boundaries correctly? → A: Yes. FR-028 uses `NOW() - INTERVAL '1 hour'` / `NOW() - INTERVAL '1 day'` as a rolling trailing window, NOT calendar-aligned. A turn fired at 23:59:59 charges against the rolling 24-hour window, not the calendar day; midnight has no semantic effect.

- Q: What is interrupt-queue saturation behavior under 1000+ pending interrupts? → A: Phase 1 has no enforced cap — a session with 1000 pending interrupts scans all of them per turn, growing per-turn latency O(n). Phase 3 trigger: any deployment observing pathological interrupt accumulation; implementation: enforce `MAX_PENDING_INTERRUPTS_PER_SESSION` cap, oldest dropped with `routing_log.reason='interrupt_queue_saturated'`.

### Session 2026-05-03 (audit fix/api-bridge-tokenizer-adapter)

- Q: Why per-target-model tokenization rather than one canonical estimator? → A: Cross-provider tokenizer drift is well-documented; English prose lands within 5–15% across providers, code-heavy / non-Latin content drifts much more. A char/4 heuristic systematically under- or over-allocates the budget against the participant's actual context window. The adapter resolves the right tokenizer per participant so `_available_budget` lands against the target rather than a generic estimator.

- Q: Why fallback as the default-runtime path with the SDK API on reconcile only? → A: Calling the provider's count-tokens endpoint on every turn would add a network round-trip to a hot path. The fallback path is in-process and instant; the API path is reserved for end-of-session / facilitator-triggered reconciliation that produces a drift report. LiteLLM's post-call cost remains the truth source for billing per FR-028.

- Q: Why no new env var for the fallback multipliers? → A: They're empirical constants documented in `comm-design/02-byok-compatibility.md` §4 and codified in the module. Operator-tunable runtime overrides would invite drift between the live config and the documented baseline; reconciliation is the right surface for "is the multiplier still right?", not a knob.

- Q: What about call sites that don't have a participant in scope (announcements, divergence prompt, summarizer persistence)? → A: Default tokenizer (cl100k tiktoken) for system content; per-participant adapter only at sites with participant scope. The default tokenizer is more accurate than the prior `len(text) // 4` for any provider, so the migration is a strict accuracy improvement at every site.

- Q: Why is the MCP tool for facilitator-triggered reconciliation deferred to Phase 3? → A: The reconcile function is operationally useful but the surface for invoking it (a facilitator-only debug tool) needs threat-model review per the role-scoping rules. Shipping the function without the surface lets Phase 3 add the MCP wiring with a focused PR rather than tangling it with the bridge work.

### Session 2026-05-02 (audit fix/api-bridge-caching)

- Q: Why pass `cache_directives` through dispatch instead of having the bridge pick a default policy unconditionally? → A: Sovereignty + audit-log integrity. The orchestrator owns the policy; the bridge owns the per-provider translation. A future Phase 3 may let participants opt out of caching for compliance reasons (cache writes are still data egress); the dispatch parameter keeps that decision at the orchestrator layer rather than burying it in the bridge.

- Q: Why default `SACP_ANTHROPIC_CACHE_TTL` to `1h` rather than the new Anthropic default `5m`? → A: Multi-minute session cadence is the SACP norm (turn budgets, review-gate latency, human-in-the-loop pauses). The 2x cache-write surcharge for `1h` is recovered after the third read; for sprint cadence specifically operators can set `SACP_ANTHROPIC_CACHE_TTL=5m` to match the workload.

- Q: Why `prompt_cache_key=session_id` rather than `participant_id` for OpenAI? → A: Sessions, not participants, share the cached prefix (system prompt + tool defs + history). Keying by participant_id would fan out cache state across backends within the same session and lose hit rate. session_id keeps a session's per-participant fan-out routed to one backend.

- Q: Why is the OpenAI 24h-retention allowlist empty in Phase 1? → A: `prompt_cache_retention="24h"` only meaningfully applies to Extended Prompt Caching models (GPT-5.5+ family). Phase 1 ships the parameter wiring so the env var is honoured, but model activation waits for production-traffic confirmation per the prompt's "out of scope" call. Operators can set `SACP_OPENAI_CACHE_RETENTION=24h` today; the request-side passthrough fires only on allowlisted models.

- Q: When `cache_directives` is None, what changes about the dispatched payload? → A: Nothing. Byte-identical to pre-amendment behaviour: messages stay as `{role, content: str}` dicts, no `cache_control` blocks, no `prompt_cache_key`/`cached_content` kwargs. Existing call sites (e.g., `summarizer.py`) inherit the no-op default.

- Q: Does compression-vs-cache tension apply in Phase 1? → A: No. Phase 1 ships caching only — hard compression is deferred to Phase 2 (per local research bundle §7). The cache breakpoint policy assumes the prefix is byte-stable across turns; the rolling-summary checkpoint already preserves prefix stability by becoming part of the cached head once written.

### Session 2026-05-02 (audit fix/003-compliance — Phase D)

- Q: Which 003 record is the Art. 28(3)(h) processor-disclosure trail? → A: `routing_log` (FR-011). Every turn records which provider received which content; combined with FR-007 (key decrypt at dispatch only) and 001 §FR-008 (append-only repository invariant), this is the canonical sub-processor audit trail. Operators are responsible for documenting Art. 28 DPA / SCC contracts with each enabled AI provider (Anthropic, OpenAI, Google, Groq, Ollama).

- Q: For EU data subjects, does litellm dispatch trigger Art. 44 cross-border transfer? → A: Yes for cloud providers (Anthropic US, OpenAI US, Google US, Groq US). Ollama on operator-controlled infrastructure is the only Phase 1 option that avoids transfer. Per-region routing policy is deferred to Phase 3; trigger: any deployment with a data-residency requirement not met by switching to Ollama.

- Q: Are `routing_log` and `usage_log` purge jobs wired? → A: No. `SACP_ROUTING_LOG_RETENTION_DAYS` and `SACP_USAGE_LOG_RETENTION_DAYS` are reserved env vars in `docs/env-vars.md` but no purge job exists in Phase 1. Erasure is via session / participant cascade only. Phase 3 trigger: any deployment with a regulatory retention cap below indefinite.

- Q: Does `usage_log` duplicate message content? → A: No. Only the accounting columns are persisted (cost_usd, input_tokens, output_tokens, timestamp). This is Art. 5(1)(c) data minimization at the budget-tracking boundary; the content lives in `messages`.

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
- What happens when a provider returns a response after the timeout? The response is dropped — once a turn times out, the request is cancelled and any late reply is discarded. No grace window, no [LATE] tagging. This is NOT a "silent drop" per 007 §FR-013 because the turn never persisted; it's an aborted dispatch with a logged skip reason.
- What happens when the API key decryption fails at dispatch time? The turn is skipped with an error log; the participant is not auto-paused (encryption failure is an infrastructure problem, not a provider problem). The decryption traceback is scrubbed via the root-logger ScrubFilter (007 §FR-012) so the failed-to-decrypt ciphertext bytes don't leak.
- What happens when a burst participant's interval is reached but no turns have occurred? The burst fires with whatever history is available.
- What happens when an observer chooses not to respond? The observation is logged as 'observer_read' (not 'observer_inject') and consumes zero output tokens.
- What happens when delegate_low tries to delegate but no cheaper model is active? Phase 1 always proceeds with the original participant's model regardless of cheaper-model availability — see FR-026. Phase 3 actual delegation will need to address this case.
- What happens when an LLM dispatch hangs past the turn timeout (FR-019)? The 180s timeout cancels the asyncio task; the cancellation propagates to LiteLLM's `acompletion`, which closes its HTTP connection. The decrypted API key falls out of scope when the cancelled coroutine unwinds. No persistent leak.
- What happens during a rate-limit retry (FR-020)? Each retry calls the dispatch helper fresh, which decrypts the key per attempt and dereferences after each call. Plaintext does not persist across retries — it's re-decrypted each time.
- What happens when adversarial rotation (deferred to feature 004) targets a budget-exceeded participant? The rotation logic skips to the next eligible participant; budget enforcement (FR-014) wins over adversarial-rotation insistence.
- What happens during pipeline-internal failure (regex bug, unicode error)? Per FR-023, the turn skips with `reason='security_pipeline_error'`; circuit breaker is NOT incremented; a `security_events` row with `layer='pipeline_error'` is written.

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
- **FR-022**: Concurrent turn writes MUST be serialized at the branch level via a transaction-scoped PostgreSQL advisory lock on `pg_advisory_xact_lock(hashtext(branch_id))` taken inside `MessageRepository.append_message`. The lock prevents `turn_number` collisions when an inject and an AI-turn persist race within the same branch (clarified 2026-04-15). The lock has no application-level timeout; lock contention blocks indefinitely until the holding transaction commits or aborts. Concurrent contention is bounded in practice because each transaction is short and the loop is single-threaded per session.
- **FR-023**: Pipeline-internal failures during output validation, exfiltration filtering, or any future pipeline layer MUST fail closed: the turn is skipped with `reason='security_pipeline_error'`, a `security_events` row with `layer='pipeline_error'` is written (per 007 §FR-013, §FR-015), and the participant's circuit-breaker counter is NOT incremented (the failure is the system's, not the participant's). The dispatched LLM response is discarded; no partial transcript write occurs.
- **FR-024**: Plaintext API-key memory residency is bounded by Python's reference lifetime — the key is decrypted into a local variable, passed to LiteLLM's `acompletion`, and dereferenced via re-binding to `None` at the end of the dispatch call. Memory zeroing (e.g., `ctypes.memset` on the underlying buffer) is NOT implemented in Phase 1 because Python strings are immutable and refcounted; a heap-trace attacker can recover plaintext until garbage collection runs. This is accepted residual risk: the trust boundary is "process-memory access by the orchestrator owner is equivalent to encryption-key access" — both are operator-controlled. Re-evaluation trigger: any deployment where the orchestrator's process memory is accessible to lower-trust users (e.g., shared multi-tenant container).
- **FR-025**: Routing-mode tampering during an in-flight turn is bounded by snapshot-at-route-time semantics: the routing decision (next speaker, mode, complexity, domain) is computed at the start of each turn from the participants table snapshot. Mid-turn changes to `routing_preference` apply on the *next* turn, not the current one. There is no race window because the dispatch happens within the same coroutine that read the routing snapshot.
- **FR-026**: The `delegate_low` routing mode in Phase 1 RECORDS the routing decision (`action='delegated'`) in the routing log for audit purposes but does NOT actually delegate response generation to a cheaper model. The original participant's model still produces the response; the `delegated_from` message field is unused in Phase 1. Actual cost-aware delegation is deferred to Phase 3 — trigger: a deployment with a documented per-turn cost reduction target.
- **FR-027**: Exactly one orchestrator process MUST run the turn loop per session at any moment. Phase 1 enforces this implicitly via single-deployment topology (one orchestrator container per database). Multi-process deployments would race on the advisory lock (FR-022) but also produce duplicate dispatches; explicit single-loop-per-session coordination (e.g., via a session lease) is deferred to Phase 3 multi-instance deployment.
- **FR-028**: Budget enforcement uses POST-CALL accounting via the usage_log table. Before each turn dispatch, the system queries `SUM(cost_usd)` over a TRAILING window (`NOW() - INTERVAL '1 hour'` for hourly, `NOW() - INTERVAL '1 day'` for daily — not calendar-aligned). The check compares accumulated cost against the participant's ceiling; if the sum already exceeds the ceiling, the turn is skipped with `reason='budget_exceeded'`. Pre-call cost estimation is NOT used; LiteLLM's post-call cost is the source of truth. A single turn that pushes total over the ceiling is allowed to complete (the over-spend is bounded by one turn's max cost).
- **FR-029**: When a participant's `context_window - max_tokens_per_turn - prompt_estimate <= 0`, the participant fails the MVC floor check and MUST be marked too-small for active dispatch (no turn is attempted). This is checked at participant configuration time (FR-004 budget calculation) and on every turn (the budget-too-small condition skips with `reason='context_too_small'`). The MVC floor is `MVC_FLOOR_TURNS=3` system + 3 history messages by default.
- **FR-030**: Per-stage turn timing MUST be captured into `routing_log` (additional columns or a sibling `turn_timings` table): `routing_ms`, `context_assembly_ms`, `dispatch_ms` (LLM round-trip), `persist_ms`, `post_pipeline_ms` (security pipeline; cross-ref 007 §FR-014). The end-to-end total MUST equal the sum of stage timings within ±5%. This makes regression detection per-stage rather than aggregate-only and replaces today's "where did the time go" investigation pattern with a queryable record.
- **FR-031**: Compound-retry worst-case duration MUST be bounded. The compounding of FR-016 quality retries (≤3) × FR-019 per-attempt timeout (default 180s) × FR-020 rate-limit retries (≤3 per attempt) admits a 27-minute worst case; this is unacceptable for Phase 1+. (a) When total-elapsed for a turn exceeds 2× per-attempt timeout (default 360s), `routing_log` MUST record `reason='compound_retry_warn'` with the cumulative elapsed value so operators can diagnose pathological cascades. (b) A hard total-elapsed cap MUST short-circuit further retries: configurable per participant via `compound_retry_total_max_seconds` (default 600s = 10 minutes), exceeding it skips the turn with `reason='compound_retry_exhausted'` per FR-021. The cap is independent of FR-019's per-attempt timeout.
- **FR-032**: Advisory-lock contention waits (FR-022) MUST be captured into `routing_log.advisory_lock_wait_ms` per acquisition. Sustained values > 100ms indicate cross-session lock pressure that single-instance Phase 1 deployments shouldn't normally exhibit; operators SHOULD alert on rolling-window means. The lock itself remains untimed at the application layer (FR-022 unchanged); only the wait duration is observed.
- **FR-033**: Provider dispatch (FR-006) MUST accept an optional `cache_directives` parameter of type `CacheDirectives` carrying per-provider cache hints (Anthropic breakpoint positions + TTL, OpenAI `prompt_cache_key`, Gemini `cachedContent` reference). The bridge layer translates the directive to the matching provider request shape inside `_call_litellm`. When `cache_directives` is None OR `SACP_CACHING_ENABLED='0'`, the dispatched payload MUST be byte-identical to pre-FR-033 behaviour (no `cache_control` blocks, no extra kwargs). Default policy: the orchestrator constructs directives via `build_session_cache_directives(session_id, model)` per turn — Anthropic gets `AFTER_SYSTEM` + `AFTER_HISTORY_OLD` breakpoints with `ttl=SACP_ANTHROPIC_CACHE_TTL` (default `1h`), OpenAI gets `prompt_cache_key=session_id`, Gemini relies on implicit caching. Three new validated env vars (`SACP_CACHING_ENABLED`, `SACP_ANTHROPIC_CACHE_TTL`, `SACP_OPENAI_CACHE_RETENTION`) per V16 — see `docs/env-vars.md`. Cache hit-rate telemetry and OpenAI Extended Prompt Caching (24h TTL) model activation are deferred to Phase 3.
- **FR-034**: Token counting MUST resolve a per-target-model adapter (the `TokenizerAdapter` Protocol in `src/api_bridge/tokenizer.py`) rather than the prior `len(text) // 4` heuristic. The adapter exposes `count_tokens`, `truncate_to_tokens`, and `get_tokenizer_name`. Three concrete adapters ship: OpenAI (tiktoken local — cl100k_base or o200k_base by model), Anthropic (tiktoken cl100k_base × empirical multiplier as the runtime path; SDK count-tokens API as the reconciliation path), Gemini (tiktoken cl100k_base × empirical multiplier as the runtime path; SDK countTokens API as the reconciliation path). `get_tokenizer_for_participant(pool, participant_id)` looks up the participant's model and caches the adapter for the process lifetime. `default_estimator()` returns a process-lifetime singleton for orchestrator-generated content (announcements, divergence prompt, summarizer persistence) where no participant is in scope. `_available_budget` (FR-004) and history accumulation in context assembly migrate to the adapter; LiteLLM's post-call cost remains the truth source for billing per FR-028. `reconcile_budget(pool, participant_id, *, api_key)` ships as a function returning a drift report; the facilitator-only MCP surface for triggering it is deferred to Phase 3.
- **FR-035**: Context budget MUST clamp the operator-supplied `participant.context_window` against an authoritative known-models catalog (`src/api_bridge/model_limits.py:known_max_input_tokens`) before allocating turn budget. The catalog resolves in two layers: LiteLLM `get_model_info(model)["max_input_tokens"]` first, then a small explicit fallback table covering the models the project tests against most often. When both are present the smaller value wins. Unknown models (catalog returns `None`) trust the operator-declared value — no clamp, no warning — to preserve compatibility with self-hosted / non-catalog providers. The clamp emits a single `WARNING` per `(session_id, participant_id)` pair the first time `declared > catalog`. Provider dispatch MUST surface `litellm.ContextWindowExceededError` as a distinct `ContextWindowOverflowError` (subclass of `ProviderDispatchError`) so `routing_log.reason` records `context_window_overflow` rather than the generic `provider_error`. The new error subclass MUST NOT be retried — the same payload would overshoot again — and existing `except ProviderDispatchError` paths keep working unchanged via subclass inheritance.

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
- **SC-010**: Per-stage P95 budgets (orchestrator overhead only; LLM dispatch_ms is model-dependent and excluded): routing ≤ 5ms, context_assembly ≤ 50ms, persist ≤ 20ms, post_pipeline ≤ 50ms (cross-ref 007 §FR-014 layer evaluation). Aggregate non-dispatch overhead P95 ≤ 125ms — this is the SACP turn-loop tax operators can plan around independent of model choice.
- **SC-011**: Per-turn end-to-end latency SLOs MUST be reported on a rolling 30-day window: P50 ≤ model-baseline (cloud Haiku class ~3s, local llama3.2:3b on CPU class ~30s), P95 ≤ 2× P50, P99 ≤ FR-019 per-attempt timeout. Persistent P95 > 2× P50 indicates degradation worth root-cause investigation. Without telemetry to compute these, the contract is aspirational; operators backing this with metrics are providing a perf signal the spec asserts is observable.

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

## Threat model traceability

| FR | Defends against | OWASP LLM / API | NIST AI 100-2 / SP 800-53 |
|----|-----------------|------------------|---------------------------|
| FR-001 (serialized loop) | Concurrent-dispatch races | API4 | SC-5 |
| FR-002 (round-robin skip) | Forced participation despite paused/budget | — | AC-3 |
| FR-003, FR-005 (context priority + truncation) | Context-budget overflow → provider error | — | SC-5 |
| FR-007, FR-024 (key decrypt at dispatch + bounded residency) | API-key exposure via memory or logs | LLM02 | SC-12, SC-28, AU-9 |
| FR-010, FR-011 (immutable persistence + routing log) | Transcript/audit tampering | — | AU-2, AU-3, AU-12, SI-7 |
| FR-013 (interrupt queue) | Silent loss of human inputs | — | AC-3 |
| FR-014, FR-028 (budget enforcement) | Runaway provider cost / DoS | API4, LLM04 | SC-5(2) |
| FR-015 (circuit breaker) | Cascading provider failure halts session | — | SI-13 |
| FR-016 (degenerate-output retry+skip) | Garbage transcript pollution | — | SI-10 |
| FR-018, FR-026 (review_gate + delegate_low scope) | Direct-output bypass / unaudited delegation | LLM05 | AC-3 |
| FR-019, FR-020 (timeout + rate-limit retry) | DoS via hung provider; hot-loop rate-limit thrash | API4 | SC-5 |
| FR-021 (no halt on single failure) | Single point of failure halts session | — | SI-13 |
| FR-022 (advisory lock) | turn_number collision | — | SI-7 |
| FR-023 (fail-closed pipeline error) | Defense erosion via uncaught exception | LLM05 | SI-4 |
| FR-025 (snapshot routing) | Mid-flight tampering race | — | AC-3 |
| FR-027 (single loop per session) | Duplicate dispatch / cost double-charge | API4 | CM-2 |
| FR-029 (MVC floor) | Context-too-small dispatch error | — | SC-5 |

Sister cross-references: log scrubbing (007 §FR-012) covers any traceback emitted by `_validate_and_persist` because exception logs go through the root-logger ScrubFilter; pipeline ordering (007 §FR-014) is the layer-precedence rule used inside `_run_pipeline`; per-layer detection persistence (007 §FR-015) is the schema FR-023 writes into on pipeline error.

### GDPR article mapping (Phase D fix/003-compliance, 2026-05-02)

Authoritative project-wide GDPR mapping is in `docs/compliance-mapping.md`. The 003-specific FR-to-article mappings are:

| FR / asset | GDPR article | Mapping |
|----|----|----|
| FR-006, FR-007, FR-024 (provider dispatch) | Art. 28 | Sub-processor relationship; operator-mediated DPA / SCC |
| FR-011 (routing_log) | Art. 28(3)(h), Art. 30 | Processor disclosure record + records of processing |
| FR-006 (litellm cross-border) | Art. 44 | International transfer (operator's SCC requirement) |
| FR-014, FR-028 (budget) | Art. 5(1)(c) | Data minimization in usage_log columns |
| FR-007, FR-024 (key residency) | Art. 32(1)(a) | Pseudonymisation of access credentials |
| FR-022, FR-027 (advisory lock + single loop) | Art. 5(1)(f), Art. 32(1)(b) | Integrity of processing |
| FR-021 (no halt on single failure) | Art. 32(1)(c) | Availability of processing systems |

## Compliance / Privacy (Phase D fix/003-compliance, 2026-05-02)

This section documents 003's privacy posture around provider dispatch, routing logs, and budget accounting. Authoritative project-wide compliance mapping is in `docs/compliance-mapping.md`; per-table retention in `docs/retention.md`.

### Processor relationships (Art. 28)

`routing_log` is the canonical processor-disclosure record for SACP's orchestrator role: every turn records which provider received which content. For an operator acting as data controller, this is the Art. 28(3)(h) audit-trail evidence for the sub-processor relationship between the operator and each AI provider.

The processor relationship is mediated through `participants.invited_by` (the sponsor that supplied the third-party API key) and `routing_log.provider` / `routing_log.model` (the dispatch target). FR-011 + FR-007 + 001 §FR-008 (append-only repository invariant) together form the Art. 28(3)(h) record.

**Operator obligation**: operators MUST document Art. 28 contracts (DPAs / standard contractual clauses) with each AI provider they enable for participants — Anthropic, OpenAI, Google, Groq, Ollama (self-hosted), litellm-supported others. SACP does not enumerate these contracts; the orchestrator only records the dispatch.

### Cross-border transfer (Art. 44)

LiteLLM dispatch carries personal data (message content, system prompts, participant display names embedded in content) to provider endpoints. For Phase 1, the cloud provider matrix is:

| Provider | Default region | Art. 44 mechanism |
|----|----|----|
| Anthropic | US | Operator's SCC / DPA with Anthropic |
| OpenAI | US | Operator's SCC / DPA with OpenAI |
| Google (Vertex AI / Gemini) | US (multi-region available) | Operator's SCC / DPA with Google Cloud |
| Groq | US | Operator's SCC / DPA with Groq |
| Ollama | Operator-controlled (self-hosted) | No transfer (data stays in operator's region) |

For operators serving EU data subjects, every cloud-provider dispatch is a third-country transfer under Art. 44 and requires an appropriate transfer mechanism (typically Standard Contractual Clauses). Ollama on operator-controlled infrastructure is the only Phase 1 option that avoids cross-border transfer entirely.

**Operator guidance**: if participants are EU residents, you (the operator) are the data controller; AI providers are processors. Document the Art. 28 contract with each enabled provider before opening the deployment to those participants. SACP's role is to faithfully record what was dispatched (`routing_log`) — not to enforce per-region routing constraints. Per-region routing policy is a Phase 3 feature; trigger: any deployment with a documented data-residency requirement that cannot be met by switching to Ollama.

### Budget data as minimization (Art. 5(1)(c))

Budget enforcement (FR-014, FR-028) persists only the cost data necessary to enforce the per-participant ceiling: `usage_log.cost_usd`, `usage_log.input_tokens`, `usage_log.output_tokens`, dispatch timestamp. No prompt content or response content is duplicated into `usage_log`. This is data minimization at the budget-tracking boundary — `messages` holds the content; `usage_log` holds only the accounting columns.

### Retention

Per `docs/retention.md`:
- `routing_log` retention: indefinite by default; configurable via reserved env var `SACP_ROUTING_LOG_RETENTION_DAYS`. Purge job NOT YET WIRED in Phase 1; FK cascade from `sessions` covers session-scoped erasure (Art. 17).
- `usage_log` retention: indefinite by default; configurable via reserved env var `SACP_USAGE_LOG_RETENTION_DAYS`. Purge job NOT YET WIRED in Phase 1; FK cascade from `participants` covers participant-scoped erasure.

Both env vars are documented in `docs/env-vars.md` as reserved. The Phase 3 trigger for wiring the purge jobs is "any deployment with a regulatory retention cap below indefinite" (e.g., HIPAA-aligned 7-year cap, sector-specific retention limits). Until then, operators relying on session-deletion cascade for retention must be aware that `routing_log` and `usage_log` rows survive only as long as the parent `sessions` / `participants` row.

### Cross-references

- `docs/compliance-mapping.md` — project-wide GDPR mapping (Art. 28 + Art. 44 rows authoritative)
- `docs/retention.md` — per-table retention (`routing_log`, `usage_log` entries)
- `docs/env-vars.md` — `SACP_ROUTING_LOG_RETENTION_DAYS`, `SACP_USAGE_LOG_RETENTION_DAYS` reserved-var entries
- 001 §FR-008 — append-only repository invariant (Art. 28(3)(h) audit-trail integrity)
- 001 §FR-019 — admin_audit_log retention pattern (Art. 17(3)(b) carve-out)
- 002 Compliance / Privacy section — auth-surface privacy posture (sister)

## Operations (Phase E fix/003-ops-reliability, 2026-05-02)

This section documents 003's operator-facing decisions for turn-loop operation. Operator playbook lives in `docs/operational-runbook.md`; this section covers the architectural contracts and Phase 3 deferrals.

### Tunable env vars (operator decision points)

The 003-relevant operator-tunable env vars:

| Variable | Purpose | Default | FR |
|---|---|---|---|
| `SACP_TURN_TIMEOUT_DEFAULT` | Per-turn dispatch timeout | 180 s | FR-019 |
| `SACP_CONTEXT_MAX_TURNS` | History truncation limit | 20 | FR-005 |
| `SACP_BREAKER_THRESHOLD` | Consecutive failures before circuit-breaker trips | 3 | FR-015 |
| `SACP_COMPOUND_RETRY_WARN_FACTOR` | Multiple of turn timeout that triggers warn (proposed reserved) | 2× | FR-031 |
| `SACP_COMPOUND_RETRY_TOTAL_MAX_SECONDS` | Hard cap on cumulative retry elapsed | 600 s | FR-031 |
| `SACP_ADVISORY_LOCK_WAIT_ALERT_MS` | Operator-observed alert threshold (advisory; not enforced) | 100 ms | FR-032 |

Cross-ref `docs/env-vars.md` for the canonical catalog.

### Loop lifecycle (FR-021, FR-027)

**SIGTERM behavior** — uvicorn's graceful-shutdown signal cancels the loop coroutine. In-flight turns are abandoned (transactional rollback; no partial state). RPO=0 for committed turns; see runbook §10.4.

**Startup recovery** — no per-turn resumption. The next dispatch uses persisted state (`messages`, `routing_log`, `usage_log`) as the source of truth; an interrupted turn's coroutine state is gone. Sessions with `status='active'` resume their loop on the next eligible participant.

**Single-loop-per-session enforcement (FR-027)** — Phase 1 enforces this implicitly via single-deployment topology (one orchestrator container per database). The advisory lock (FR-022) provides defense-in-depth — a hypothetical second writer would race on the lock but also produce duplicate dispatches. Phase 3 multi-instance trigger: any deployment requiring HA orchestrator pods. Implementation surface: explicit single-loop coordination via a session lease (lease-on-claim, heartbeat-on-tick, expire-on-stale).

### Operator override (kill switch)

Phase 1 operator overrides for a stuck loop:

1. Pause the session via facilitator API or `UPDATE sessions SET status='paused' WHERE id=...`
2. Process-level: restart the orchestrator (RTO ~5–10 s; abandons in-flight turns across ALL sessions)

Phase 3 trigger: any deployment where individual sessions can wedge without affecting others. Implementation surface: a `/tools/admin/kill_loop?session_id=...` admin endpoint that cancels the session's loop task without process-restart.

### Cadence-preset runtime switching

Cadence preset (`SACP_CADENCE_PRESET`) is read at orchestrator startup; per-session override via the cadence config UI takes effect on the next turn (snapshot semantics per FR-025). Switching from `sprint` to `cruise` mid-session is supported; the orchestrator does not enforce who can change cadence — the facilitator role gate applies at the API layer (002 §FR-010).

### Deploy-time env-var validation

Per 012 US2 V16 contract (`scripts/check_env_vars.py`), all `SACP_*` env vars validate at startup. 003-relevant range checks:

- `SACP_TURN_TIMEOUT_DEFAULT` MUST be > 0
- `SACP_CONTEXT_MAX_TURNS` MUST be ≥ `MVC_FLOOR_TURNS` (currently 3) per FR-029
- `SACP_BREAKER_THRESHOLD` MUST be ≥ 1
- `SACP_COMPOUND_RETRY_TOTAL_MAX_SECONDS` MUST be ≥ `SACP_TURN_TIMEOUT_DEFAULT`

The validator prevents deploys with nonsensical values (e.g., timeout 0 = instant skip on every turn).

## Reliability (Phase E fix/003-ops-reliability, 2026-05-02)

This section documents 003's failure-mode behavior. Operator-facing recovery procedures live in `docs/operational-runbook.md`; this section covers the contracts.

### Provider partial-outage behavior

Per FR-021, single-provider failure does NOT halt the session:

1. Provider returns 5xx / connection error → asyncio.TimeoutError or LiteLLM exception
2. Turn coroutine catches per FR-021, logs `routing_log.reason='dispatch_error'`, advances to next participant
3. Failed participant's circuit breaker (FR-015) increments; auto-pause after `SACP_BREAKER_THRESHOLD` consecutive failures (default 3)
4. Other participants on other providers continue normally — loop never halts

Operator playbook: runbook §6.1.

### Multi-provider failover

Phase 1 does NOT support automatic provider failover for a single participant. Each participant has ONE configured provider; if that provider fails, the participant's circuit breaker trips. Manual recovery: operator updates `participants.provider` + `participants.api_key_encrypted` to a new provider, then resets the breaker.

Phase 3 trigger: any deployment with documented per-participant resilience requirements. Implementation surface: per-participant `provider_chain` field (ordered list); on circuit-breaker trip, advance to next provider in chain; track which provider in chain is active in `routing_log`.

### Retry-storm prevention

Bounded retries per FR-016 (≤3 quality retries) × FR-019 (per-attempt timeout) × FR-020 (rate-limit retries respecting Retry-After). FR-031 caps total elapsed at `SACP_COMPOUND_RETRY_TOTAL_MAX_SECONDS` (default 600 s). Cross-session retry-storm coordination is NOT supported — each session retries independently.

Phase 3 trigger: any deployment observing rate-limit cascades when ≥10 sessions hit the same upstream provider simultaneously. Implementation surface: a global rate-limit observer that reads `routing_log` aggregate `dispatch_ms` growth and feeds a back-pressure signal into per-session retry decisions.

### Session-state corruption recovery

Mid-persist failure (DB connection drops between message INSERT and routing_log INSERT):

- The surrounding `async with conn.transaction()` rolls back both writes; no partial state
- Next turn re-evaluates from persisted state; the failed dispatch produces NO row (treated as if the turn never fired from the data-model view)
- Operator-side observation: a small gap in `routing_log` turn numbers per session (the failed turn skipped without writing)

Phase 3 trigger: any deployment where gap detection in `routing_log` is required for compliance auditing. Implementation surface: a sentinel-row pattern (write `routing_log` first with `reason='dispatch_started'`, update on success or failure) that closes the gap-detection blind spot.

### Graceful degradation

**Under DB latency spike** (persist takes 30 s instead of 100 ms):

- Per-turn timeout (FR-019, default 180 s) provides headroom; persist completes within budget
- `routing_log.persist_ms` percentiles spike — operator-observable signal
- If persist exceeds turn timeout, dispatch context cancellation aborts; treated as `dispatch_error`

**Under provider latency spike**:

- Per-turn timeout (FR-019) caps per-attempt latency
- Quality retry × rate-limit retry × per-attempt timeout = compound elapsed; FR-031 caps total at 600 s default
- Circuit breaker trips after sustained failures per FR-015

### RTO / RPO

- **RPO**: zero for committed turns. In-flight turns abandoned on crash; no partial state.
- **RTO**: orchestrator restart-to-first-turn ~5–10 seconds (boot sequence in runbook §1.4). DB failover RTO is operator's HA stack responsibility; SACP's pool reconnects on next request after primary accepts connections.

### Session quarantine

Phase 1 does NOT support per-session quarantine. A session repeatedly hitting `pipeline_error` (007 §FR-013) cannot be isolated without halting the whole orchestrator. Operator workaround: pause the session manually.

Phase 3 trigger: any deployment where one bad session can degrade other sessions' latency. Implementation surface: per-session resource caps + session-level fault-isolation (separate task pool per session).

### Chaos-testing surface

Phase 1 has no fault-injection harness for asyncpg connection drops, advisory-lock unavailability, or FK violations. Phase 3 trigger: when reliability claims (RTO / RPO / FR-021 invariants) require automated verification. Implementation surface: a separate chaos-test harness (`tests/chaos/`) using LiteLLM's mock-provider hooks + asyncpg connection-mock injection. Cross-cutting with 005 + 006 reliability.

### Cross-references

- `docs/operational-runbook.md` §6 (provider degradation), §11 (turn-loop ops)
- 003 §FR-015 — circuit breaker
- 003 §FR-019 — per-attempt timeout
- 003 §FR-021 — loop never halts (canonical reliability invariant)
- 003 §FR-022, §FR-027 — advisory lock + single-loop-per-session
- 003 §FR-031, §FR-032 — compound-retry cap + advisory-lock instrumentation
- 001 Operations section — DB-level ops (sister)
- 005 Reliability section — fallback-cascade exhaustion (sister; once landed)
- 006 Reliability section — connection drop, partial DB outage (sister; once landed)

## Audit closeout (2026-04-29)

The security-requirements quality audit (`checklists/security.md`) raised 40 findings; resolution split:

**Code changes**: NONE. The audit found one apparent drift (CHK015 `delegate_low` doesn't actually delegate) which is resolved as a Phase 1 scope decision via FR-026 rather than a code change — Phase 1 records the routing decision but defers actual cost-aware delegation to Phase 3. All other findings are either spec-level gaps or accepted residual.

**Spec amendments (this commit)**: CHK001 / CHK002 / CHK024 (FR-024 plaintext memory residency + accepted residual + re-eval trigger), CHK003 (Edge Case + threat-model row codifying ScrubFilter coverage of dispatch tracebacks), CHK006 / CHK023 (FR-023 restates 007 §FR-013 fail-closed), CHK007 / CHK022 (FR-022 promotes advisory lock from Clarification to FR; CHK022 confirmed already-tested by tests/test_scrubber.py), CHK010 / CHK011 / CHK028 (FR-028 codifies post-call accounting + trailing-window semantics), CHK013 / CHK025 (FR-025 snapshot-at-route-time), CHK015 / CHK026 (FR-026 delegate_low Phase 1 records-but-doesn't-delegate; Phase 3 trigger), CHK026 / CHK027 (FR-027 single-loop-per-session deployment requirement), CHK029 (Edge Case adversarial+budget interaction), CHK030 / CHK029 (FR-029 MVC floor + Edge Case), CHK032 (Threat-model traceability table), CHK038 (Edge Case key-per-retry confirmed in spec), CHK040 (Edge Case timeout-vs-007-FR-013 distinction documented).

**Closed as cross-reference / accepted residual / out-of-scope**: CHK004 (provider-response trust — handled by 007 pipeline running inside `_validate_and_persist`), CHK005 (pipeline order — 007 §FR-014 is authoritative), CHK008 (advisory-lock timeout — accepted residual; bounded in practice by short transactions), CHK009 (concurrent inject + loop iteration in multi-machine deployment — Phase 3 concern; FR-027 single-loop), CHK012 (post-call cost mismatch via LiteLLM — accepted; LiteLLM is source of truth), CHK014 (routing log audit-grade — already FR-011 + 001 §FR-008 append-only), CHK016 (key-discard wording — FR-024 settles), CHK017 (consecutive-failure threshold config — env var `SACP_BREAKER_THRESHOLD` default 3), CHK018 (turn timeout vs cadence — FR-019 + 004 §FR-009 cadence ceilings ensure timeout < cadence cycle), CHK019 (retry skip + audit log — FR-016 retry counter + FR-011 routing log), CHK020 (FR-021 vs 007 §FR-013 — both consistent: session continues, fail-closed turn is a logged skip), CHK021 (review_gate cross-ref — FR-018 + 007 §FR-016 + 008 §FR-008), CHK022 (API-key log scrubbing already tested via tests/test_scrubber.py), CHK023 (SC-009 testable via fault injection — out-of-scope automated harness for Phase 1), CHK024 (no SC for budget skip precision — FR-014 + FR-028 wording sufficient), CHK025 (advisory-lock timeout recovery — accepted residual; healthcheck on Postgres detects deadlocks), CHK027 (provider returning malicious responses repeatedly — handled by 007 pipeline + circuit breaker), CHK031 (cancelled-task connection cleanup — LiteLLM's `acompletion` honors asyncio cancellation), CHK033 (loop iteration overhead — observational only; FR-019 timeout dominates), CHK034 (per-event observability — FR-011 routing log covers all skip categories), CHK035 (tiktoken vs LiteLLM token estimation — accepted; LiteLLM is the canonical source), CHK036 (relevance-based rotation security risk — Phase 3 concern), CHK037 (advisory-lock dependency on Postgres — out-of-scope deployment requirement), CHK039 ("moment of provider dispatch" precision — defined as the LiteLLM `acompletion` call site), CHK040 (cancellation-vs-silent-drop semantic distinction confirmed in Edge Case).

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): Topologies 1–6 only (orchestrator-driven). The turn loop engine assumes the orchestrator drives turn selection, context assembly, and provider dispatch. Topology 7 (MCP-to-MCP, client-side AI execution) requires peer routing — no orchestrator turn loop. Phase 2+ will implement peer-to-peer coordination for topology 7.

**Use cases** (per constitution §1): Serves all seven equally within orchestrator-driven topologies (1–6). Routing modes (always, review_gate, delegate_low, etc.) and budget enforcement enable the flexible participation patterns needed for consulting, asymmetric expertise, and zero-trust scenarios.
