# Security Requirements Quality Checklist: AI Response Shaping (Verbosity Reduction + Register Slider)

**Purpose**: Validate that spec 021's security requirements (FR-016 no-content-compression boundary, content-privacy in audit shapes, facilitator-only mutation rights, sovereignty preservation, threat model alignment) are specified clearly, completely, and consistently with the SACP Constitution. This checklist tests the security-requirement quality, not the implementation security.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md) + [plan.md](../plan.md) + Constitution §3, §V8, §V10, §V19

## FR-016 — No-Content-Compression Boundary

- [ ] CHK001 Is the rule "the shaping pipeline (FR-001 through FR-006) MUST NOT introduce new compression of stored content" specified as binding, with the boundary explicitly drawn at `messages.content`, the `messages.content` column, and the rolling context window? [Completeness, Spec §FR-016]
- [ ] CHK002 Is the boundary between "scorer reads in-flight draft text to compute three signals" and "scorer never modifies persisted content" specified at sufficient detail to prevent regression? [Clarity, Spec §FR-016 + Plan §"V8"]
- [ ] CHK003 Are the requirements for "the retry's output replaces the original draft BEFORE persistence; once persisted, content is immutable per spec 001 §FR-008" specified consistently across FR-016, the assumption section, and the cross-spec section? [Consistency, Spec §FR-016 + "Assumptions" + "Cross-References"]
- [ ] CHK004 Is the rule "any task that touches `messages.content`, the rolling context window, or the persisted message body belongs to spec 026" specified at sufficient detail to apply at task-review time? [Verifiability, Plan §"Notes for /speckit.tasks"]

## Filler-Scorer Content Privacy

- [ ] CHK005 Is the rule "the scorer never reads message body content beyond what the three signals need" specified clearly enough to prevent scope creep into deeper content inspection? [Clarity, Plan §"V8"]
- [ ] CHK006 Are the requirements for the three signals' content scope specified (hedge ratio reads tokens; restatement reads embedding bytes; closing reads regex-matched substrings — none read or store full content beyond the signal computation)? [Completeness, Contracts §"Three signal helpers"]
- [ ] CHK007 Is the contract for the scorer's lifetime over content specified (in-memory only during evaluation; immediately discarded after `FillerScore` is returned; not persisted)? [Completeness, Plan §"V8" + Data-model §"FillerScore"]
- [ ] CHK008 Are the requirements for the scorer's pure-function contract (no side effects, no DB writes) specified at sufficient detail to prevent accidental persistence of intermediate signals? [Clarity, Contracts §"Top-level entry point"]

## Audit-Log Content Scope (admin_audit_log)

- [ ] CHK009 Is the rule "audit events MUST NOT carry shaped content; they carry only slider values, preset names, and timestamps" specified at sufficient detail across the three new event types? [Completeness, Contracts §"audit-events.md" + Data-model §"DB-persistent audit shapes"]
- [ ] CHK010 Is the contract for `previous_value` / `new_value` JSON shapes specified to carry only `slider_value` (int) and `preset` (canonical name string) — never message content, never participant content, never any signal value? [Completeness, Contracts §"audit-events.md"]
- [ ] CHK011 Are the requirements for `participant_register_override_set`'s `session_slider_at_time` field specified to be informational only (NOT carrying content)? [Clarity, Research §8 + Contracts §"audit-events.md"]
- [ ] CHK012 Is the rule "cascade-deletes do NOT emit `participant_register_override_cleared`" specified to prevent audit-log flooding on session delete (which would also be a content-leak risk if the event payload ever expanded)? [Completeness, Research §8]

## Routing-Log Content Scope

- [ ] CHK013 Is the rule "the `shaping_retry_delta_text` column carries operator-controlled fixed text only (the per-family `retry_delta_text` from the BehavioralProfile)" specified at sufficient detail to prevent participant content from ever entering the column? [Clarity, Data-model §"routing_log extension" + Contracts §"Per-stage cost capture"]
- [ ] CHK014 Are the requirements for `filler_score`, `shaping_score_ms`, `shaping_retry_dispatch_ms`, and `shaping_reason` columns specified — these are derived signals/timings, NOT content — and document any leakage risk if a future expansion adds content-derived columns? [Gap, Data-model §"routing_log extension"]
- [ ] CHK015 Is the contract for `routing_log` retention specified consistently with existing spec 003 retention (no spec-021-specific retention divergence)? [Gap]

## Facilitator-Only Mutation Rights (Authorization Model)

- [ ] CHK016 Is the rule "session-level slider AND per-participant override are facilitator-only mutations" specified consistently across FR-008, FR-009, the audit-events contract, and the operator authority boundary in quickstart? [Consistency, Spec §FR-008 + FR-009 + Quickstart §"Operator authority boundary"]
- [ ] CHK017 Are the requirements for the facilitator-only auth guard on the new MCP-server endpoints specified at sufficient detail (`set_session_register`, `set_participant_register_override`, `clear_participant_register_override` mirror existing facilitator endpoints' auth pattern)? [Completeness, Tasks §T040 + T052]
- [ ] CHK018 Is the contract for `set_by_facilitator_id` capture specified (every set/clear records which facilitator made the change for forensic review)? [Completeness, Data-model §"session_register" + "participant_register_override"]
- [ ] CHK019 Are the requirements for "facilitator personnel changes mid-session" specified — the audit row's `facilitator_id` is the facilitator who made the change, not the session facilitator at large? [Clarity, Contracts §"audit-events.md" §"Cross-cutting"]

## Constitution §3 — Sovereignty Preservation

- [ ] CHK020 Is the rule "no change to API key isolation, model choice, budget autonomy, prompt privacy, or exit freedom" specified consistently across plan §"V1" and the cross-spec section? [Consistency, Plan §"V1"]
- [ ] CHK021 Are the requirements for "the filler scorer evaluates output text only; register presets emit prompt deltas only — neither alters participant configuration nor surfaces values across participants" specified at sufficient detail? [Completeness, Plan §"V1"]
- [ ] CHK022 Is the contract for "register slider does not leak participant identity across the session" specified (slider/override changes are facilitator-visible via `/me` and audit log; but the slider value itself is per-session/per-participant state, not cross-participant state)? [Gap]

## Constitution V8 — Trust-Tiered Content (Tier 4)

- [ ] CHK023 Is the rule "Tier 4 deltas (register preset + shaping retry) land at the existing prompt-assembler hook (spec 008 §FR-008); the security pipeline (sanitization, canary placement) is unchanged" specified at sufficient detail? [Completeness, Plan §"V3" + V10]
- [ ] CHK024 Are the requirements for "Tier 4 is operator-injected text — make sure it's not crossing tiers" specified clearly enough to prevent regression of the security pipeline? [Clarity, Plan §"V10"]
- [ ] CHK025 Is the contract "the shaping retry's tightened delta is fixed-text Tier 4 (FR-013, Direct preset's text); no learned per-model deltas in v1" specified at sufficient detail to prevent scope creep into adaptive content? [Completeness, Plan §"V10" + Spec §"Assumptions"]
- [ ] CHK026 Are the requirements for "the canary embedding still wraps the assembled output" specified as binding to prevent regression of inbound-prompt protections? [Completeness, Contracts §"Prompt-assembly integration"]

## Constitution V10 — AI Security Pipeline

- [ ] CHK027 Is the rule "the tightened delta passes through the same canary-placed prompt assembly as the original draft" specified at sufficient detail to prevent the retry path from bypassing security? [Clarity, Plan §"V10"]
- [ ] CHK028 Are the requirements for "the shaping retry never re-runs sanitization on already-clean tier text" specified to prevent double-sanitization regressions? [Completeness, Plan §"V3"]

## Threat Model — Operator vs Participant

- [ ] CHK029 Is the threat "could a participant manipulate output to game the scorer (e.g., produce text that scores artificially low while still being filler-heavy)" addressed in the spec or research? [Gap]
- [ ] CHK030 Is the threat "could a facilitator weaponize register (e.g., set slider to 5 Academic for a participant who can't read formal text)" addressed — the audit log captures every change, but is the surface mitigated beyond auditability? [Gap]
- [ ] CHK031 Are the requirements for "the per-participant override is an escape hatch; misuse is detectable via audit-log review" specified at sufficient detail? [Clarity, Spec §US3 priority rationale]
- [ ] CHK032 Is the threat "filler-scorer signal lists (`_HEDGE_TOKENS`, `_CLOSING_PATTERNS`) are hardcoded — could a malicious actor file an amendment that adds participant-content tokens to the list" addressed (the constitutional amendment process is the gate)? [Gap, Plan §"V8" + Constitution §14.2]

## Fail-Closed Semantics

- [ ] CHK033 Are the fail-closed requirements for the three new validators specified consistently across FR-014, SC-008, and the contracts? [Consistency, Spec §FR-014 + SC-008 + Contracts §"SACP_*"]
- [ ] CHK034 Is the contract for scorer-internal failures (regex bug, embedding read failure, sentence-transformers unavailable) specified at sufficient detail across spec edge cases, the contract's fail-closed table, and tasks T054? [Consistency, Spec §"Edge Cases" + Contracts §"Fail-closed contract" + Tasks §T054]
- [ ] CHK035 Is the rule "session continues on every fail-closed path; one bad draft does not gate the loop" specified at sufficient detail to set expectation that fail-closed here means "drop the retry, persist the original" not "stop the session"? [Clarity, Spec §"Edge Cases"]

## Audit & Forensics

- [ ] CHK036 Are the requirements for audit-log capture of every register change specified consistently across FR-008, FR-009, and the audit-events contract? [Consistency, Spec §FR-008 + FR-009 + Contracts §"audit-events.md"]
- [ ] CHK037 Is the contract for `routing_log` per-shaping-decision audit specified to be separate from `admin_audit_log` register-change audit (the two surfaces serve different purposes — per-turn shaping decisions vs facilitator-action register changes)? [Clarity, Contracts §"audit-events.md" §"Cross-cutting"]

## V19 Evidence and Judgment Markers

- [ ] CHK038 Are the factual claims in the spec (Phase 1+2 shakedown observations, ~30-50% output-token waste on reasoning-heavy turns, ≥ 15% reduction target on flagged drafts) cited per V19 or marked as `[OBSERVATION]` / `[ASSUMPTION]`? [Traceability, Constitution V19]
- [ ] CHK039 Are the judgment-call statements in the spec (per-family threshold split, hedge token list, closing pattern list) marked as `[JUDGMENT]` or rendered as facts? [Verifiability, Constitution V19]

## Notes

Highest-impact open items at draft time: CHK022 (register slider as cross-participant identity-leak vector — the slider value is per-session/per-participant state but visible to all participants via their own `/me`; the spec doesn't address whether this constitutes a sovereignty concern), CHK029-CHK032 (the threat model for "participant gaming the scorer" and "facilitator weaponizing register" is implicit; the audit log is the only mitigation specified), CHK015 (`routing_log` retention is unspecified relative to the new shaping columns; might inherit spec 003's existing retention but the contract is silent). Annotation convention for runs of this checklist: `[PASS]`, `[PARTIAL]`, `[GAP]`, `[DRIFT]`, `[ACCEPTED]`. The threat-model gaps (CHK029-CHK032) likely warrant `[ACCEPTED]` rather than `[GAP]` — the spec deliberately scopes threat-model rigor to the audit-log/auditability mitigation, leaving deeper analysis for a future hardening pass.
