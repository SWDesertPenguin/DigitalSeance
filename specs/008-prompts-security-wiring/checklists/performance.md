# Performance Requirements Quality Checklist: Prompts & Security Wiring

**Purpose**: Validate the quality, clarity, and completeness of performance requirements in the Prompts & Security Wiring spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Audited**: 2026-04-29
**Feature**: [spec.md](../spec.md)

**Audit summary**: 4 items pass cleanly, 24 have findings. This spec is a wiring layer — it composes prompts (008 FR-001-003) and runs the 007 pipeline at well-defined points. Most perf characteristics defer to the underlying components (007 pipeline, 003 turn loop). The unique perf surface here: the per-turn cost of tier assembly + sanitization on custom_prompt + canary embedding + spotlighting on every cross-speaker message.

## Tier Assembly

- [x] CHK001 Is the per-turn tier-assembly latency bounded?
  [GAP]. FR-001 cumulative delta concatenation is O(tier-text-size) string ops. Sub-ms in practice but unspecified.

- [x] CHK002 Is the SC-001 token-count target (+/- 15% of low/mid/high/max budgets) measured at construction or at dispatch?
  [GAP]. SC-001 uses rough estimator `max(len(text) // 4, 1)`. Unclear whether check runs every turn or once per session.

- [x] CHK003 Is the assembled-prompt size memory-bounded?
  [PARTIAL]. Edge cases mention MVC floor catches over-budget participants. Memory cost of an in-flight 1730-token (max tier) prompt is bounded but unsurfaced.

## Per-Turn Sanitization on Custom Prompt

- [x] CHK004 Is the FR-002 sanitization on custom_prompt latency bounded per turn (or memoized)?
  [GAP]. Custom prompt rarely changes; sanitizing it every turn is wasted work. Spec doesn't specify whether to memoize at participant-update time.

- [x] CHK005 Is the FR-004 runtime message sanitization cost in context assembly bounded by message count × message size?
  [GAP]. Cross-ref 003 CHK002 (context-assembly latency unspecified). With `SACP_CONTEXT_MAX_TURNS=20` × per-message sanitize, cost grows with history depth.

## Canary Embedding

- [x] CHK006 Is the FR-003 three-canary embedding (per assembly) latency bounded?
  [GAP]. `secrets.token_bytes(10)` × 3 + base32 encode + 3 string-join points = sub-ms but unspecified.

- [x] CHK007 Is the canary-storage cost specified (FR-003 notes "per-session canary persistence ... is tracked as a Phase 3 follow-up")?
  [PARTIAL]. The deferral is documented; when wiring lands, per-session canary table writes will add latency. No reservation in current budget.

- [x] CHK008 Is the FR-003.detect deferred check, when wired, latency-budgeted?
  [GAP]. Cross-ref 007 CHK007 — same shape: prompt_protector latency unspecified.

## Spotlighting (Cross-Reference 007 FR-002)

- [x] CHK009 Is the FR-005 spotlighting cost (per cross-speaker AI message) bounded?
  [GAP]. Cross-ref 007 CHK003 — per-word marker insertion, O(words). For a 20-turn history × 4 AI participants, every turn the assembler runs spotlighting on ~15-20 messages = O(words × messages).

- [x] CHK010 Is the FR-005 same-speaker exemption (don't spotlight an AI's own messages) a documented optimization?
  [PARTIAL]. The exemption is correctness, not perf — but its perf benefit (skip spotlighting on N% of messages) isn't surfaced.

## Output Validation & Exfiltration (Cross-Reference 007)

- [x] CHK011 Is the FR-006/FR-007 cost (validate + exfiltration on every AI response, every turn) cross-referenced to 007's <50ms aggregate target?
  [GAP]. 008 spec is silent; 007 CHK001 already flags the budget decomposition gap.

- [x] CHK012 Is the FR-008 staging path (review-gate draft INSERT + 3 notification surfaces) latency-bounded?
  [GAP]. Stage involves DB write + WS event broadcast + security_events row. Not specified.

## Compound Cost Per Turn

- [x] CHK013 Is the per-turn cost of THIS wiring decomposed: tier assembly + sanitize messages + sanitize custom_prompt + spotlight cross-speakers + canary embed + run pipeline?
  [GAP]. Each step bounded individually (ish, mostly via 007 cross-refs); aggregate cost across the wiring is not surfaced.

- [x] CHK014 Is the cost reconciled with 003 FR-019 turn-timeout budget?
  [GAP]. 003 CHK001 (decompose end-to-end) would surface this; 008 doesn't independently account.

## Cold-Start

- [x] CHK015 Is the first-assembly latency (tier text loaded once at module init) specified?
  [GAP]. `src/prompts/tiers.py` loaded at import; trivial cost but unsurfaced.

## Throughput / Concurrency

- [x] CHK016 Is concurrent-assembly cost specified (multiple sessions × per-turn assembly)?
  [GAP]. Each turn re-assembles its participant's prompt; no shared cache for tier-set output (which is identical for any participant of the same prompt_tier).

- [x] CHK017 Is the tier-text shared across sessions (read-only constant) or copied per assembly?
  [GAP]. Memoizable: tier+canary insertion points are deterministic given prompt_tier; only the canary values differ per assembly. Unsurfaced as an optimization opportunity.

## Memory Footprint

- [x] CHK018 Is the in-memory cost of N concurrent assemblies bounded?
  [GAP]. Each assembly = ~1.7KB max + canaries; with 100 sessions × 4 participants, ~700KB worst case. Bounded but unsurfaced.

- [x] CHK019 Is the per-session canary-store memory cost specified (when FR-003.detect lands)?
  [GAP]. Phase 3 work; budget should be pre-allocated.

## Degradation Under Load

- [x] CHK020 Is the system's behavior specified when sanitization takes longer than expected (e.g. crafted inputs that trip catastrophic backtracking in regexes)?
  [GAP]. Cross-ref 007 — pattern lists are open-ended. Future patterns could introduce ReDoS risk; spec is silent.

- [x] CHK021 Is the FR-009 fail-closed path (security_pipeline_error skip) latency-bounded?
  [GAP]. Cross-ref 003 CHK036 + 007 CHK011 — same shape.

## Measurement & Instrumentation

- [x] CHK022 Is per-stage timing required for the wiring (assembly vs. sanitize vs. spotlight vs. pipeline)?
  [GAP]. Cross-ref 007 CHK027 (same shape).

- [x] CHK023 Is a benchmark fixture required (assembled prompt for each tier × per-turn assembly cost)?
  [GAP].

- [x] CHK024 Is per-tier assembly cost reported in CI to track budget creep?
  [GAP]. SC-001 token-count target is observational; perf cost isn't measured.

## Trade-offs & Assumptions

- [x] CHK025 Is the trade-off between per-turn re-assembly (current) and assembly memoization (potential optimization) documented?
  [GAP].

- [x] CHK026 Is the trade-off between fixed tier set (FR-001 hardcoded) and runtime-configurable tiers documented as a perf knob?
  [GAP]. Phase 1 hardcodes; Phase 3 trigger is "operator demand for custom tiers" but not a perf trigger.

- [x] CHK027 Is the assumption that "tier text is fixed English prose and doesn't need sanitization" (FR-002) cross-referenced as a perf optimization?
  [PARTIAL]. The reasoning is documented (security: trust source). Perf benefit (skip sanitize on the largest portion of the prompt) is implicit.

- [x] CHK028 Is the canary-uniqueness check (FR-003 "Canaries MUST be unique per assembly") bounded?
  [PARTIAL]. With 80-bit entropy, collision probability is astronomical; uniqueness check is trivial. Spec doesn't pin whether this is a runtime check or a statistical guarantee.

## Notes

- 28 items audited. 008 is mostly a wiring spec; perf is largely an aggregation of 007's surface plus a thin per-turn assembly tax.
- Highest-leverage findings to convert into spec amendments:
  - CHK013 (per-turn wiring cost decomposed — clarifies what 008 contributes vs. what's in 007).
  - CHK004 (memoize sanitization on custom_prompt — wasted work today).
  - CHK017 (memoize per-tier text — minor but real).
  - CHK020 (ReDoS risk on user-controlled inputs — pattern list is open per 007 FR-017).
  - CHK022 / CHK023 (instrumentation + benchmark — cross-ref 003, 004, 007 all share this gap).
- Lower-priority but useful:
  - CHK007 / CHK019 (pre-allocate budget for FR-003.detect when wiring lands).
  - CHK010 / CHK027 (surface implicit perf benefits of correctness rules).
- Sister checklists: `requirements.md`, `security.md` already on main. Cross-refs throughout to 007 (the actual security work) and 003 (the turn-loop integration point).

## Closeout (2026-04-29)

Spec amendments to 008 close the highest-leverage GAPs:

- **CHK001** (per-turn tier-assembly latency bounded) closed by FR-011 (memoization) + SC-005 (tier_assembly_ms <= 1ms P95).
- **CHK004** (memoize sanitize on custom_prompt) closed by FR-012 (memoize at participant-update boundary, not per turn).
- **CHK013** (per-turn wiring cost decomposed) closed by FR-013 (per-stage timings to routing_log) + SC-005 (per-stage P95 budgets).
- **CHK017** (memoize per-tier text) closed by FR-011 (4-entry cache, invalidate on process restart only).
- **CHK020** (ReDoS risk on user-controlled inputs) closed by FR-014 (every regex MUST be ReDoS-verified on 10KB pathological input; >100ms = reject).
- **CHK022** (per-stage timing required for wiring) closed by FR-013.
- **CHK025** (memoization trade-off documented) closed by FR-011 + FR-012 + SC-006 (memoization-effectiveness check).

Items remaining [GAP]:

- CHK023 (benchmark fixture) same shape across all 7 perf checklists.
- CHK005 / CHK009-010 (compound runtime sanitize cost, spotlighting cost on every cross-speaker message) partially addressed by SC-005 per-stage budgets.
- CHK006-008 (canary embedding cost, per-session storage when wired) addressed by existing FR-003 deferral; perf budget pre-allocated.

Implementation of FR-011 / FR-012 / FR-013 / FR-014 / SC-005 / SC-006 ships as a follow-up PR (memoization caches, ReDoS test fixture).
