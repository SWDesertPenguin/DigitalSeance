# Performance Requirements Quality Checklist: Turn Loop Engine

**Purpose**: Validate the quality, clarity, and completeness of performance requirements in the Turn Loop Engine spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Audited**: 2026-04-29
**Feature**: [spec.md](../spec.md)

**Audit summary**: 6 items pass cleanly, 30 have findings. The turn loop is the critical-path runtime — every user-facing latency adds here. The spec pins ONE numeric target (FR-019 180s turn timeout) and one secondary cap (`SACP_CONTEXT_MAX_TURNS=20`), but no per-stage budgets, no SLOs, no measurement methodology, and no degradation-under-load contract.

## Latency Budgets

- [x] CHK001 Is the per-turn end-to-end latency budget specified, decomposed into stages (interrupt processing → routing → context assembly → dispatch → persist → next-turn delay)?
  [GAP]. Only the turn TIMEOUT (180s, FR-019) exists as a numeric target. That's a ceiling, not a budget. Operators have no idea what "normal" looks like.

- [x] CHK002 Is the context-assembly latency (FR-003 5-priority allocation) bounded?
  [GAP]. `_fill_history` reads `SACP_CONTEXT_MAX_TURNS` rows + summary + interjection + proposals — variable cost depending on session length. Unspecified ceiling.

- [x] CHK003 Is the LLM-dispatch latency budget separate from total turn latency?
  [PARTIAL]. FR-019 wraps both; spec doesn't differentiate "context assembly took 200ms vs LLM took 2s" for diagnostic purposes.

- [x] CHK004 Is the persist-step latency (FR-010 message append + advisory lock) bounded?
  [GAP]. FR-022 advisory lock can block indefinitely under contention; no spec ceiling.

- [x] CHK005 Is the routing-decision computation latency (FR-011 8-mode evaluation) bounded?
  [GAP]. O(participants × modes) but unspecified.

- [x] CHK006 Is the cadence-enforced inter-turn delay (cross-ref 004 FR-009) included or excluded from the per-turn budget?
  [GAP]. Cadence delay is dead time between turns; spec doesn't pin whether observability conventions count it.

## Timeouts & Bounds

- [x] CHK007 Is the FR-019 180s timeout decomposed (network connect / first-byte / total-completion / read)?
  [GAP]. `asyncio.wait_for` wraps the whole call — single ceiling. Slow-first-byte vs. slow-stream are indistinguishable.

- [x] CHK008 Is the timeout's interaction with streaming (FR-008) specified — does the 180s reset on each token, or wall-clock?
  [GAP]. Implementation is wall-clock per current `wait_for` shape; spec is silent.

- [x] CHK009 Is the FR-020 retry-with-backoff bound on TOTAL elapsed time, not just retry count?
  [GAP]. 3 retries with exponential backoff respecting Retry-After can wall-clock for minutes; no aggregate cap.

- [x] CHK010 Is the FR-016 quality-retry path (3 retries on empty/duplicate/repetitive) latency-bounded as a multiplier on FR-019?
  [GAP]. 3×180s = 9 minutes worst case. No spec.

- [x] CHK011 Is the advisory-lock contention timeout (FR-022) specified?
  [DRIFT]. FR-022 explicitly says "no application-level timeout; lock contention blocks indefinitely until the holding transaction commits or aborts." Indefinite blocking is a perf characteristic; the spec's framing accepts it but doesn't surface the implication.

## Throughput / Concurrency

- [x] CHK012 Is the maximum concurrent-session count bounded?
  [GAP]. Each session has its own loop coroutine. No process-wide cap. Memory + connection-pool exhaustion is the implicit bound.

- [x] CHK013 Is the per-process turn-rate ceiling specified (sum across all sessions)?
  [GAP]. Cross-session contention on shared state (DB connection pool, LiteLLM client, embedding executor) unspecified.

- [x] CHK014 Is the FR-001 single-loop-per-session contract paired with a thread/coroutine limit?
  [GAP]. One coroutine per session, but no spec on whether 100 sessions × 1 coroutine each is healthy.

- [x] CHK015 Is the LiteLLM HTTP connection pool size specified?
  [GAP]. Default httpx pool (100 connections); spec is silent.

- [x] CHK016 Is the embedding executor (cross-ref 004) shared across sessions, and is its queue depth bounded?
  [GAP]. Default ThreadPoolExecutor; no application bound.

## Cold-Start

- [x] CHK017 Is the cold-start latency (first turn after process restart) specified?
  [GAP]. First LLM call establishes a fresh httpx connection per provider; first embedding call loads the model (cross-ref 004). Both add to first-turn latency.

- [x] CHK018 Is the lazy-load strategy for LiteLLM model registry specified?
  [GAP]. Implementation detail unspecified.

## Memory & Resource Footprint

- [x] CHK019 Is the in-memory size of an in-flight turn bounded (context payload + response stream + key plaintext)?
  [GAP]. Context payload is the dominant component — bounded by FR-004 (token budget) but no byte-count translation.

- [x] CHK020 Is the streaming-response accumulator (FR-008) memory-bounded?
  [GAP]. Response can grow unbounded until the model stops; no upper cap.

- [x] CHK021 Are interrupt-queue size limits specified (FR-013)?
  [GAP]. Pending interrupts could accumulate indefinitely if no AI turn fires.

## Degradation Under Load

- [x] CHK022 Is the system's behavior specified when context assembly latency starts approaching the turn timeout?
  [GAP]. With huge sessions or cold caches, context assembly could eat half the budget; spec is silent on degradation.

- [x] CHK023 Is the FR-014 budget-check latency bounded (cost lookup may hit DB)?
  [GAP]. Per-turn cost-aggregation query unspecified.

- [x] CHK024 Are SLOs specified (P50, P95, P99) for total turn latency?
  [GAP]. None.

- [x] CHK025 Is the back-pressure path specified for routing-log INSERT throughput vs. turn rate?
  [GAP]. `routing_log` INSERT every turn; sustained sprint cadence × many sessions can saturate.

- [x] CHK026 Is the convergence-log write contention (cross-ref 004) accounted for in the persist budget?
  [GAP]. Two writes per AI turn (message + convergence_log); coupling cost unspecified.

## Cost-of-Quality Trade-offs

- [x] CHK027 Is the trade-off between FR-016 retry depth (3) and worst-case turn duration documented?
  [GAP]. 3 retries × 180s + backoff is the known worst case; spec doesn't surface the ceiling implication.

- [x] CHK028 Is the FR-019 default 180s timeout justified for all model classes (cloud fast vs. local CPU slow)?
  [PARTIAL]. Clarification log: "180s default chosen because 60s proved insufficient for local models like llama3.2:3b on CPU." Justification recorded; per-model tuning unsurfaced as a tunable in FR-019.

- [x] CHK029 Is `SACP_CONTEXT_MAX_TURNS` (default 20) trade-off (latency vs. context coherence) documented as a tuning knob?
  [PARTIAL]. Clarification log mentions the secondary cap; FR doesn't surface as a perf knob with example values for different hardware.

## Measurement & Instrumentation

- [x] CHK030 Is per-stage timing instrumentation required (routing / assembly / dispatch / persist)?
  [GAP]. `routing_log` records action + reason but not stage latencies.

- [x] CHK031 Is per-turn structured logging required for diagnostic replay?
  [GAP]. Some logs exist; spec doesn't pin a contract.

- [x] CHK032 Is a benchmark fixture required (so SC-001 / FR-019 are testable against future regressions)?
  [GAP]. Cross-ref 004 CHK022 — same shape: no benchmark, no enforcement.

- [x] CHK033 Are perf-regression CI gates required?
  [GAP].

- [x] CHK034 Is request-id / turn-id correlation across logs (routing_log + usage_log + convergence_log + admin_audit_log) required for diagnosis?
  [GAP]. Each table has its own keys; no cross-table correlation contract.

## Failure Path Performance

- [x] CHK035 Is the FR-021 "loop never halts" path latency-bounded (skip + log + advance)?
  [GAP]. Skip path is the fast path but no ceiling.

- [x] CHK036 Is the FR-023 fail-closed (security_events row + skip) latency-bounded?
  [GAP]. Fail-closed adds a write; cross-ref 007 FR-015.

## Notes

- 36 items audited. The turn loop is critical-path; the lack of perf SLOs makes regression detection essentially impossible without manual investigation.
- Highest-leverage findings to convert into spec amendments:
  - CHK001 (decompose end-to-end into stage budgets — single most useful change for catching future regressions).
  - CHK009 / CHK010 / CHK027 (compound-retry total-time caps — 9-minute worst case is invisible to the spec today).
  - CHK011 (advisory-lock contention is documented as "indefinite" — should be paired with a metric showing how often it actually blocks > N seconds).
  - CHK024 (SLO percentiles — operationally critical for any production deployment).
  - CHK030 / CHK032 / CHK033 (instrumentation + benchmark fixture + CI gates — cross-ref 004 CHK022 same shape).
- Lower-priority but useful:
  - CHK012 / CHK013 / CHK014 (process-wide concurrency caps — relevant for multi-instance deploy if 006 CHK011 ever ships).
  - CHK034 (cross-log turn-id correlation — pairs with 006 CHK016 observability work).
- Sister checklists: `requirements.md`, `security.md`, `testability.md` already on main. Cross-refs to 004 (embedding latency in `process_turn` is part of this turn's clock) and 005 (summarization is fire-and-forget but shares the executor pool).
