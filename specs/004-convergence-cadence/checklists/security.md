# Security Requirements Quality Checklist: Convergence Detection & Adaptive Cadence

**Purpose**: Validate the quality, clarity, and completeness of security requirements in the Convergence & Cadence spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Feature**: [spec.md](../spec.md)
**Sister checklist**: [requirements.md](requirements.md) (general spec completeness — already passed).

Markers used in findings (apply during audit, before resolution):
- `→ ✅` requirement is adequately specified
- `→ ⚠️ partial` spec addresses some aspect but leaves the rest implicit
- `→ ❌ gap` spec silent; code may or may not address it
- `→ 🐛 drift` spec and shipped code disagree
- `→ 📌 accepted` gap is documented in spec already — confirm and re-check

## Requirement Completeness — Embedding Model Trust

- [ ] CHK001 Is FR-013 ("SafeTensors only, no pickle") covered by a load-time verification (does the loader hard-fail on .bin / .pt files, or only refuse to load .pkl)? [Completeness, Spec §FR-013]
- [ ] CHK002 Are requirements specified for model-file integrity (checksum, signature, supply-chain pinning)? [Completeness, Gap]
- [ ] CHK003 Are requirements defined for the model-load-failure case (Edge Cases mention "skip embedding" — but is that fail-open from a convergence-detection standpoint)? [Completeness, Spec §Edge Cases, partial]
- [ ] CHK004 Are requirements specified for the embedding model's network access during load (huggingface.co fetch vs offline-only)? [Completeness, Gap]

## Requirement Completeness — Embedding Exposure

- [ ] CHK005 Is FR-016 ("embeddings never exposed externally") covered by a serializer-level guard (any debug/export path that would include them)? [Completeness, Spec §FR-016, cross-ref 010 §FR-4]
- [ ] CHK006 Are requirements specified for embedding-storage encryption-at-rest (the convergence_log stores raw bytes — should they be encrypted given they leak content shape)? [Completeness, Gap]
- [ ] CHK007 Are requirements specified for embedding-derived data (similarity scores, sparkline points) — are those also confidential, or can they appear in audit logs? [Completeness, Gap]

## Requirement Completeness — Divergence & Adversarial Prompts

- [ ] CHK008 Is the divergence-prompt content specified (it's injected into AI context — its wording is a security-relevant blob, treated as system-trust)? [Completeness, Spec Assumptions, Gap]
- [ ] CHK009 Are requirements specified for the case where a divergence prompt itself contains injection-shaped patterns (sanitized? exempt from sanitization because it's system content?) [Completeness, Gap, cross-ref 007 §FR-001]
- [ ] CHK010 Is the adversarial prompt content specified or referenced (FR-011 says "challenge weakest assumption" — but the actual text matters)? [Completeness, Spec §FR-011, Gap]
- [ ] CHK011 Are requirements specified for adversarial-rotation interaction with paused / over-budget participants (Edge Cases say "skip to next active" — but is the rotation index advanced or held)? [Completeness, Spec §Edge Cases, partial]

## Requirement Clarity

- [ ] CHK012 Is "configurable threshold" (FR-004 default 0.85) specified as deployment env var, per-session, or per-deployment? [Clarity, Spec §FR-004]
- [ ] CHK013 Is "sliding window" (FR-003 default 5 turns) specified at message-type granularity (does it include human interjections, summary messages, or only AI turns)? [Clarity, Spec §FR-003, Gap]
- [ ] CHK014 Is "asynchronously after the response is persisted" (FR-001) specified as fire-and-forget or awaited-but-non-blocking? [Clarity, Spec §FR-001]
- [ ] CHK015 Is "every N turns" (FR-011 default 12) specified per-session, per-rotation-cycle, or globally? [Clarity, Spec §FR-011]

## Requirement Consistency

- [ ] CHK016 Does FR-009 cadence presets (sprint 2-15s, cruise 5-60s, idle trigger-only) align with the cadence-affects-rate-limit interaction (a 60s cruise floor + 60 req/min limit gives 60 capacity per minute — consistent)? [Consistency, Spec §FR-009, cross-ref 009 §FR-001]
- [ ] CHK017 Does FR-010 ("reset to floor on human interjection") align with 003 §FR-013 (interrupt queue processed first)? [Consistency, Spec §FR-010, cross-ref 003 §FR-013]
- [ ] CHK018 Does FR-005 (divergence prompt injection) align with 007 §FR-001 (sanitization runs on context assembly)? Is the divergence prompt sanitized or exempt as system content? [Consistency, Spec §FR-005, cross-ref 007 §FR-001]

## Acceptance Criteria Quality

- [ ] CHK019 Is SC-003 ("divergence prompts reduce subsequent similarity by at least 20%") testable with a deterministic fixture, or only as a statistical claim across many runs? [Measurability, Spec §SC-003]
- [ ] CHK020 Is SC-005 ("adversarial rotation visits each participant exactly once before cycling") testable when participants are added/removed mid-rotation? [Measurability, Spec §SC-005, Edge Case]

## Scenario Coverage

- [ ] CHK021 Are recovery requirements defined for embedding-model crash mid-session (Edge Cases say "log warning and skip" — but does the convergence log mark the gap)? [Coverage, Recovery Flow, Spec §Edge Cases, partial]
- [ ] CHK022 Are concurrent-embedding scenarios addressed (two turns persisting near-simultaneously — both spawn embedding tasks; does the order in convergence_log match turn_number)? [Coverage, Gap]
- [ ] CHK023 Are session-shutdown scenarios specified for in-flight async embedding tasks (turn loop ends; embeddings still computing — orphan tasks)? [Coverage, Gap]

## Edge Case Coverage

- [ ] CHK024 Are requirements defined for adversarial input designed to game similarity (a participant outputting the same content paraphrased — embeddings detect, but what if they're embedding-aware adversaries)? [Edge Case, Gap]
- [ ] CHK025 Are requirements defined for very-short responses where embedding quality degrades (1-token responses produce noisy embeddings)? [Edge Case, Gap]
- [ ] CHK026 Are requirements defined for the case where ALL participants are paused / over-budget when adversarial rotation fires (no one to inject into)? [Edge Case, Gap]
- [ ] CHK027 Are requirements defined for the convergence threshold being misconfigured (>1.0 = always converging; <0.0 = never)? [Edge Case, Gap]

## Non-Functional Requirements

- [ ] CHK028 Is the threat model documented and requirements traced to it (OWASP LLM05 prompt injection via divergence prompts; LLM01 indirect via adversarial-rotation prompt; supply-chain LLM03 for the embedding model)? [Traceability, Gap]
- [ ] CHK029 Are observability requirements specified beyond convergence_log (alerts on persistent escalation, model-load failures, embedding-task queue depth)? [Coverage, Gap]
- [ ] CHK030 Are performance regression requirements specified (FR-014 says "must not block loop" — but if embedding takes 30s on a hot path, what's the contract)? [Performance, Spec §FR-014, partial]

## Dependencies & Assumptions

- [ ] CHK031 Is the dependency on sentence-transformers all-MiniLM-L6-v2 (Assumptions) paired with a re-evaluation trigger (model deprecated, replaced, or cost optimization to local fastembed)? [Assumption, Spec Assumptions, Gap]
- [ ] CHK032 Is the assumption "in-memory cadence + adversarial state, not persisted" paired with a session-restart-loosening acknowledgment (a deploy resets the rotation index — adversarial fairness perturbed briefly)? [Assumption, Spec Assumptions, partial]
- [ ] CHK033 Is the dependency on the convergence_log table (cross-ref 001) covered by a schema-evolution requirement (if 001 changes the table shape, this feature must adapt)? [Dependency, Spec Assumptions, cross-ref 001]

## Ambiguities & Conflicts

- [ ] CHK034 Does FR-016 ("embeddings never exposed externally") conflict with 010 debug-export's broad data dump? Is the convergence_log section of the export filtered, or is the embedding column stripped per-row? [Conflict, Spec §FR-016, cross-ref 010]
- [ ] CHK035 Is "asynchronously" (FR-001, FR-014) consistent across both — could the loop advance, persist a follow-up turn, and trigger convergence eval before the prior embedding lands? [Ambiguity, Spec §FR-001, §FR-014]
- [ ] CHK036 Does FR-008 (cadence adjusts based on similarity) conflict with FR-010 (human interjection resets to floor) when both fire on the same turn? [Conflict, Spec §FR-008, §FR-010]

## Notes

- Highest-leverage findings to expect: CHK001 (SafeTensors enforcement at code level — easy to regress), CHK008 / CHK010 (the actual prompt text is a security-relevant blob; spec doesn't pin it), CHK028 (no traceability), CHK034 (embedding leakage via debug-export).
- Lower-priority but easy wins: CHK002 (model checksum), CHK012 (config knob), CHK016 (cadence + rate-limit interaction).
- Run audit by reading [src/convergence/](../../../src/convergence/) (or wherever embedding logic lives), [src/orchestrator/loop.py](../../../src/orchestrator/loop.py) for cadence integration, and the divergence/adversarial prompt strings; cross-reference 007 (sanitization), 009 (rate-limit interaction), 010 (export filtering).
