# Behavioral Requirements Quality Checklist: AI Response Shaping

**Purpose**: Validate that the spec's behavioral requirements (filler scoring rules, retry-budget threading, register-slider semantics, override resolution order, cascade behavior, master-switch and topology-7 gates) are unambiguous, complete, and testable. Tests the writing, not the implementation.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md)

## Filler Scoring Behavior

- [ ] CHK001 Is the hedge-ratio signal defined precisely (token list scope, ratio denominator: total tokens vs sentence tokens)? [Clarity, Spec §FR-001 / research.md]
- [ ] CHK002 Is the restatement-overlap signal defined precisely (cosine threshold, comparison window: prior 1 turn vs prior N)? [Clarity, Spec §FR-001 / research.md]
- [ ] CHK003 Is the closing-pattern signal defined precisely (regex list scope, partial-match vs full-match semantics)? [Clarity, Spec §FR-001 / research.md]
- [ ] CHK004 Is signal normalization specified (each signal in [0.0, 1.0] independently before weighted-sum)? [Completeness, contracts/filler-scorer-adapter.md / research.md]
- [ ] CHK005 Are out-of-language inputs (non-English) addressed (signal degrades gracefully vs scores 0 vs scores 1)? [Edge Case, Gap]

## Retry Budget Threading

- [ ] CHK006 Is the per-output-attempt retry-consumption rule specified (each attempt counts toward the cap, including the original)? [Clarity, Spec §FR-005 / FR-006]
- [ ] CHK007 Is the cap-exhaustion behavior specified (last attempt's output ships even if score > threshold)? [Completeness, Spec §FR-005]
- [ ] CHK008 Is the FR-006 joint-cap interaction specified for participants with topology-7 fallback retries? [Coverage, Spec §FR-006 / Gap]
- [ ] CHK009 Is the retry-delta-text injection point specified (appended to the original prompt vs replacing the assistant turn vs other)? [Clarity, contracts/filler-scorer-adapter.md / Gap]

## Register Slider Semantics

- [ ] CHK010 Is the slider's per-session scope specified (one slider value per session, not per-participant or per-turn)? [Clarity, Spec §FR-007]
- [ ] CHK011 Are facilitator-only mutation rights specified (only facilitator role can call slider-set; participants cannot)? [Completeness, Spec §FR-007]
- [ ] CHK012 Is the slider-default behavior specified (new sessions inherit `SACP_REGISTER_DEFAULT`; explicit set persists for the session)? [Coverage, Spec §FR-008]
- [ ] CHK013 Is the slider-change effective-time specified (next turn vs immediate vs queued)? [Clarity, Spec §FR-007 / Gap]

## Per-Participant Override Semantics

- [ ] CHK014 Is the override-resolution order specified precisely (override > session > SACP_REGISTER_DEFAULT)? [Clarity, Spec §FR-008]
- [ ] CHK015 Is the override-set authorization specified (facilitator-only mutation, target_participant_id required)? [Completeness, Spec §FR-008]
- [ ] CHK016 Is override clearing distinguished from setting to the session default value (FR-008's `_cleared` event vs `_set` event)? [Clarity, contracts/audit-events.md / FR-008]
- [ ] CHK017 Is the human-participant override case specified (humans get no Tier 4 delta because they aren't dispatched to LLMs)? [Coverage, Spec §FR-008 / Edge Cases]

## Cascade Delete Behavior

- [ ] CHK018 Is the session-delete cascade specified (deleting a session removes session_register row AND all participant_register_override rows for that session)? [Completeness, Spec §FR-015]
- [ ] CHK019 Is the participant-remove cascade specified (removing a participant emits `_cleared` event AND removes the override row)? [Clarity, Spec §FR-015 / contracts/audit-events.md]
- [ ] CHK020 Are cascade tests specified at the spec level (two cascade scenarios called out as required test coverage)? [Coverage, Spec §FR-015 / tasks.md Phase 5]
- [ ] CHK021 Is the spec 001 §FR-011 cross-link explicit, with the participant-remove FK behavior anchor specified? [Traceability, Spec §FR-015]

## Master Switch Behavior (SC-002)

- [ ] CHK022 Is `SACP_RESPONSE_SHAPING_ENABLED=false` (default) specified to result in zero filler-scorer dispatch, zero retry, zero shaping-row plumbing? [Completeness, Spec §FR-005 / SC-002]
- [ ] CHK023 Is the master-switch effect on the slider specified (slider state still readable via `/me` even when master switch is off, OR slider state becomes inert when master switch is off)? [Clarity, Gap]
- [ ] CHK024 Is the master-switch transition (off → on, on → off) effect on in-flight sessions specified (immediate vs next-turn)? [Edge Case, Gap]

## Topology-7 Conditional Behavior

- [ ] CHK025 Is the topology-7 skip path specified at the FR level (not just V12), with the rationale (no orchestrator-side prompt assembler to inject into)? [Clarity, Spec §V12 / research.md]
- [ ] CHK026 Is the partial-skip case addressed (topology 7 deployments that retain orchestrator-side message logging but lose Tier 4 injection)? [Coverage, Gap]

## /me Source Resolver

- [ ] CHK027 Is the `register_source` value enumerated with all three possibilities (`"override"`, `"session"`, `"default"`)? [Completeness, contracts/register-preset-interface.md / FR-008]
- [ ] CHK028 Is the source-resolver invariant specified (the resolved register_slider value MUST equal what the prompt-assembler would inject for that participant on the next turn)? [Consistency, FR-008]

## No Content Compression (FR-016)

- [ ] CHK029 Is the FR-016 boundary specified at the participant content level (filler-scorer signals never read message body content beyond what's needed for the three signals)? [Clarity, Spec §FR-016]
- [ ] CHK030 Is the FR-016 cross-cutting prohibition consistent across all five touched modules (no compression of conversation messages, audit content, or routing_log payloads)? [Consistency, Spec §FR-016 / tasks.md]

## Edge Cases

- [ ] CHK031 Is the empty-output behavior specified (zero-length AI turn → score = 0 vs error vs skip)? [Edge Case, Gap]
- [ ] CHK032 Is the embedding-unavailable case specified (sentence-transformers absent → restatement signal contributes 0 vs scorer fails closed)? [Edge Case, contracts/filler-scorer-adapter.md / fail-closed table]
- [ ] CHK033 Is the very-first-turn case specified (no prior turn for restatement comparison → restatement signal = 0)? [Edge Case, contracts/filler-scorer-adapter.md / Gap]

## Notes

- Items CHK013, CHK023, CHK024 (timing of slider/master-switch state changes) are the most likely to surface as ambiguity during implementation. Resolve before /speckit.tasks runs T012+.
- The cascade-delete tests (CHK020) are mandatory coverage at /speckit.tasks Phase 5; the spec must specify them, not just the data-model.
