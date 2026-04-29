# Feature Specification: Rate Limiting

**Feature Branch**: `009-rate-limiting`
**Created**: 2026-04-12
**Status**: Draft

## Clarifications

### Session 2026-04-14

- Q: Which window algorithm? → A: Sliding window (track individual request timestamps, prune old ones)
- Q: Counter persistence? → A: In-memory only (resets on process restart)
- Q: Configuration source? → A: Fixed process-level default (60 req/min hardcoded, no override in Phase 1)
- Q: Scope of enforcement? → A: All authenticated /tools/* endpoints uniformly (reads and writes count equally)
- Q: Retry-After semantics? → A: Seconds until oldest in-window request expires (precise, computed per participant)

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

## Success Criteria

- **SC-001**: Requests within limit succeed; requests over limit return 429.
- **SC-002**: Rate limit resets after the configured window.
- **SC-003**: The bucket map's memory footprint is bounded. Synthetic load creating >10,000 distinct participant ids over a 5-minute window MUST NOT grow the bucket map beyond `DEFAULT_MAX_BUCKETS` after the eviction sweep (FR-007).
- **SC-004**: A 429 response body MUST NOT contain participant id, current count, window length, or any internal counter state. Only the `detail` string and `Retry-After` header carry timing information.

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

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): Topologies 1–6 only (orchestrator-driven). Rate limits apply to MCP tool calls routed through the orchestrator's `/tools/*` endpoints. Topology 7 (client-side peer AI with local MCP) has no orchestrator to enforce uniform limits; peer-side rate limiting is deferred to Phase 2+.

**Use cases** (per constitution §1): Serves all scenarios equally within orchestrator-driven topologies. Per-participant rate limiting prevents accidental DoS from misconfigured routing modes or runaway tool calls, reducing operational risk in consulting and open-source contexts.
