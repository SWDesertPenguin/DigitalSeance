# Performance Requirements Quality Checklist: Summarization Checkpoints

**Purpose**: Validate the quality, clarity, and completeness of performance requirements in the Summarization Checkpoints spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Audited**: 2026-04-29
**Feature**: [spec.md](../spec.md)

**Audit summary**: 4 items pass cleanly, 24 have findings. The spec already accepts a perf-residual gap (CHK031/CHK032 in security audit closeout: "perf SLA / observability — accepted residual"), so this checklist mostly upgrades that residual to a structured punch-list. The summarizer is fire-and-forget per FR-010 but the recursive sanitize+exfil filter added by PR #157 (FR-011, every string leaf of the JSON tree) introduces non-trivial CPU work that has never been benchmarked.

## Latency Budgets

- [x] CHK001 Is the end-to-end summarization latency budget specified (LLM round-trip + JSON parse + sanitize + DB write)?
  [GAP]. No target. Cheapest-model selection (FR-002 / FR-007) means latency varies wildly: Haiku ~1-2s, gpt-4o-mini ~2-4s, Ollama local ~10-60s. Without a budget, "summarization runs out-of-band" hides slow-path latency.

- [x] CHK002 Is the LLM-call latency bounded (timeout, retry-with-backoff, cancellation on session shutdown)?
  [PARTIAL]. FR-004 specifies retry-up-to-3 on invalid JSON but not on transport-level timeout. FR-008 specifies "fall back to next cheapest model if primary fails after retries" — what counts as "fails" (timeout vs. malformed JSON vs. provider 5xx) is unspecified.

- [x] CHK003 Is the fire-and-forget contract (FR-010 `asyncio.create_task`) latency-bounded for shutdown?
  [PARTIAL]. CHK010 of security audit closed as "awaited inside the loop; not fire-and-forget at session-shutdown granularity" — but the spec wording in FR-010 still says "asyncio.create_task fire-and-forget." Drift between spec and shipped semantics, with perf implications (orphan tasks vs. graceful-shutdown wait time).

- [x] CHK004 Is the recursive sanitize+exfil-filter cost (FR-011) per-summary bounded?
  [GAP]. PR #157 added recursive sanitization on every string leaf. A summary with 50 key_positions × 200-char strings = 50 × NFKC normalize + regex-match passes. CPU cost not quantified.

- [x] CHK005 Is the JSON parsing cost (FR-003 / FR-004) bounded for adversarial inputs (deeply nested objects, very long strings)?
  [GAP]. Standard `json.loads` is fast but unbounded.

## Throughput / Concurrency

- [x] CHK006 Are concurrent summarization tasks across multiple sessions bounded?
  [GAP]. No upper-bound on simultaneous in-flight summarizations. Each one holds an LLM-call coroutine; `httpx.AsyncClient` connection pool is the implicit bound.

- [x] CHK007 Is the cheapest-model selection cost (FR-007 sort across active participants) bounded?
  [GAP]. O(n) over participants per checkpoint; bounded by participant count which is small. Worth declaring as bounded.

- [x] CHK008 Are concurrent summarizations on the same session deduplicated by the SQL race guard (FR-013), and is the latency cost specified?
  [PARTIAL]. FR-013 specifies the deduplication mechanism (`UPDATE … WHERE last_summary_turn < $1` no-ops the loser) but the perf characteristic — the loser still ran the LLM call, paid for it, and only failed at persistence — is not surfaced. Wasted-work upper bound is unspecified.

## Memory & Resource Footprint

- [x] CHK009 Is the in-memory size of the accumulated turns being summarized bounded?
  [GAP]. `_collect_turns_for_summary` reads `WHERE turn_number > last_summary_turn` and can return arbitrarily many rows. With long summarization intervals or recovery from a downed worker, this could be 1000+ rows.

- [x] CHK010 Is the LiteLLM context-window usage bounded for the summarization prompt?
  [ACCEPTED]. CHK026 closed in security audit: "LiteLLM truncates per-model context window." Perf implication of the truncation (silent quality degradation) is not surfaced.

- [x] CHK011 Is the size of the persisted summary row bounded?
  [PARTIAL]. FR-014 says "no truncation of raw response; downstream context truncation discards silently." Summary row could be 100KB+. `messages` table can hold it but query latency on bulk-fetch is unspecified.

## Cold-Start / Warmup

- [x] CHK012 Is there a cold-start latency target (first summarization in a session vs. steady state)?
  [GAP]. LLM provider connection establishment, first HTTPS handshake, first prompt evaluation all amortize over time. No target distinguishes them.

- [x] CHK013 Is the LiteLLM client lazy-loaded or eager?
  [GAP]. Implementation detail unspecified.

## Degradation Under Load

- [x] CHK014 Is the system's behavior specified when checkpoints can't keep up (turn N+50 happens before checkpoint at N completes)?
  [PARTIAL]. FR-013's race guard prevents double-checkpointing but doesn't address sustained backlog. With long summarizer latency + sprint cadence, a session could accumulate multiple "missed" checkpoint windows.

- [x] CHK015 Is the per-session checkpoint backpressure specified (refuse to start checkpoint N+1 if N is still in flight)?
  [PARTIAL]. The race guard is at persistence; nothing prevents a second `run_checkpoint` task from starting. Spec should pin "at most one in-flight checkpoint per session."

- [x] CHK016 Are SLOs specified for percentage of checkpoints completing within latency budget (P50, P95, P99)?
  [GAP]. CHK031 of security audit accepts this as residual. Worth documenting as a Phase 3 trigger.

- [x] CHK017 Is fallback-cascade depth bounded (FR-008 next cheapest on fail; can it cascade through every participant?)?
  [GAP]. With 5 participants all failing, the cascade does 5 LLM calls × 3 retries = 15 calls before giving up. Wall-clock can be minutes. Cap unspecified.

## Cost Performance

- [x] CHK018 Is the per-checkpoint dollar-cost target specified?
  [GAP]. Cheapest-model is the design choice but no per-checkpoint cost ceiling. A summarizer model with $0.50/M input × 100K input tokens = $0.05 per checkpoint — bounded but unsurfaced.

- [x] CHK019 Are over-budget participants excluded from summarizer selection (cross-ref 003 budget enforcement)?
  [GAP]. Cheapest active participant could be over their budget. FR-007 doesn't specify whether budget gating applies. With over-budget participant selected, the LLM call may fail at the gate, triggering FR-008 fallback — wasted attempt.

- [x] CHK020 Is the asymmetry from FR-012 (cheapest participant pays for the whole session's summaries) latency-relevant or only cost-relevant?
  [PARTIAL]. FR-012 calls out the cost asymmetry but not the rate-limit asymmetry — the cheapest participant's per-minute LLM quota gets consumed by all summarizations, which can pause their normal turn dispatch.

## Measurement & Instrumentation

- [x] CHK021 Is per-stage timing instrumentation required (LLM call vs. JSON parse vs. sanitize vs. DB write)?
  [GAP]. CHK032 of security audit closes as "perf SLA / observability — accepted residual." Same shape as CHK032 here; worth elevating in Phase 3.

- [x] CHK022 Is a benchmark fixture required (so the FR-011 recursive-sanitize cost is testable against future regressions)?
  [GAP].

- [x] CHK023 Is structured logging of summarization attempts (which model, latency, retries, fallback depth, output size) required?
  [GAP]. `routing_log` covers normal turn dispatch; summarization-specific instrumentation is incidental.

- [x] CHK024 Are perf-regression CI gates required?
  [GAP].

## I/O & Storage

- [x] CHK025 Is the `_collect_turns_for_summary` query indexed on `(session_id, turn_number)`?
  [GAP]. Spec doesn't pin the supporting index. Code uses an existing index but spec is silent on the dependency.

- [x] CHK026 Is the summary-row INSERT cost bounded (foreign-key check on speaker_id, message persistence overhead)?
  [GAP]. Standard message INSERT but with FR-005 facilitator-id attribution forcing an FK lookup.

- [x] CHK027 Are bulk-fetch queries (e.g. `get_summaries` for the 011 §US9 Summary panel) latency-bounded?
  [GAP]. Phase 2 added the Summary panel; reading multiple summaries (Round10 #2: earlier-checkpoints refetch) for browsing is an unspecified perf path.

## Trade-offs & Assumptions

- [x] CHK028 Is the trade-off between checkpoint frequency (more = better recovery, more cost / latency) and latency / cost documented?
  [GAP]. Default 50 turns is named in FR-001 but no rationale or trade-off curve.

- [x] CHK029 Is the assumption "cheapest model is fast enough" challenged when the cheapest model is local Ollama (potentially 10-60s)?
  [PARTIAL]. FR-007 prefers paid models over free/local "to prevent summarization from always routing to slow local models" — explicit awareness — but the perf consequence of a cheapest-paid Ollama-equivalent (slow + cheap) is unspecified.

- [x] CHK030 Are shutdown semantics for in-flight summarizations specified (await vs. cancel vs. abandon)?
  [PARTIAL]. CHK010 of security audit accepts the gap. Affects deploy-time perf (graceful drain duration).

## Notes

- 30 items audited. Spec already accepted "perf SLA / observability" as residual in security audit (CHK031 / CHK032); this checklist makes that acceptance specific.
- Highest-leverage findings to convert into spec amendments:
  - CHK001 (specify end-to-end latency budget — currently undocumented; cheapest-model variance is wide).
  - CHK002 (define what "fails" means for FR-008 fallback trigger — timeout vs. JSON-invalid vs. provider error are not equivalent).
  - CHK004 (cost of FR-011 recursive sanitize — added by PR #157 without benchmark).
  - CHK015 (per-session checkpoint backpressure — pin "at most one in-flight per session").
  - CHK017 (fallback-cascade depth bound — unbounded today, can wall-clock for minutes).
- Lower-priority but useful:
  - CHK009 / CHK011 (input + output size bounds — both unbounded today).
  - CHK020 (cost vs. rate-limit asymmetry on the cheapest participant).
  - CHK023 (summarization-specific structured logging — pairs with 004 CHK024).
- Sister 004 perf checklist covers the inference-on-hot-path side; this one covers the LLM-call slow path. Both share the "no benchmark, no enforcement, no measurement harness" pattern (cross-ref 007 §CHK013).
- Cross-ref 011 §US9 (Summary panel) for the read-side perf path which neither this nor 004 covers.
