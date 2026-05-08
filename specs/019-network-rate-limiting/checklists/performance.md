# Performance Requirements Quality Checklist: Network-Layer Per-IP Rate Limiting

**Purpose**: Validate that the spec's V14 performance budget requirements are quantified, measurable, and complete enough to be enforceable contracts. Tests the writing of the requirements, not the implementation.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md)

## Limiter Middleware Overhead

- [ ] CHK001 Is the per-request overhead budget quantified with a time bound (not just "O(1)" complexity language)? [Measurability, Spec §V14 / Gap]
- [ ] CHK002 Are the constituent operations of the per-request budget enumerated (hash lookup, refill computation, increment/decrement)? [Completeness, Spec §V14]
- [ ] CHK003 Is the V14 per-stage budget tolerance referenced with a specific numeric value or cross-link to the budget registry, rather than left open? [Clarity, Spec §V14 / Gap]
- [ ] CHK004 Is the routing_log sampling strategy for middleware duration capture specified (sample rate, sampling key)? [Completeness, Spec §V14 / Gap]

## Per-IP Budget Eviction

- [ ] CHK005 Is "amortized O(1)" eviction quantified with the underlying data structure constraint (LRU on the key map)? [Clarity, Spec §V14]
- [ ] CHK006 Is `SACP_NETWORK_RATELIMIT_MAX_KEYS` specified with both lower and upper bounds, and a default? [Completeness, Spec §FR-013 / Configuration]
- [ ] CHK007 Is the worst-case memory bound under flood quantified (MAX_KEYS × per-entry size)? [Measurability, Spec §Assumptions]
- [ ] CHK008 Is the eviction-while-flood scenario covered (eviction firing per-request when MAX_KEYS pressure is sustained)? [Coverage, Spec §V14]

## Audit-Log Coalescing Flush

- [ ] CHK009 Is the "asynchronous flush" requirement specified with an explicit non-blocking-on-request-path constraint? [Clarity, Spec §V14]
- [ ] CHK010 Is the coalescing window granularity (1 minute) specified as a fixed value or as a tunable, and if tunable, is the env var named? [Completeness, Spec §FR-009 / Assumptions]
- [ ] CHK011 Is the flush mechanism (background asyncio task vs scheduled timer vs other) sufficient to guarantee non-blocking, or is the choice deferred to /speckit.plan with a budget enforcement rule? [Clarity, Spec §V14]
- [ ] CHK012 Are flush-failure scenarios specified (what happens to in-flight summary entries if the orchestrator crashes mid-window)? [Edge Case, Gap]

## Token Bucket Algorithm Specification

- [ ] CHK013 Is the token-bucket math fully specified (capacity = BURST; refill rate = RPM/60; admit when current_tokens >= 1.0)? [Completeness, Spec §FR-003 / C4 resolution]
- [ ] CHK014 Is the lazy-refill-on-each-lookup semantic specified, distinguishing from a background-refill alternative? [Clarity, Spec §C4 resolution / Gap]
- [ ] CHK015 Is the burst-at-window-edge behavior addressed (token-bucket smooths it; spec acknowledges fixed-window vulnerability rejected)? [Coverage, Spec §Edge Cases]

## Bcrypt Invocation Bound (SC-001)

- [ ] CHK016 Is SC-001's "at most RPM bcrypt invocations per minute" quantified in a way that can be observed (orchestrator counter or load-test instrumentation)? [Measurability, Spec §SC-001]
- [ ] CHK017 Does the spec specify how the bcrypt-invocation count is captured (test-harness instrumentation, not a runtime feature)? [Completeness, Spec §SC-001 / Gap]

## Latency Non-Interference (SC-002)

- [ ] CHK018 Is the legitimate-IP latency contract during a flood ("≤ pre-feature P95") specified with a measurement methodology? [Measurability, Spec §SC-002]
- [ ] CHK019 Is the cross-IP isolation guarantee tied to a specific test (flood from IP A, measure auth latency from IP B)? [Coverage, Spec §SC-002]

## Exempt Path Performance

- [ ] CHK020 Are exempt paths specified to bypass the limiter middleware entirely (not just "exempt from counting")? [Clarity, Spec §FR-006]
- [ ] CHK021 Is the exempt-path match performance bounded (constant-time path+method lookup, since the registry is fixed and small)? [Coverage, Gap]

## Default Tuning

- [ ] CHK022 Are the autonomous defaults (RPM=60, BURST=15, MAX_KEYS=100_000) justified in research.md or plan.md, or specified inline? [Traceability, Spec §Configuration / Assumptions]
- [ ] CHK023 Is the rationale for BURST = RPM/4 documented, or is it left unjustified? [Clarity, Spec §SACP_NETWORK_RATELIMIT_BURST]

## Notes

- Each [Gap] item requires either spec amendment or research.md / plan.md cross-reference.
- The V14 per-stage tolerance value (currently a placeholder reference in the spec) is the highest-impact open item.
