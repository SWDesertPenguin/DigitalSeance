# Security Requirements Quality Checklist: Rate Limiting

**Purpose**: Validate the quality, clarity, and completeness of security requirements in the Rate Limiting spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Feature**: [spec.md](../spec.md)
**Sister checklist**: [requirements.md](requirements.md) (general spec completeness — already passed).
**Cross-feature reference**: [007-ai-security-pipeline §FR-013](../../007-ai-security-pipeline/spec.md) — 007 audit CHK015 already cleared the apparent conflict between FR-013 (no silent drop of AI responses) and 009's 429 rejection of inbound HTTP requests; this audit assumes that boundary is settled.

Markers used in findings (apply during audit, before resolution):
- `→ ✅` requirement is adequately specified
- `→ ⚠️ partial` spec addresses some aspect but leaves the rest implicit
- `→ ❌ gap` spec silent; code may or may not address it
- `→ 🐛 drift` spec and shipped code disagree
- `→ 📌 accepted` gap is documented in spec (assumptions / edge cases) — not a finding, but worth re-evaluating

## Requirement Completeness — Threat Coverage

- [x] CHK001 Are unauthenticated-endpoint rate-limiting requirements specified, or are only authenticated `/tools/*` endpoints in scope? FR-006 names authenticated only — is unauth attack surface explicitly out of scope? [Completeness, Spec §FR-006, Gap]
- [x] CHK002 Are anonymous-IP-based fallback rate-limiting requirements specified for endpoints reachable before authentication completes (login, token rotation, invite redemption)? [Completeness, Gap]
- [x] CHK003 Are global / process-wide cap requirements specified (upper bound on total memory consumed by per-participant sliding-window timestamps)? [Completeness, Gap]
- [x] CHK004 Are cardinality-attack defenses specified — what stops an attacker from creating many participants to exhaust the in-memory counter map? [Completeness, Gap]
- [x] CHK005 Are bypass-path requirements specified (admin tooling, internal calls, health checks)? [Completeness, Gap]

## Requirement Completeness — Operation Semantics

- [x] CHK006 Are concurrent-counter-update requirements specified (multiple async tasks updating the same participant's window — is the counter update atomic)? [Completeness, Gap]
- [x] CHK007 Are clock-source requirements specified (monotonic clock, wall clock, drift tolerance)? [Completeness, Gap]
- [x] CHK008 Are observability requirements defined for 429s (logged at what level, alertable, rate of 429s as a metric)? [Completeness, Gap]
- [x] CHK009 Are requirements specified for the response body of a 429 (does it leak counter state, current window position, only Retry-After)? [Completeness, Spec §FR-002, FR-003]
- [x] CHK010 Are requirements specified for behavior on counter-state corruption (stale timestamps, skewed clock)? [Completeness, Gap]

## Requirement Completeness — Operational Lifecycle

- [x] CHK011 Are graceful-shutdown / counter-loss-on-restart requirements specified — what's the security impact when in-memory counters reset on a deploy? FR-005 declares persistence not required, but is reset semantics testable? [Completeness, Spec §FR-005, partial]
- [x] CHK012 Are warmup / cold-start requirements specified for a fresh process (first N requests not yet windowed)? [Completeness, Gap]
- [x] CHK013 Are requirements specified for participant-deletion timing — when a participant's record is removed, is the counter cleaned up immediately or lazy-evicted? [Completeness, Gap]

## Requirement Clarity

- [x] CHK014 Is "60 req/min" (US1 / Assumptions) defined per *participant* (per FR-004) or per *token* (which can rotate within the window)? Token rotation could effectively reset or double the window. [Clarity, Ambiguity, Spec §FR-001, FR-004]
- [x] CHK015 Is "tool call" (US1) the same unit as a "request" to a `/tools/*` endpoint, or do internal sub-calls count separately (e.g., a tool that triggers another tool)? [Clarity, Spec §US1]
- [x] CHK016 Is the Retry-After value format pinned (integer seconds vs HTTP-date)? FR-003 says "seconds" but RFC 7231 allows both. [Clarity, Spec §FR-003]
- [x] CHK017 Is "uniformly" in FR-006 quantified — does it mean equal weighting, or just "same algorithm applied" with potentially different weights per endpoint? [Clarity, Spec §FR-006]

## Requirement Consistency

- [x] CHK018 Are 429 responses' shape and headers consistent with the auth layer's 401/403 responses (so client error handling is uniform)? [Consistency, cross-ref 002-participant-auth]
- [x] CHK019 Does the per-participant scope (FR-004 "never global or pooled") interact correctly with shared resources downstream (e.g., LiteLLM provider rate limits) — is the boundary documented? [Consistency, Gap]
- [x] CHK020 Is the spec consistent with constitution §11 / similar fairness clauses (preventing one participant from monopolizing capacity)? [Consistency, Gap]

## Acceptance Criteria Quality

- [x] CHK021 Is SC-001 measurable without an explicit load profile (request rate, concurrency, payload size)? [Measurability, Spec §SC-001]
- [x] CHK022 Is "rate limit resets after the configured window" (SC-002) testable as an exact-second contract or as approximate? [Measurability, Spec §SC-002]
- [x] CHK023 Are negative-path success criteria specified (Retry-After accuracy, false-positive rate of 429s, 429-after-window-reset)? [Acceptance Criteria, Gap]
- [x] CHK024 Is the "no false positive" target stated (a participant doing exactly 60 req/min should never see a 429)? [Acceptance Criteria, Gap]

## Scenario Coverage

- [x] CHK025 Are recovery requirements defined when a participant is rate-limited at exactly the moment a turn is dispatched (the rate-limit affects tool calls — does the in-flight turn fail or get queued)? [Coverage, Recovery Flow, Gap]
- [x] CHK026 Are batched-request requirements defined (a single API call that internally fans out to N tool calls — does it count as 1 or N)? [Coverage, Gap]
- [x] CHK027 Are admin / health-check exemption scenarios addressed (Kubernetes liveness probe, Prometheus scrape)? [Coverage, Gap]

## Edge Case Coverage

- [x] CHK028 Are requirements defined for the case where the system clock jumps backward (NTP correction, container time-skew)? [Edge Case, Gap]
- [x] CHK029 Are requirements defined for very-large windows or burst patterns (60 requests in 1 second vs evenly spaced — is burst tolerance specified)? [Edge Case, Spec §FR-001]
- [x] CHK030 Are requirements defined for the boundary case where the 60th request arrives exactly at the 60-second mark (off-by-one inclusivity)? [Edge Case, Gap]
- [x] CHK031 Are requirements defined for the case where a participant's window is nearly full and they rotate their token (does the new token inherit the old window or start fresh)? [Edge Case, Gap, cross-ref 002 §FR-008]

## Non-Functional Requirements

- [x] CHK032 Is the threat model documented and rate-limiting traced to it (OWASP API4 Lack of Resources & Rate Limiting, OWASP LLM04 Model Denial of Service)? [Traceability, Gap]
- [x] CHK033 Are performance overhead requirements specified for the rate-limit check on every request (target latency budget for the check itself)? [Performance, Gap]
- [x] CHK034 Are observability / audit requirements specified for repeated 429 patterns (do they get logged, surfaced to a facilitator, escalated)? [Coverage, Gap]

## Dependencies & Assumptions

- [x] CHK035 Is the assumption "in-memory only" paired with a re-evaluation trigger (e.g., revisit when deployment goes multi-process, or when persistence-loss creates a measurable security regression)? [Assumption, Spec §FR-005]
- [x] CHK036 Is the assumption "60 req/min hardcoded" paired with a re-evaluation trigger (when does this become per-deployment configurable)? [Assumption, Spec Clarifications]
- [x] CHK037 Is the dependency on participant identity established BEFORE rate-limiting kicks in — what enforces "authenticated only"? [Dependency, Spec §FR-006, partial]

## Ambiguities & Conflicts

- [x] CHK038 Does FR-002 ("reject with HTTP 429") conflict with 007 §FR-013 ("never silently drop or block")? Audit 007 CHK015 cleared this in favor of "different surfaces" — is that distinction documented in 009 too? [Conflict, Spec §FR-002, cross-ref 007 §FR-013]
- [x] CHK039 Is "process-level default" (Clarifications) the same as the in-memory single-process counter, or could a future multi-process deployment need synchronization? [Ambiguity, Spec Clarifications]
- [x] CHK040 Does the Topology coverage statement ("Topologies 1–6 only") fully address whether a peer-driven topology 7 needs equivalent local rate limiting, or just defer it? [Ambiguity, Spec Topology]

## Notes

- Highest-leverage findings to expect: CHK002 (no unauth fallback rate-limiting), CHK004 (no cardinality-attack defense), CHK032 (no threat-model traceability), CHK038 (the 007 §FR-013 boundary is settled by audit but not codified in 009 spec).
- Lower-priority but easy wins: CHK016 (Retry-After format), CHK029 (burst tolerance), CHK030 (off-by-one), CHK035/CHK036 (re-eval triggers).
- Run audit by reading [src/mcp_server/middleware/](../../../src/mcp_server/middleware/) (or wherever rate-limit middleware lives), the sliding-window data structure, and the 429 response shape; cross-reference with this spec's requirements / clarifications / topology.
