# Security Requirements Quality Checklist: Summarization Checkpoints

**Purpose**: Validate the quality, clarity, and completeness of security requirements in the Summarization Checkpoints spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Feature**: [spec.md](../spec.md)
**Sister checklist**: [requirements.md](requirements.md) (general spec completeness — already passed).
**Cross-feature reference**: A summary becomes context for ALL subsequent turns. A poisoned summary persists indefinitely. This checklist treats summary content with the same trust weight as system prompt content.

Markers used in findings (apply during audit, before resolution):
- `→ ✅` requirement is adequately specified
- `→ ⚠️ partial` spec addresses some aspect but leaves the rest implicit
- `→ ❌ gap` spec silent; code may or may not address it
- `→ 🐛 drift` spec and shipped code disagree
- `→ 📌 accepted` gap is documented in spec already — confirm and re-check

## Requirement Completeness — Summarizer Trust Model

- [ ] CHK001 Is the summarizer-model trust level specified — does the summarizer's output go through 007's pipeline (sanitization + output validation), or is it trusted as system content? [Completeness, Gap, cross-ref 007]
- [ ] CHK002 Are requirements specified for cheapest-model selection's trust implications (an Ollama / free-tier model could produce malicious / low-quality summaries that poison future context)? [Completeness, Spec §FR-007, partial]
- [ ] CHK003 Is the summary content-injection surface specified (the prompt asks for JSON; the model's output becomes part of every future participant's context — a malicious model could inject instructions through narrative)? [Completeness, Gap]
- [ ] CHK004 Are requirements specified for summarizer-model authorization (does the summarizer use the cheapest participant's API key — if so, that participant's quota pays for everyone)? [Completeness, Gap]

## Requirement Completeness — JSON Parsing & Fallback

- [ ] CHK005 Is the "fallback to narrative-only" behavior (FR-004) specified for what counts as the narrative (the entire raw response, just a substring, the model's own narrative claim)? [Completeness, Spec §FR-004, partial]
- [ ] CHK006 Are requirements specified for fallback when the parsed JSON has missing required fields (Assumptions say "lenient — defaults to empty arrays/strings" — but is that documented as a security choice or just convenience)? [Completeness, Spec Assumptions]
- [ ] CHK007 Are requirements specified for the case where the model returns valid JSON with adversarial content (e.g., `decisions: ["ignore previous instructions"]`)? [Completeness, Gap]

## Requirement Completeness — Async Race Conditions

- [ ] CHK008 Is the async-trigger guard (Edge Cases mention "last_summary_turn as guard — only one fires") specified at the SQL-level (UPDATE ... WHERE last_summary_turn < N) or just code-level? [Completeness, Spec §Edge Cases, partial]
- [ ] CHK009 Are requirements specified for in-flight summarization when the session is paused / archived / deleted (orphaned async task; possible write to deleted session)? [Completeness, Gap]
- [ ] CHK010 Are requirements specified for the case where the async task survives a process restart (it doesn't — but does the spec acknowledge that a restart loses pending summaries)? [Completeness, Gap]

## Requirement Completeness — Storage Integrity

- [ ] CHK011 Are requirements specified for summary content immutability — same as messages (cross-ref 001 §FR-007), but the summary's role as "trusted context" is more sensitive? [Completeness, cross-ref 001 §FR-007]
- [ ] CHK012 Are requirements specified for summary tampering detection (a summary that's been modified post-creation should raise a flag — but FR-007 already prevents that, so confirm)? [Completeness, Gap]
- [ ] CHK013 Is summary export visibility specified (the summary appears in `/tools/session/summary` — who can read it; cross-ref 010 debug-export sensitive-field stripping)? [Completeness, cross-ref 010]

## Requirement Clarity

- [ ] CHK014 Is "cheapest available" (FR-002, FR-007) specified at the comparison-precision level (cost_per_input_token tie-breaking, model still active, key not revoked)? [Clarity, Spec §FR-007, partial]
- [ ] CHK015 Is "configurable threshold" (FR-001 default 50) specified per-session, deployment-wide, or per-participant? [Clarity, Spec §FR-001]
- [ ] CHK016 Is the JSON schema (Assumptions: `decisions[], open_questions[], key_positions[], narrative`) pinned as authoritative, or is it descriptive? [Clarity, Spec Assumptions]

## Requirement Consistency

- [ ] CHK017 Does FR-005 (summary stored as message with speaker_type='summary') align with 001 §FR-006 (sequential turn numbering per session-branch)? Does the summary consume a turn_number? [Consistency, Spec §FR-005, cross-ref 001 §FR-006]
- [ ] CHK018 Does FR-010 (asyncio.create_task fire-and-forget) align with 003 turn-loop's "no concurrent turns" guarantee? An async summarization isn't a turn, so consistent — confirm. [Consistency, Spec §FR-010, cross-ref 003 §FR-001]
- [ ] CHK019 Does FR-009 (warning logged on narrative-only fallback) align with 007 §FR-015 (security_events for layer findings)? Could a fallback indicate adversarial summarizer behavior worth a security event? [Consistency, Spec §FR-009, cross-ref 007 §FR-015]

## Acceptance Criteria Quality

- [ ] CHK020 Is SC-002 ("90%+ valid JSON on first try") testable — across what corpus, with what prompt version? [Measurability, Spec §SC-002]
- [ ] CHK021 Is SC-005 ("cheapest model selection correctly identifies lowest-cost participant") testable when costs are equal or when the lowest-cost model is paused? [Measurability, Spec §SC-005, Edge Case]
- [ ] CHK022 Are negative-path success criteria specified (zero summary-induced injections detected by 007, zero summary writes to deleted sessions, zero double-fire under race)? [Acceptance Criteria, Gap]

## Scenario Coverage

- [ ] CHK023 Are recovery requirements defined for the case where the summarizer model is unavailable (rate-limited, key revoked) — does it skip the checkpoint, retry next turn, or attempt fallback)? [Coverage, Recovery Flow, Spec §FR-008, partial]
- [ ] CHK024 Are concurrent-summarization scenarios addressed (two threshold-crossing events fire close together — covered by Edge Cases but the implementation guard isn't specified)? [Coverage, Spec §Edge Cases, partial]
- [ ] CHK025 Are repeat-failure scenarios specified (model produces invalid JSON repeatedly across multiple checkpoints — does the system stop trying, escalate, alert)? [Coverage, Gap]

## Edge Case Coverage

- [ ] CHK026 Are requirements defined for summarization input that exceeds the cheapest model's context window (Edge Cases say "truncate to most recent" — but is the truncation contract specified)? [Edge Case, Spec §Edge Cases, partial]
- [ ] CHK027 Are requirements defined for the case where a summary itself triggers convergence detection (FR-001 of 004 might fire on the summary, treating it as "another similar response")? [Edge Case, Gap, cross-ref 004 §FR-001]
- [ ] CHK028 Are requirements defined for the case where all candidate summarizer models fail (all fall-throughs exhausted) — fall back to a hardcoded narrative? Skip the checkpoint? [Edge Case, Spec §FR-008, partial]
- [ ] CHK029 Are requirements defined for adversarial summary content embedded in `key_positions` (a malicious summarizer attributes inflammatory positions to participants)? [Edge Case, Gap]

## Non-Functional Requirements

- [ ] CHK030 Is the threat model documented and requirements traced to it (OWASP LLM01 indirect injection via summary content; LLM03 supply chain via cheapest-model trust; LLM05 over-reliance on summary content)? [Traceability, Gap]
- [ ] CHK031 Are performance requirements specified for summarization completion target (the spec says async fire-and-forget but a slow summarizer that never lands means future turns lack the checkpoint they expect)? [Performance, Gap]
- [ ] CHK032 Are observability requirements specified for fallback rate, narrative-only count, summarizer model selection (which model paid for which checkpoint)? [Coverage, Gap]

## Dependencies & Assumptions

- [ ] CHK033 Is the dependency on existing ProviderBridge (Assumptions) covered by a contract test (the bridge handles dispatch + retry — does it also propagate cost_per_input_token correctly for cheapest selection)? [Dependency, Spec Assumptions, Gap]
- [ ] CHK034 Is the assumption "summarization prompt is a constant string in Phase 1" paired with a re-evaluation trigger (when does prompt-tuning become necessary; how does prompt versioning interact with summary parsing across versions)? [Assumption, Spec Assumptions, Gap]
- [ ] CHK035 Is the assumption "summary epoch tracking" (Assumptions) paired with a max-epoch contract (does the field overflow ever; can a session have unlimited epochs)? [Assumption, Spec Assumptions, Gap]

## Ambiguities & Conflicts

- [ ] CHK036 Does FR-007 ("prefer paid over free models") conflict with the "cheapest model" assumption when there's a paid Ollama model deployed locally? [Ambiguity, Spec §FR-007]
- [ ] CHK037 Is "speaker_id='system'" (FR-005) consistent across 001 (summaries are messages) — does the messages table accept literal 'system' as a speaker_id, or does it require an FK to participants? [Conflict, Spec §FR-005, cross-ref 001 §FR-006]
- [ ] CHK038 Does FR-009 (warn-on-fallback) interact correctly with 007 §FR-015 — should fallback events be logged to security_events too, given they may indicate adversarial behavior? [Ambiguity, Spec §FR-009, cross-ref 007 §FR-015]

## Notes

- Highest-leverage findings to expect: CHK001 (summary content goes through 007 pipeline or not — major decision), CHK003 (summarizer is an injection surface — narrative becomes context for everyone), CHK004 (whose budget pays for whose summary), CHK030 (no traceability).
- Lower-priority but easy wins: CHK006 (lenient JSON parsing as security choice vs convenience), CHK016 (schema authority), CHK017 (turn_number consumption).
- Run audit by reading [src/orchestrator/summarizer.py](../../../src/orchestrator/summarizer.py) (or wherever summarization lives), the prompt template, the JSON parser, and the fallback path; cross-reference with 001 (storage), 003 (turn loop), 004 (convergence interaction), 007 (pipeline), 010 (export visibility).
