# Performance Requirements Quality Checklist: Rate Limiting

**Purpose**: Validate the quality, clarity, and completeness of performance requirements in the Rate Limiting spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Audited**: 2026-04-29
**Feature**: [spec.md](../spec.md)

**Audit summary**: 6 items pass cleanly, 18 have findings. Rate limiting runs on every authenticated `/tools/*` request — its per-call latency is a tax on every API operation. The spec is unusually thorough on memory bounds (FR-007 + SC-003 cardinality cap, lazy eviction) but light on per-call latency, throughput, and instrumentation.

## Per-Call Latency

- [x] CHK001 Is the per-`check()` latency bounded?
  [GAP]. FR-008 says "no await points; read-prune-append sequence is atomic" — implies sub-ms but no spec ceiling.

- [x] CHK002 Is the cost of timestamp pruning (FR-001 sliding window) bounded by window-density?
  [GAP]. With 60 req/sec, prune walks 60 timestamps in worst case. O(n) per call where n is window size; bounded but unspecified.

- [x] CHK003 Is the cost of FR-007 lazy stale-bucket eviction sweep bounded?
  [PARTIAL]. SC-003 says bucket map "MUST NOT grow beyond DEFAULT_MAX_BUCKETS after the eviction sweep." Sweep cost itself unspecified — could be O(buckets) which at 10K is meaningful work on the request path that triggered it.

- [x] CHK004 Is the FR-002 429 response build cost bounded?
  [GAP]. JSON construction + Retry-After header build is sub-ms but unsurfaced.

## Throughput

- [x] CHK005 Is the maximum throughput-per-participant specified?
  [PARTIAL]. FR-001 says "60 in 1 second" is the burst ceiling — that's a design parameter, not a measured throughput.

- [x] CHK006 Is the cross-participant aggregate throughput bounded?
  [GAP]. With N participants × 60 req/sec each, aggregate scales linearly. No application bound.

- [x] CHK007 Is the rate-limit middleware position in the request pipeline specified relative to auth?
  [PARTIAL]. FR-006 says "applies to all authenticated /tools/* endpoints" — implies post-auth. Performance implication: failed auth still consumes auth cost but not RL cost. Worth surfacing.

## Memory Footprint

- [x] CHK008 Is the per-bucket memory footprint specified?
  [GAP]. Each bucket = participant_id + deque of timestamps + lock or atomic. With 60 timestamps × 8 bytes = ~480 bytes + Python overhead = ~1KB per bucket. Bounded but unsurfaced.

- [x] CHK009 Is the SC-003 cap (10,000 buckets) memory translation specified (~10MB ceiling)?
  [GAP]. 10K × ~1KB = 10MB — modest but worth surfacing as the actual ceiling.

- [x] CHK010 Is the eviction-trigger memory cost bounded (the sweep that runs when DEFAULT_MAX_BUCKETS is exceeded)?
  [GAP]. Sweep iterates the bucket map; O(N) memory walk per trigger. Trigger frequency unspecified — could happen on every request once the cap is hit.

## Cold-Start

- [x] CHK011 Is the empty-bucket-map cold-start cost specified?
  [GAP]. Trivial — first request creates first bucket. Unsurfaced.

- [x] CHK012 Is the FR-005 process-restart reset (every bucket cleared) latency-relevant for the first window after deploy?
  [PARTIAL]. FR-005 documents the reset as defended; perf consequence (a 60-req burst right after deploy gets through unchecked because counters are empty) is implicit.

## Concurrency

- [x] CHK013 Is the FR-008 single-threaded-atomicity assumption stated as a perf-bound (no contention to wait on)?
  [PARTIAL]. FR-008 acknowledges the assumption and the future-multi-threaded "explicit lock will be required" path. Lock cost not pre-budgeted.

- [x] CHK014 Is per-process concurrent-request contention bounded?
  [GAP]. asyncio is single-threaded but multiple requests can interleave between `check()` calls; spec is silent on whether order matters.

- [x] CHK015 Is the FR-007 forget() call latency bounded (called from /remove_participant, /revoke_token)?
  [GAP]. Single dict delete; sub-ms but unspecified.

## Cross-Reference: Token Rotation

- [x] CHK016 Is the FR-009 "rotation doesn't reset window" path latency-relevant?
  [GAP]. Rotation hits the auth path; the rate-limit bucket is unchanged. Worth surfacing that rotation has zero RL cost.

## Degradation Under Load

- [x] CHK017 Is behavior specified when bucket count approaches DEFAULT_MAX_BUCKETS (does eviction frequency increase pathologically)?
  [GAP]. With cap full + every new participant triggering eviction sweep, throughput could degrade non-linearly. No spec.

- [x] CHK018 Is sustained burst behavior specified (60 req/sec for 10 minutes — does prune work scale?)?
  [GAP]. Window slides forward; prune always walks the deque. With sustained traffic, prune is constant-cost per call.

- [x] CHK019 Is SLO percentile (P50/P95/P99) for `check()` latency specified?
  [GAP].

## Hot Path Cost-Per-Endpoint

- [x] CHK020 Is the rate-limit cost per endpoint differentiated (cheap reads vs. expensive writes both pay the same RL tax)?
  [PARTIAL]. FR-006 says "reads and writes count equally toward the per-participant limit" — that's policy. Perf-wise, the RL check itself is the same cost for all endpoints; this is implicit.

- [x] CHK021 Is the RL middleware exempt from the rate-limit measurement (i.e. the spec doesn't require self-instrumentation)?
  [GAP].

## Measurement & Instrumentation

- [x] CHK022 Is per-call timing instrumentation required?
  [GAP]. With high request volume, RL is on every call; histogram visibility is critical.

- [x] CHK023 Are 429-rate metrics required (per-participant, per-endpoint)?
  [GAP]. Operationally important — sustained 429s indicate either an attacker or a legitimate workload that needs limit tuning.

- [x] CHK024 Is bucket-count-vs-cap monitoring required?
  [GAP]. SC-003 caps the count but doesn't require visibility on how close to the cap the system runs.

- [x] CHK025 Is eviction-sweep-frequency a tracked metric?
  [GAP]. Pairs with CHK017 — sustained eviction is a perf signal.

- [x] CHK026 Is a benchmark fixture required (synthetic 1M-request load × 1K participants)?
  [GAP]. SC-003 references "synthetic load creating >10,000 distinct participant ids" but as a memory test, not a perf benchmark.

- [x] CHK027 Is per-call latency a CI-gated regression target?
  [GAP].

## Trade-offs

- [x] CHK028 Is the trade-off between sliding-window precision (per-timestamp pruning) and approximation (token-bucket smoothing) documented?
  [PARTIAL]. FR-001 says "count-only, no token-bucket smoothing" + "operators who need smoother dispatch should layer an upstream proxy." Trade-off acknowledged; perf implication (per-call prune cost vs. constant-time token-bucket update) not surfaced.

- [x] CHK029 Is the cost-vs-fidelity of in-memory state (FR-005, no persistence) documented?
  [PARTIAL]. FR-005 acknowledges the brief loosening at restart as defended; no perf cost for the persistence we don't have.

- [x] CHK030 Is the FR-007 lazy-eviction (vs. eager periodic sweep) trade-off documented?
  [PARTIAL]. FR-007 specifies lazy "on next check()". Trade-off (no background scheduler vs. occasional latency spikes during sweeps) not surfaced.

## Notes

- 30 items audited. 009 is the most thorough on memory bounds (FR-007 + SC-003) but the per-call latency contract is implicit.
- Highest-leverage findings to convert into spec amendments:
  - CHK001 / CHK022 (per-call latency target + instrumentation — RL is on every authenticated request, so even sub-ms regressions compound).
  - CHK017 / CHK025 (eviction-frequency under cap-pressure — degradation path that's currently invisible).
  - CHK023 (429-rate metric — operationally important for distinguishing attack from legitimate-workload-hits-cap).
  - CHK009 (codify the ~10MB memory ceiling implied by SC-003 — makes the bound concrete for capacity planning).
- Lower-priority but useful:
  - CHK026 / CHK027 (benchmark fixture + CI gate — same shape as 003/004/006/007/008 — system-wide gap).
  - CHK020 (per-endpoint RL cost differentiation — relevant for tuning).
- Sister checklists: `requirements.md`, `security.md` already on main. Cross-refs to 002 (auth runs before RL), 006 (RL middleware lives in MCP server), 011 (Web UI same-origin requests pay this tax too).

## Closeout (2026-04-29)

Spec amendments to 009 close the highest-leverage GAPs:

- **CHK001** (per-check() latency bounded) closed by FR-011 (P95 <= 1ms steady state) + SC-005 (synthetic-load measurement contract).
- **CHK002** (timestamp pruning cost) addressed by FR-011 (cost components enumerated).
- **CHK003** (eviction sweep cost) closed by FR-013 (at-most-once-per-second + duration capture).
- **CHK009** (10MB memory ceiling codified) closed by FR-014 + SC-007 (RSS-delta enforcement at 20MB ceiling).
- **CHK017** (eviction-frequency under cap-pressure) closed by FR-013 (rate-limited sweep prevents pathological cascading).
- **CHK019** (P50/P95/P99 SLO) closed by SC-005 (P95 <= 1ms, P99 <= 5ms).
- **CHK022** (per-call timing instrumentation) closed by FR-011 + SC-005.
- **CHK023** (429-rate metrics) closed by FR-012 (per-participant + aggregate counters) + SC-006 (attack-vs-legit-workload distinguishing rule).
- **CHK024** (bucket-count-vs-cap monitoring) addressed by FR-013 + FR-014.
- **CHK025** (eviction-sweep-frequency tracked metric) closed by FR-013 (rate_limit_eviction_sweep_ms capture).

Items remaining [GAP]:

- CHK026 / CHK027 (benchmark fixture + CI regression gate) same shape across all 7 perf checklists.
- CHK006-016 (cross-participant aggregate throughput, middleware position cost, per-bucket footprint) depend on telemetry stack.
- CHK020 / CHK028-030 (per-endpoint RL cost differentiation, sliding-window vs token-bucket trade-off, lazy vs eager eviction) design notes for Phase 3.

Implementation of FR-011 / FR-012 / FR-013 / FR-014 / SC-005 / SC-006 / SC-007 ships as a follow-up PR (sweep-rate-limit logic, 429-counter capture, per-check() timing, RSS measurement test).
