# Security Requirements Quality Checklist: Turn Loop Engine

**Purpose**: Validate the quality, clarity, and completeness of security requirements in the Turn Loop Engine spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Feature**: [spec.md](../spec.md)
**Sister checklist**: [requirements.md](requirements.md) (general spec completeness — already passed).
**Cross-feature reference**: [007-ai-security-pipeline](../../007-ai-security-pipeline/spec.md) — output validation runs INSIDE the turn loop. Many items below check whether 003's wording stays consistent with 007's authoritative requirements.

Markers used in findings (apply during audit, before resolution):
- `→ ✅` requirement is adequately specified
- `→ ⚠️ partial` spec addresses some aspect but leaves the rest implicit
- `→ ❌ gap` spec silent; code may or may not address it
- `→ 🐛 drift` spec and shipped code disagree
- `→ 📌 accepted` gap is documented in spec already — confirm and re-check

## Requirement Completeness — API Key In-Memory Window

- [ ] CHK001 Is the duration of the API-key plaintext in-memory window specified ("decrypt at dispatch, discard immediately after" — but what's the upper bound when a provider call hangs)? [Completeness, Spec §FR-007, Gap]
- [ ] CHK002 Are requirements specified for memory clearing after discard (zeroing the bytes, not just dereferencing — Python's GC doesn't guarantee timely deallocation)? [Completeness, Spec §FR-007, Gap]
- [ ] CHK003 Are requirements specified for the case where the dispatch call raises an exception with the key on the stack (traceback may capture it — cross-ref 007 §FR-012 excepthook scrubbing)? [Completeness, Spec §FR-007, cross-ref 007 §FR-012]

## Requirement Completeness — Provider Response Trust

- [ ] CHK004 Are requirements specified for treating the provider response as untrusted before persistence (cross-ref 007 §FR-004 output validation, §FR-006-§FR-008 exfiltration filtering)? [Completeness, Spec §FR-010, cross-ref 007]
- [ ] CHK005 Are requirements specified for the order of operations between persistence and security-pipeline checks (007 §FR-014 says validate -> exfil; does 003 enforce that ordering)? [Completeness, cross-ref 007 §FR-014]
- [ ] CHK006 Are requirements specified for fail-closed pipeline-internal failures (cross-ref 007 §FR-013 — turn skipped with `security_pipeline_error`, breaker NOT incremented)? [Completeness, cross-ref 007 §FR-013]

## Requirement Completeness — Concurrency

- [ ] CHK007 Is the advisory-lock pattern (Clarifications session 2026-04-15) specified as a requirement, or just a clarification note? [Completeness, Spec Clarifications]
- [ ] CHK008 Are requirements specified for what happens if the advisory lock can't be acquired (timeout, fall through, deadlock detection)? [Completeness, Gap]
- [ ] CHK009 Are interrupt-queue race conditions specified beyond turn-number collision (concurrent inject + concurrent loop iteration on different machines if scaled out — Phase 1 single-process, but spec doesn't say so explicitly)? [Completeness, Gap]

## Requirement Completeness — Budget Enforcement

- [ ] CHK010 Is "would be exceeded" (FR-014) specified at the precision level — pre-call estimation, post-call accounting, hybrid? [Completeness, Spec §FR-014]
- [ ] CHK011 Are requirements specified for budget-window definition (rolling, calendar, fiscal — the spec mentions "hourly and daily" but not the window boundaries)? [Completeness, Spec §FR-014, Gap]
- [ ] CHK012 Are requirements specified for the case where budget tracking lags actual provider cost (LiteLLM returns final cost; what if it's wrong)? [Completeness, Edge Case, Gap]

## Requirement Completeness — Routing Modes

- [ ] CHK013 Are requirements specified for routing-mode tampering (a participant changes their own mode mid-loop — race condition with active dispatch)? [Completeness, Gap]
- [ ] CHK014 Are requirements specified for the trust boundary between routing decision and dispatch (the routing log records "intended" vs "actual" — is that audit-grade)? [Completeness, Spec §FR-011]
- [ ] CHK015 Is the `delegate_low` mode's privilege model specified (the original participant pays — does the delegate AI's response carry the original speaker_id or the delegate's)? [Completeness, Spec §FR-012, Gap]

## Requirement Clarity

- [ ] CHK016 Is "discarded immediately after the call completes" (FR-007) defined behaviorally (variable rebinding, explicit zero, ctypes wipe)? [Clarity, Spec §FR-007]
- [ ] CHK017 Is "configurable threshold" (FR-015 default 3) specified as deployment env var, per-session, or per-participant? [Clarity, Spec §FR-015]
- [ ] CHK018 Is the 180s default turn timeout (FR-019) cross-referenced to the turn loop's own deadlines so a 180s turn doesn't deadlock the cadence? [Clarity, Spec §FR-019]

## Requirement Consistency

- [ ] CHK019 Does FR-016 (retry up to 3 times on degenerate output) align with 007 §FR-013 (no silent drop) — a retried-then-discarded response was never persisted, but the retries SHOULD log? [Consistency, Spec §FR-016, cross-ref 007 §FR-013]
- [ ] CHK020 Does FR-021 ("never halt session due to single-participant failure") align with 007 §FR-013's fail-closed behavior on pipeline-internal errors (the turn fails closed but the session continues — consistent)? [Consistency, Spec §FR-021, cross-ref 007 §FR-013]
- [ ] CHK021 Does FR-018 (review_gate staging) align with 007 §FR-016 (operator notification path) and 008 §FR-008 (staging + 007 §FR-016 path)? [Consistency, cross-ref 007 §FR-016, 008 §FR-008]

## Acceptance Criteria Quality

- [ ] CHK022 Can SC-008 ("API keys never appear in any log output") be objectively measured (regex grep over collected logs) or only as code review? [Measurability, Spec §SC-008]
- [ ] CHK023 Is SC-009 ("turn loop continues when one provider fails") testable with a fault-injection harness? [Measurability, Spec §SC-009]
- [ ] CHK024 Are success criteria specified for the budget-enforcement path (zero turns dispatched after budget exceeded — currently SC-005 covers it but the threshold for "approximate" precision isn't stated)? [Acceptance Criteria, Spec §SC-005]

## Scenario Coverage

- [ ] CHK025 Are recovery requirements defined for the case where the advisory lock times out mid-turn (turn-number collision risk)? [Coverage, Recovery Flow, Gap]
- [ ] CHK026 Are concurrent-loop scenarios addressed (two orchestrator processes accidentally on the same session — DB locks help, but spec doesn't say "single-loop-per-session")? [Coverage, Gap]
- [ ] CHK027 Are repeat-offender provider scenarios specified beyond circuit breaker (a provider returning malicious responses repeatedly — caught by 007's pipeline; does 003 escalate)? [Coverage, Gap]

## Edge Case Coverage

- [ ] CHK028 Are requirements defined for the case where the participant's encryption-key version was rotated mid-session (cross-ref 001 CHK029)? [Edge Case, Gap, cross-ref 001 §FR-004]
- [ ] CHK029 Are requirements defined for adversarial-rotation interaction with budget enforcement (the adversarial prompt picks an over-budget participant — defer or skip)? [Edge Case, Gap, cross-ref 004]
- [ ] CHK030 Are requirements defined for context-payload size approaching the model's hard limit (the spec mentions context_window minus reserves; but FR-005 truncates at turn boundaries — what if a single turn exceeds the budget)? [Edge Case, Spec §FR-005]
- [ ] CHK031 Are requirements defined for late-response handling beyond drop (cancellation cleanup — does the cancelled `acompletion` task leak a connection)? [Edge Case, Spec Edge Cases, partial]

## Non-Functional Requirements

- [ ] CHK032 Is the threat model documented and requirements traced to it (OWASP LLM01/LLM02/LLM04, NIST AI 100-2 §3.4 indirect injection, NIST SP 800-53 SC-5 DoS protection)? [Traceability, Gap]
- [ ] CHK033 Are observability requirements specified for budget-exceeded skips, circuit-breaker trips, retry-exhausted skips (each should produce a routing-log entry — partly covered by FR-011)? [Coverage, Spec §FR-011, partial]
- [ ] CHK034 Are performance requirements specified for the loop iteration overhead (route + assemble + dispatch should fit in cadence floor of 2-5s)? [Performance, Gap]

## Dependencies & Assumptions

- [ ] CHK035 Is the dependency on LiteLLM's token estimation (Assumptions) paired with a re-evaluation trigger (when does inexact tiktoken counting become a budget-enforcement bug)? [Assumption, Spec Assumptions, Gap]
- [ ] CHK036 Is the assumption "round-robin only Phase 1" paired with a security-relevant trigger (relevance-based rotation could enable participant-targeted DoS — accept or defer)? [Assumption, Spec Assumptions, Gap]
- [ ] CHK037 Is the dependency on PostgreSQL advisory locks (Clarifications) covered by a deployment requirement (does the operator need to ensure pg_advisory_xact_lock is enabled)? [Dependency, Gap]

## Ambiguities & Conflicts

- [ ] CHK038 Does FR-007 ("decrypted only at moment of provider dispatch and discarded immediately after") conflict with FR-020 (retry on rate limits with exponential backoff — does the key get re-decrypted on each retry, or held)? [Conflict, Spec §FR-007, §FR-020]
- [ ] CHK039 Is "moment of provider dispatch" (FR-007) defined as the LiteLLM call site, or earlier (when building the kwargs dict)? [Ambiguity, Spec §FR-007]
- [ ] CHK040 Does the late-response drop semantic (Clarifications "no grace window, no [LATE] tagging") conflict with 007 §FR-013 ("never silently drop")? Audit must confirm: cancelled is not silently-dropped, it's "never started" from the loop's perspective. [Conflict, Spec Clarifications, cross-ref 007 §FR-013]

## Notes

- Highest-leverage findings to expect: CHK002 (no zeroing requirement for plaintext API keys in memory — Python heap probe could expose them), CHK003 (excepthook scrubbing must cover dispatch tracebacks), CHK006 (007 fail-closed should be re-stated in 003), CHK038 (key handling on retry).
- Lower-priority but easy wins: CHK010-CHK012 (budget precision wording), CHK017 (config knob locations), CHK032 (no traceability to OWASP/NIST).
- Run audit by reading [src/orchestrator/loop.py](../../../src/orchestrator/loop.py), [src/orchestrator/dispatch.py](../../../src/orchestrator/dispatch.py), [src/orchestrator/budget.py](../../../src/orchestrator/budget.py) (if present); cross-reference with this spec AND 007.
