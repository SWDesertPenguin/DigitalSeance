# Cross-Spec Integration Quality Checklist: AI Response Shaping (Verbosity Reduction + Register Slider)

**Purpose**: Validate that spec 021's cross-spec integration contracts (with specs 001, 003, 004, 008, 011, 020, 026, and constitutional rules §3, §V14, §V16) are specified clearly, completely, and without coupling violations. This checklist tests integration-requirement quality, not the consumer specs' implementations.
**Created**: 2026-05-08
**Feature**: [spec.md §"Cross-References to Existing Specs"](../spec.md) + [data-model.md "Hooks introduced"](../data-model.md) + [plan.md "Notes for /speckit.tasks"](../plan.md)

## Spec 003 — Turn-Loop-Engine

- [ ] CHK001 Is the cross-spec contract "spec 003 §FR-030 `routing_log` per-stage timings receive `shaping_score_ms` and `shaping_retry_dispatch_ms`" specified consistently across FR-011, performance budgets, and the data-model `routing_log` extension? [Consistency, Spec §FR-011 + "Performance Budgets" + Data-model §"routing_log extension"]
- [ ] CHK002 Is the cross-spec contract "spec 003 §FR-031 compound-retry budget is shared with the shaping retry, NOT separately budgeted" specified at sufficient detail to apply consistently per FR-006? [Completeness, Spec §FR-006 + Research §4]
- [ ] CHK003 Are the requirements for the joint-cap behavior (shaping cap of 2 AND compound-budget remaining apply jointly; whichever fires first wins) specified at sufficient detail for the joint-cap test (the contract test landing before either path's individual tests)? [Clarity, Spec §FR-006 last sentence + Plan §"Notes for /speckit.tasks"]
- [ ] CHK004 Is the contract for the existing `@with_stage_timing` decorator integration specified — the new stages (`shaping_score_ms`, `shaping_retry_dispatch_ms`) reuse the existing pattern without modification? [Completeness, Contracts §"Per-stage cost capture" + Data-model §"routing_log instrumentation"]

## Spec 004 — Convergence-Cadence

- [ ] CHK005 Is the cross-spec contract "the restatement signal reads `convergence_log.embedding` for the prior 1-3 turns via spec 004's pipeline" specified as binding (no second sentence-transformers model load per FR-012)? [Completeness, Spec §FR-012 + Research §2]
- [ ] CHK006 Is the spec 004 hook specified at sufficient detail (`last_embedding` property + `recent_embeddings(depth)` helper + `_recent_embeddings: deque[bytes]` ring buffer with `maxlen=3`; single-line additions; no behavior change to spec 004)? [Clarity, Research §2 + Data-model §"Hooks introduced"]
- [ ] CHK007 Is the dependency direction documented as "021 depends on 004; 004 has no dependency on 021" — and does any consumer spec inadvertently force a reverse dependency? [Verifiability, Research §2 "Alternatives considered"]
- [ ] CHK008 Are the requirements for the spec 004 unavailability path specified (sentence-transformers gone or model raises → restatement signal returns `0.0`; hedge + closing still contribute; degrades gracefully rather than failing closed on the whole turn)? [Completeness, Spec §"Edge Cases" + Contracts §"Fail-closed contract"]

## Spec 008 — Prompts-Security-Wiring

- [ ] CHK009 Is the cross-spec contract "Tier 4 delta is the integration point" specified at sufficient detail (spec 021 specifies what deltas exist; spec 008 owns how they wire into the prompt assembler)? [Clarity, Spec §"Cross-References" + Contracts §"Prompt-assembly integration"]
- [ ] CHK010 Is the prompt-assembly order specified consistently (TIER_LOW → tier deltas → custom_prompt → register_delta_text → shaping_retry_delta_text; canary embedding wraps the whole)? [Consistency, Data-model §"Hooks introduced" + Contracts §"Prompt-assembly integration"]
- [ ] CHK011 Are the requirements for `assemble_prompt`'s two new optional parameters (`register_delta_text`, `shaping_retry_delta_text`) specified clearly enough to extend without breaking existing callers? [Completeness, Contracts §"Prompt-assembly integration"]
- [ ] CHK012 Is the rule "the canary embedding still wraps the assembled output (existing spec 008 behavior)" specified as binding to prevent regression of the security pipeline? [Clarity, Plan §"V3" + V10]

## Spec 001 — Core-Data-Model

- [ ] CHK013 Is the cross-spec contract "messages are immutable per spec 001 §FR-008 (the persisted retry output is immutable like any other message)" specified at sufficient detail to prevent accidental mutation paths? [Completeness, Spec §FR-016 + "Cross-References"]
- [ ] CHK014 Is the cascade-delete contract for `participant_register_override` rows specified consistently across FR-015, SC-007, research §7, and data-model? [Consistency, Spec §FR-015 + SC-007 + Data-model §"participant_register_override"]
- [ ] CHK015 Are the requirements for "no orphan override rows after a session delete or participant remove" specified clearly enough to apply via cascade tests? [Measurability, Spec §SC-007 + Tasks §T048-T049]
- [ ] CHK016 Is the rule "cascade-deletes do NOT emit `participant_register_override_cleared` audit rows" specified consistently across research §8, data-model, and the audit-events contract? [Consistency, Research §8 + Contracts §"audit-events.md"]

## Spec 011 — Web UI (Forward-Reference)

- [ ] CHK017 Is the spec 011 forward-reference specified at sufficient detail (the slider control widget is spec 011's deliverable, NOT this spec's; the `/me` field extension is the only client-visible surface here)? [Clarity, Plan §"Notes for /speckit.tasks" + Tasks §T059]
- [ ] CHK018 Is the spec 011 amendment carried at impl time specified per memory `reminder_spec_011_amendments_at_impl_time` — ASK before drafting that surface? [Completeness, Tasks §T059]
- [ ] CHK019 Are the requirements for the `/me` payload extension (three additive top-level fields, snake_case, two-value source enum) specified at sufficient detail to apply without breaking existing clients? [Completeness, Spec §FR-010 + Research §6]

## Spec 020 — Provider Adapter (BehavioralProfile per family)

- [ ] CHK020 Is the cross-spec relationship between spec 021's `BehavioralProfile` (per provider family) and spec 020's adapter capability surface (provider_family attribute) specified — does spec 021 read `provider_family` from spec 020's adapter or from the participant row? [Gap]
- [ ] CHK021 Are the requirements for a future provider-specific adapter's interaction with the per-family `BehavioralProfile` documented (does adding a new family require a `BehavioralProfile` entry, and is that captured anywhere in spec 020's onboarding procedure)? [Gap]

## Spec 026 — Context Compression (Future)

- [ ] CHK022 Is the cross-spec boundary with spec 026 specified consistently across FR-016, the "Compression boundary" overview section, and the "Cross-References" list (this spec attacks generation-side; 026 attacks storage-side; the two specs MUST NOT touch the same column or pipeline)? [Consistency, Spec §"Compression boundary" + FR-016 + "Cross-References"]
- [ ] CHK023 Are the requirements for rejecting any `/speckit.tasks` task that touches `messages.content` or the rolling context window specified at sufficient detail to apply at task-review time? [Verifiability, Plan §"Notes for /speckit.tasks"]

## Spec 005 — Summarization-Checkpoints

- [ ] CHK024 Is the cross-spec relationship with spec 005 specified — tighter generation-time drafts mean tighter summarizer inputs at checkpoint time; no spec 005 change required? [Completeness, Spec §"Cross-References"]

## Constitution §3 — Sovereignty Five Guarantees

- [ ] CHK025 Is the rule "all five sovereignty guarantees preserved" verified per-guarantee in the spec/plan, not just asserted as a single check? [Verifiability, Plan §"Constitution Check V1"]
- [ ] CHK026 Are the requirements specified for "the filler scorer evaluates output text only; register presets emit prompt deltas only — neither alters participant configuration nor surfaces values across participants"? [Completeness, Plan §"V1"]

## Constitution V14 — Performance Budgets

- [ ] CHK027 Are the three V14 performance budgets specified at sufficient detail (filler scorer P95 ≤ 50ms; slider lookup P95 < 1ms; shaping retry dispatch bounded by hardcoded 2-retry cap)? [Measurability, Spec §"Performance Budgets"]
- [ ] CHK028 Is the `routing_log` instrumentation per FR-011 specified consistently with V14 (the per-stage timing columns enforce the budget)? [Consistency, Spec §FR-011 + "Performance Budgets"]

## Constitution V16 — Configuration Validated at Startup

- [ ] CHK029 Is the V16 deliverable gate (FR-014) specified consistently across spec, plan, contracts, and tasks Phase 2? [Consistency, Spec §FR-014 + Plan §"V16" + Tasks §"V16 deliverable gate"]
- [ ] CHK030 Are the requirements for V16's "validators run BEFORE binding any port" specified as binding for the three new validators? [Completeness, Constitution §V16]

## Constitution V12 — Topology Compatibility

- [ ] CHK031 Is the topology-7 incompatibility specified consistently across spec V12 section, research §10, and quickstart's forward note? [Consistency, Spec §V12 + Research §10 + Quickstart §"Topology-7 forward note"]
- [ ] CHK032 Are the requirements for the topology-7 gate (read `SACP_TOPOLOGY` at shaping pipeline init; skip filler-scorer init AND register-preset emitter; one-time INFO log) specified at sufficient detail to apply consistently? [Clarity, Research §10]

## Constitution V13 — Use Case Coverage

- [ ] CHK033 Is the V13 mapping to use cases §3 (Consulting Engagement) and §2 (Research Paper Co-authorship) specified at sufficient detail to drive the priority ordering of US1 / US2 / US3? [Traceability, Spec §V13]

## Phase 3 Readiness

- [ ] CHK034 Is the Phase 3 declaration prerequisite (recorded 2026-05-05) specified at sufficient detail — the spec is independent of spec 013 / 014 implementation status? [Clarity, Plan §"Notes for /speckit.tasks"]
- [ ] CHK035 Are the requirements for `/speckit.tasks` having run + V16 validators landing BEFORE implementation specified at sufficient detail to apply at task-creation time? [Completeness, Spec §FR-014 + Plan §"V16"]

## Coupling Quality

- [ ] CHK036 Are the cross-spec coupling directions documented (021 depends on 003, 004, 008; 026 depends on 021's boundary statement; consumer specs do NOT inject reverse dependencies)? [Verifiability, Spec §"Cross-References"]
- [ ] CHK037 Is the principle "the orchestrator is authoritative; consumers consult, never override" specified consistently across all cross-spec touchpoints? [Consistency, Spec §FR-001 / FR-007 / FR-008 / FR-010]

## Notes

Highest-impact open items at draft time: CHK020-CHK021 (the relationship between spec 021's per-family `BehavioralProfile` and spec 020's adapter `provider_family` capability is implicit — the spec assumes the participant row carries `provider_family`, which works today but won't survive a future direct-Anthropic adapter without an explicit cross-spec contract), CHK023 (the FR-016 boundary is stated; the task-review enforcement mechanism is implicit), CHK027 (the three V14 budgets are stated but not all three carry the same level of measurability — slider lookup is "by construction"; scorer is "P95 ≤ 50ms" which is testable; retry-dispatch budget is bounded by the cap, which is structural rather than measured). Annotation convention for runs of this checklist: `[PASS]`, `[PARTIAL]`, `[GAP]`, `[DRIFT]`, `[ACCEPTED]`.
