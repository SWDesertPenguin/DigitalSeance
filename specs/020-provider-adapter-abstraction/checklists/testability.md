# Testability Quality Checklist: Pluggable Provider Adapter Abstraction

**Purpose**: Validate that spec 020's testability requirements (mock adapter, fixture format, regression contract, architectural test) are specified clearly enough that test authors and CI gates can apply them without ambiguity. This checklist tests testability-requirement quality.
**Created**: 2026-05-08
**Feature**: [spec.md §US2 + §SC-003 / SC-004](../spec.md) + [contracts/mock-fixtures.md](../contracts/mock-fixtures.md)

## Mock Adapter Shape

- [ ] CHK001 Are the requirements for mock-adapter "shape conformity" (deterministic dispatch, plausibly-shaped streaming events, injectable error modes) specified clearly enough to distinguish "shape-conforming" from "quirk-faithful"? [Clarity, Spec §"Initial draft assumptions" + Clarification 2026-05-08]
- [ ] CHK002 Is the contract for `MockFixtureMissing` specified as binding (raise rather than default; exception payload names the missing fixture key with canonical hash + last-message substring)? [Completeness, Spec §FR-007 + §SC-004]
- [ ] CHK003 Are the requirements for mock-adapter capability negotiation (fixture-controllable per-test) specified at sufficient detail to support tests that simulate "no tool calling" or "8K-context" models? [Completeness, Spec §US2 + Contracts §mock-fixtures "capabilities"]
- [ ] CHK004 Is the boundary between "mock simulates injection" and "mock emulates provider quirks" specified explicitly enough to reject scope creep into provider-specific event-sequence emulation? [Clarity, Spec §"Initial draft assumptions"]

## Fixture File Format

- [ ] CHK005 Are the requirements for the JSON fixture file's top-level shape (`responses` + `errors` + `capabilities`) specified at sufficient detail to mechanically validate? [Completeness, Contracts §mock-fixtures]
- [ ] CHK006 Is the rationale for choosing JSON over YAML documented (no new runtime dep; `json` stdlib import covers parse)? [Traceability, Research §7]
- [ ] CHK007 Are the requirements for hash-mode vs substring-mode match keys specified clearly enough to avoid ambiguity (hash tried first; substring fallback; first-match-wins within mode)? [Clarity, Research §8 + Contracts §mock-fixtures]
- [ ] CHK008 Are the requirements for canonical hash computation specified precisely (`sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False))` — what about field ordering, what about nested structures)? [Clarity, Research §8]
- [ ] CHK009 Is the contract for fixture-file maintenance specified when canonical hash inputs change (e.g., a new field added to message dicts)? [Completeness, Contracts §mock-fixtures]

## Regression Contract (SC-001)

- [ ] CHK010 Are the requirements for SC-001 byte-identical regression specified at sufficient detail to determine pass/fail in CI (which test suite runs, what counts as identical, what counts as drift)? [Measurability, Spec §SC-001]
- [ ] CHK011 Is the rule "no test changes, no fixture changes, no golden-output changes" stated as binding for SC-001 verification? [Completeness, Spec §US1 acceptance scenario 1]
- [ ] CHK012 Are the requirements for the SC-001 CI matrix entry specified (how it's wired, where it runs, what triggers failure)? [Clarity, Tasks §T022]
- [ ] CHK013 Is the contract for test-time adapter selection specified — do existing tests gain a new fixture that selects the LiteLLM adapter, or is the default sufficient? [Gap]

## Architectural Test (FR-005)

- [ ] CHK014 Are the requirements for the architectural test's scan logic specified (`grep -rn "import litellm\|from litellm" src/` excluding `src/api_bridge/litellm/`)? [Clarity, Tasks §T021 + Spec §SC-002]
- [ ] CHK015 Is the test's "initially fails, then passes" lifecycle documented clearly enough to avoid a regression where it always passes vacuously? [Clarity, Tasks §T021]
- [ ] CHK016 Are the requirements for the test's behavior on transitive imports specified (a file imports a helper that imports litellm — does that count)? [Gap, Spec §SC-002]
- [ ] CHK017 Is the contract for test-code allowance documented (test files may import litellm for fixture construction; src/ files may not)? [Clarity, Plan §"FR-005 architectural-test canary"]

## Cross-Spec Test Migration

- [ ] CHK018 Are the requirements for spec 015's circuit-breaker test migration to canonical categories specified at sufficient detail (which test files, which assertions, which idiom changes)? [Completeness, Tasks §T040]
- [ ] CHK019 Is the test-migration's failure mode documented (if a spec 015 test still references `litellm.RateLimitError`, the architectural test catches it; CI fails)? [Verifiability, Tasks §T041]
- [ ] CHK020 Are the requirements for parallel-CI runs of spec 015 tests under both adapters (LiteLLM + mock) specified, or is mock-adapter the sole post-migration path? [Gap, Spec §SC-003]

## Network Isolation Verification

- [ ] CHK021 Is the requirement "no outbound network call when mock adapter is selected" specified as a binding test contract per US2 acceptance scenario 3? [Completeness, Spec §US2]
- [ ] CHK022 Are the requirements for the socket-level isolation harness specified (which mechanism — monkey-patch `socket.create_connection`, NetworkBlockingScope, container-egress block)? [Clarity, Spec §US2]
- [ ] CHK023 Is the contract for tests that intentionally exercise network paths (e.g., LiteLLM adapter integration tests) specified — do they opt out of the isolation harness? [Gap]

## Test Coverage by FR

- [ ] CHK024 Is each FR (FR-001 through FR-015) traceable to at least one test task in tasks.md? [Traceability, Tasks §T024-T062]
- [ ] CHK025 Are the SC-001 through SC-008 success criteria each traceable to at least one verification task? [Traceability, Spec §"Success Criteria"]
- [ ] CHK026 Is the contract for "every adapter must produce equivalent test results" specified — if a future adapter is added, must it pass the same test suite? [Gap]

## Test Data Quality

- [ ] CHK027 Are the requirements for sample fixture content specified at sufficient detail (what entries each of the three sample files should contain)? [Completeness, Tasks §T055-T057]
- [ ] CHK028 Is the rule "fixture files contain no real credentials" specified as a binding contract (and verifiable via gitleaks/2MS scan)? [Verifiability, Plan §"Constitution Check V11"]
- [ ] CHK029 Are the requirements for fixture-file maintenance specified when canonical hash inputs change (recompute hashes via helper script)? [Completeness, Contracts §mock-fixtures + Tasks §T058]

## Determinism

- [ ] CHK030 Is "deterministic responses keyed on input fixtures" specified at sufficient detail to verify (same input → same output across runs, across processes, across machines)? [Measurability, Spec §FR-006]
- [ ] CHK031 Are the requirements for streaming-event determinism specified (same fixture → same event sequence, same timing characteristics)? [Gap]
- [ ] CHK032 Is the contract for `count_tokens` determinism specified for the mock adapter (e.g., always returns a deterministic count based on message-text length)? [Completeness, Tasks §T053]

## Cross-Spec Smoke Tests

- [ ] CHK033 Are the requirements for spec 016 metrics smoke test specified (Prometheus query, expected bounded-enum values)? [Completeness, Tasks §T069]
- [ ] CHK034 Are the requirements for spec 017 freshness smoke test specified (capability-driven cache invalidation verification)? [Completeness, Tasks §T070]
- [ ] CHK035 Are the requirements for spec 018 deferred-loading smoke test specified (capability-driven partition policy verification)? [Completeness, Tasks §T071]

## Test Flakiness & Reliability

- [ ] CHK036 Are the requirements for test isolation specified (each test's mock-adapter state is independent; no fixture-set leakage across tests)? [Gap]
- [ ] CHK037 Is the contract for test-time `initialize_adapter()` re-entry specified (per-test fixture re-init vs process-scope adapter)? [Gap]
- [ ] CHK038 Are the requirements for test-time canonical-hash computation specified to avoid drift (test-author writes a hash that matches what the production code computes)? [Completeness, Contracts §mock-fixtures + Tasks §T058]

## Test Documentation

- [ ] CHK039 Are the requirements for each test file's docstring specified (what FR/SC it exercises)? [Gap]
- [ ] CHK040 Is the test-naming convention specified (`test_020_*` prefix mirroring spec 025's pattern)? [Consistency, Plan §"Source Code"]
