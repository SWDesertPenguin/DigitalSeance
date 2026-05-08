# Performance Requirements Quality Checklist: AI Response Shaping

**Purpose**: Validate that the spec's V14 performance budget requirements (filler scorer P95, slider lookup, retry dispatch cap, routing_log instrumentation, per-family thresholds) are quantified, measurable, and enforceable contracts. Tests the writing of the requirements, not the implementation.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md)

## Filler Scorer P95 Budget

- [ ] CHK001 Is the filler-scorer P95 budget (≤ 50ms) specified with a measurement window, sample size, and percentile semantic? [Measurability, Spec §V14]
- [ ] CHK002 Are the constituent signal computations (hedge ratio, restatement cosine, closing pattern) called out with their own bounds, or is only the aggregate P95 specified? [Completeness, Spec §V14 / Gap]
- [ ] CHK003 Is the routing_log instrumentation field (`shaping_score_ms`) named precisely, with the per-stage timing schema cross-referenced to spec 003 §FR-030? [Clarity, Spec §V14 / FR-011]
- [ ] CHK004 Is the budget enforced as a CI gate (test asserts P95 in a benchmark suite) or as a runtime SLO (alert)? [Measurability, Gap]

## Retry Dispatch Cap

- [ ] CHK005 Is the hardcoded 2-retry cap specified as an absolute upper bound (not "typically 2"), with the consequence of cap-exhaustion explicitly defined? [Clarity, Spec §FR-005 / V14]
- [ ] CHK006 Is the per-attempt retry-budget consumption rule specified (each attempt consumes from the joint cap)? [Completeness, Spec §FR-006]
- [ ] CHK007 Is `shaping_retry_dispatch_ms` defined with the timing semantic (per retry attempt vs cumulative)? [Clarity, Spec §V14 / data-model.md]
- [ ] CHK008 Is the FR-006 joint-cap behavior (filler retries + topology-7 fallback retries share a cap, if applicable) specified with a precedence rule? [Coverage, Spec §FR-006 / Gap]

## Slider Lookup O(1) < 1ms

- [ ] CHK009 Is the "O(1) < 1ms P95" specification both an algorithmic complexity claim AND a measurable latency budget? [Clarity, Spec §V14]
- [ ] CHK010 Is the lookup path defined (in-memory `REGISTER_PRESETS` tuple indexed by slider value 1-5)? [Completeness, contracts/register-preset-interface.md]
- [ ] CHK011 Is the cache strategy for `session_register` and `participant_register_override` specified (DB lookup per `/me` request vs cached)? [Coverage, Spec §FR-009 / Gap]

## Per-Family Threshold Calibration

- [ ] CHK012 Are the per-family default thresholds (anthropic/openai 0.60; gemini/groq/ollama/vllm 0.55) documented with a rationale? [Completeness, Spec §C resolution / research.md]
- [ ] CHK013 Is the relationship between `SACP_FILLER_THRESHOLD` (override) and per-family defaults specified precisely (override applies to all families, no per-family override env var)? [Clarity, Spec §FR-002]
- [ ] CHK014 Is the threshold-tuning calibration target (SC-001's reduction percentage) tied to the default values with a feedback loop? [Traceability, Spec §SC-001 / Gap]

## Instrumentation Coverage (routing_log Extensions)

- [ ] CHK015 Are all five new `routing_log` columns (`shaping_score_ms`, `shaping_retry_dispatch_ms`, `filler_score`, `shaping_retry_delta_text`, `shaping_reason`) enumerated with type, nullability, and default? [Completeness, data-model.md]
- [ ] CHK016 Is each column tied to a specific FR (e.g., `filler_score` → FR-001-004; `shaping_reason` → FR-005)? [Traceability]
- [ ] CHK017 Is the backward-compatibility constraint specified (all five new columns NULL-default so old rows remain valid)? [Clarity, Spec §FR-016 / data-model.md]

## Master Switch Cost (SC-002 regression)

- [ ] CHK018 Is the SC-002 master-switch-disabled regression specified to add zero per-request overhead when `SACP_RESPONSE_SHAPING_ENABLED=false`? [Measurability, Spec §SC-002]
- [ ] CHK019 Is the SC-002 verification methodology explicit (test compares P95 with shaping disabled vs pre-feature baseline)? [Clarity, Spec §SC-002]

## Topology-7 Conditional Skip

- [ ] CHK020 Is the topology-7 skip path specified with a runtime gate (env var `SACP_TOPOLOGY=7`), and is the budget impact (skip = zero shaping cost) documented? [Coverage, Spec §V12 / research.md]
- [ ] CHK021 Is the topology-7 path's testability addressed (skip-when-set test, default-on test) given that topology 7 is aspirational? [Gap, Spec §V12]

## Embedding Reuse from Spec 004

- [ ] CHK022 Is the `ConvergenceEngine.last_embedding` access pattern specified as O(1) (property access, no recomputation)? [Clarity, contracts/filler-scorer-adapter.md]
- [ ] CHK023 Is the ring-buffer depth (3 turns) specified with a justification (restatement signal needs N=2 history)? [Completeness, research.md / data-model.md]

## Notes

- The CI-gate-vs-runtime-SLO distinction (CHK004) determines whether the budget is a hard fail or a soft alert. The spec does not currently specify either; resolve before /speckit.tasks.
- Per-family threshold calibration (CHK012, CHK014) is currently soft (research.md inline rationale only); a dedicated calibration record may be warranted.
