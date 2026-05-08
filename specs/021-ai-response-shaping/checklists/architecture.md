# Architecture Quality Checklist: AI Response Shaping (Verbosity Reduction + Register Slider)

**Purpose**: Validate that spec 021's design — the filler-scorer pipeline, the register-preset registry, the state-resolution model, and the spec-004 hook — is specified at sufficient detail that two implementers would produce equivalent module shapes. This checklist tests architectural-specification quality, not the implementation.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md) + [plan.md](../plan.md) + [research.md](../research.md) + [data-model.md](../data-model.md) + [contracts/filler-scorer-adapter.md](../contracts/filler-scorer-adapter.md) + [contracts/register-preset-interface.md](../contracts/register-preset-interface.md)

## Filler-Scorer Pipeline Decomposition

- [ ] CHK001 Are the three signal helpers (`_hedge_signal`, `_restatement_signal`, `_closing_signal`) each defined with full signatures (parameter names, types, return-type contract, normalization range)? [Completeness, Contracts §"Three signal helpers"]
- [ ] CHK002 Is the contract for each signal helper's empty-input behavior specified (empty draft, empty embedding ring buffer, zero closing matches)? [Completeness, Contracts §"Three signal helpers"]
- [ ] CHK003 Is the rule "the three signal helpers do not call each other" specified at sufficient detail to prevent accidental coupling during implementation? [Clarity, Contracts §"No cross-signal coupling"]
- [ ] CHK004 Is the boundary between "signal helper" (returns float in `[0.0, 1.0]`) and "aggregator" (weighted sum) defined precisely enough to keep signals independently testable per US1 acceptance scenarios? [Clarity, Contracts §"Aggregation"]

## Aggregator and Per-Family Profile Dispatch

- [ ] CHK005 Is the `BehavioralProfile` dataclass shape (five fields: `default_threshold`, `hedge_weight`, `restatement_weight`, `closing_weight`, `retry_delta_text`) specified consistently across spec, research, data-model, and contracts? [Consistency, Data-model §BehavioralProfile + Research §1]
- [ ] CHK006 Is the rule "the three weights MUST sum to 1.0 per family" specified as a module-load assertion contract, with the failure mode documented? [Completeness, Contracts §"Aggregation"]
- [ ] CHK007 Is the `BEHAVIORAL_PROFILES` dict's lookup-key contract specified (provider-family string source, case sensitivity, missing-family failure mode — fail-loud KeyError per contracts)? [Clarity, Contracts §"Per-family BehavioralProfile dispatch"]
- [ ] CHK008 Are the requirements for `BehavioralProfile` immutability documented (frozen dataclass, module-level constant, no mutation post-load)? [Completeness, Data-model §"Lifetime"]

## Retry Orchestration

- [ ] CHK009 Is `evaluate_and_maybe_retry`'s return tuple `(persisted_draft, decision, retries_consumed)` shape specified at sufficient detail to wire into `loop.py`'s dispatch path? [Clarity, Contracts §"Retry orchestration"]
- [ ] CHK010 Is the joint-cap rule (whichever of `SHAPING_RETRY_CAP=2` or `compound_budget_remaining` reaches zero first) specified consistently across FR-004, FR-006, research §4, and the contract? [Consistency, Spec §FR-006 + Research §4]
- [ ] CHK011 Are the requirements for retry-delta source specified (`profile.retry_delta_text` per family — uniform Direct text in v1, per-family room reserved for future) so that an implementer doesn't accidentally hardcode a single string? [Completeness, Research §1]
- [ ] CHK012 Is the rule "per-attempt budget consumption (not pre-debit-the-worst-case)" specified clearly enough to prevent regression? [Clarity, Research §4]

## Register-Preset Registry

- [ ] CHK013 Is the `RegisterPreset` dataclass shape (three fields: `slider`, `name`, `tier4_delta` with `tier4_delta=None` for slider 3) specified consistently across spec FR-013, data-model, and the contract? [Consistency, Spec §FR-013 + Contracts §"Registry shape"]
- [ ] CHK014 Are the canonical `tier4_delta` strings for sliders 1, 2, 4, 5 specified verbatim, with slider 3's None contract called out explicitly? [Completeness, Spec §FR-013 + Data-model §RegisterPreset]
- [ ] CHK015 Are the lookup-helper contracts (`preset_for_slider`, `preset_for_name`) documented with O(1) cost characteristics and failure modes (ValueError vs KeyError)? [Clarity, Contracts §"Lookup helpers"]
- [ ] CHK016 Is the rule "registry is a 5-element tuple with `REGISTER_PRESETS[slider - 1]` indexing" specified at sufficient detail to satisfy V14 budget 2 (P95 < 1ms slider lookup) by construction? [Measurability, Contracts §"Lookup helpers"]

## State-Resolution Architecture (override / session / default)

- [ ] CHK017 Is the resolver's three-layer precedence (override row → session row → `SACP_REGISTER_DEFAULT`) specified consistently across FR-007/FR-008/FR-009/FR-010, research §5, and the contract? [Consistency, Research §5 + Contracts §"Resolver"]
- [ ] CHK018 Is the SQL JOIN pattern (LEFT JOIN to `participant_register_override`, LEFT JOIN to `session_register`, COALESCE) specified at sufficient detail to mechanically apply? [Clarity, Research §5 + Data-model §"Register-resolution at /me query time"]
- [ ] CHK019 Is the source-attribution rule specified at sufficient detail to distinguish `'session'` (row exists OR row absent → env-default) vs `'participant_override'` (row exists)? [Clarity, Research §5]
- [ ] CHK020 Are the requirements for resolver re-use specified (`/me` query path AND per-turn dispatch path call the same resolver — no divergence)? [Completeness, Research §5 + Contracts §"Prompt-assembly integration"]

## Spec 004 Hook Design

- [ ] CHK021 Is the `last_embedding` property + `recent_embeddings(depth)` helper contract specified with sufficient detail (single-line additions in `convergence.py`, ring buffer with `maxlen=3`, byte-array return type matching the existing `convergence_log.embedding` column)? [Completeness, Research §2 + Data-model §"Hooks introduced"]
- [ ] CHK022 Is the dependency direction documented (021 → 004, never reversed — the signal-computation stays in `shaping.py`)? [Clarity, Research §2 "Alternatives considered"]
- [ ] CHK023 Are the requirements for the candidate draft's freshly-computed embedding specified (reuses the already-loaded sentence-transformers model on the orchestrator's existing thread-pool executor; no second model load per FR-012)? [Completeness, Research §2]
- [ ] CHK024 Is the contract "single-point change at line 177 of `convergence.py` mirroring spec 014's `last_similarity` precedent" specified at sufficient fidelity to apply consistently? [Traceability, Research §2]

## No Cross-Pipeline Coupling (FR-016 Compression Boundary)

- [ ] CHK025 Is FR-016's boundary ("the shaping pipeline MUST NOT introduce new compression of stored content") specified at sufficient detail that an implementer can mechanically reject any task that touches `messages.content` or the rolling context window? [Clarity, Spec §FR-016]
- [ ] CHK026 Is the rule "retry's output replaces the original draft BEFORE persistence; once persisted, content is immutable per spec 001 §FR-008" specified consistently across FR-016 and the cross-spec section? [Consistency, Spec §FR-016 + "Cross-References"]
- [ ] CHK027 Are the requirements for spec 026's scope boundary (the *persisted* representation lives in spec 026; the *generated* draft lives here) specified at sufficient detail to prevent accidental scope creep at task time? [Completeness, Spec §"Compression boundary"]

## Module Boundaries

- [ ] CHK028 Are the responsibilities of each new/modified module (`src/orchestrator/shaping.py`, `src/prompts/register_presets.py`, `src/repositories/register_repo.py`, `src/orchestrator/convergence.py` extension) specified with non-overlapping scope? [Clarity, Plan §"Source Code"]
- [ ] CHK029 Is the rule "the scorer is a pure function — no DB writes, no side effects" specified as a binding contract for `compute_filler_score`? [Completeness, Contracts §"Top-level entry point"]
- [ ] CHK030 Are the imports between `src/orchestrator/shaping.py`, `src/prompts/register_presets.py`, and `src/repositories/register_repo.py` documented as a directed acyclic dependency? [Gap, Plan §"Source Code"]

## Topology-7 Architectural Skip Path

- [ ] CHK031 Is the topology-7 gate's behavior specified at sufficient detail (read `SACP_TOPOLOGY` at shaping pipeline init, skip filler-scorer init AND register-preset emitter, one-time INFO log)? [Clarity, Research §10]
- [ ] CHK032 Are the requirements for the topology-7 gate as "aspirational dead code until topology 7 ships and a topology-selection mechanism exists" specified clearly enough to prevent confusion at implementation time? [Clarity, Research §10]
- [ ] CHK033 Is the contract "V16 validators run unconditionally; the topology gate is at the consumer, not the validator" specified to prevent the gate from leaking up into the validator layer? [Completeness, Research §10]

## Master-Switch Architectural Placement

- [ ] CHK034 Is the location at which `SACP_RESPONSE_SHAPING_ENABLED=false` short-circuits specified clearly (in `loop.py`'s post-dispatch stage, before `evaluate_and_maybe_retry` is called)? [Clarity, Plan §"Source Code" + Tasks §T029]
- [ ] CHK035 Is the rule "slider deltas always emit regardless of master switch" specified consistently across spec edge case, research, and contract — and traceable to a specific code location (the resolver runs unconditionally on every prompt assembly)? [Consistency, Spec §"Edge Cases" + Contracts §"Independence from the master switch"]
- [ ] CHK036 Are the requirements for SC-002 byte-identical regression specified at sufficient detail for the canary test (T017) to reliably detect a leak (no spec 021 shaping code path fires when disabled)? [Measurability, Spec §SC-002 + Tasks §T017]

## Documentation Quality

- [ ] CHK037 Is the contract documentation in `contracts/` self-contained (a reader can implement the scorer + resolver without consulting other repo files)? [Completeness, Contracts §*]
- [ ] CHK038 Are the contract docs traceable from the spec (each FR-001 through FR-016 maps to one or more contract sections)? [Traceability]

## Notes

Highest-impact open items at draft time: CHK010 (joint-cap consistency across spec/research/contract — the rule is correct but stated three times; drift between them is the highest-risk regression vector), CHK030 (the directed-acyclic-dependency contract between the three new modules is implicit, not stated), CHK034 (the exact short-circuit location for the master switch should be unambiguous to prevent accidental leak when SC-002 canary is the only guard). Annotation convention for runs of this checklist: `[PASS]`, `[PARTIAL]`, `[GAP]`, `[DRIFT]`, `[ACCEPTED]`. `[GAP]` marks items where no requirement exists in the spec/contracts; `[DRIFT]` marks items where the spec, plan, research, data-model, and contracts disagree among themselves.
