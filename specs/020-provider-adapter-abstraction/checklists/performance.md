# Performance Requirements Quality Checklist: Pluggable Provider Adapter Abstraction

**Purpose**: Validate that spec 020's V14 performance budget requirements (adapter-call overhead, `normalize_error()` execution, byte-identical regression vs pre-feature LiteLLM, streaming pass-through cost) are quantified, measurable, and enforceable contracts. This checklist tests the writing of the budget specifications, not the runtime implementation.

The existing [operations.md](./operations.md) §"V14 Performance Monitoring" covers runtime monitoring (alerts, thresholds at deploy time), and [testability.md](./testability.md) §"Regression Contract (SC-001)" covers the byte-identical regression test scaffolding. This checklist covers the orthogonal question: **are the budgets themselves written precisely enough that two reviewers would judge them the same way?**
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md) + [plan.md](../plan.md)

## Adapter-Call Overhead Budget

- [ ] CHK001 Is the "adapter-call overhead per dispatch" budget quantified with an absolute numeric value (microseconds or milliseconds), or is it left as a relative reference to "V14 per-stage budget tolerance"? [Measurability, Spec §"Performance Budgets" / Gap]
- [ ] CHK002 Is "the V14 per-stage budget tolerance" defined elsewhere with a concrete value, and if so, is the cross-reference explicit (constitution section, Phase 1 budget registry, etc.)? [Traceability, Spec §"Performance Budgets" / Gap]
- [ ] CHK003 Is the budget defined at p50, p95, p99, or another percentile, and is the percentile specified? [Clarity, Spec §"Performance Budgets" / Gap]
- [ ] CHK004 Are the prohibited mechanisms in the adapter ("no buffering, copying, serialization beyond what LiteLLM already does") enumerated precisely enough to be checkable in a code review? [Clarity, Spec §"Performance Budgets"]
- [ ] CHK005 Is the comparison baseline ("pre-feature direct-LiteLLM call") specified with a measurement methodology (which call path, on which model, with which input shape)? [Completeness, Spec §"Performance Budgets" / Gap]
- [ ] CHK006 Does "single virtual-method dispatch" cost specification account for Python's per-call overhead (attribute lookup, frame setup), or is it a wave-of-the-hand at C-level method dispatch? [Clarity, Spec §"Performance Budgets" / Ambiguity]

## `normalize_error()` O(1) Budget

- [ ] CHK007 Is the constant-time claim quantified (single-digit microseconds at p99? bounded by N where N is the number of registered exception classes?), or stated only as algorithmic complexity? [Measurability, Spec §"Performance Budgets" / Gap]
- [ ] CHK008 Is the no-I/O constraint enumerated with what counts as I/O (file reads, network calls, dict lookups against an external cache)? [Completeness, Spec §"Performance Budgets"]
- [ ] CHK009 Is the no-allocation-beyond-canonical-error constraint specified with the canonical-error object's expected size (small dataclass, no nested collections)? [Clarity, Spec §"Performance Budgets" / contracts/canonical-error-mapping.md]
- [ ] CHK010 Is the spec 015 audit-entry instrumentation cross-link explicit (which audit-event field carries the duration; what units)? [Traceability, Spec §"Performance Budgets" / Spec 015 cross-ref]

## Streaming Pass-Through Cost

- [ ] CHK011 Is the per-event cost of the adapter's streaming-event normalization specified (the streaming.py layer between LiteLLM events and SACP events)? [Gap]
- [ ] CHK012 Are the buffer-and-reorder cases (out-of-causal-order events, per [spec.md §Edge Cases](../spec.md)) bounded with a per-stream memory cap? [Coverage, Gap]
- [ ] CHK013 Is the streaming back-pressure semantic specified (does the adapter block on slow consumer, drop events, or buffer unboundedly)? [Edge Case, Gap]

## Token-Counting Cost

- [ ] CHK014 Is the cost of `count_tokens(messages, model)` specified with a per-message-list bound (linear in token count? linear in message count? cached)? [Completeness, Spec §FR-012 / Gap]
- [ ] CHK015 Is the cost difference between native-tokenizer and conservative-fallback tokenizer paths specified (are they comparable or is one an order of magnitude slower)? [Coverage, Spec §FR-012 / Gap]
- [ ] CHK016 Is the call-frequency expectation documented (per-turn, per-message, cached at session-scope)? [Clarity, Gap]

## Byte-Identical Regression Specification (SC-001)

- [ ] CHK017 Is "byte-identical" enumerated across all observable surfaces (text content, token counts, timing, cost values, audit-log entries, routing_log entries)? [Completeness, Spec §SC-001]
- [ ] CHK018 Is the regression budget for timing differences specified (zero variance demanded, or a tolerance threshold, since wall-clock timing is non-deterministic)? [Clarity, Spec §SC-001 / Ambiguity]
- [ ] CHK019 Is the regression test sample size and run frequency specified (single-run vs N-run with statistical bound; CI-runtime vs scheduled benchmark)? [Measurability, Spec §SC-001 / Gap]
- [ ] CHK020 Are the inputs that drive the regression test specified (golden-fixture input set, with stable model and stable provider keys)? [Completeness, Spec §SC-001 / Gap]

## Capabilities Cache and Validation Cost

- [ ] CHK021 Is `capabilities(model)` cost specified (cached at startup vs per-call; if cached, when invalidated)? [Completeness, Spec §FR-007 / Gap]
- [ ] CHK022 Is `validate_credentials(api_key, model)` cost specified, and is the network-touching expectation documented (does it hit the provider, or is it a local sanity check)? [Clarity, Spec §FR-006 / Gap]

## Routing Log Instrumentation

- [ ] CHK023 Are the routing_log fields used for V14 budget capture enumerated (per-dispatch timing field, normalize-error timing field, sampling fraction)? [Completeness, Spec §"Performance Budgets" / Gap]
- [ ] CHK024 Is the sampling strategy specified (rate, sampling key — random, every-Nth, or per-participant rotating)? [Clarity, Spec §"Performance Budgets" / Gap]
- [ ] CHK025 Is the sample retention specified (rows kept for N days, downsampled, or written through to a long-term metrics surface)? [Coverage, Gap]

## CI-Gate vs SLO Distinction

- [ ] CHK026 Is each V14 budget enforced as a hard CI gate (test fails if exceeded) or as a runtime SLO (alert if exceeded), and is the choice explicit per budget? [Clarity, Gap]
- [ ] CHK027 If CI-gated: is the gate-runtime environment specified (which CI runner, which baseline machine, which warmup) so the budget is reproducible? [Measurability, Gap]
- [ ] CHK028 If SLO-only: is the alerting threshold and on-call surface specified, and does it tie into spec 016's metrics? [Coverage, Spec 016 cross-ref / Gap]

## Constitution V14 Alignment

- [ ] CHK029 Are the two budgets in spec 020 consistent with the V14 enumeration in the constitution (no missing budget, no extra budget claimed)? [Consistency, Constitution §V14 / Spec §"Performance Budgets"]
- [ ] CHK030 Is the V14 budget-registry entry for spec 020 cross-referenced (does the constitution / a central registry enumerate all spec budgets and is 020's listing accurate)? [Traceability, Gap]

## Non-Functional Requirement Cross-Cuts

- [ ] CHK031 Does the performance specification interact correctly with the trust-tiered content model (V8) — is there overhead added when content is wrapped in trust-tiered envelopes that the adapter must strip or pass through? [Coverage, Constitution §V8 / Gap]
- [ ] CHK032 Does the performance specification account for spec 015 (circuit breaker) interaction — does breaker-state probing add to the per-dispatch cost path? [Coverage, Spec 015 cross-ref / Gap]
- [ ] CHK033 Does the performance specification account for spec 017/018 (tool-list freshness, deferred tool loading) interaction — do those features call into the adapter on cold-start paths that should be bounded? [Coverage, Spec 017/018 cross-ref / Gap]

## Notes

- The biggest open issue is the **"V14 per-stage budget tolerance"** placeholder (CHK001-CHK002) — the spec defers to a number that is currently a wave-of-the-hand. Either inline the number or commit to a constitution amendment that adds the registry.
- The byte-identical timing-tolerance question (CHK018) is the second-biggest issue; "byte-identical" wall-clock is impossible, but a stated tolerance keeps SC-001 honest.
- CI-gate-vs-SLO ambiguity (CHK026) determines whether a budget exceedance fails a PR or pages on-call. The spec must specify each budget's enforcement class before /speckit.tasks runs.
- This checklist tests the **specification quality** of the budgets — the runtime monitoring of those budgets is covered by [operations.md](./operations.md) §"V14 Performance Monitoring", and the regression test scaffolding by [testability.md](./testability.md) §"Regression Contract (SC-001)".
- Pass/fail markers `[PASS] / [PARTIAL] / [GAP] / [DRIFT] / [ACCEPTED]` for inline annotation as the checklist is reviewed.
