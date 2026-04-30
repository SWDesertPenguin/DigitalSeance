# Testability Requirements Quality Checklist: Turn Loop Engine

**Purpose**: Validate the quality, clarity, and completeness of testability characteristics in the Turn Loop Engine spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Audited**: 2026-04-29
**Feature**: [spec.md](../spec.md)

**Audit summary**: 9 items pass cleanly, 24 have findings. The turn loop is the most state-rich component in SACP — 8 routing modes, circuit breaker, advisory lock, retry-with-key, multi-key same-model AIs, interrupt processing, security-pipeline failure path, complexity classifier. Many edge cases were caught only after they surfaced in shakedowns (PRs #77, #83, #140). This audit makes the testability surface explicit so Phase 3 can convert observed gaps into structured test gates.

## State Transitions & Coverage

- [x] CHK001 Are all participant state transitions enumerated as a state machine, with each transition required to have a test?
  [GAP]. Implicit machine: active ↔ paused (manual) ↔ paused (breaker) ↔ over-budget ↔ pending ↔ removed. No explicit diagram or coverage matrix.

- [x] CHK002 Is the cross-product of routing-modes (FR-012, 8 modes) × participant-state required to be tested?
  [GAP]. 8 modes × 5 states = 40 cells; subset is exercised in `test_turn_loop`/`test_orchestrator` but no requirement to cover all.

- [x] CHK003 Is the routing-mode-tampering snapshot semantics (FR-025: "mid-turn changes apply on the *next* turn") required to have a regression test?
  [GAP]. Specified behavior is testable; no test mandate.

## Race Conditions & Concurrency

- [x] CHK004 Is the advisory-lock contention path (FR-022, two concurrent appends on the same branch) required to have a test?
  [PARTIAL]. The lock is in `MessageRepository.append_message`. CHK008 from earlier audits closed this as "implementation detail" but contention IS testable: spawn two coroutines that race on the same branch_id; assert turn_number monotonicity. No explicit requirement.

- [x] CHK005 Is the inject-vs-AI-turn race (the original advisory-lock motivation per Session 2026-04-15 clarification) required to be reproduced as a test fixture?
  [GAP]. The race is documented; spec doesn't require a regression test against it.

- [x] CHK006 Is the FR-027 ("exactly one orchestrator process per session") testable from outside (i.e. is there a way to detect duplicate orchestrators in production)?
  [PARTIAL]. FR-027 says enforcement is via single-deployment topology. Detection (and therefore testability) requires session-lease coordination which is deferred to Phase 3.

## Provider Dispatch & Retry

- [x] CHK007 Is the rate-limit retry path (FR-020, exponential backoff, Retry-After header) required to be tested with a fixture provider that returns 429?
  [GAP]. Real providers are flaky to test against; need a mock.

- [x] CHK008 Is the rate-limit retry-and-key path (Round05 / PR #77 / #83 surfaced this — humans-in-LiteLLM-dispatch bug) required to have a regression test?
  [PARTIAL]. The recurring bug class is captured in `feedback_exclude_humans_from_dispatch.md` memory; test coverage exists in `test_loop_humans_filtered`. Spec doesn't formally name "human filter must be tested for every dispatch path."

- [x] CHK009 Is the per-turn timeout (FR-019, default 180s) testable without actually waiting 180s?
  [GAP]. Tests would need a configurable timeout fixture; spec is silent on injectability.

- [x] CHK010 Is provider-failure recovery (transient 5xx vs. terminal 401) required to differentiate test paths?
  [GAP]. FR-020 covers rate-limits; transient vs. terminal failures aren't differentiated for retry semantics.

## Circuit Breaker

- [x] CHK011 Are FR-015's "consecutive failures" semantics testable (a single success between 2 failures resets to 0; what counts as a "failure")?
  [PARTIAL]. Threshold default 3 is named; reset semantics described. Edge: does a security-pipeline-error count as a failure? FR-023 explicitly says NO ("circuit-breaker counter is NOT incremented"). Test must verify both paths.

- [x] CHK012 Is the breaker-trip → human-notification path (US7) required to have an end-to-end test (provider fails 3x → participant paused → notification fires)?
  [GAP].

- [x] CHK013 Is the manual-unpause-resets-breaker path tested?
  [GAP].

## Interrupt Processing

- [x] CHK014 Is the interrupt-priority + creation-order ordering (FR-013) required to have a test that mixes priorities?
  [GAP]. Subtle ordering bugs (e.g. higher-priority newer item vs. lower-priority older item) are testable but not mandated.

- [x] CHK015 Is the interrupt-while-AI-is-mid-turn behavior tested (does the interrupt land before, after, or interrupt the AI turn)?
  [GAP]. Per FR-013: "process pending interrupt queue entries before each AI turn." Boundary semantics: an interrupt arriving DURING an AI turn waits until that turn finishes — but spec doesn't pin this beyond the "before each AI turn" wording.

## Budget Enforcement

- [x] CHK016 Is the FR-014 budget-skip semantics testable (turn starts → cost would exceed budget → skip without dispatch)?
  [PARTIAL]. Pre-dispatch cost estimation requires the model's cost rate; testable but not mandated.

- [x] CHK017 Is the precision-of-budget-enforcement (cents-level rounding, hour-window definition) specified well enough to test?
  [GAP]. "Hourly" and "daily" budget windows: rolling vs. fixed-clock? No spec, no test.

## Routing Modes

- [x] CHK018 Are each of the 8 routing modes (FR-012) required to have a per-mode acceptance test?
  [GAP]. Modes: always, review_gate, delegate_low, domain_gated, burst, observer, addressed_only, human_only. Per-mode tests exist in `test_routing` but spec doesn't require coverage parity.

- [x] CHK019 Is the FR-026 drift (`delegate_low` "RECORDS the routing decision but does NOT actually delegate") required to have a test that verifies the action='delegated' log row + the original participant's response?
  [GAP]. Documented Phase 1 behavior; testable; not required.

- [x] CHK020 Is the round-robin rotation skipping (paused / over-budget / pending) testable end-to-end?
  [GAP].

## Multi-Key Same-Model AIs

- [x] CHK021 Is the multi-key same-model AI scenario (Round07 organic discovery) required to have a regression test?
  [GAP]. Bug surfaced in shakedown PR #140 area. Spec doesn't formalize the test.

## Security Pipeline Integration

- [x] CHK022 Is the FR-023 fail-closed path (pipeline-internal-error → turn skipped, no breaker increment, security_events row written) required to be tested with an injected pipeline error?
  [GAP]. Easy-to-test path (mock a regex error inside one layer); not mandated.

- [x] CHK023 Is the FR-024 plaintext-API-key bounded-memory residency testable?
  [GAP] (and arguably not testable from Python alone — would require a heap-dump tool). Documented limitation.

## Test Infrastructure & Fixtures

- [x] CHK024 Is the test-conftest schema mirror requirement (per `feedback_test_schema_mirror.md` memory) surfaced as a testability requirement in spec?
  [GAP]. Recurring bug class: alembic migration adds a column; conftest DDL doesn't; CI skips DB-tests locally. Spec could mandate "every column added via migration must also be added to conftest DDL."

- [x] CHK025 Is mocking strategy specified for LiteLLM calls (record/replay, fixture provider, in-process stub)?
  [GAP].

- [x] CHK026 Is a fixture corpus required for adversarial inputs (rate-limit responses, malformed providers, unicode-heavy content)?
  [GAP].

- [x] CHK027 Is the per-turn unit-test isolation required (each test runs in a fresh transaction / rollback at end)?
  [PARTIAL]. Existing tests use this pattern; spec is silent on the requirement.

## Observability of Test Failures

- [x] CHK028 Are tests required to surface enough state on failure to diagnose without re-running with logging-enabled?
  [GAP]. Common pytest pattern; not codified.

- [x] CHK029 Is structured failure output required for routing-mode tests (e.g. "expected next_speaker=A, got B; participants: [A active, B paused]")?
  [GAP].

## Coverage Targets

- [x] CHK030 Are coverage targets specified (line coverage, branch coverage, mutation coverage)?
  [GAP]. No spec'd coverage minimum.

- [x] CHK031 Is the `pytest -m loop` (or equivalent) test-marker scheme specified?
  [GAP]. Test organization is ad hoc.

## Edge-Case Reproducibility

- [x] CHK032 Are the spec's Edge Cases section entries (rate-limit retry, pipeline-internal failure, etc.) required to have direct test counterparts?
  [PARTIAL]. Some have tests; mapping isn't enforced.

- [x] CHK033 Is the cascade-skip behavior (Round07 cascade-announcements PR) testable end-to-end?
  [GAP]. Cascade scenario: participant A skipped (over-budget) → B (paused) → C (active) — the chain. Testable but not mandated.

## Notes

- 33 items audited. The turn loop is in many ways the most testable component in SACP (clear state machine, deterministic given inputs, mockable provider boundary) but the spec doesn't surface those characteristics as requirements.
- Highest-leverage findings to convert into spec amendments:
  - CHK002 (cross-product matrix of routing modes × participant states — would catch entire bug classes that surface organically in Round-N shakedowns).
  - CHK008 (formalize "human filter must be tested for every dispatch path" per recurring `feedback_exclude_humans_from_dispatch.md` bug class).
  - CHK022 (FR-023 fail-closed path — easy test, high security value).
  - CHK024 (conftest schema mirror — recurring CI surprise; surface as a testability requirement).
  - CHK004 / CHK005 (advisory-lock contention regression test — protects against future race regressions).
- Lower-priority but useful:
  - CHK009 (injectable per-turn timeout — speeds up test suite).
  - CHK030 (coverage target — doesn't matter what the number is, just that there is one).
  - CHK033 (cascade-skip end-to-end test — Round07 surfaced this organically; nail it down).
- Sister checklists `requirements.md` and `security.md` (closed 2026-04-29). Cross-ref `feedback_exclude_humans_from_dispatch.md`, `feedback_test_schema_mirror.md` memories — both name recurring bug classes that this checklist would help convert into structured test gates.
