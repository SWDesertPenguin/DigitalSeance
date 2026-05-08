# Testability Quality Checklist: Network-Layer Per-IP Rate Limiting

**Purpose**: Validate that spec 019's testability requirements (middleware-ordering startup-test canary, per-FR coverage, per-SC coverage, §7.5 byte-identical contract test, privacy-contract test, regression test for unset-env-var byte-identical baseline, CI runtime constraints, determinism under simulated time, fixture quality, smoke tests, flakiness considerations) are specified clearly enough that test authors and CI gates can apply them without ambiguity. This checklist tests testability-requirement quality, not the implementation of any test.
**Created**: 2026-05-08
**Feature**: [spec.md §"Success Criteria"](../spec.md) + [contracts/middleware-ordering.md](../contracts/middleware-ordering.md) + [contracts/audit-events.md](../contracts/audit-events.md) + [contracts/metrics.md](../contracts/metrics.md)

## Middleware-Ordering Startup Test (FR-001 / FR-002 — the highest-leverage canary)

- [ ] CHK001 Is the requirement for `tests/test_019_middleware_order.py` to assert "NetworkRateLimit is the OUTERMOST middleware when ENABLED=true" specified at sufficient detail (which `app.user_middleware` slot is checked, what assertion fails the test)? [Measurability, Contracts §middleware-ordering "Property 1"]
- [ ] CHK002 Is the requirement for the same test file to assert "NetworkRateLimit is ABSENT from `user_middleware` when ENABLED=false" specified as binding for SC-006 byte-identical preservation? [Completeness, Contracts §middleware-ordering "Property 2"]
- [ ] CHK003 Are the four enumerated failure modes the test must catch (auth-after-limiter, limiter-first-instead-of-last, unconditional registration, conditional ordering drift) each specified at sufficient detail to translate into individual test assertions? [Completeness, Contracts §middleware-ordering "Failure modes"]
- [ ] CHK004 Is the contract "the test does NOT verify behavioral correctness of the limiter; it verifies registration-order topology only" specified clearly enough to keep this test fast and targeted? [Clarity, Contracts §middleware-ordering "Failure modes"]
- [ ] CHK005 Are the requirements for the `monkeypatch.setenv` pattern specified to ensure the test does not leak env-var state across tests? [Gap]

## Per-FR Test Coverage

- [ ] CHK006 Is FR-001 (limiter is FIRST middleware on every non-exempt request) traceable to `test_019_middleware_order.py` and at least one behavioral test? [Traceability, Plan §"Source Code"]
- [ ] CHK007 Is FR-002 (middleware MUST run BEFORE auth/bcrypt/token-inspection; verified at startup) traceable to `test_019_middleware_order.py`? [Traceability, Plan §"Source Code" + Contracts §middleware-ordering]
- [ ] CHK008 Is FR-003 (token-bucket algorithm with RPM + BURST) traceable to `test_019_flood_blocked.py`? [Traceability, Plan §"Source Code"]
- [ ] CHK009 Is FR-004 (IPv4 /32 + IPv6 /64 keying) traceable to a test that exercises both address families and verifies the keyed form (not raw IPv6) appears in audit? [Traceability, Plan §"Source Code"]
- [ ] CHK010 Is FR-005 (HTTP 429 + `Retry-After` header per RFC 6585; fixed body text; no echoed content) traceable to `test_019_flood_blocked.py`? [Traceability, Spec §FR-005 + Quickstart §"Verify Retry-After header"]
- [ ] CHK011 Is FR-006 (exempt paths `GET /health` + `GET /metrics`; method-restricted) traceable to `test_019_exempt_and_isolation.py`? [Traceability, Plan §"Source Code"]
- [ ] CHK012 Is FR-007 (no shared state with §7.5 limiter; independently testable) traceable to `test_019_exempt_and_isolation.py` covering SC-004? [Traceability, Plan §"Notes for /speckit.tasks"]
- [ ] CHK013 Is FR-008 (network-rejected request short-circuits at middleware boundary; never reaches application layer) traceable to a test that asserts cost tracker / participant counters / conversation state unchanged? [Traceability, Spec §SC-005]
- [ ] CHK014 Is FR-009 (per-(source_ip_keyed, minute) coalescing; `rejection_count` field) traceable to `test_019_audit_and_metrics.py`? [Traceability, Plan §"Source Code"]
- [ ] CHK015 Is FR-010 (counter labels `(endpoint_class, exempt_match)` only; no PII) traceable to `test_019_audit_and_metrics.py` covering SC-009? [Traceability, Contracts §metrics "Test signature"]
- [ ] CHK016 Is FR-011 (forwarded-header parsing gated by `_TRUST_FORWARDED_HEADERS`; rightmost-trusted entry) traceable to a test? [Traceability, Spec §FR-011 + Research §4]
- [ ] CHK017 Is FR-012 (source-IP-unresolvable → HTTP 400 + audit row) traceable to a test that drives malformed input and verifies the audit `reason` field? [Traceability, Spec §FR-012 + Contracts §audit-events `source_ip_unresolvable`]
- [ ] CHK018 Is FR-013 (V16 deliverable gate; 5 validators + docs sections before `/speckit.tasks`) traceable to `test_019_validators.py`? [Traceability, Contracts §env-vars "Test obligations"]
- [ ] CHK019 Is FR-014 (byte-identical pre-feature behavior when all vars unset; clear startup-exit error on invalid value) traceable to `test_019_validators.py` and a regression test? [Traceability, Spec §FR-014 + SC-006 + SC-007]
- [ ] CHK020 Is FR-015 (WebSocket upgrade counts as one request at upgrade; subsequent traffic out of scope) traceable to a test? [Traceability, Spec §FR-015]

## Per-SC Test Coverage

- [ ] CHK021 Is SC-001 (200 RPS flood from one IP → bcrypt invocation count bounded by RPM/min) traceable to `test_019_flood_blocked.py` with a load-test mechanism? [Traceability, Spec §SC-001]
- [ ] CHK022 Is SC-002 (legitimate auth from non-flooding IP completes within nominal latency during sustained flood) traceable to a test that drives flood from IP A and measures auth latency from IP B? [Traceability, Spec §SC-002]
- [ ] CHK023 Is SC-003 (exempt endpoints remain available at unbounded rate; no HTTP 429 on `/health` or `/metrics`) traceable to `test_019_exempt_and_isolation.py`? [Traceability, Spec §SC-003 + Quickstart §"Confirm exempt paths"]
- [ ] CHK024 Is SC-004 (§7.5 per-participant limiter behaves byte-identically with network-layer limiter active) traceable to `test_019_exempt_and_isolation.py` running the §7.5 acceptance suite under load? [Measurability, Spec §SC-004 + Plan §"Notes for /speckit.tasks"]
- [ ] CHK025 Is SC-005 (network-layer rejected request never reaches application-layer state) traceable to a test that asserts cost tracker / participant counters / conversation state / unrelated audit entries unchanged? [Traceability, Spec §SC-005]
- [ ] CHK026 Is SC-006 (all four-or-five env vars unset → full pre-feature acceptance suite passes byte-identically) traceable to a CI matrix entry that runs the pre-feature suite with the spec-019 vars unset? [Measurability, Spec §SC-006]
- [ ] CHK027 Is SC-007 (any env var invalid → orchestrator exits at startup with clear error naming the offending var) traceable to `test_019_validators.py`? [Traceability, Spec §SC-007]
- [ ] CHK028 Is SC-008 (1-hour sustained flood → audit-log volume bounded by `unique_flooding_IPs × 60 minutes`) traceable to a test that drives a sustained flood and asserts the row count? [Measurability, Spec §SC-008]
- [ ] CHK029 Is SC-009 (privacy contract: no raw IPv6, no query string, no headers, no body in audit row OR metric labels) traceable to `test_019_audit_and_metrics.py`? [Traceability, Contracts §metrics "Test signature" + Contracts §audit-events "Privacy contract"]

## §7.5 Byte-Identical Contract Test (SC-004)

- [ ] CHK030 Are the requirements for the SC-004 contract test specified at sufficient detail (run the §7.5 acceptance suite with the network-layer limiter active; assert no behavior change in §7.5's thresholds, rejections, or audit shape)? [Measurability, Spec §SC-004 + Plan §"Notes for /speckit.tasks"]
- [ ] CHK031 Is the contract "drives a §7.5 contract probe under load and asserts no behavioral drift" specified at sufficient detail to translate into test assertions? [Clarity, Plan §"Notes for /speckit.tasks"]
- [ ] CHK032 Are the requirements for "the two limiters MUST be independently testable" specified at sufficient detail to guarantee SC-004 can run without spec-019-specific mocks of §7.5? [Completeness, Spec §FR-007]

## Privacy Contract Test (SC-009)

- [ ] CHK033 Are the requirements for the SC-009 audit-row privacy test specified at sufficient detail (assert `target_id` is keyed form, not raw IPv6; assert `endpoint_paths_seen` is path-only; assert no headers/body in `new_value`)? [Completeness, Contracts §audit-events "Privacy contract"]
- [ ] CHK034 Are the requirements for the SC-009 metric-label privacy test specified at sufficient detail (assert label set is exactly `{endpoint_class, exempt_match}`; reject any addition; reject any forbidden label key)? [Measurability, Contracts §metrics "Test signature"]
- [ ] CHK035 Is the contract for "the privacy contract test rejects future label additions that would inflate cardinality or leak PII" specified clearly enough to catch reviewer drift? [Clarity, Contracts §metrics "Privacy contract"]

## Regression Test for Unset-Env-Var Byte-Identical Baseline (SC-006)

- [ ] CHK036 Are the requirements for the SC-006 regression test specified — full pre-feature acceptance suite passes byte-identically when all five vars are unset? [Measurability, Spec §SC-006 + FR-014]
- [ ] CHK037 Is the contract for the CI matrix entry that runs the pre-feature suite under spec-019-vars-unset specified at sufficient detail (which suite, what triggers failure)? [Clarity, Spec §SC-006]
- [ ] CHK038 Are the requirements for "no middleware registered, no rejections, no audit entries for network-layer events" specified as binding consequences when vars are unset? [Completeness, Spec §FR-014]

## Determinism

- [ ] CHK039 Is "deterministic token-bucket lazy-refill behavior under simulated time" specified at sufficient detail to verify (`monotonic` time mock, advance by N seconds, assert refill amount = `N × RPM / 60.0`)? [Measurability, Research §1]
- [ ] CHK040 Are the requirements for streaming-rejection determinism specified (same flood input → same rejection sequence across runs, across processes, across machines)? [Gap]
- [ ] CHK041 Is the contract for `count`-based assertions specified for SC-001 (the load test asserts bcrypt invocation count, not wall-clock latency) to keep tests deterministic? [Clarity, Spec §SC-001]

## Test Fixture Quality

- [ ] CHK042 Are the requirements for source-IP fixture values specified at sufficient detail (use `203.0.113.0/24` TEST-NET-3 documentation prefix to avoid collision with real IPs)? [Completeness, Contracts §metrics "Test signature"]
- [ ] CHK043 Is the rule "fixtures contain no real credentials" specified as binding (and verifiable via gitleaks/2MS scan)? [Verifiability, Plan §"Constitution Check V11"]
- [ ] CHK044 Are the requirements for IPv6 keying tests specified at sufficient detail (IPv4-mapped-IPv6 unmapped to v4; link-local addresses keyed at /64; zone identifiers stripped)? [Completeness, Research §5]

## CI Runtime Constraints

- [ ] CHK045 Are the requirements for CI test runtime specified — flood tests should not take longer than the existing CI budget (e.g., flood tests use mock-time, not wall-clock)? [Gap]
- [ ] CHK046 Is the contract for "load tests run with synthetic clock advancement, not real-time `sleep` calls" specified at sufficient detail to keep CI deterministic? [Clarity, Research §1]
- [ ] CHK047 Are the requirements for parallel-test isolation specified — `OrderedDict` per-IP map state does not leak across tests; flush-task is stopped between tests? [Gap, Data-model §"PerIPBudget" "Concurrency"]

## Smoke Tests for the Production Path

- [ ] CHK048 Are the requirements for cross-spec smoke tests specified (spec 016 counter increment with correct labels; `routing_log` middleware-duration row appearance; `admin_audit_log` row write via background flush)? [Completeness, Plan §"Source Code" + Plan §"Notes for /speckit.tasks"]
- [ ] CHK049 Is the contract for "post-deployment smoke test against a real orchestrator" specified — synthetic flood + audit-log query + metrics scrape (per quickstart §"Observe limiter behavior")? [Completeness, Quickstart §"Observe limiter behavior"]

## Flakiness Considerations

- [ ] CHK050 Are the requirements for timer-based test reliability specified — background flush task fired exactly once per minute (mock the timer; advance by 60 seconds; assert exactly one flush)? [Measurability, Research §6]
- [ ] CHK051 Is the contract for retry-on-flake explicitly forbidden specified — flakiness is a bug, not a tolerable test cost? [Gap]
- [ ] CHK052 Are the requirements for asyncio task lifecycle in tests specified — the background flush task started by the middleware must be cancelled at test teardown to prevent leak across tests? [Gap, Data-model §"PerIPBudget" "Concurrency"]

## Test Documentation

- [ ] CHK053 Are the requirements for each spec-019 test file's docstring specified (which FR/SC it exercises)? [Gap]
- [ ] CHK054 Is the test-naming convention specified (`test_019_*` prefix mirroring spec 025's pattern)? [Consistency, Plan §"Source Code"]

## Notes

Highest-impact open items:
- CHK001-CHK004 (the FR-002 middleware-ordering startup test) is the single highest-leverage canary in the entire spec; if this test is incomplete, "auth-before-limiter" regressions slip through and silently break the threat model.
- CHK024 + CHK030-CHK032 are the SC-004 §7.5 byte-identical contract — load-bearing for the architectural claim that the two limiters do not interact.
- CHK040 ([Gap]) on streaming-rejection determinism — without this, intermittent CI failures under flood-load may be hard to triage.
- CHK045 + CHK046 + CHK047 + CHK051 + CHK052 ([Gap]) cluster on flakiness / CI runtime / asyncio task lifecycle — flush-task leak across tests is the most likely flakiness vector and the spec is currently silent on its mitigation.
- CHK053 ([Gap]) on test docstrings — without FR/SC references in docstrings, traceability degrades over time.

Use the `[PASS] / [PARTIAL] / [GAP] / [DRIFT] / [ACCEPTED]` annotation convention when triaging items.
