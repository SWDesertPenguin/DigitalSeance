# Implementation Plan: Network-Layer Per-IP Rate Limiting

**Branch**: `019-network-rate-limiting` | **Date**: 2026-05-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/019-network-rate-limiting/spec.md`

## Summary

Phase 1 hardening that registers a per-IP token-bucket rate limiter as the FIRST middleware on every non-exempt inbound HTTP request to the MCP server (port 8750). The limiter runs strictly before any auth or bcrypt work so unauthenticated flood traffic cannot turn bcrypt's CPU work factor into a CPU-DoS vector. Source IP is the immediate peer by default; operators can opt in to RFC 7239 `Forwarded` / `X-Forwarded-For` parsing via `SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS=true`. IPv4 keys at `/32`, IPv6 at `/64` (the keyed form, not the raw v6 address, surfaces in audit). A fixed exempt set (`GET /health`, `GET /metrics`) bypasses the limiter so Prometheus scrapers and Docker healthchecks remain unbounded. Rejections return HTTP 429 with `Retry-After` (RFC 6585), increment spec 016's `sacp_rate_limit_rejection_total` counter per-rejection, and emit per-(source_ip_keyed, minute) coalesced `network_rate_limit_rejected` rows to `admin_audit_log` to bound audit volume during sustained floods. Source-IP-unresolvable requests reject HTTP 400 and audit as `source_ip_unresolvable`. Five new `SACP_NETWORK_RATELIMIT_*` env vars + V16 validators land before `/speckit.tasks`. The spec 011 SPA is untouched (no UI surface). The §7.5 application-layer per-participant limiter shares no state with this middleware (FR-007).

Technical approach: introduce `src/middleware/network_rate_limit.py` carrying an asyncio-safe token-bucket evaluator with lazy refill, an `OrderedDict`-backed LRU bound on the keyed-IP map (capacity `SACP_NETWORK_RATELIMIT_MAX_KEYS`), a forwarded-header parser gated by `_TRUST_FORWARDED_HEADERS`, and an exempt-path early-out checked before any keying work. Register in `src/mcp_server/app.py` (inside the existing `_add_middleware(app)` helper called from `create_app()`) as the LAST `add_middleware` call so FastAPI's reverse-order registration semantics put it outermost on the request stack (the LAST registered middleware executes FIRST on inbound requests). Add a startup test asserting the registration order. Audit-log coalescing lives in `src/audit/network_rate_limit_audit.py`: a per-(IP, minute) accumulator with a background asyncio task that flushes every minute on a timer (NOT in the request path). Extend spec 016's metrics module to label `sacp_rate_limit_rejection_total` with `(endpoint_class, exempt_match)`. No alembic migration — the limiter state is in-memory only. No `tests/conftest.py` schema-mirror change for the same reason.

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. No new runtime dependencies.
**Storage**: N/A — limiter state is in-memory (`OrderedDict[str, PerIPBudget]`). No new tables. No alembic migration. The audit-log coalescing buffer is in-memory; flushes write existing `admin_audit_log` rows via the established append-only path.
**Testing**: pytest with the existing per-test FastAPI fixture (spec 012 US7). Three new spec-019 test files cover US1 (flood-blocked-before-bcrypt), US2 (exempt paths + non-interaction with §7.5 limiter), US3 (audit + metrics visibility + coalescing). One additional test asserts middleware-registration order at startup (FR-002).
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm). The middleware runs in-process; no new container, no new sidecar.
**Project Type**: Single project (existing `src/` + `tests/` layout; no frontend changes).
**Performance Goals**:
- Limiter middleware overhead per request: **p95 ≤ 1ms** measured via `routing_log` sample. O(1) work — exempt-path check, source-IP resolution, hash lookup on keyed-IP, lazy refill via timestamp delta, bucket increment/decrement. The limiter is a hash lookup + arithmetic operations; 1ms is conservative for Python. Captured on a sample of requests via `routing_log` middleware-duration row (spec 003 §FR-030).
- Per-IP-budget eviction at MAX_KEYS pressure: **p95 ≤ 100μs amortized** via `OrderedDict.popitem(last=False)` LRU (O(1)).
- Audit-log coalescing flush: **MUST NOT increment per-request latency by any measurable amount** — asynchronous background task, out-of-band, never blocks the request path. Flush cadence is once per minute per `(source_ip_keyed, minute)` bucket.
- NOTE: These numeric tolerances are spec-019-local pending a constitution-level V14 registry.
**Constraints**:
- Default behavior MUST be byte-identical to pre-feature: `SACP_NETWORK_RATELIMIT_ENABLED=false` (the unset default) means the middleware is not registered, no rejections, no audit entries (FR-014, SC-006).
- V15 fail-closed: invalid env-var values exit at startup before binding ports (V16); source-IP-unresolvable requests reject HTTP 400 rather than allowing the request through (FR-012).
- 25/5 coding standards (Constitution §6.10) + 25-line function cap.
- The middleware MUST NOT share state with, read from, or write to the §7.5 per-participant rate limiter (FR-007). Both limiters are independently testable.
**Scale/Scope**: Phase 1 surface is the MCP server on port 8750. Phase 2 reuses the same middleware on port 8751 (Web UI) without spec change — registration is process-wide, not per-port. The `MAX_KEYS` bound caps worst-case memory under flood at `MAX_KEYS × small constant per entry`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | Network-layer limiter has no participant context, no ability to deduce participant identity from IP, and writes no participant state. Per-IP keying is a network-layer concern; per-participant cost tracking and §7.5 rate limiting are application-layer concerns and remain untouched (FR-007). |
| **V2 No cross-phase leakage** | PASS | Phase 1 scope explicit. Phase 2 reuse is a wiring change (no spec amendment). Topology 7 forward note in spec §V12. |
| **V3 Security hierarchy** | PASS | Network-layer rate limiting is foundational hardening (Constitution §6.5 anchor — bcrypt CPU-DoS closure). No security trade-off introduced. |
| **V4 Facilitator powers bounded** | PASS | No new facilitator surface. Limiter is operator-configured at deploy time via env vars; runtime tuning requires restart. |
| **V5 Transparency** | PASS | Every rejection emits to `admin_audit_log` (FR-009) and increments `sacp_rate_limit_rejection_total` (FR-010). Source-IP-unresolvable rejections audit as `source_ip_unresolvable` (FR-012). |
| **V6 Graceful degradation** | PASS | When unset (default), middleware is not registered — pre-feature behavior preserved (FR-014). Audit-coalescing flush is best-effort; failures log but do not block request path. |
| **V7 Coding standards** | PASS | Function bodies stay under 25 lines; new helpers respect 5-arg positional limit. |
| **V8 Data security** | PASS | Audit row stores `source_ip_keyed` (full IPv4 or /64 IPv6 prefix), NOT raw IPv6 host address. No headers, query string, body content in metric labels (FR-010, SC-009). |
| **V9 Log integrity** | PASS | Audit events use the existing append-only `admin_audit_log` path. Coalescing summarizes per-(IP, minute) rather than per-rejection but does not skip events. |
| **V10 AI security pipeline** | PASS | Limiter runs at HTTP middleware tier — does not touch prompt assembly, tier composition, or output validation. |
| **V11 Supply chain** | PASS | No new runtime dependencies. Token-bucket and `OrderedDict` LRU are stdlib. |
| **V12 Topology compatibility** | PASS | Spec §V12 enumerates topology 1-6 applicability; topology 7 forward note documents the limiter is registered but typically idle. |
| **V13 Use case coverage** | PASS | Spec §V13 maps to all four use cases as foundational hardening. |
| **V14 Performance budgets** | PASS | Three budgets specified in spec §"Performance Budgets (V14)" with `routing_log` instrumentation hooks. |
| **V15 Fail-closed** | PASS | Source-IP-unresolvable rejects HTTP 400 (FR-012). Invalid env vars exit at startup (V16). Audit-coalescing-flush failure logs but the request path is already complete; no fail-open vector. |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Five new env vars require validators + `docs/env-vars.md` sections BEFORE `/speckit.tasks` (FR-013). Validators land in this feature's task list. |
| **V17 Transcript canonicity respected** | PASS | Limiter does not touch transcripts. |
| **V18 Derived artifacts traceable** | PASS | No derived artifacts produced by this feature. |
| **V19 Evidence and judgment markers** | PASS | Spec uses [JUDGMENT] / drafted-as / clarify-session markers consistently; clarify session 2026-05-08 resolved all five draft markers with no divergence. |

No violations. Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/019-network-rate-limiting/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (env-vars, audit-events, middleware-ordering, metrics)
├── checklists/          # Phase 1 output (requirements.md)
├── spec.md              # Feature spec (Status: Draft, clarify session 2026-05-08 complete)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created here)
```

### Source Code (repository root)

```text
src/
├── middleware/
│   ├── __init__.py                  # NEW (if missing) — package marker
│   └── network_rate_limit.py        # NEW — token-bucket middleware: per-IP budget map, lazy refill, exempt-path check, forwarded-header parser, LRU eviction at MAX_KEYS
├── audit/
│   └── network_rate_limit_audit.py  # NEW — per-(IP, minute) coalescing accumulator + background asyncio flush task; writes to admin_audit_log via existing append-only path
├── main.py                          # extend — register network_rate_limit middleware FIRST per FR-001/FR-002 (FastAPI add_middleware reverse-order semantics)
├── config/
│   └── validators.py                # extend — add 5 validators (validate_network_ratelimit_enabled, _rpm, _burst, _trust_forwarded_headers, _max_keys); register in VALIDATORS tuple
└── observability/
    └── metrics.py                   # extend — extend sacp_rate_limit_rejection_total label set with (endpoint_class, exempt_match) per FR-010 (or wherever spec 016's prometheus counters live)

tests/
├── conftest.py                      # NO CHANGE — limiter state is in-memory; no DB tables introduced
├── test_019_flood_blocked.py        # NEW — US1: flood from IP A blocked before bcrypt; nominal latency from IP B; Retry-After header
├── test_019_exempt_and_isolation.py # NEW — US2: exempt paths bypass limiter; §7.5 limiter unchanged; no shared state
├── test_019_audit_and_metrics.py    # NEW — US3: rejection emits audit row + counter; coalescing per-(IP, minute); privacy contract
├── test_019_middleware_order.py     # NEW — FR-002 startup-test asserting limiter is the FIRST middleware
└── test_019_validators.py           # NEW — 5 env-var validators + V16 startup gate

docs/
└── env-vars.md                      # extend — add 5 new sections (V16 gate; FR-013)

(NO alembic migration — limiter state is in-memory.)
```

**Structure Decision**: Single Python service ("Option 1") consistent with the existing repo layout. New `src/middleware/` package isolates request-pipeline middleware from business logic. Audit coalescing lives under `src/audit/` because the per-(IP, minute) flush has its own lifecycle (background task) distinct from request handling. `src/mcp_server/app.py::_add_middleware` gains only the registration call site; the middleware body stays in its module. No frontend changes — this is operator-facing infrastructure (V13 parallel to spec 016).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(No violations.)

## Phase 0 — Outline & Research

Open decisions queued for `research.md`:

1. **Token-bucket implementation in FastAPI middleware**. Lazy refill via timestamp delta vs. background timer driving refill. Decision criteria: O(1) per-request, V14 budget compliance, lock contention under flood.
2. **Lazy refill vs. background timer**. Continued from §1: confirm lazy is the default and document why background timer was rejected even though it sounds simpler.
3. **LRU eviction at MAX_KEYS bound**. `OrderedDict` move-to-end on access vs. dedicated LRU library vs. unbounded map with periodic prune. Decision criteria: stdlib-only, O(1) eviction, memory bound under flood.
4. **RFC 7239 `Forwarded` vs. `X-Forwarded-For` parsing precedence**. Decision criteria: RFC compliance, real-world proxy behavior, attacker-spoofing surface.
5. **/64 IPv6 keying transform implementation**. First 8 bytes of 16-byte address vs. `ipaddress` module's network-aware helpers. Decision criteria: stdlib-only, performance per request, correctness on link-local / mapped-v4 / etc.
6. **Audit-log per-(IP, minute) coalescing flush mechanism**. Background asyncio task vs. flush-on-rotate vs. flush-on-rejection-batch. Decision criteria: NOT in request path (V14), bounded memory, durability under crash.
7. **Spec 016 metric label set for `sacp_rate_limit_rejection_total`**. Decision criteria: cardinality bound, no PII / IP / query-string in labels, joinable with existing spec 016 dashboards.
8. **Topology-7 forward note**. Document that the limiter is registered but typically idle when the orchestrator runs in topology 7 (no participant-facing inbound HTTP surfaces). Decision criteria: forward-compatibility without spec amendment when topology 7 lands.

Output: [research.md](./research.md) with one decision section per open question.

## Phase 1 — Design & Contracts

**Prerequisites:** `research.md` complete.

1. **Data model** ([data-model.md](./data-model.md)) extracts entities from spec:
   - `PerIPBudget` (process-scope, in-memory) — token-bucket state per source-IP keyed form: `(source_ip_keyed, current_tokens, last_refill_at)`. Bounded by `SACP_NETWORK_RATELIMIT_MAX_KEYS` via LRU eviction.
   - `NetworkRateLimitRejectedRecord` (audit row shape) — captures rejections per FR-009 with `rejection_count` coalescing field.
   - `ExemptPathRegistry` — frozen tuple of `(method, path)` pairs: `((GET, /health), (GET, /metrics))`. Defined at module load; read-only at runtime.
   - NO DB tables. NO alembic migration. NO `sessions`/`participants` schema additions.

2. **Contracts** ([contracts/](./contracts/)) — Phase 1 outputs four contract docs:
   - `contracts/env-vars.md` — five new vars × six standard fields (Default, Type, Valid range, Blast radius, Validation rule, Source spec).
   - `contracts/audit-events.md` — two `action` strings (`network_rate_limit_rejected` with coalescing fields, `source_ip_unresolvable`).
   - `contracts/middleware-ordering.md` — FastAPI middleware-registration ordering contract per FR-001/FR-002, including the startup-test signature that proves it.
   - `contracts/metrics.md` — spec 016 `sacp_rate_limit_rejection_total` label set per FR-010.

3. **Quickstart** ([quickstart.md](./quickstart.md)) — operator workflow:
   - Set deployment-wide env vars (`SACP_NETWORK_RATELIMIT_ENABLED=true`, `_RPM`, `_BURST`, `_TRUST_FORWARDED_HEADERS`, `_MAX_KEYS`).
   - Restart orchestrator stack from Dockge.
   - Verify `routing_log` middleware-duration sample.
   - Verify Retry-After header on a synthetic flood.
   - Audit-log query example for `network_rate_limit_rejected` rows.
   - Disable / rollback to pre-feature: unset `SACP_NETWORK_RATELIMIT_ENABLED` (or set to `false`), restart.

4. **Agent context update**: run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType claude` to merge spec 019's tech surface into `CLAUDE.md`.

5. **Re-evaluate Constitution Check** post-design — confirm V14 (limiter middleware overhead, eviction, audit-flush budgets) and V16 (5 env vars) surfaces are still accurate after `data-model.md` and `contracts/` lock the entity shapes and label set.

**Output**: data-model.md, contracts/*.md, quickstart.md, updated CLAUDE.md.

## Notes for `/speckit.tasks`

- Task list MUST gate the V16 deliverable (5 validators in `src/config/validators.py` registered in `VALIDATORS` tuple + `docs/env-vars.md` sections) BEFORE any middleware code-path work per FR-013.
- The startup-test asserting middleware registration order (FR-002) is the early canary — should land alongside the middleware body so any "auth-before-limiter" regression surfaces in CI.
- NO alembic migration, NO `tests/conftest.py` schema-mirror change. The limiter is in-memory only; reviewers verifying the test-schema-mirror invariant will find no DB delta in this spec's task list.
- `test_019_audit_and_metrics.py` covers SC-009 privacy contract: assert no raw IPv6, no query string, no headers, no body content in audit row payload OR metric labels.
- `test_019_exempt_and_isolation.py` covers SC-004: §7.5 per-participant rate limiter behaves byte-identically with the network-layer limiter active. Drives a §7.5 contract probe under load and asserts no behavioral drift. NOTE: §7.5 is currently a `sacp-design.md` design-doc reference (not a coded spec with an existing acceptance suite); the test takes a probe-style isolation form rather than running an "existing §7.5 acceptance suite" — see tasks.md T035 wording.
- Default values lock at: `SACP_NETWORK_RATELIMIT_RPM=60`, `SACP_NETWORK_RATELIMIT_BURST=15` (= RPM/4 per spec assumption), `SACP_NETWORK_RATELIMIT_MAX_KEYS=100_000` (range `[1024, 1_000_000]`), `SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS=false`, `SACP_NETWORK_RATELIMIT_ENABLED=false` (master switch ships off; opt-in only).
- Phase-2 `/ws/*` extension (Web UI on port 8751) is out of scope for this spec's tasks; the middleware is process-wide and will pick up port 8751 when Phase 2 lands. No additional task here.
- §4.13 PROVISIONAL adherence: this spec produces no AI-facing prompt content; the rule is not engaged.
- Test scaffolding leans on spec 012's per-test FastAPI fixture pattern (US7) — implicit dependency now made explicit.
