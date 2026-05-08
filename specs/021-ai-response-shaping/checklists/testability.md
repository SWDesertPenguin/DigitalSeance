# Testability Quality Checklist: AI Response Shaping (Verbosity Reduction + Register Slider)

**Purpose**: Validate that spec 021's testability requirements (SC-002 master-switch regression canary, fail-closed pipeline tests, cascade-delete tests, signal-helper tests, retry-budget threading tests, /me source-resolver tests, conftest schema mirror invariant, determinism) are specified clearly enough that test authors and CI gates can apply them without ambiguity. This checklist tests testability-requirement quality.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md) + [tasks.md](../tasks.md) + [contracts/filler-scorer-adapter.md](../contracts/filler-scorer-adapter.md)

## SC-002 Master-Switch Regression Canary

- [ ] CHK001 Is the SC-002 master-switch regression canary specified as the most foundational testability contract — landing EARLY in tasks (T017 in Phase 2) before user-story code grows? [Completeness, Spec §SC-002 + Tasks §T017 + Plan §"Notes for /speckit.tasks"]
- [ ] CHK002 Is the requirement "with `SACP_RESPONSE_SHAPING_ENABLED=false`, every pre-feature acceptance test MUST pass byte-identically" specified at sufficient detail to determine pass/fail in CI? [Measurability, Spec §SC-002]
- [ ] CHK003 Are the requirements for the canary's scan logic specified clearly enough to detect a leak (assert no spec 021 shaping code path fires when the master switch is off)? [Clarity, Tasks §T017]
- [ ] CHK004 Is the canary's "initially fails, then passes" lifecycle documented clearly enough to avoid a regression where it always passes vacuously? [Clarity, Tasks §T017]

## Per-FR Test Coverage

- [ ] CHK005 Is each FR (FR-001 through FR-016) traceable to at least one test task in tasks.md? [Traceability, Tasks §T018-T058]
- [ ] CHK006 Is FR-001 (filler scorer evaluates each draft on three signals) traceable to T018-T026? [Traceability, Tasks §"User Story 1"]
- [ ] CHK007 Is FR-005 (master switch off → scorer doesn't run) traceable to T017 (canary) AND T020 (US1 acceptance scenario 3) — overlap acknowledged in T020? [Consistency, Tasks §T017 + T020]
- [ ] CHK008 Is FR-008 (per-participant override audit-log) traceable to T044 + T045 + T049? [Traceability, Tasks §"User Story 3"]
- [ ] CHK009 Is FR-015 (cascade-delete on participant or session remove) traceable to T048 + T049? [Traceability, Tasks §"User Story 3"]
- [ ] CHK010 Is FR-016 (no-content-compression boundary) traceable to a test, or is it enforced only by task-review discipline? [Gap]

## Per-SC Test Coverage

- [ ] CHK011 Is SC-001 (≥ 15% mean reduction on flagged drafts) specified at sufficient detail to determine pass/fail (test corpus from Phase 1+2 shakedown sessions; threshold; calibration method)? [Measurability, Spec §SC-001]
- [ ] CHK012 Is SC-002 (byte-identical pre-feature behavior with master switch off) specified with a CI verification mechanism named? [Verifiability, Spec §SC-002 + Tasks §T017 + T020]
- [ ] CHK013 Is SC-003 (both retries exhausted → second retry persists; one routing_log row with `reason='filler_retry_exhausted'`; no infinite loop) specified at sufficient detail and traceable to T021? [Completeness, Spec §SC-003 + Tasks §T021]
- [ ] CHK014 Is SC-004 (session register slider reflected in `/me` AND in assembled prompt's Tier 4 delta) specified at sufficient detail and traceable to T033 + T034? [Completeness, Spec §SC-004]
- [ ] CHK015 Is SC-005 (per-participant override affects ONLY the targeted participant) traceable to T045? [Traceability, Spec §SC-005 + Tasks §T045]
- [ ] CHK016 Is SC-006 (all shaping decisions in routing_log with per-stage timings) traceable to T022? [Traceability, Spec §SC-006 + Tasks §T022]
- [ ] CHK017 Is SC-007 (cascade-delete contract) traceable to T048 + T049? [Traceability, Spec §SC-007 + Tasks §T048-T049]
- [ ] CHK018 Is SC-008 (invalid env var exits at startup with clear error) traceable to T011? [Traceability, Spec §SC-008 + Tasks §T011]

## Fail-Closed Pipeline Tests

- [ ] CHK019 Are the fail-closed test requirements specified at sufficient detail across the four documented failure modes (regex bug; embedding read failure; sentence-transformers unavailable; closing-pattern regex compile failure)? [Completeness, Contracts §"Fail-closed contract" + Tasks §T054]
- [ ] CHK020 Is the requirement "regex bug → original draft persisted; `routing_log.shaping_reason='shaping_pipeline_error'`; no retry" specified consistently across spec edge case, contract fail-closed table, and T054? [Consistency, Spec §"Edge Cases" + Contracts §"Fail-closed contract" + Tasks §T054]
- [ ] CHK021 Is the requirement "sentence-transformers unavailable → restatement signal returns `0.0` with warning log; hedge + closing still contribute" specified at sufficient detail to distinguish from full pipeline failure? [Clarity, Spec §"Edge Cases" + Contracts §"Fail-closed contract"]
- [ ] CHK022 Are the requirements for "scorer continues vs scorer fails closed" specified consistently — restatement-only failures degrade gracefully; `_HEDGE_TOKENS` or `_CLOSING_PATTERNS` failures fail closed for the whole turn? [Consistency, Contracts §"Fail-closed contract"]

## Cascade-Delete Tests

- [ ] CHK023 Is the cascade-on-participant-remove test specified at sufficient detail (override row vanishes; no orphan rows; no `participant_register_override_cleared` audit row emitted)? [Completeness, Spec §SC-007 + Tasks §T048]
- [ ] CHK024 Is the cascade-on-session-delete test specified at sufficient detail (override row vanishes; parent delete event is the audit-visible action; no per-cascade audit row)? [Completeness, Tasks §T049]
- [ ] CHK025 Are the requirements for distinguishing explicit-clear-by-facilitator (DELETE on `participant_register_override`; emits `_cleared` audit) from cascade-delete (no audit) specified at sufficient detail to test both paths? [Clarity, Research §8 + Contracts §"audit-events.md"]
- [ ] CHK026 Is the contract for "no orphan override rows after a session delete" specified at sufficient detail to verify via SQL query in tests? [Measurability, Spec §FR-015 + SC-007]

## Three Signal Helper Tests

- [ ] CHK027 Are the test requirements for `_hedge_signal` specified at sufficient detail (hardcoded `_HEDGE_TOKENS` matched case-insensitively; whitespace-split denominator; empty draft returns `0.0`; result in `[0.0, 1.0]`)? [Completeness, Contracts §"Hedge-to-content ratio"]
- [ ] CHK028 Are the test requirements for `_restatement_signal` specified at sufficient detail (reads `engine.recent_embeddings(depth=3)`; max cosine similarity returned; empty buffer returns `0.0`; sentence-transformers unavailable returns `0.0` with warning log)? [Completeness, Contracts §"Restatement"]
- [ ] CHK029 Are the test requirements for `_closing_signal` specified at sufficient detail (regex matches against `_CLOSING_PATTERNS`; capped at 3 with `min(matches, 3) / 3.0`; result in `[0.0, 1.0]`)? [Completeness, Contracts §"Boilerplate closing detection"]
- [ ] CHK030 Is the rule "the three signal helpers do not call each other" specified clearly enough to be a structural test (independence enforceable by mocking the others)? [Clarity, Contracts §"No cross-signal coupling"]

## Retry-Budget Threading Tests

- [ ] CHK031 Are the test requirements for the joint-cap behavior specified at sufficient detail (shaping cap of 2 AND compound-budget remaining apply jointly; whichever fires first wins)? [Completeness, Spec §FR-006 + Plan §"Notes for /speckit.tasks"]
- [ ] CHK032 Is the test for "compound budget reaches zero mid-shaping → shaping loop exits early; persists the most recent draft" specified at sufficient detail? [Clarity, Research §4]
- [ ] CHK033 Are the test requirements for "per-attempt budget consumption" specified to prevent regression to pre-debit-the-worst-case? [Verifiability, Research §4]
- [ ] CHK034 Is the joint-cap test specified to land BEFORE either path's individual tests per plan's note? [Completeness, Plan §"Notes for /speckit.tasks"]

## /me Source-Resolver Tests

- [ ] CHK035 Are the test requirements for the `/me` resolver specified at sufficient detail (override row found → `register_source='participant_override'`; no override but session row found → `'session'`; neither found → still `'session'` per FR-010)? [Completeness, Research §5 + Contracts §"Resolver"]
- [ ] CHK036 Is the test for "the env-var default is reported as the session's value" specified consistently with FR-010's two-value enum (no third `'default'` value emitted)? [Consistency, Spec §FR-010 + Research §5]
- [ ] CHK037 Are the test requirements for the SQL JOIN's COALESCE precedence specified at sufficient detail (COALESCE(override.slider_value, session.slider_value, SACP_REGISTER_DEFAULT))? [Clarity, Research §5]
- [ ] CHK038 Is the test for `/me`-payload backward compatibility specified (existing clients ignore the three new top-level fields)? [Completeness, Research §6]

## Conftest Schema Mirror Invariant

- [ ] CHK039 Is the conftest schema-mirror invariant specified at sufficient detail per memory `feedback_test_schema_mirror` (any column added by alembic must also appear in `tests/conftest.py` raw DDL)? [Verifiability, Plan §"Testing" + Tasks §T012]
- [ ] CHK040 Is the requirement "alembic migration + conftest DDL update MUST land in the same task" specified consistently across plan, research §7, and tasks T012? [Consistency, Plan §"Testing" + Research §7 + Tasks §T012]
- [ ] CHK041 Are the requirements for the two new tables (`session_register`, `participant_register_override`) plus the five new `routing_log` columns specified to mirror in conftest? [Completeness, Tasks §T012]

## Determinism

- [ ] CHK042 Is the rule "the scorer is a pure function — same input → same output across runs, across processes, across machines" specified at sufficient detail to verify? [Measurability, Contracts §"Top-level entry point"]
- [ ] CHK043 Are the requirements for embedding-derived signals' determinism specified — the sentence-transformers model produces deterministic outputs for the same input, BUT timing characteristics vary? [Gap]
- [ ] CHK044 Is the contract for closing-pattern regex compilation specified to be module-load (not per-call) for determinism + cost? [Gap, Contracts §"Boilerplate closing detection"]

## Smoke Tests / Quickstart Walk-Through

- [ ] CHK045 Are the requirements for the quickstart walk-through (T057) specified at sufficient detail to apply on a deployed orchestrator (Steps 1-6)? [Completeness, Tasks §T057 + Quickstart §1-6]
- [ ] CHK046 Is the contract for V14 perf-budget regression check (T056) specified at sufficient detail (`shaping_score_ms` p95 ≤ 50ms across the test corpus)? [Measurability, Tasks §T056 + Spec §"Performance Budgets"]

## Flakiness & Reliability Considerations

- [ ] CHK047 Are the requirements for embedding-timing flakiness specified — the `_compute_embedding_async` reuses the loaded model on the existing thread-pool executor; timing varies but value is deterministic? [Gap]
- [ ] CHK048 Is the contract for retry-timing flakiness specified — provider retry latencies vary; `shaping_retry_dispatch_ms` is wall-clock and inherently noisy? [Gap]
- [ ] CHK049 Are the requirements for test isolation specified (each test's session/participant/override state is independent; no leakage across tests)? [Gap]
- [ ] CHK050 Is the contract for SC-001's calibration-against-recorded-corpus specified at sufficient detail to be a stable test rather than a flaky one (recorded corpus checked into the repo or referenced from a fixture)? [Clarity, Spec §SC-001 + "Assumptions"]

## Test Documentation

- [ ] CHK051 Are the requirements for each test file's docstring specified (what FR/SC each exercises)? [Gap]
- [ ] CHK052 Is the test-naming convention specified (`test_021_*` prefix mirroring spec 020's pattern)? [Consistency, Plan §"Source Code"]

## Notes

Highest-impact open items at draft time: CHK001 (the SC-002 canary is THE foundational testability contract — landing it early per Plan's note is the most important single discipline; the spec calls it out, but the canary's specific assertions need to be concrete enough to detect a leak), CHK010 (FR-016 compression boundary is a task-review discipline, not a test — there's no automated guard), CHK043-CHK044 (determinism contract is implicit; test isolation contract is implicit), CHK047-CHK049 (flakiness considerations for embedding timing, retry timing, and test-state isolation are all unaddressed). Annotation convention for runs of this checklist: `[PASS]`, `[PARTIAL]`, `[GAP]`, `[DRIFT]`, `[ACCEPTED]`. CHK043-CHK044 and CHK047-CHK049 most likely receive `[GAP]` on first run; the determinism + flakiness story is implicit.
