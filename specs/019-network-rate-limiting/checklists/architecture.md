# Architecture Quality Checklist: Network-Layer Per-IP Rate Limiting

**Purpose**: Validate that spec 019's middleware design and architectural commitments (ordering, in-memory state lifecycle, keying invariants, async flush task lifecycle, FastAPI registration pattern, no-DB-state stance, non-interaction with the §7.5 application-layer limiter) are specified clearly enough that two implementers would produce architecturally equivalent middleware. This checklist tests architectural-specification quality, not the implementation.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md) + [plan.md](../plan.md) + [contracts/middleware-ordering.md](../contracts/middleware-ordering.md) + [data-model.md](../data-model.md)

## Middleware Ordering Contract

- [ ] CHK001 Is the rule "the limiter MUST be the FIRST middleware on every non-exempt request" stated as binding for the FastAPI registration block, with the reverse-order semantics documented? [Completeness, Spec §FR-001 + Contracts §middleware-ordering]
- [ ] CHK002 Is the contract for what "first" means (outermost on the request stack; runs before auth, bcrypt, logging, CORS, anything) specified explicitly enough to reject ambiguous orderings? [Clarity, Contracts §middleware-ordering]
- [ ] CHK003 Are the requirements for the startup-test that proves ordering specified at sufficient detail (which `app.user_middleware` slot is checked, what assertion fails the test)? [Measurability, Spec §FR-002 + Contracts §middleware-ordering "Startup-test signature"]
- [ ] CHK004 Is the rule "conditional registration when `SACP_NETWORK_RATELIMIT_ENABLED=false` means the middleware is NOT in `user_middleware` at all" stated as binding rather than relying on a no-op pass-through? [Clarity, Contracts §middleware-ordering "Conditional registration"]
- [ ] CHK005 Are the four enumerated failure modes the startup-test must catch (auth-after-limiter, limiter-first-instead-of-last, unconditional registration, conditional ordering drift) each specified at sufficient detail to translate into test assertions? [Completeness, Contracts §middleware-ordering "Failure modes"]

## In-Memory State Lifecycle

- [ ] CHK006 Is the `PerIPBudget` dataclass shape specified with all three fields (`source_ip_keyed`, `current_tokens`, `last_refill_at`) and their types? [Completeness, Data-model §"PerIPBudget"]
- [ ] CHK007 Are the requirements for `PerIPBudget` creation (first request from a new keyed IP starts with `current_tokens = BURST`, `last_refill_at = now`) specified clearly enough to apply consistently? [Clarity, Data-model §"PerIPBudget" "State transitions"]
- [ ] CHK008 Is the lazy-refill arithmetic (`refill = (now - last_refill_at) × RPM / 60.0`; clamp to BURST; decrement; update timestamp) specified at sufficient detail to reproduce token-bucket behavior across implementations? [Measurability, Research §1 + Data-model §"PerIPBudget"]
- [ ] CHK009 Are the requirements for the `OrderedDict[str, PerIPBudget]` LRU recency rule (`move_to_end` on access, `popitem(last=False)` on overflow) specified as binding rather than as an implementation hint? [Clarity, Research §3 + Data-model §"PerIPBudget"]
- [ ] CHK010 Is the contract for in-memory state non-survival across orchestrator restart specified — operators are warned that restart resets all per-IP buckets? [Completeness, Quickstart §"Tune the limit"]

## ExemptPathRegistry Invariants

- [ ] CHK011 Is the rule "exempt paths are a frozen tuple defined at module load, read-only at runtime, not operator-configurable in v1" stated as binding? [Clarity, Spec §FR-006 + Data-model §"ExemptPathRegistry"]
- [ ] CHK012 Are the match semantics (exact-path match, no prefix matching, no glob; method-restricted; `POST /metrics` is NOT exempt) specified with no ambiguity? [Clarity, Data-model §"ExemptPathRegistry" "Match semantics"]
- [ ] CHK013 Is the requirement "exempt-path check runs BEFORE source-IP resolution work so exempt requests incur no keying cost" specified as architectural commitment, not just an optimization? [Clarity, Data-model §"ExemptPathRegistry" + V14 budget]
- [ ] CHK014 Are the future-evolution boundaries documented (a v2 amendment may introduce `SACP_NETWORK_RATELIMIT_EXEMPT_PATHS`; v1 is fixed) specified clearly enough to reject scope creep? [Completeness, Data-model §"ExemptPathRegistry" "Future evolution"]

## Source-IP Keying Transform

- [ ] CHK015 Is the IPv4 keying rule (full /32 dotted-decimal) specified as binding, with no operator override? [Clarity, Spec §FR-004]
- [ ] CHK016 Is the IPv6 keying rule (`/64` prefix via `ipaddress.IPv6Address(addr).packed[:8]`) specified as binding, with the rationale (privacy-address rotation defeat) documented? [Completeness, Spec §FR-004 + Research §5]
- [ ] CHK017 Are the edge-case requirements for the keying transform specified (link-local addresses, IPv4-mapped-IPv6 `::ffff:1.2.3.4` unmapped to v4, zone identifiers like `%eth0`)? [Completeness, Research §5]
- [ ] CHK018 Is the rule "the keyed form (NOT the raw IPv6 host address) is what appears in audit entries" stated as a binding privacy contract? [Clarity, Spec §FR-004 + SC-009]
- [ ] CHK019 Are the requirements for forwarded-header parsing precedence (`Forwarded` RFC 7239 preferred; `X-Forwarded-For` fallback; rightmost-trusted entry) specified at sufficient detail to apply consistently? [Clarity, Spec §FR-011 + Research §4]

## Async Audit-Flush Task Lifecycle

- [ ] CHK020 Is the rule "audit-log coalescing flush MUST run on a background timer, NOT in the request path" stated as binding for the V14 budget? [Completeness, Spec §"Performance Budgets" + Research §6]
- [ ] CHK021 Are the requirements for the in-memory accumulator shape (`dict[(source_ip_keyed, minute_bucket), CoalesceState]`) specified with the minute-bucket derivation (`floor(now_ts / 60)`) documented? [Clarity, Research §6 + Data-model §"NetworkRateLimitRejectedRecord"]
- [ ] CHK022 Is the flush cadence (once per minute) specified as binding, with the rationale (forensic-vs-volume trade-off) documented? [Completeness, Research §6 + Spec §"Assumptions"]
- [ ] CHK023 Are the requirements for crash-mid-minute durability specified — up to 60 seconds of coalesced rejections lost on crash, but the per-rejection metrics counter survives via Prometheus scrape? [Completeness, Research §6 + Contracts §audit-events "Sequencing"]
- [ ] CHK024 Is the contract for flush-task failure handling specified — a flush failure logs but does NOT block the request path, and the metrics counter retains durability? [Clarity, Plan §"Constitution Check V6" + Contracts §audit-events]
- [ ] CHK025 Are the requirements for flush-task lifecycle (started at orchestrator boot, stopped at shutdown, no per-request invocation) specified at sufficient detail to verify it does not leak across test runs? [Gap]

## FastAPI Middleware-Registration Pattern

- [ ] CHK026 Is the rule "register inner middleware FIRST, register `NetworkRateLimitMiddleware` LAST so it becomes outermost" specified with the FastAPI reverse-order semantics documented? [Clarity, Contracts §middleware-ordering "Required pattern"]
- [ ] CHK027 Are the requirements for the operator-visible startup log line (outermost-first listing of registered middleware) specified at sufficient detail to render consistently across deployments? [Completeness, Contracts §middleware-ordering "Operator-visible introspection"]
- [ ] CHK028 Is the contract for "the startup log line is informational; FR-002 is enforced by CI test, not by parsing log output" specified clearly enough to avoid relying on log parsing for correctness? [Clarity, Contracts §middleware-ordering]

## No-DB-State Architectural Commitment

- [ ] CHK029 Is the rule "limiter state is in-memory only; NO new tables, NO alembic migration, NO `tests/conftest.py` schema-mirror change" stated as binding architectural commitment? [Completeness, Plan §"Storage" + Data-model §"Schema additions"]
- [ ] CHK030 Are the requirements for the audit row writes (using existing `admin_audit_log` table via established append-only path; no schema delta) specified consistently across spec, plan, and data-model? [Consistency, Plan §"Storage" + Data-model + Contracts §audit-events]
- [ ] CHK031 Is the rationale for in-memory-only (per-worker per-IP budget when multi-worker FastAPI deployment is adopted; documented limitation) specified at sufficient detail to inform future scaling decisions? [Completeness, Data-model §"PerIPBudget" "Concurrency"]

## Non-Interaction with §7.5 Application-Layer Limiter

- [ ] CHK032 Is the rule "the network-layer limiter MUST NOT share state with, read state from, write state to, or otherwise interact with the §7.5 per-participant rate limiter" specified as binding architectural rule (FR-007)? [Completeness, Spec §FR-007]
- [ ] CHK033 Are the requirements for "the two limiters MUST be independently testable" specified at sufficient detail to drive the SC-004 byte-identical contract test? [Measurability, Spec §FR-007 + SC-004]
- [ ] CHK034 Is the boundary "network-layer runs PRE-AUTH on per-IP key; application-layer runs POST-AUTH on per-participant key" specified clearly enough to reject any future code that bridges them? [Clarity, Spec §"Overview" + FR-007 + FR-008]
- [ ] CHK035 Is the rule "a network-rejected request never updates per-participant state, never reaches the cost tracker, never touches conversation state" specified as a binding short-circuit semantic (FR-008)? [Completeness, Spec §FR-008 + SC-005]

## Topology-7 Forward-Compatibility

- [ ] CHK036 Is the topology-7 stance (middleware registered but typically idle; no conditional skip) specified at sufficient detail to avoid spec amendment when topology 7 lands? [Clarity, Spec §V12 + Research §8]
- [ ] CHK037 Are the requirements for the audit and metrics surfaces in topology 7 (remain wired but emit nothing when no traffic) specified consistently with the V12 commitment? [Consistency, Research §8]

## Concurrency Semantics

- [ ] CHK038 Is the contract "single-process middleware under the GIL; `OrderedDict` mutations are atomic at bytecode level; no explicit locking required for v1" specified as a binding architectural assumption? [Clarity, Data-model §"PerIPBudget" "Concurrency"]
- [ ] CHK039 Are the requirements for asyncio-safe operation (purely synchronous arithmetic; no `await` in hot path) specified to avoid task-switch-induced state inconsistency? [Completeness, Research §1]
- [ ] CHK040 Is the multi-worker-FastAPI limitation (each worker has its own map → per-worker per-IP budget) specified explicitly enough that operators reading the spec understand the per-worker boundary? [Completeness, Data-model §"PerIPBudget" "Concurrency"]

## Notes

Highest-impact open items:
- CHK025 (flush-task lifecycle across test runs) is a [Gap] — the spec does not yet name the start/stop hooks or how pytest fixtures avoid leaking the background task between tests.
- CHK033 + CHK035 carry the SC-004/SC-005 contract weight; if those are under-specified, the §7.5 non-interaction guarantee is unverifiable.
- CHK001 + CHK003 carry FR-001/FR-002 — the highest-leverage canary in the entire spec; the startup test is what catches "auth registered after limiter" regressions.

Use the `[PASS] / [PARTIAL] / [GAP] / [DRIFT] / [ACCEPTED]` annotation convention when triaging items: PASS if the spec answers the question fully; PARTIAL if it answers part; GAP if the spec is silent and the item flags real missing content; DRIFT if the spec answers but the answer disagrees with another doc; ACCEPTED if the gap/drift is known and a deferred-amendment ticket exists.
