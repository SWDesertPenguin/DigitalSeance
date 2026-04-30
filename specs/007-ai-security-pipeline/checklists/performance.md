# Performance Requirements Quality Checklist: AI Security Pipeline

**Purpose**: Validate the quality, clarity, and completeness of performance requirements in the AI Security Pipeline spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Audited**: 2026-04-29
**Feature**: [spec.md](../spec.md)

**Audit summary**: 4 items pass cleanly, 28 have findings. The pipeline runs synchronously on the turn-loop hot path AFTER LLM dispatch but BEFORE persistence (FR-014 layer order), so its latency is a pure tax on every turn. The spec's own assumption ("<50ms for the full pipeline excluding LLM-as-judge") is unenforced — security audit CHK013 already flagged "no benchmark, no enforcement, no measurement harness."

## Latency Budgets

- [x] CHK001 Is the assumption "<50ms for the full pipeline" decomposed per layer (sanitizer / spotlighting / output_validator / exfiltration / jailbreak / prompt_protector)?
  [GAP]. Aggregate target only. Cross-ref security audit CHK013 — same shape, same gap.

- [x] CHK002 Is the sanitizer latency (FR-001 8 pattern groups + NFKC + homoglyph fold) bounded per-message?
  [GAP]. Regex passes are O(content) but spec is silent. With long AI responses (no upper bound on response length per 003), scanning cost grows.

- [x] CHK003 Is the spotlighting latency (FR-002 SHA-256 prefix + per-word marker) bounded?
  [GAP]. Per-word work is O(words); for a 1000-word response, that's 1000 marker insertions. Unspecified.

- [x] CHK004 Is the output_validator latency (FR-004 injection-pattern checks) bounded?
  [GAP].

- [x] CHK005 Is the exfiltration filter latency (FR-007/FR-008 URL pattern + 6 credential patterns) bounded?
  [GAP].

- [x] CHK006 Is the jailbreak detector latency (FR-009 length-deviation + 8 phrase matches) bounded?
  [GAP].

- [x] CHK007 Is the prompt_protector latency (FR-010 canary scan + FR-011 25-word fragment match) bounded?
  [GAP]. FR-011 is the most expensive: substring search across the assembled system prompt (Tier 1+2+3+4) for 25-word windows. With long prompts and long responses, O(prompt × response).

- [x] CHK008 Is the security_events INSERT latency (FR-015) bounded?
  [GAP]. Per-layer detection records mean potentially 6+ INSERTs per turn under heavy detection. Spec is silent.

## Compound-Cost Bounds

- [x] CHK009 Is the worst-case pipeline latency (every layer flags, max risk_score path, full security_events write) bounded?
  [GAP]. 50ms target is for the steady state; worst-case (all layers detect + write events) is unspecified.

- [x] CHK010 Is the FR-014 fixed-order layer evaluation (vs. fail-fast or short-circuit) a documented perf trade-off?
  [PARTIAL]. FR-014 says "each layer emits independent flags ... blocking decision is max(risk_score)" — fixed-order is implicit; not surfaced as a perf choice.

- [x] CHK011 Is the cost of FR-013 fail-closed path (security_pipeline_error → skip + security_events row) bounded?
  [GAP]. Cross-ref 003 CHK036 — same shape.

- [x] CHK012 Is the deferred LLM-as-judge layer's latency budget pre-allocated?
  [GAP]. Assumption says "<50ms excluding LLM-as-judge" — but when LLM-as-judge ships, it'll add an LLM round-trip per response (cheapest model ~1-2s). The aggregate budget will need to expand 20-40x.

## Throughput / Concurrency

- [x] CHK013 Is per-turn pipeline parallelism specified (can layers run concurrently or are they strictly sequential)?
  [GAP]. FR-014 fixed order implies sequential. Some layers are independent (sanitizer vs. exfiltration) and could run in parallel; spec doesn't address.

- [x] CHK014 Is concurrent-pipeline workload bounded (multiple sessions × turn rate)?
  [GAP]. Pipeline runs in the turn-loop coroutine; no separate executor. Cross-session contention is via the shared CPU + regex caches.

- [x] CHK015 Are the regex compilation costs amortized (compiled once at module load, reused)?
  [PARTIAL]. Implementation amortizes via module-level constants; spec is silent on this expectation.

## Memory & Resource Footprint

- [x] CHK016 Is the in-memory size of an in-flight pipeline evaluation bounded (response copy + flags + findings + accumulated reasons)?
  [GAP]. Each layer emits independent flags; with 6+ layers + per-finding metadata, memory is small but unspecified.

- [x] CHK017 Is the FR-015 security_events row size bounded (findings JSON-encoded)?
  [GAP]. With every layer's findings appended, payload could grow. No cap.

- [x] CHK018 Is the FR-011 fragment-match memory cost bounded?
  [GAP]. Sliding window over full assembled prompt + full response = O(prompt + response) memory at peak.

## Cost-Per-Turn Tax

- [x] CHK019 Is the pipeline tax on per-turn latency reconciled with 003 FR-019 turn timeout (180s) and 004 SC-001 (500ms embedding budget)?
  [GAP]. 50ms pipeline + 500ms embedding + 100s+ LLM dispatch = tax on the user-facing total. Spec doesn't surface compounding.

- [x] CHK020 Is the cost added by 005 FR-011 (recursive sanitize on summaries) accounted for in the pipeline budget?
  [GAP]. 005 CHK004 already flagged this — same regex passes run on every string leaf of the summary JSON tree. Cumulative cost unsurfaced.

- [x] CHK021 Is the FR-012 log-scrubbing per-message cost specified (every log line passes through ScrubFilter)?
  [GAP]. With high log volume during normal operation, scrubbing cost compounds.

## Cold-Start

- [x] CHK022 Is the first-turn pipeline latency (regex compilation at module load) specified?
  [GAP]. Module-level compile is one-time but not surfaced.

- [x] CHK023 Is the FR-009 cold-start path (avg_length <= 0 → skip length-deviation check) latency-different from steady state?
  [PARTIAL]. FR-009 documents the cold-start branch; the perf delta (skipped one regex pass) is implicit.

## Degradation Under Load

- [x] CHK024 Is the system's behavior under high false-positive rate specified (FR-019 targets: <2%, <1%, <8%, <0.5%)?
  [PARTIAL]. FR-019 sets targets but they're "advisory until the fixture lands." If real false-positive rate exceeds budget, downstream review-gate queue swells; spec doesn't address that congestion path.

- [x] CHK025 Is the security_events table growth bounded?
  [GAP]. Every detection writes a row. With multiple layers per turn × many turns × many sessions, the table grows fast. No retention.

- [x] CHK026 Is the SLO percentile (P50/P95/P99) for pipeline latency specified?
  [GAP].

## Measurement & Instrumentation

- [x] CHK027 Is per-layer timing instrumentation required (so a slow regex in one layer is diagnosable)?
  [GAP]. CHK001 of security audit identical shape. Re-iterating: no per-stage timing.

- [x] CHK028 Is a benchmark fixture (the deferred `tests/fixtures/benign_corpus.txt` referenced by FR-019) required to be created as a perf reference, not just a false-positive reference?
  [GAP]. FR-019 names the fixture for FP measurement only; same fixture would let SC-006 perf testing run.

- [x] CHK029 Is a perf-regression CI gate required?
  [GAP].

## Cross-Layer Optimizations

- [x] CHK030 Is the trade-off between layer independence (FR-014 — each layer self-contained) and cross-layer optimization (e.g. tokenize once, reuse) documented?
  [GAP]. Each layer reads the response from scratch; aggregate cost > sum of unique work.

- [x] CHK031 Is a fast-path specified for clean responses (most responses are not adversarial; could short-circuit on null findings)?
  [GAP]. Implementation runs every layer regardless. Trade-off (security thoroughness vs. happy-path latency) unsurfaced.

- [x] CHK032 Is the cost of FR-002 spotlighting on EVERY cross-AI message (regardless of trust) bounded by the cross-AI message rate?
  [GAP]. Spotlighting is mandatory per FR-002 for every cross-speaker AI→AI message; worst-case all participants are AI, every turn spotlights.

## Notes

- 32 items audited. The pipeline is the single most-touched piece of code per turn after the LLM call itself; lack of per-stage budgets and SLOs makes regressions essentially undetectable.
- Highest-leverage findings to convert into spec amendments:
  - CHK001 / CHK027 (decompose 50ms target per-layer + per-stage instrumentation — closes both this checklist's CHK001 and security audit's CHK013).
  - CHK012 (LLM-as-judge budget pre-allocation — the 20-40x latency expansion when it ships will surprise no one if codified now).
  - CHK009 (worst-case latency bound — currently invisible to anyone but a profiler).
  - CHK020 / CHK021 (cumulative tax across spec boundaries — pipeline + summarizer-recursive-sanitize + log-scrubbing all run on the same regex set).
  - CHK025 (security_events retention — table grows unbounded, mirrors 001 CHK021).
- Lower-priority but useful:
  - CHK013 / CHK030 / CHK031 (parallelization + tokenize-once + happy-path short-circuit are real optimization paths not yet contemplated).
  - CHK028 (the deferred benign_corpus.txt fixture is dual-use: FP measurement AND perf benchmark).
- Sister checklists: `requirements.md`, `security.md` already on main. Cross-refs: 003 CHK036 (fail-closed path), 004 CHK022 (no benchmark fixture), 005 CHK004 (recursive sanitize cost), 006 CHK020 (debug-export pulls security_events).

## Closeout (2026-04-29)

Spec amendments to 007 close the highest-leverage GAPs:

- **CHK001** (decompose 50ms target per-layer) closed by FR-020 (security_events.layer_duration_ms) + SC-008 (per-layer P95 budgets summing to <=50ms aggregate).
- **CHK002-007** (per-layer latency: sanitizer, spotlighting, output_validator, exfiltration, jailbreak, prompt_protector) closed by SC-008 (explicit per-layer budgets).
- **CHK008** (security_events INSERT latency) addressed by FR-021 (90ms worst-case ceiling).
- **CHK009** (worst-case latency bound) closed by FR-021 (90ms adversarial-pass ceiling, regression-detection rule).
- **CHK012** (LLM-as-judge budget pre-allocation) closed by FR-023 (target expands to <2s when wired; placement after pattern layers).
- **CHK020** (cumulative tax across spec boundaries with 005 + 008) closed by FR-022 (pipeline_total_ms aggregate to routing_log).
- **CHK025** (security_events retention) closed by SC-009 (90-day default + SACP_SECURITY_EVENTS_RETENTION_DAYS override + purge job).
- **CHK027** (per-stage timing instrumentation) closed by FR-020.

Items remaining [GAP]:

- CHK028 / CHK029 (benchmark fixture benign_corpus.txt + adversarial sibling, CI regression gate) same shape across all 7 perf checklists.
- CHK013-018 (parallelization, regex compile amortization, memory bounds) implementation-detail optimizations.
- CHK022-024 (cold-start, false-positive rate vs review-gate-queue congestion) requires telemetry stack.
- CHK030-032 (cross-layer optimizations, fast-path short-circuit) Phase 3 perf work, not blocked by spec.

Implementation of FR-020 / FR-021 / FR-022 / FR-023 / SC-008 / SC-009 ships as a follow-up PR (per-layer timing capture, retention purge job, pipeline_total_ms emit).
