---

description: "Task list for implementing spec 019 (Network-Layer Per-IP Rate Limiting)"
---

# Tasks: Network-Layer Per-IP Rate Limiting

**Input**: Design documents from `/specs/019-network-rate-limiting/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — spec defines three Independent Tests + 14 Acceptance Scenarios across US1-US3, plus the FR-002 middleware-ordering canary, the SC-006 master-switch regression, the SC-004 §7.5-isolation contract test, the SC-009 privacy contract, and three fail-closed pipeline edge cases. Tests land alongside implementation.

**Organization**: Tasks grouped by user story so each can be implemented and tested independently. Phase 2 covers the V16 deliverable gate (per spec FR-013) and the middleware-ordering canary (per FR-002). NO schema migration and NO `tests/conftest.py` mirror change — the limiter is in-memory only (data-model.md "Schema additions: None").

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, OR independent functions in the same file with no shared edit point)
- **[Story]**: US1 / US2 / US3 (no label for Setup, Foundational, Polish)

## Path Conventions

Single project, paths under repo root. Backend code under [src/](../../src/); tests under [tests/](../../tests/) per [plan.md "Source Code"](./plan.md). No frontend changes — this is operator-facing infrastructure (V13 parallel to spec 016). The Phase-2 Web UI on port 8751 reuses this exact middleware without spec change; the Phase-2 wiring task is out of scope here.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repo hygiene + new module placeholders. Working tree is on `019-network-rate-limiting` branch off main.

- [ ] T001 Verify on branch `019-network-rate-limiting` and run `python scripts/check_env_vars.py` to confirm V16 baseline passes after the gate work in Phase 2 lands
- [ ] T002 [P] Create empty module skeletons: [src/middleware/__init__.py](../../src/middleware/__init__.py) (package marker), [src/middleware/network_rate_limit.py](../../src/middleware/network_rate_limit.py), [src/audit/__init__.py](../../src/audit/__init__.py) (package marker if missing), [src/audit/network_rate_limit_audit.py](../../src/audit/network_rate_limit_audit.py) — each containing only a module docstring referencing spec 019

---

## Phase 2: Foundational (Blocking Prerequisites — V16 Gate per FR-013 + middleware-ordering canary)

**Purpose**: V16 env-var deliverables (5 validators + 5 docs sections — landed THIS round per spec FR-013), the middleware-ordering startup canary (per FR-002 — the highest-leverage early signal that the limiter sits BEFORE auth/bcrypt). All three user stories depend on these.

**CRITICAL**: No user-story task in Phase 3+ may begin until Phase 2 completes. The V16 gate is non-negotiable per spec FR-013.

### V16 deliverable gate (5 validators + 5 doc sections) — landed THIS round

- [X] T003 [P] Add `validate_network_ratelimit_enabled` to [src/config/validators.py](../../src/config/validators.py) per [contracts/env-vars.md §SACP_NETWORK_RATELIMIT_ENABLED](./contracts/env-vars.md): empty OR `'true'/'false'` (case-insensitive) OR `'1'/'0'`; out-of-set exits at startup
- [X] T004 [P] Add `validate_network_ratelimit_rpm` to [src/config/validators.py](../../src/config/validators.py) per [contracts/env-vars.md §SACP_NETWORK_RATELIMIT_RPM](./contracts/env-vars.md): empty (admissible only when `_ENABLED` unset/false) OR integer in `[1, 6000]`; cross-validator failure when `_ENABLED=true` AND `_RPM` unset
- [X] T005 [P] Add `validate_network_ratelimit_burst` to [src/config/validators.py](../../src/config/validators.py) per [contracts/env-vars.md §SACP_NETWORK_RATELIMIT_BURST](./contracts/env-vars.md): empty OR integer in `[1, 10000]`; out-of-range exits at startup
- [X] T006 [P] Add `validate_network_ratelimit_trust_forwarded_headers` to [src/config/validators.py](../../src/config/validators.py) per [contracts/env-vars.md §SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS](./contracts/env-vars.md): empty OR `'true'/'false'` (case-insensitive) OR `'1'/'0'`; out-of-set exits at startup
- [X] T007 [P] Add `validate_network_ratelimit_max_keys` to [src/config/validators.py](../../src/config/validators.py) per [contracts/env-vars.md §SACP_NETWORK_RATELIMIT_MAX_KEYS](./contracts/env-vars.md): empty OR integer in `[1024, 1_000_000]`; out-of-range exits at startup
- [X] T008 Append the five new validators to the `VALIDATORS` tuple at the bottom of [src/config/validators.py](../../src/config/validators.py) (depends on T003-T007)
- [X] T009 [P] Add `### SACP_NETWORK_RATELIMIT_ENABLED` section to [docs/env-vars.md](../../docs/env-vars.md) with the six standard fields per [contracts/env-vars.md](./contracts/env-vars.md)
- [X] T010 [P] Add `### SACP_NETWORK_RATELIMIT_RPM` section to [docs/env-vars.md](../../docs/env-vars.md) with the six standard fields plus the cross-validator constraint note
- [X] T011 [P] Add `### SACP_NETWORK_RATELIMIT_BURST` section to [docs/env-vars.md](../../docs/env-vars.md) with the six standard fields
- [X] T012 [P] Add `### SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS` section to [docs/env-vars.md](../../docs/env-vars.md) with the six standard fields
- [X] T013 [P] Add `### SACP_NETWORK_RATELIMIT_MAX_KEYS` section to [docs/env-vars.md](../../docs/env-vars.md) with the six standard fields
- [X] T014 Run `python scripts/check_env_vars.py` from repo root and confirm V16 CI gate green for the five new vars (validators + doc sections in lockstep)
- [ ] T015 [P] Validator unit tests in [tests/test_019_validators.py](../../tests/test_019_validators.py): each of the five validators — valid value passes, out-of-range raises `ConfigValidationError` naming the offending var, empty handled per the var's allowed-empty rule, and the cross-validator constraint (`_ENABLED=true` with `_RPM` unset → `ConfigValidationError` naming `SACP_NETWORK_RATELIMIT_RPM`)

### No schema migration / no conftest mirror — deliberate negative requirement

This spec introduces ZERO database tables, ZERO new columns on existing tables, and ZERO `tests/conftest.py` schema-mirror changes. The limiter is in-memory only ([data-model.md "Schema additions: None"](./data-model.md)); the audit-log rejection rows ride the existing `admin_audit_log` table without delta. Reviewers expecting a schema-mirror task per memory `feedback_test_schema_mirror` should find this section and confirm the negative requirement is intentional. There is no T-number for an alembic migration here because none is needed.

### Middleware-ordering startup canary (FR-002 — highest-leverage early signal)

- [ ] T016 [P] Middleware-ordering startup test in [tests/test_019_middleware_order.py](../../tests/test_019_middleware_order.py) per [contracts/middleware-ordering.md "Startup-test signature"](./contracts/middleware-ordering.md): two properties — (1) when `SACP_NETWORK_RATELIMIT_ENABLED=true`, `app.user_middleware[-1].cls.__name__ == "NetworkRateLimitMiddleware"` (the LAST entry is the OUTERMOST per FastAPI semantics; FR-002); (2) when `SACP_NETWORK_RATELIMIT_ENABLED=false`, `NetworkRateLimitMiddleware` is absent from `app.user_middleware` (FR-014 / SC-006). The canary lands EARLY so any "auth-before-limiter" regression surfaces in CI before US-phase code grows
  - Caplog assertion: with `SACP_NETWORK_RATELIMIT_ENABLED=true`, exactly one log record matching `r"^Middleware order \(outermost first\): \[NetworkRateLimitMiddleware,"` is emitted per `build_app()` invocation. With ENABLED=false, NO record matching that prefix is emitted. (Pins the operator-visible introspection contract from contracts/middleware-ordering.md.)

**Checkpoint**: V16 gate green. T003-T014 landed in the V16-gate landing pass (commit reference TBD when committed). On rerun, these tasks SHOULD remain `[X]`; treat any unchecked state as a regression and re-run `python scripts/check_env_vars.py` to confirm gate green. Middleware-ordering canary in place. Schema/conftest negative requirement explicit. User-story phases unblocked.

---

## Phase 3: User Story 1 — Per-IP rate limiting blocks a bcrypt-flood attack before bcrypt runs (Priority: P1) MVP

**Goal**: A token-bucket per-IP rate limiter rejects flood traffic with HTTP 429 + `Retry-After` BEFORE any auth or bcrypt work runs. Source IP is the immediate peer by default; operators can opt in to RFC 7239 `Forwarded` / `X-Forwarded-For` parsing. IPv4 keys at `/32`, IPv6 at `/64`. The map is bounded at `MAX_KEYS` via `OrderedDict` LRU. Source-IP-unresolvable requests reject with HTTP 400 per FR-012.

**Independent Test**: Drive the MCP server's auth endpoint with a synthetic flood (200+ requests/second per source IP, all with syntactically valid but invalid tokens). Verify the limiter rejects the bulk with HTTP 429 BEFORE bcrypt is invoked, that the orchestrator's bcrypt-validation count stays bounded by the per-window budget, and that legitimate authentication from a different source IP completes within nominal latency.

### Tests for User Story 1

- [ ] T017 [P] [US1] Acceptance scenario 1 (flood from IP A: at most `RPM` requests reach bcrypt; remaining requests rejected HTTP 429 BEFORE bcrypt — verified by mocking the bcrypt entry point and counting calls) in [tests/test_019_us1_bcrypt_flood.py](../../tests/test_019_us1_bcrypt_flood.py) — covers SC-001
  - Assert that an ADMITTED request decrements the per-IP bucket regardless of whether the downstream auth path subsequently succeeds, fails, or never runs (the limiter has paid its cost at the admit decision; auth-failure refunds are NOT performed). Per spec.md §"Edge Cases" — "Bcrypt validation succeeds but the auth path then fails for some other reason."
- [ ] T018 [P] [US1] Acceptance scenario 2 (legitimate request from IP B during IP A's flood completes within nominal latency — limiter's per-IP scoping has no collateral effect) in [tests/test_019_us1_bcrypt_flood.py](../../tests/test_019_us1_bcrypt_flood.py) — covers SC-002
- [ ] T019 [P] [US1] Acceptance scenario 3 (HTTP 429 response carries a `Retry-After` header per RFC 6585, integer-seconds form indicating time until the next admission) in [tests/test_019_us1_bcrypt_flood.py](../../tests/test_019_us1_bcrypt_flood.py) — covers FR-005
  - Assert the response body equals the fixed string `"rate limit exceeded"` exactly.
  - Assert the response body contains NONE of the request's path components, query string content, header values, or body bytes (FR-005 privacy contract).
- [ ] T020 [P] [US1] Acceptance scenario 4 (`SACP_NETWORK_RATELIMIT_ENABLED=false` → behavior byte-identical to pre-feature; no middleware registered, no rejections, no audit entries) in [tests/test_019_us1_bcrypt_flood.py](../../tests/test_019_us1_bcrypt_flood.py) — covers FR-014 / SC-006 (overlaps with T016 ordering canary but exercises end-to-end byte-identity)
- [ ] T021 [P] [US1] IPv6 keying test: requests from two distinct `/128` addresses within the same `/64` share a budget; requests from a different `/64` do not (FR-004) in [tests/test_019_us1_bcrypt_flood.py](../../tests/test_019_us1_bcrypt_flood.py)
- [ ] T022 [P] [US1] Source-IP-unresolvable test: malformed connection / missing peer → HTTP 400 + `source_ip_unresolvable` audit row per FR-012 in [tests/test_019_us1_bcrypt_flood.py](../../tests/test_019_us1_bcrypt_flood.py)
- [ ] T022a [P] [US1] WebSocket upgrade single-decrement test in [tests/test_019_us1_bcrypt_flood.py](../../tests/test_019_us1_bcrypt_flood.py) per spec.md FR-015: a WS upgrade decrements the per-IP token bucket exactly once at the upgrade moment, and subsequent inbound WS frames over the established socket do NOT consume bucket tokens (post-auth in-band traffic is §7.5 / spec 002 territory).

### Implementation for User Story 1

- [ ] T023 [P] [US1] Implement `PerIPBudget` dataclass + `TokenBucket.evaluate(source_ip_keyed, now)` lazy-refill core in [src/middleware/network_rate_limit.py](../../src/middleware/network_rate_limit.py) per [data-model.md §PerIPBudget](./data-model.md): `current_tokens` clamps to `BURST`; `refill = (now - last_refill_at) × RPM / 60.0`; admit / reject decision returned alongside the post-decision `current_tokens` value (used to derive `Retry-After`). Each function body stays under 25 lines per Constitution §6.10
- [ ] T024 [P] [US1] Implement `_key_source_ip(remote_addr)` transform in [src/middleware/network_rate_limit.py](../../src/middleware/network_rate_limit.py) per [data-model.md §PerIPBudget](./data-model.md) and FR-004: IPv4 → full 32-bit dotted-decimal; IPv6 → first 64 bits in canonical hex form. Stdlib `ipaddress` module only — no third-party. Returns `None` on parse failure (drives FR-012 rejection)
- [ ] T025 [P] [US1] Implement `_parse_forwarded_header(headers)` per FR-011 + research.md §4 in [src/middleware/network_rate_limit.py](../../src/middleware/network_rate_limit.py): RFC 7239 `Forwarded` rightmost-trusted entry preferred, `X-Forwarded-For` rightmost as fallback. Gated on `SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS=true`; otherwise the function is never called and the immediate peer IP is used directly
- [ ] T026 [US1] Implement `OrderedDict[str, PerIPBudget]` LRU map with `_admit_or_reject(source_ip_keyed)` wrapper in [src/middleware/network_rate_limit.py](../../src/middleware/network_rate_limit.py) per [data-model.md "State transitions"](./data-model.md) and research.md §3: move-to-end on every access; `popitem(last=False)` evicts the least-recently-accessed entry when `len(map) > MAX_KEYS`. Depends on T023
- [ ] T027 [US1] Implement `NetworkRateLimitMiddleware` ASGI middleware class in [src/middleware/network_rate_limit.py](../../src/middleware/network_rate_limit.py): `__call__(scope, receive, send)` early-out for non-`http`/`websocket` scopes; calls `_admit_or_reject`; on rejection sends HTTP 429 with `Retry-After` header per FR-005 (RFC 6585) and fixed body `b"rate limit exceeded"` (no echo of request content). On source-IP-unresolvable, sends HTTP 400 per FR-012 and triggers the `source_ip_unresolvable` audit emission. Depends on T024-T026
- [ ] T028 [US1] Register `NetworkRateLimitMiddleware` as the LAST `add_middleware` call (= outermost on the request stack) in [src/main.py](../../src/main.py) per [contracts/middleware-ordering.md "Required pattern"](./contracts/middleware-ordering.md). Conditional on `SACP_NETWORK_RATELIMIT_ENABLED=true` (FR-014 / SC-006 — middleware MUST NOT appear in `user_middleware` when disabled). Add an INFO log line emitting the resolved middleware order outermost-first per [contracts/middleware-ordering.md "Operator-visible introspection"](./contracts/middleware-ordering.md). The startup canary (T016) verifies the registration. NOTE: This is the ONLY edit to `src/main.py` for this spec
  - The startup INFO log line MUST emit the resolved middleware order in a stable, regex-checkable format: `Middleware order (outermost first): [<name1>, <name2>, ...]`. Use this exact prefix so downstream caplog assertions can match without parsing JSON or structured-log fields.
- [ ] T029 [US1] Plumb the limiter middleware's per-request duration into `routing_log` on a sample of requests per [plan.md "Performance Goals"](./plan.md) and spec 003 §FR-030: V14 budget enforcement via the existing `@with_stage_timing(stage_name='network_rate_limit_ms')` pattern (or the equivalent middleware-duration sample shape used elsewhere). One row per sampled request; sampling rate operator-tunable via existing routing-log knobs

**Checkpoint**: US1 fully functional and testable independently. MVP increment: bcrypt-flood traffic is rejected BEFORE bcrypt runs; legitimate traffic from other IPs is unaffected; HTTP 429 responses carry `Retry-After`; source-IP-unresolvable requests reject HTTP 400.

---

## Phase 4: User Story 2 — Operational endpoints stay reachable; layers do not interact (Priority: P2)

**Goal**: `GET /health` and `GET /metrics` bypass the limiter entirely (no per-IP budget consumption, no rejection possibility) so Prometheus scrapers and Docker healthchecks remain unbounded. Other methods on those paths fall through to normal limiter handling. The §7.5 application-layer per-participant rate limiter behaves byte-identically to its pre-feature implementation — the two limiters share NO state.

**Independent Test**: Start the orchestrator with `SACP_NETWORK_RATELIMIT_RPM=10` (deliberately low). Drive the limit to its threshold from a single IP. Verify (a) `/health` and `/metrics` continue to respond on that IP at unbounded rate, (b) the application-layer per-participant limiter for that participant behaves identically to before this spec — same thresholds, same rejections, same audit shape, with zero shared state.

### Tests for User Story 2

- [ ] T030 [P] [US2] Acceptance scenario 1 (IP A's per-IP budget exhausted; `GET /health` and `GET /metrics` from IP A still serve normally) in [tests/test_019_us2_exempt_and_layers.py](../../tests/test_019_us2_exempt_and_layers.py) — covers SC-003
- [ ] T031 [P] [US2] Acceptance scenario 2 (participant P at IP A: §7.5 limiter throttles per-participant independent of network-layer state — even when network-layer budget is plentiful) in [tests/test_019_us2_exempt_and_layers.py](../../tests/test_019_us2_exempt_and_layers.py) — covers FR-007
- [ ] T032 [P] [US2] Acceptance scenario 3 (network-layer rejected request never updates §7.5 per-participant counters — application-layer state unchanged) in [tests/test_019_us2_exempt_and_layers.py](../../tests/test_019_us2_exempt_and_layers.py) — covers FR-008 / SC-005
- [ ] T033 [P] [US2] Acceptance scenario 4 (participant P at §7.5 limit: §7.5 throttles independent of plentiful per-IP budget — both limiters fire on different signals) in [tests/test_019_us2_exempt_and_layers.py](../../tests/test_019_us2_exempt_and_layers.py)
- [ ] T034 [P] [US2] Method-restricted exempt test: `POST /health` and `POST /metrics` are NOT exempt — fall through to normal limiter handling (FR-006) in [tests/test_019_us2_exempt_and_layers.py](../../tests/test_019_us2_exempt_and_layers.py)
- [ ] T035 [US2] §7.5 application-layer per-participant rate-limiter isolation probe in [tests/test_019_us2_exempt_and_layers.py](../../tests/test_019_us2_exempt_and_layers.py) per FR-007/FR-008 + SC-004: drive a synthetic per-participant call sequence at a rate ABOVE the §7.5 30-write/min threshold (per `sacp-design.md` §7.5 — note: §7.5 is currently a sacp-design.md design-doc reference, not a coded spec with an existing acceptance suite). Assert: (a) the §7.5 limiter rejects calls at the documented threshold regardless of network-layer state, AND (b) the network-layer rejection counter is unchanged when the §7.5 limiter rejects.

### Implementation for User Story 2

- [ ] T036 [US2] Implement `EXEMPT_PATHS` frozen module-level constant in [src/middleware/network_rate_limit.py](../../src/middleware/network_rate_limit.py) per [data-model.md §ExemptPathRegistry](./data-model.md): `tuple[tuple[str, str], ...]` shape `(("GET", "/health"), ("GET", "/metrics"))`. Read-only at runtime; defined at module load
- [ ] T037 [US2] Wire exempt-path early-out into `NetworkRateLimitMiddleware.__call__` in [src/middleware/network_rate_limit.py](../../src/middleware/network_rate_limit.py): the check runs BEFORE source-IP resolution work (V14 — exempt requests incur no keying cost). Exact path match; method-restricted (`GET` only). Other methods fall through to normal limiter handling per FR-006

**Checkpoint**: US2 functional. Exempt paths are unbounded; non-GET methods on those paths are normally rate-limited; the §7.5 application-layer limiter is provably untouched by this spec's middleware (FR-007 / FR-008).

---

## Phase 5: User Story 3 — Rejected requests are auditable and visible in the metrics surface (Priority: P3)

**Goal**: Every limiter rejection emits to the spec 016 metric counter (`sacp_rate_limit_rejection_total{endpoint_class="network_per_ip", exempt_match="false"}`) per-rejection AND coalesces into the `admin_audit_log` per-`(source_ip_keyed, minute_bucket)` summary row via a background asyncio flush task that runs OUTSIDE the request path (V14 budget per [plan.md "Performance Goals"](./plan.md)). Source-IP-unresolvable rejections write one audit row each (NOT coalesced — rare and forensically important).

**Independent Test**: Drive the limiter to its threshold from a single IP. Verify the audit log captures each rejection cluster with the documented payload shape, that the spec 016 metric counter increments with the correct labels, and that the metric labels do NOT carry the rejected request's headers, query string, or body content.

### Tests for User Story 3

- [ ] T038 [P] [US3] Acceptance scenario 1 (rejection writes `admin_audit_log` row of action `network_rate_limit_rejected` with `target_id=source_ip_keyed`, `new_value` JSON containing `(minute_bucket, first_rejected_at, last_rejected_at, rejection_count, endpoint_paths_seen, methods_seen, limiter_window_remaining_s)` per [contracts/audit-events.md](./contracts/audit-events.md)) in [tests/test_019_us3_audit_metrics.py](../../tests/test_019_us3_audit_metrics.py)
- [ ] T039 [P] [US3] Acceptance scenario 2 (`sacp_rate_limit_rejection_total` counter increments with `endpoint_class="network_per_ip"` AND `exempt_match="false"`; no other labels present per [contracts/metrics.md "Label set"](./contracts/metrics.md)) in [tests/test_019_us3_audit_metrics.py](../../tests/test_019_us3_audit_metrics.py)
- [ ] T040 [P] [US3] Acceptance scenario 3 (sustained 200-rejection minute → ONE audit row with `rejection_count=200`; counter incremented 200 times — per-rejection durability via Prometheus scrape, per-(IP, minute) compactness via audit log) in [tests/test_019_us3_audit_metrics.py](../../tests/test_019_us3_audit_metrics.py) — covers FR-009 / SC-008
  - Compute the total `network_rate_limit_rejected` row count over a 1-hour synthetic flood with N unique flooding IPs, and assert the count is `≤ N × 60` per SC-008's bound formula. Use simulated time so the test runs in under a few seconds.
- [ ] T041 [P] [US3] Acceptance scenario 4 (`source_ip_unresolvable` rejection → HTTP 400, ONE non-coalesced audit row with `reason` field, counter increments with same labels — per [contracts/audit-events.md §source_ip_unresolvable](./contracts/audit-events.md)) in [tests/test_019_us3_audit_metrics.py](../../tests/test_019_us3_audit_metrics.py) — covers FR-012
- [ ] T042 [P] [US3] Privacy contract test: assert audit row's `new_value` JSON contains NO raw IPv6 host (only the `/64` keyed form), NO query string in `endpoint_paths_seen`, NO request headers, NO body content; assert metric label set is exactly `{endpoint_class, exempt_match}` and rejects any addition per [contracts/metrics.md "Privacy contract"](./contracts/metrics.md) in [tests/test_019_us3_audit_metrics.py](../../tests/test_019_us3_audit_metrics.py) — covers SC-009

### Implementation for User Story 3

- [ ] T043 [US3] Implement `RejectionCoalescer` accumulator class in [src/audit/network_rate_limit_audit.py](../../src/audit/network_rate_limit_audit.py) per [data-model.md §NetworkRateLimitRejectedRecord](./data-model.md) and research.md §6: in-memory `dict[(source_ip_keyed, minute_bucket), CoalesceState]` aggregator; `record_rejection(source_ip_keyed, path, method, now)` updates the bucket; `endpoint_paths_seen` capped to a small N with `paths_truncated` flag (per [contracts/audit-events.md "Row contract"](./contracts/audit-events.md))
- [ ] T044 [US3] Implement background flush task in [src/audit/network_rate_limit_audit.py](../../src/audit/network_rate_limit_audit.py): asyncio task wakes once per minute, drains complete-minute buckets, writes one `admin_audit_log` row per drained bucket via the existing append-only path (V9), clears drained state. MUST NOT block the request path (V14 budget — flush is asynchronous). Failure to flush logs but does not propagate; metric counter retains per-rejection durability across the gap
- [ ] T045 [US3] Implement `emit_source_ip_unresolvable(path, method, reason, now)` helper in [src/audit/network_rate_limit_audit.py](../../src/audit/network_rate_limit_audit.py) per [contracts/audit-events.md §source_ip_unresolvable](./contracts/audit-events.md): writes ONE row per call (NOT coalesced); `reason` is one of `"no_peer"`, `"malformed_forwarded_header"`, `"no_xff_when_trust_enabled"`, `"parse_error"`. Failure to write logs but does NOT cause the HTTP 400 response to fall through (the 400 still goes out)
- [ ] T046 [P] [US3] Extend [src/observability/metrics.py](../../src/observability/metrics.py) (or wherever spec 016's prometheus counters live) to add the `(endpoint_class, exempt_match)` label set on `sacp_rate_limit_rejection_total` per [contracts/metrics.md "Label set"](./contracts/metrics.md). Cardinality bound: this spec contributes exactly 1 new time series (`endpoint_class="network_per_ip", exempt_match="false"`); the `app_layer_per_participant` value is reserved for §7.5's future adoption per [contracts/metrics.md "Future label values"](./contracts/metrics.md). Increment per-rejection (not per-coalesced-row) per FR-010
- [ ] T047 [US3] Wire `RejectionCoalescer.record_rejection` and `metrics.sacp_rate_limit_rejection_total.labels(...).inc()` calls into `NetworkRateLimitMiddleware`'s rejection branch in [src/middleware/network_rate_limit.py](../../src/middleware/network_rate_limit.py): coalescer call is in-memory only (NOT a DB write); metric increment is in-memory only; both are O(1). Depends on T027, T043, T046
- [ ] T048 [US3] Wire `emit_source_ip_unresolvable` into the FR-012 rejection branch in [src/middleware/network_rate_limit.py](../../src/middleware/network_rate_limit.py): increments the same metric counter labels as a normal rejection (cardinality bound preserved); audit row's `reason` field surfaces the unresolvable cause. Depends on T027, T045, T046

**Checkpoint**: US3 functional. Operators can query `admin_audit_log` for `network_rate_limit_rejected` rows and Prometheus for `sacp_rate_limit_rejection_total` to see flooding patterns; per-rejection durability via metrics, per-(IP, minute) compactness via audit log; privacy contract verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Fail-closed pipeline tests, V14 perf instrumentation verification, quickstart validation, Phase-2 forward note, cross-spec audit.

- [ ] T049 [P] Fail-closed pipeline tests in [tests/test_019_pipeline_failure.py](../../tests/test_019_pipeline_failure.py):
  - validator-failure-at-startup: invalid env var (e.g. `SACP_NETWORK_RATELIMIT_RPM=99999`) → the orchestrator process exits non-zero AND stderr contains the offending env-var name (e.g., `SACP_NETWORK_RATELIMIT_RPM`), per SC-007 ("clear error message naming the offending var"). Verify both: process exit code != 0 AND named-var substring in captured stderr.
  - source-IP-unresolvable rejection → HTTP 400 (NOT HTTP 200, NOT silent drop); audit row written; metric incremented (covers FR-012)
  - audit-flush task crash → metric counter remains accurate across the gap; orchestrator stays up (audit-write failure logs via existing audit-failure path); covers V15 fail-closed
- [ ] T050 [P] V14 perf-budget regression check: query `routing_log` to confirm `network_rate_limit_ms` p95 stays well below the V14 per-stage budget tolerance across the test corpus per [plan.md "Performance Goals"](./plan.md). Eviction at MAX_KEYS bound is O(1) amortized per `OrderedDict.popitem(last=False)` (research.md §3); confirm no spike at the eviction boundary
- [ ] T051 Quickstart.md walk-through: operator workflow per [quickstart.md](./quickstart.md) (enable master switch → tune RPM/BURST → drive synthetic flood → confirm `Retry-After` headers → query audit log for rejection rows → confirm metric counter → disable/rollback). Run on a deployed orchestrator (Dockge stack) per memory `project_deploy_dockge_truenas`
- [ ] T052 [P] Phase-2 web-UI port-8751 forward note (NO CODE — comment only): add a docstring note in [src/middleware/network_rate_limit.py](../../src/middleware/network_rate_limit.py) referencing [spec.md "Assumptions"](./spec.md) — the middleware is process-wide, not per-port, so Phase-2 reuse on port 8751 is a wiring change in `src/main.py`'s app construction, not a spec amendment. No additional task here
- [ ] T053 [P] Cross-spec FR audit:
  - spec 002 §FR-016 (XFF rightmost trust): the existing `SACP_TRUST_PROXY` semantics are unchanged. This spec's `SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS` is an INDEPENDENT opt-in scoped to network-layer rate-limiter source-IP keying (FR-011) — confirm no overlap or shadowing with `SACP_TRUST_PROXY` per spec edge case
  - spec 003 §FR-030 `routing_log` per-stage timings: confirm `network_rate_limit_ms` integrates with the existing `@with_stage_timing` pattern (T029)
  - spec 016 §FR-002 `/metrics` exempt path + counter surface: confirm `sacp_rate_limit_rejection_total` label-set extension lands at the existing counter (T046); `/metrics` is in this spec's exempt set (T036) — no scrape self-throttling
  - §7.5 application-layer per-participant limiter: confirm zero shared state, zero shared code path (T035 contract test); both limiters are independently testable per FR-007
  - Constitution §6.5 (bcrypt auth, Phase 1): the threat-model anchor is preserved — every flood-rejected request is rejected BEFORE bcrypt runs (T017 acceptance scenario 1)
  - V12 topology compatibility: topology 7 forward note in spec.md §V12 — the middleware is registered but typically idle when the orchestrator runs in topology 7 with no participant-facing inbound HTTP surfaces
- [ ] T054 [P] ruff + standards-lint pass: every commit on this branch passes the full pre-commit hook chain (gitleaks + 2ms + ruff + ruff-format + bandit + standards-lint 25/5)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — branch is already created from prior commit
- **Foundational (Phase 2)**: Depends on Setup — V16 gate (T003-T015) + middleware-ordering canary (T016). The gate work T003-T014 is already DONE THIS round; T015 unit-test work and T016 ordering-canary work are pending. BLOCKS all user stories
- **User Story 1 (Phase 3, P1)**: Depends on Phase 2 — primary value increment (token-bucket + middleware + 429 + 400)
- **User Story 2 (Phase 4, P2)**: Depends on Phase 2 + US1 (uses the middleware shell from US1; adds exempt-path early-out + §7.5 isolation contract)
- **User Story 3 (Phase 5, P3)**: Depends on Phase 2 + US1 (uses the middleware rejection branch from US1; adds audit emission + metric increment)
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies (recap)

- **US1**: Phase 2 → US1 (no story dependencies)
- **US2**: Phase 2 + US1 → US2 (exempt-path check inserts into US1's middleware shell)
- **US3**: Phase 2 + US1 → US3 (audit + metric emission inserts into US1's rejection branch)

### Within Each User Story

- Tests (which are included for this spec) MUST be written and FAIL before implementation per the test-first convention from Phase 2's middleware-ordering canary
- Per memory `feedback_test_schema_mirror`: NO alembic migration, NO `tests/conftest.py` mirror change — explicit negative requirement (see "No schema migration / no conftest mirror" above)
- Models / dataclasses before services; services before middleware wiring; middleware wiring before routing_log emissions
- Middleware-ordering canary (T016) is a prerequisite for any US-phase middleware work; if T016 fails after US1's T028 lands, the registration order is wrong

### Parallel Opportunities

- All Phase 2 [P] validator + doc tasks (T003-T013, except T008 and T014 which aggregate / verify) can run in parallel — landed THIS round
- T015 (validator unit tests) and T016 (ordering canary) can run in parallel — different files
- All [P] test tasks within a user story can run in parallel
- Five validator function additions in `src/config/validators.py` are [P] — different functions, no shared edit point; the `VALIDATORS` tuple append (T008) is NOT [P]
- Three signal helpers in US1 (T023-T025) can run in parallel — different functions in the same file with no shared edit point
- All Phase 6 [P] polish tasks can run in parallel

---

## Parallel Example: Phase 2 V16 deliverable gate (DONE THIS round)

```bash
# Five validator additions in src/config/validators.py (different functions, no shared edit point):
Task: "T003 [P] validate_network_ratelimit_enabled"
Task: "T004 [P] validate_network_ratelimit_rpm"
Task: "T005 [P] validate_network_ratelimit_burst"
Task: "T006 [P] validate_network_ratelimit_trust_forwarded_headers"
Task: "T007 [P] validate_network_ratelimit_max_keys"

# Five docs/env-vars.md sections in parallel:
Task: "T009 [P] SACP_NETWORK_RATELIMIT_ENABLED section"
Task: "T010 [P] SACP_NETWORK_RATELIMIT_RPM section"
Task: "T011 [P] SACP_NETWORK_RATELIMIT_BURST section"
Task: "T012 [P] SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS section"
Task: "T013 [P] SACP_NETWORK_RATELIMIT_MAX_KEYS section"

# Then T008 (append to VALIDATORS tuple) + T014 (CI gate verification) run sequentially.
```

---

## Parallel Example: User Story 1 token-bucket + keying + parsing

```bash
# Three pure-helper functions in src/middleware/network_rate_limit.py — different functions, no shared edit point:
Task: "T023 [P] [US1] PerIPBudget + TokenBucket.evaluate"
Task: "T024 [P] [US1] _key_source_ip transform (IPv4 /32, IPv6 /64)"
Task: "T025 [P] [US1] _parse_forwarded_header (RFC 7239 + XFF fallback)"

# LRU map wrapper and middleware shell run sequentially after the helpers land:
Task: "T026 [US1] OrderedDict LRU map + _admit_or_reject (depends on T023)"
Task: "T027 [US1] NetworkRateLimitMiddleware ASGI shell (depends on T024-T026)"
Task: "T028 [US1] register middleware in src/main.py (depends on T027)"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (V16 gate done THIS round; only T015 unit tests + T016 ordering canary pending)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Drive a synthetic bcrypt-flood from one IP and confirm rejections happen BEFORE bcrypt runs; confirm legitimate IPs unaffected; confirm `Retry-After` header present
5. Deploy / demo if ready (network-layer limiter on; audit + metrics surfaces follow in US3)

### Incremental Delivery

1. Setup + Foundational → Foundation ready (V16 gate already green)
2. US1 → MVP (limiter rejects floods BEFORE bcrypt; bcrypt-DoS vector closed)
3. US2 → exempt paths reachable; §7.5 isolation contract verified
4. US3 → audit + metrics visibility; operators can see flooding patterns
5. Polish → fail-closed tests, V14 perf verification, quickstart walk-through, cross-spec audit

### Parallel Team Strategy

With multiple developers after Phase 2:

- Developer A: US1 (P1 MVP — token-bucket + middleware shell + registration)
- Developer B: US2 (P2 exempt paths + §7.5 isolation — can start once US1's middleware shell exists)
- Developer C: US3 (P3 audit coalescing + metric labels — can start once US1's rejection branch exists)

Polish closes out after all three user stories.

---

## Notes

- [P] tasks = different files OR independent functions in the same file with no shared edit point (e.g., five validator functions in `src/config/validators.py` are P; the `VALIDATORS` tuple append is not)
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Verify tests fail before implementing (the middleware-ordering canary T016 is the foundational example)
- Per memory `feedback_test_schema_mirror`: this spec deliberately introduces NO alembic migration and NO `tests/conftest.py` mirror change — see "No schema migration / no conftest mirror" subsection in Phase 2. Reviewers verifying the schema-mirror invariant will find no DB delta in this spec's task list
- Per memory `feedback_no_auto_push`: do not push the branch upstream without explicit confirmation
- Per memory `feedback_exclude_humans_from_dispatch`: NOT engaged here — this spec's middleware runs at the HTTP tier, BEFORE auth, with no participant context (FR-007); the recurring-bug-class filter (`provider != "human"`) is application-layer
- Per spec FR-015 (WebSocket scope): the middleware counts a WebSocket upgrade as a single request at the upgrade moment; subsequent traffic over an established WebSocket is OUT OF SCOPE — handled by §7.5 / spec 002 application-layer limiter post-auth
- Per [plan.md "Notes for /speckit.tasks"](./plan.md): default values lock at `_RPM=60`, `_BURST=15`, `_MAX_KEYS=100_000`, `_TRUST_FORWARDED_HEADERS=false`, `_ENABLED=false` (master switch ships off; opt-in only)
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence (US2 and US3 each depend on US1's middleware shell — that dependency is explicit in the dependency graph above)
