# Performance Requirements Quality Checklist: Convergence & Adaptive Cadence

**Purpose**: Validate the quality, clarity, and completeness of performance requirements in the Convergence & Adaptive Cadence spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Audited**: 2026-04-29
**Feature**: [spec.md](../spec.md)

**Audit summary**: 7 items pass cleanly, 25 have findings. The spec ships ONE numeric perf target (SC-001 "≤500ms per turn") with no measurement methodology, no per-layer breakdown, no degradation behavior, and no cold-start handling. Round-trip latency on the embedding path is the closest thing to load-bearing perf in SACP — the gap surface here is large.

## Latency Budgets

- [x] CHK001 Is the per-turn embedding-computation budget (SC-001 ≤500ms) decomposed into stages (model inference vs. tokenization vs. cosine-similarity vs. DB write)?
  [GAP]. SC-001 is aggregate. With MiniLM-L6-v2 reported as ~80ms on CPU, the other ~420ms is unaccounted budget — no spec on how it's split, leaving regressions invisible to anyone but a profiler.

- [x] CHK002 Is the cosine-similarity computation latency (over a 5-turn window) specified?
  [GAP]. NumPy dot-product over 5×384 vectors is sub-ms in practice but unspecified. With longer-window experiments in Phase 3, this latency will matter.

- [x] CHK003 Is the divergence-prompt injection (FR-005) latency budget specified, or only the detection path?
  [GAP]. Injection is part of the next turn's context assembly; perf cost is unaccounted vs. baseline turn assembly.

- [x] CHK004 Is the adversarial-rotation evaluation cost (FR-011, every N turns) specified?
  [GAP]. Lookup of "next active participant" iterates participants — bounded by participant count but unspecified.

- [x] CHK005 Is the adaptive-cadence computation cost (FR-008, every turn) specified?
  [GAP]. Trivial in practice; spec is silent on whether it's part of the turn-loop hot path.

## Cold-Start / First-Load

- [x] CHK006 Is the model first-load latency specified separately from steady-state per-turn latency?
  [GAP]. SC-001 implies steady state; first `SentenceTransformer(...)` call downloads the model + materializes the SafeTensors weights, which is materially slower (seconds to minutes depending on disk).

- [x] CHK007 Is the air-gapped / pre-cache load path latency bounded?
  [PARTIAL]. Edge Cases mention pre-cache requirement for air-gapped deployments but no latency target.

- [x] CHK008 Is the lazy-load semantics specified (model loaded on first use vs. eager at startup)?
  [GAP]. Code lazy-loads in `ConvergenceDetector.load_model`; spec is silent on whether that's an intentional design decision (defers cost to first turn) or an implementation detail (could move to startup).

- [x] CHK009 Is a model-load failure mode quantified (timeout, retry, degraded mode)?
  [PARTIAL]. Edge Cases describe "warning + skip" semantics but no retry strategy or timeout. Cold-start network failure during first-turn = first turn waits indefinitely.

## Throughput / Concurrency

- [x] CHK010 Is the maximum concurrent embedding workload bounded (multiple sessions × multiple participants × turn rate)?
  [GAP]. `run_in_executor` uses the default ThreadPoolExecutor — unbounded by spec, capped by Python defaults. With high session count + sprint cadence (2s floor), the executor backlog could grow.

- [x] CHK011 Is the executor pool size specified or required to be configurable?
  [GAP]. Default is `min(32, os.cpu_count() + 4)`; spec doesn't pin this or document the trade-off.

- [x] CHK012 Are GPU / CPU-only mode requirements differentiated?
  [ACCEPTED]. SC-001 says "MiniLM-L6-v2 is ~80ms on CPU" pinning CPU as the target. The Docker image installs CPU-only torch wheels (`fix(docker): install CPU-only torch wheels`) — aligned with intent. Spec could state "CPU-only inference is the production target" explicitly.

- [x] CHK013 Is the memory footprint of the loaded embedding model specified?
  [GAP]. MiniLM-L6-v2 is ~22MB on disk, but in-process is ~90MB. Multiplies with workers if pool is per-process. Spec doesn't bound or document.

## Degradation Under Load

- [x] CHK014 Is the system's behavior specified when embedding computation can't keep up with the turn rate (queue grows; turns proceed without convergence detection)?
  [PARTIAL]. FR-019 says "must complete before next turn's routing decision" — implies a hard sync barrier. So under load, turns BLOCK on embedding rather than degrade silently. Spec should make this explicit: "convergence detection adds latency; under sustained load, turn rate is bounded by embedding throughput."

- [x] CHK015 Is the degraded-mode behavior specified for partial failures (some turns processed, some skipped)?
  [PARTIAL]. Edge Cases cover full failure (warning + skip for whole session). Per-turn skip on transient failure is unspecified.

- [x] CHK016 Are SLOs specified for the percentage of turns that meet SC-001's 500ms target (P50, P95, P99)?
  [GAP]. SC-001 is an aggregate "completes within 500ms" — no percentile specification. P99 spikes from disk swap, GC pauses, or memory pressure are invisible to the spec.

- [x] CHK017 Is back-pressure specified when the convergence-log INSERT throughput lags the turn rate?
  [GAP]. `convergence_log` writes serialize per session via the loop's lock, but cross-session contention on the table is unbounded by spec.

## I/O & Storage

- [x] CHK018 Is the convergence-log INSERT cost bounded (single row, indexed columns)?
  [GAP]. Embedding column is BYTEA (~1.5KB per row); spec doesn't size the row or quantify INSERT time at scale. After 100 turns × 4 participants × 100 sessions, table size is bounded but not declared.

- [x] CHK019 Are convergence-log retention / pruning requirements specified?
  [GAP]. Embedding storage grows monotonically. No retention, no archival, no prune. Long-running sessions = unbounded growth.

- [x] CHK020 Are the indexes on `convergence_log` (for the sliding-window query) specified by name?
  [GAP]. Sliding window is `WHERE session_id = $1 ORDER BY turn_number DESC LIMIT 5`. Spec doesn't pin the supporting index.

## Measurement & Instrumentation

- [x] CHK021 Is per-stage timing instrumentation required (so a regression in tokenization can be distinguished from a regression in inference)?
  [GAP]. CHK013 of 007's audit also flagged this: "no benchmark, no enforcement, no measurement harness." Same shape here.

- [x] CHK022 Is a benchmark fixture / regression-suite required (so SC-001 is testable against future model swaps)?
  [GAP]. No reference dataset. SC-001 is observational, not enforced.

- [x] CHK023 Are perf-regression CI gates required (e.g. fail if 95th percentile embedding time > 1.2× baseline)?
  [GAP].

- [x] CHK024 Is structured logging of per-turn latency required at any persistence layer (`routing_log`, `convergence_log`)?
  [GAP]. Latency timing exists in metrics emitted by `process_turn` but spec doesn't mandate persistence for diagnostic replay.

## Cadence Latency

- [x] CHK025 Is the cadence-floor (2s sprint, 5s cruise) compatible with SC-001's 500ms embedding budget? Worst case: embedding 500ms + DB write + next-turn assembly approaches the 2s floor.
  [GAP]. Math: 500ms embedding + ~200ms turn assembly + ~100ms DB writes + LLM dispatch + … sprint floor leaves little margin. Spec doesn't reconcile.

- [x] CHK026 Is the human-interjection cadence-reset (FR-010) latency bounded?
  [GAP]. Reset happens in-loop; latency budget unspecified.

## Resource Limits & Bounds

- [x] CHK027 Is the maximum sliding-window size bounded?
  [PARTIAL]. Default 5; FR-003 says "configurable." No upper bound specified — operator could set 1000 and the cosine-sim cost scales linearly.

- [x] CHK028 Is the maximum response length the embedder accepts bounded?
  [ACCEPTED]. MiniLM-L6-v2 has a 256-token limit; longer text is truncated. Spec doesn't surface this — quality implications (long responses get embedded by their first 256 tokens only) unspecified.

- [x] CHK029 Is the convergence-log row size capped (BYTEA column upper bound)?
  [GAP]. Embedding is fixed 384×4 bytes ≈ 1.5KB but spec doesn't pin or guard against future model swap that ships 1024-d vectors.

## Trade-offs & Assumptions

- [x] CHK030 Is the trade-off between detection accuracy (larger window) and per-turn cost (more embeddings to compare) documented?
  [GAP].

- [x] CHK031 Is the assumption that "MiniLM-L6-v2 is ~80ms on CPU" paired with the CPU specification (SACP_CPU_TARGET, Docker CPU-only intent)?
  [PARTIAL]. SC-001 cites the 80ms but doesn't specify the reference CPU. A 2-core 1GHz container has very different perf than a desktop runner.

- [x] CHK032 Is GPU support a future possibility, or explicitly out of scope?
  [PARTIAL]. Cross-spec context (CPU-only torch wheels in Docker, spec 004 SC-001 framing) implies CPU-only target. Spec could state "CPU is the production target; GPU is out of scope" as Assumption.

## Notes

- 32 items audited. Heavy clusters around: missing per-stage decomposition (CHK001-005), missing instrumentation (CHK021-024), missing degradation behavior (CHK014-017), missing resource bounds (CHK010-013, CHK027-029).
- Highest-leverage findings to convert into spec amendments:
  - CHK001 (decompose SC-001's 500ms budget into stages — single most useful change for catching future regressions).
  - CHK016 (specify P95 / P99 percentiles, not just aggregate — observability turning point).
  - CHK022 / CHK023 (benchmark fixture + CI regression gate — would make SC-001 actually enforceable).
  - CHK014 (codify "convergence detection blocks the turn rate under load" — currently implicit in FR-019 but not surfaced as a perf characteristic).
- Lower-priority but useful:
  - CHK018 / CHK019 (convergence-log size growth + retention — Phase 3 ops concern).
  - CHK032 (CPU-only target as a stated Assumption — closes the loop with the Docker decision).
- Sister checklists `requirements.md` and `security.md` (closed 2026-04-29). Performance is the natural next axis after security for an inference-on-hot-path component. Cross-ref: 007 §CHK013 already flagged "no benchmark, no enforcement, no measurement harness" — same shape; closing one closes both.
