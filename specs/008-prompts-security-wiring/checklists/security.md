# Security Requirements Quality Checklist: System Prompts & Security Wiring

**Purpose**: Validate the quality, clarity, and completeness of security requirements in the System Prompts & Security Wiring spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Feature**: [spec.md](../spec.md)
**Sister checklist**: [requirements.md](requirements.md) (general spec completeness — already passed).
**Cross-feature reference**: [007-ai-security-pipeline/spec.md](../../007-ai-security-pipeline/spec.md) — 008 wires 007's defenses into context assembly and the turn loop. Many items below check whether 008's wording stays consistent with 007's authoritative requirements.

Markers used in findings (apply during audit, before resolution):
- `→ ✅` requirement is adequately specified
- `→ ⚠️ partial` spec addresses some aspect but leaves the rest implicit
- `→ ❌ gap` spec silent; code may or may not address it
- `→ 🐛 drift` spec and shipped code (or sister spec) disagree
- `→ 📌 accepted` gap is documented in spec (assumptions / edge cases) — not a finding, but worth re-evaluating

## Requirement Completeness

- [x] CHK001 Are tier-stacking semantics specified — does `prompt_tier=high` mean low+mid+high concatenated, or only the high-tier delta? [Completeness, Spec §FR-001]
- [x] CHK002 Is the order tier content is concatenated explicitly defined (low → mid → high → max), and is skipping intermediate tiers permitted or forbidden? [Completeness, Spec §FR-001]
- [x] CHK003 Are sanitization requirements specified for the participant-supplied `system_prompt` itself, not just runtime messages? [Completeness, Spec §FR-002, cross-ref 007 §FR-001]
- [x] CHK004 Is the canary placement specified concretely — "near the start" / "in the middle" / "at the end" relative to what (tier text, full prompt, custom prompt)? [Completeness, Spec §FR-003]
- [x] CHK005 Is the canary lifecycle defined (created when, rotated under what conditions, cleared when)? [Completeness, Spec §FR-003, Assumptions]
- [x] CHK006 Is the canary storage model specified (DB column, in-memory session state only, reachable across restarts)? [Completeness, Spec §FR-003, Assumptions]
- [x] CHK007 Is the response defined for when a canary IS detected in output (block, hold for review, terminate session, escalate to facilitator)? [Completeness, Spec §FR-003, Gap]
- [x] CHK008 Are pipeline-failure semantics specified (one layer raises — does the turn proceed, halt, or auto-pause the participant)? [Gap, cross-ref 007 §FR-013]
- [x] CHK009 Is the staging mechanism for high-risk responses defined (DB state, in-memory queue, status field on `messages`)? [Completeness, Spec §FR-008]
- [x] CHK010 Are bypass-path requirements specified (debug routes, direct DB inserts, test fixtures must skip vs MUST go through pipeline)? [Gap, cross-ref 007 §SC-007]

## Requirement Clarity

- [x] CHK011 Is "configurable tiers" in FR-001 quantified — is the tier set fixed at `{low, mid, high, max}` or runtime-configurable, and where does the canonical list live? [Clarity, Spec §FR-001]
- [x] CHK012 Are tier token budgets ("~250", "~520", "~480", "~480") given a tolerance band, or treated as informational only? [Clarity, Spec §FR-001, Assumptions]
- [x] CHK013 Is "the middle of the tier content" deterministic across tier-stack lengths (low-only vs low+mid+high+max) or does the position drift? [Clarity, Spec §FR-003]
- [x] CHK014 Is "16-character base32" specified with the alphabet and case (RFC 4648 upper, lower, padding)? [Clarity, Spec §FR-003]
- [x] CHK015 Is "high-risk" reused from 007 §FR-005 (>= 0.7) or redefined locally in 008? [Clarity, Spec §FR-008, cross-ref 007 §FR-005]

## Requirement Consistency

- [x] CHK016 Does FR-005 ("spotlight AI messages") match 007 §FR-003 (no datamark for same-speaker, system, or human messages)? Is the same-speaker exemption surfaced here or only in 007? [Consistency, Spec §FR-005, cross-ref 007 §FR-003]
- [x] CHK017 Is the FR-006 → FR-007 → (canary check) → stage-for-review order explicit, and does it match 007 §FR-014 layer-precedence wording? [Consistency, Spec §FR-006, FR-007, FR-008, cross-ref 007 §FR-014]
- [x] CHK018 Does FR-002 (custom prompt appended AFTER tier content) conflict with FR-003 (canary "at the end") — does "end" mean end of tier content or end of full assembled prompt including custom? [Conflict, Spec §FR-002, §FR-003]
- [x] CHK019 Is the canary multi-canary count consistent — FR-003 says "three", clarification §1 says "3 positions (start/mid/end)", Assumptions repeats "three". Any drift to single-canary anywhere? [Consistency, Spec §FR-003]
- [x] CHK020 Does the spec wording assume `system_prompt` is trusted operator-controlled content, while runtime messages are untrusted? Is that trust gradient stated explicitly? [Consistency, Spec §FR-002, FR-004]

## Acceptance Criteria Quality

- [x] CHK021 Can SC-001 ("correct token counts for each tier") be objectively measured without a defined tolerance and a defined tokenizer? [Measurability, Spec §SC-001]
- [x] CHK022 Is SC-002 ("every context assembly call") testable against a fixture set, or does "every" rely on grep over the codebase? [Measurability, Spec §SC-002]
- [x] CHK023 Is canary-leak detection covered by an SC at all (SC-003 only mentions "output validation runs")? [Coverage, Gap, Spec §SC-003]
- [x] CHK024 Are pipeline-failure success criteria defined (zero silent drops, fail-closed turn count)? [Acceptance Criteria, Gap]

## Scenario Coverage

- [x] CHK025 Are recovery requirements defined for canary leak detection — does the response re-run through the pipeline after facilitator edit, get persisted as-is, or get blocked? [Coverage, Recovery Flow, cross-ref 007 §FR-005]
- [x] CHK026 Are exception flows specified for tier assembly errors (missing tier file, malformed tier content, tier file removed at runtime)? [Coverage, Exception Flow, Gap]
- [x] CHK027 Are concurrent-canary-leak scenarios addressed (two canaries detected in one response — which wins for audit attribution)? [Coverage, Gap]
- [x] CHK028 Is the system prompt re-assembly cadence specified (every turn, cached per session, invalidated on what)? [Coverage, Spec §FR-001, Gap]

## Edge Case Coverage

- [x] CHK029 Are requirements specified for tier content that itself contains canary-shaped strings (16-char base32) — false-positive collision? [Edge Case, Gap]
- [x] CHK030 Are requirements defined for the case where a custom `system_prompt` is empty AND no tier is configured? [Edge Case, Spec §FR-001, FR-002]
- [x] CHK031 Are requirements defined for the case where the assembled prompt (tiers + custom + canaries) exceeds a small model's context window? Edge Cases mentions "MVC floor check" but not the spec contract. [Edge Case, Spec §Edge Cases]
- [x] CHK032 Are requirements defined for sanitization of the assembled SYSTEM prompt (not just runtime messages) — could a malicious custom prompt embed ChatML markers that survive into dispatch? [Edge Case, Gap, cross-ref 007 §FR-001]
- [x] CHK033 Could spotlighting datamarks (`^hexhex^...`) be confused with canary tokens (16-char base32) by either detector? Is the disambiguation rule specified? [Edge Case, Gap, Spec §FR-003, FR-005]

## Non-Functional Requirements

- [x] CHK034 Are performance requirements specified for prompt assembly per turn (each turn re-runs assembly — what's the latency target)? [Performance, Gap]
- [x] CHK035 Is the threat-model traceability for 008's wiring documented, or does it inherit 007's table without cross-reference? [Traceability, Gap, cross-ref 007 "Threat model traceability"]
- [x] CHK036 Are auditability requirements specified for canary detections (does FR-015 of 007 cover canary findings here)? [Coverage, Gap, cross-ref 007 §FR-015]
- [x] CHK037 Are accessibility requirements specified for the staged-for-review surface (008 introduces it via FR-008 but doesn't speak to UI surface)? [Coverage, Gap]

## Dependencies & Assumptions

- [x] CHK038 Is the Assumption "tier content is constant text in Phase 1" paired with a re-evaluation trigger (when does dynamic tier content become required)? [Assumption, Spec Assumptions]
- [x] CHK039 Is the Assumption "tier token budgets are approximate" paired with a hard cap (when does "approximate" become a budget violation)? [Assumption, Spec Assumptions]
- [x] CHK040 Is the dependency on `secrets.token_bytes(10)` for canary entropy explicit, including the rationale (why 10 bytes / 16 base32 chars and not more/less)? [Dependency, Clarification §1]

## Ambiguities & Conflicts

- [x] CHK041 Does "high-risk responses are staged" in FR-008 imply DB persistence with a status flag, or in-memory queueing? Wording is silent. [Ambiguity, Spec §FR-008]
- [x] CHK042 Is "datamarked with the source participant's ID" in US2 §2 specifying the literal participant_id, or a derived marker (007 uses 6-char SHA-256 prefix)? [Ambiguity, Spec §US2, cross-ref 007 §FR-002]
- [x] CHK043 Is "exfiltration filtering on AI responses" in FR-007 the same set of patterns as 007 §FR-008 (now including Gemini/Groq), or a subset? [Ambiguity, Spec §FR-007, cross-ref 007 §FR-008]
- [x] CHK044 Does "stage for review" in FR-008 mean the same operator-notification path as 007 §FR-016 (review-gate banner + security_events row + WS routing_mode event), or a different surface? [Ambiguity, Spec §FR-008, cross-ref 007 §FR-016]

## Notes

- The cross-references to 007 are deliberate — 008 is the wiring spec, so its requirements quality is bounded by how cleanly it imports 007's contracts. Anywhere 008 restates a 007 requirement in different words is a drift risk.
- Highest-leverage findings to expect: CHK003 (custom-prompt sanitization), CHK007 (canary-detection response), CHK008 (pipeline-failure semantics), CHK032 (assembled-prompt sanitization), CHK044 (review-staging path consistency with 007's FR-016).
- Lower-priority but easy wins: CHK013/CHK014 (canary placement and base32 alphabet), CHK015/CHK017 (precedence + threshold inheritance from 007), CHK040 (entropy rationale).
- Run audit by reading [src/prompts/](../../../src/prompts/), [src/orchestrator/context.py](../../../src/orchestrator/context.py), and the turn-loop output-validation hook, cross-referencing against this spec's requirements / assumptions / edge cases AND 007's spec.
