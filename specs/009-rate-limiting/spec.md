# Feature Specification: Rate Limiting

**Feature Branch**: `009-rate-limiting`
**Created**: 2026-04-12
**Status**: Implemented (Phase 1 closed 2026-04-20)

## Clarifications

### Session 2026-04-14

- Q: Which window algorithm? → A: Sliding window (track individual request timestamps, prune old ones)
- Q: Counter persistence? → A: In-memory only (resets on process restart)
- Q: Configuration source? → A: Fixed process-level default (60 req/min hardcoded, no override in Phase 1)
- Q: Scope of enforcement? → A: All authenticated /tools/* endpoints uniformly (reads and writes count equally)
- Q: Retry-After semantics? → A: Seconds until oldest in-window request expires (precise, computed per participant)
- FR-012 / FR-013 instrumentation implemented in fix/009-rate-limit-instrumentation (2026-05-05): `RateLimiter.rate_limit_429_total` is a `Counter[participant_id]` incremented on every 429 emit; `rate_limit_429_per_minute_total` is a property over a 60s rolling deque of 429 timestamps; `forget()` clears both the bucket and the per-participant counter. Eviction sweep throttled via `_SWEEP_MIN_INTERVAL=1.0s` and `_last_sweep_ts`; `rate_limit_eviction_sweep_ms` captures the most-recent sweep duration. Every 429 emits a `rate_limit_429` structured-log line with both counters; sweeps emit `rate_limit_eviction_sweep` at debug.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Per-Participant Rate Limiting (Priority: P1)

Each participant shares a process-level rate limit on tool calls (60 requests per minute in Phase 1 — not per-participant configurable). When the limit is exceeded, subsequent requests are rejected with a 429 status until the window resets. Rate limits are tracked per participant, not globally.

**Acceptance Scenarios**:

1. **Given** a participant within their rate limit, **When** they make a tool call, **Then** it succeeds normally.
2. **Given** a participant who has exceeded their limit, **When** they make another call, **Then** it is rejected with a 429 Too Many Requests response.
3. **Given** a rate-limited participant, **When** the time window resets, **Then** they can make calls again.
4. **Given** two participants, **When** one hits their limit, **Then** the other is unaffected.

## Requirements *(mandatory)*

- **FR-001**: System MUST track request counts per participant using a sliding window algorithm (individual timestamps pruned as they fall outside the window). Bursts up to the full per-window limit (60 in 1 second) are permitted by design — the algorithm is count-only, no token-bucket smoothing. Operators who need smoother dispatch should layer an upstream proxy with burst control.
- **FR-002**: System MUST reject requests exceeding the limit with HTTP 429. The 429 response body MUST be a JSON object `{"detail": "Rate limit exceeded"}` only — no counter state, no current window position, no participant id is leaked. The `Retry-After` header carries the only timing signal the client needs (FR-003).
- **FR-003**: System MUST include a Retry-After header in 429 responses. The value MUST be an integer number of seconds (RFC 7231 §7.1.3 "delta-seconds" form) until the oldest timestamp in the sliding window expires (not the full window length).
- **FR-004**: Rate limits MUST be per-participant, never global or pooled. The participant identifier (post-authentication `participant.id`) is the bucket key; tokens may rotate within the window without resetting the bucket — see FR-009.
- **FR-005**: Counters MAY be in-memory only — persistence across process restarts is not required for Phase 1. A process restart resets every participant's window to empty, which is a defended choice: the restart event is rare, observable in deploy logs, and the brief loosening of throttles is bounded by the next deploy boundary.
- **FR-006**: Rate limiting MUST apply to all authenticated `/tools/*` endpoints uniformly; reads and writes count equally toward the per-participant limit. Internal calls (e.g., the orchestrator's own dispatch path that does not flow through HTTP) do NOT consume the participant's window.
- **FR-007**: The bucket map MUST be bounded. When the number of distinct participant buckets exceeds `DEFAULT_MAX_BUCKETS` (default 10,000), buckets whose newest timestamp is older than 2× the window are evicted lazily on the next `check()`. This defends against cardinality-attack memory exhaustion (an attacker creating many participants to inflate the in-memory map). Buckets MUST also be cleared explicitly via `RateLimiter.forget()` when a participant is removed or revoked, so the bucket map mirrors the active-participant set within one revocation cycle.
- **FR-008**: Concurrent calls to `RateLimiter.check()` are safe under CPython's single-threaded asyncio event loop because `check()` contains no `await` points — the read-prune-append sequence is atomic per call. If the event-loop assumption ever changes (multi-threaded deployment), an explicit lock will be required.
- **FR-009**: Token rotation does NOT reset the rate-limit window. The bucket is keyed by `participant.id` (which is stable across rotations), not by the token hash. This matches the threat model: rate limiting throttles a *participant*, not a credential — rotating credentials shouldn't grant a fresh window.
- **FR-010**: Health-check / liveness-probe / Prometheus-scrape endpoints MUST NOT route through the authenticated `/tools/*` namespace and therefore MUST NOT consume any participant's rate-limit window. Phase 1 ships no rate limiting on unauthenticated endpoints (login, invite redemption); pre-auth fallback rate limiting is deferred — trigger: any observed brute-force on unauthenticated routes in production logs.
- **FR-011**: Per-`check()` latency MUST P95 ≤ 1ms on the steady-state path (bucket exists, no eviction triggered). The cost components: dict lookup O(1), deque prune walks expired timestamps O(window-density, max 60), append O(1). Sustained P95 > 1ms indicates either bucket-map cardinality pressure (FR-007) or pathological window density.
- **FR-012**: 429-rate metrics MUST be captured. Per-participant counter: `rate_limit_429_total`. Aggregate counter: `rate_limit_429_per_minute_total`. These are exposed via the structured-log path (cross-ref 006 §FR-018 per-tool latency logs) and queryable from the existing log-scrape pipeline. Sustained 429s indicate either an attacker (single participant spiking) or a legitimate workload that needs limit tuning (broad rate of 429s across many participants); the two cases are distinguishable from per-participant vs aggregate counter shape.
- **FR-013**: Eviction-sweep cost (FR-007) MUST be bounded. When triggered, the sweep walks the bucket map at O(N=10000) cost which on a hot path could spike `check()` latency. The sweep MUST run AT MOST ONCE per second per process — subsequent triggers within the same second short-circuit (cap already enforced via the most-recent sweep). Sweep duration MUST be captured as `rate_limit_eviction_sweep_ms` for monitoring.
- **FR-014**: Memory ceiling: the bucket map at `DEFAULT_MAX_BUCKETS=10000` is approximately 10MB resident (10K buckets × ~1KB each: participant_id + deque(60 timestamps) + Python overhead). This codifies the implicit ceiling implied by SC-003 so capacity planning has a concrete number. If `DEFAULT_MAX_BUCKETS` is raised, this ceiling scales linearly.

## Success Criteria

- **SC-001**: Requests within limit succeed; requests over limit return 429.
- **SC-002**: Rate limit resets after the configured window.
- **SC-003**: The bucket map's memory footprint is bounded. Synthetic load creating >10,000 distinct participant ids over a 5-minute window MUST NOT grow the bucket map beyond `DEFAULT_MAX_BUCKETS` after the eviction sweep (FR-007).
- **SC-004**: A 429 response body MUST NOT contain participant id, current count, window length, or any internal counter state. Only the `detail` string and `Retry-After` header carry timing information.
- **SC-005**: Per-`check()` latency P95 ≤ 1ms (FR-011). Measured against synthetic load of 100 participants × 60 req/sec sustained for 60 seconds. P99 ≤ 5ms accommodates occasional eviction-sweep spikes (FR-013); persistent P99 > 5ms indicates eviction-sweep frequency exceeding once-per-second.
- **SC-006**: 429-rate observability: per-participant and aggregate 429 counters (FR-012) MUST be queryable from structured logs. The shape distinguishes attack (single high counter) from legitimate-workload-hits-cap (broad distribution); operators have a deterministic rule to tell the two apart without inspecting traffic.
- **SC-007**: Memory ceiling: at `DEFAULT_MAX_BUCKETS=10000` the bucket map's resident-set footprint MUST NOT exceed 20MB measured by RSS delta against a baseline-empty rate limiter. The 2× over the 10MB estimate (FR-014) accommodates Python interpreter overhead. Persistent breaches indicate either a leak (buckets not evicted) or a budget that needs raising.

## Boundary with 007 §FR-013

007's "never silently drop or block an AI response" governs *AI outputs* post-dispatch. 009's 429 rejection governs *inbound HTTP requests* before any AI dispatch. Different surfaces, no conflict — confirmed by the 007 audit's CHK015 closure. Authoritative phrasing: "blocked AI responses are always held for review" (007 FR-013); "rate-limited inbound requests get HTTP 429" (009 FR-002).

## Threat model traceability

| FR | Defends against | OWASP API / LLM Top 10 | NIST SP 800-53 |
|----|-----------------|------------------------|----------------|
| FR-001, FR-006 (sliding window per participant) | Resource exhaustion via tool-call flood | API4:2023, LLM04 | SC-5, SC-6 |
| FR-002, FR-003, SC-004 (429 + Retry-After + no counter leak) | Information disclosure via error response | API3:2023 | SI-15 |
| FR-004, FR-009 (per-participant, rotation-stable) | Credential-rotation evasion | API4:2023 | AC-7 |
| FR-005 (in-memory only) | (accepted residual: brief restart-loosening) | — | — |
| FR-007, SC-003 (bounded bucket map) | Memory-exhaustion via cardinality attack | API4:2023 | SC-5(2) |
| FR-008 (single-threaded atomicity) | Lost-update on concurrent counter writes | — | SC-5 |
| FR-010 (no unauth fallback Phase 1) | Pre-auth brute-force probing | API4:2023 | AC-7 (deferred) |

## Audit closeout (2026-04-29)

The security-requirements quality audit (`checklists/security.md`) raised 40 findings; resolution split:

**Code changes**: CHK013 (`RateLimiter.forget()` added; called from `/remove_participant`, sponsored-AI cascade, and `/revoke_token`), CHK003 / CHK004 (bucket-map cardinality cap + lazy stale-bucket eviction). CHK006 was investigated and found to be a non-finding under CPython's single-threaded event loop — no lock needed; rationale documented in FR-008 and as code comment.

**Spec amendments (this commit)**: CHK001 / CHK002 / CHK010 (FR-010 unauthenticated-endpoint fallback explicitly deferred + trigger), CHK005 (FR-006 internal calls + FR-010 health-check exemption), CHK009 / SC-004 (429 response body shape pinned), CHK013 (FR-007 bucket map bound), CHK016 (FR-003 RFC 7231 delta-seconds form pinned), CHK029 (FR-001 burst tolerance acknowledged), CHK031 / FR-009 (token rotation does NOT reset window), CHK032 (Threat-model traceability table), CHK038 (Boundary with 007 §FR-013 section), CHK039 (FR-008 single-threaded atomicity), CHK040 (Topology assertion confirmed).

**Closed as accepted residual / out-of-scope** (documented in Assumptions, Topology, or "Boundary" section): CHK005 (bypass paths — none for `/tools/*`; health-check is on a different path), CHK007 (clock source — `time.monotonic()` is the canonical choice; documented in the module), CHK008 (observability requirements — 429 logged at WARNING level by FastAPI's default; Phase 3 alerting is a future enhancement), CHK010 (counter-state corruption — in-memory + monotonic clock + restart-on-failure makes this irrelevant), CHK011 / CHK012 (warmup / cold-start — restart resets to empty, observable in deploy logs), CHK014 / CHK015 (per-participant vs per-token — FR-009 settles via participant-id keying), CHK017 (uniform algorithm, equal weighting), CHK018 (consistency with 401/403 — FastAPI HTTPException JSON shape is uniform), CHK019 (boundary with downstream LiteLLM — different surface), CHK020 (constitution fairness — per-participant IS the fairness clause), CHK021 / CHK022 / CHK023 / CHK024 (measurability — implicit; sliding-window algorithm is well-defined), CHK025 (in-flight turn vs rate limit — turn dispatch is internal, doesn't consume the window), CHK026 (batched tool calls — each HTTP request counts), CHK027 (admin / health-check exemption — FR-010), CHK028 (clock-jump backward — `time.monotonic()` immune by definition), CHK030 (boundary inclusivity — `>=` not `>`, documented in code), CHK033 / CHK034 (perf overhead, observability — in-memory dict ops are O(1) amortized; alerting deferred), CHK035 / CHK036 (re-evaluation triggers — Phase 3 candidate), CHK037 (auth-then-rate-limit ordering — `Depends(get_current_participant)` enforces order in FastAPI's DI graph).

## Operational notes (Phase F amendment, 2026-05-02)

These items capture operator-facing decisions that don't change behaviour
but are required for production deployment readiness. Sourced from the
pre-Phase-3 audit window's operations review.

**`DEFAULT_MAX_BUCKETS` tuning runbook.** The default 10,000-bucket cap
(FR-007) accommodates a single deployment with up to ~10,000 active
participants in any 2× window before eviction kicks in. Raise the cap by
increasing `DEFAULT_MAX_BUCKETS` in `src/mcp_server/rate_limiter.py` if the
deployment expects sustained higher cardinality. Memory blast radius is
linear: each 1,000-bucket increase adds ~1MB resident (FR-014). Lowering
the cap below 1,000 is unsupported in Phase 1 — eviction-sweep frequency
spikes and the eviction path becomes hot. Tuning procedure: change
constant, restart all `mcp_server` processes; no DB migration required
because state is in-memory only (FR-005).

**Per-window / per-limit operator override surface.** Phase 1 ships a fixed
60 req/min process-level default with no env-var or per-participant
override (Clarifications 2026-04-14). Operators that need a different
global default change `DEFAULT_LIMIT` / `DEFAULT_WINDOW` in
`src/mcp_server/rate_limiter.py` and restart. Per-participant overrides
are deferred to Phase 3 — trigger: any deployment where ≥3 participants
need distinct ceilings (e.g. internal automation accounts vs human users).
The Phase 3 surface is expected to be a `participants.rate_limit_override`
nullable column read at `RateLimiter.__init__`-time per participant.

**429-rate alert thresholds (FR-012).** Once the FR-012 counter wiring
lands, alerting SHALL distinguish single-participant spike from broad
saturation: alert when `rate_limit_429_total{participant_id=X}` > 100 in
1 minute (single-participant attack), AND alert when
`rate_limit_429_per_minute_total` > 1000 in 5 minutes (workload exceeded
global ceiling — operator must tune `DEFAULT_LIMIT` or shed load).
Threshold values are starting points; tune to deployment baseline after
1 week of observation.

**Pre-auth fallback trigger conditions (FR-010).** Phase 1 deliberately
ships no rate limiting on unauthenticated endpoints (login, invite
redemption). Re-evaluate this stance when ANY of: (a) authentication-
endpoint logs show ≥10 failed attempts/sec from a single source IP for
≥5 minutes (brute-force probing), OR (b) operator instrumentation
catches a credential-stuffing pattern, OR (c) deployment moves to a
public-internet exposure where pre-auth scanning becomes part of the
baseline noise. Implementation surface (when triggered): a small
in-memory IP→count map keyed on `request.client.host` with the same
sliding-window algorithm but a much tighter limit (e.g., 30 req/min).

**Eviction-sweep alerting.** Once the FR-013 sweep-throttle wiring lands,
sustained `rate_limit_eviction_sweep_ms` > 50ms or sweep frequency >
once-per-second is a capacity-pressure signal: the bucket map is at cap
and stale-eviction is on the hot path. Operator action: raise
`DEFAULT_MAX_BUCKETS`, OR tune `DEFAULT_WINDOW` so participants' buckets
go stale faster. Both options are restart-required.

**Rate-limit-bypass paths (canonical list).** Bypass paths in Phase 1:
- `/healthz`, `/readyz` (no auth dependency, see FR-010)
- `/docs`, `/redoc`, `/openapi.json` (gated by `SACP_ENABLE_DOCS=1`, no
  auth dependency)
- `/login`, `/auth/*` (pre-auth, see FR-010)
- Internal orchestrator dispatch (in-process call, never reaches HTTP
  layer, see FR-006)
The middleware test in `tests/test_009_testability.py` enforces the
single-call-site invariant — adding a bypass means deleting the limiter
call from `get_current_participant`, which the audit-plan tracker will
catch.

**Phase 1 in-memory state acceptance.** The decision to skip persistence
across restarts (FR-005) is a deliberate trade-off, not an oversight.
Deploy log entries naming process restart events ARE the audit trail of
"rate-limit windows reset here." If a deployment requires durable
windows (regulatory audit requirement, multi-instance horizontal scale),
that triggers a Phase 3 redesign — likely a Redis-backed sliding window
or a token-bucket counter on a shared store. No partial migration
exists; the in-memory implementation is correct under its assumptions
and any swap is a complete rewrite of the bucket data layer.

## Clarifications (2026-05-14)

### Session 2026-05-14 (/speckit.analyze findings)

- Q: What is the concurrency contract between an in-progress eviction sweep and concurrent `check()` calls, and what is the spec-level latency budget for the sweep? (finding 009-C1) → A: Under CPython's single-threaded asyncio event loop the sweep runs synchronously with no `await` points; concurrent `check()` calls cannot interleave mid-sweep — each call awaits the event loop turn. The once-per-second gate (FR-013) is the primary defence against event-loop stall. SR-001 below codifies the numeric budget.
- **SR-001 (sweep latency budget)**: The eviction sweep MUST complete in <50ms P95 at `DEFAULT_MAX_BUCKETS=10000`. A sweep exceeding this threshold MUST emit a `rate_limit_sweep_slow` row to `security_events` so capacity pressure is observable without inspecting application logs. The 50ms figure is already cited as an advisory threshold in the Operational notes "Eviction-sweep alerting" block; this SR promotes it to a spec-level enforceable contract.
- Q: Does this amendment change behavior? → A: No. Doc-consistency fix only; the 50ms advisory threshold existed in Operational notes; SR-001 promotes it and adds the `security_events` emit obligation.

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): Topologies 1–6 only (orchestrator-driven). Rate limits apply to MCP tool calls routed through the orchestrator's `/tools/*` endpoints. Topology 7 (client-side peer AI with local MCP) has no orchestrator to enforce uniform limits; peer-side rate limiting is deferred to Phase 2+.

**Use cases** (per constitution §1): Serves all scenarios equally within orchestrator-driven topologies. Per-participant rate limiting prevents accidental DoS from misconfigured routing modes or runaway tool calls, reducing operational risk in consulting and open-source contexts.
