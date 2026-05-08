# Feature Specification: Network-Layer Per-IP Rate Limiting

**Feature Branch**: `019-network-rate-limiting`
**Created**: 2026-05-06
**Status**: Draft
**Input**: User description: "Network-layer abuse protection via per-IP rate limiting. SACP exposes HTTP/SSE endpoints — the MCP server on port 8750 in Phase 1, the Web UI on port 8751 in Phase 2. Both surfaces need protection against abuse. Bcrypt-protected token validation paths are particularly sensitive: unbounded request rates can enable CPU-DoS via repeated bcrypt validation even before authentication succeeds. The rate limiter must coexist with the existing auth layer, exempt operational endpoints (/health, /metrics), and remain architecturally distinct from per-participant cost tracking, which is an application-layer concern. The two layers do not share state and do not interact. Rejected requests must be auditable and visible in the metrics surface. Phase 1 scope. Cross-references §7 of sacp-design.md."

## Overview

SACP exposes two network surfaces that accept inbound HTTP requests
from outside the orchestrator process:

- **MCP server on port 8750** (Phase 1): SSE-transport endpoint
  for human MCP clients. Carries auth tokens and conversation
  content (`sacp-design.md` §7.4).
- **Web UI on port 8751** (Phase 2): HTTP + WebSocket endpoint for
  human browsers connecting to the operator dashboard.

Both surfaces validate auth tokens via **bcrypt** (Constitution
§6.5: "Static tokens, bcrypt hashing, configurable expiry"). Bcrypt
is a CPU-bound work factor by design — that is what makes it
resistant to offline cracking, but it also means every token-validation
request consumes meaningful CPU time on the server. **Without
network-layer rate limiting, an unauthenticated attacker can submit
unbounded request rates and force the orchestrator to bcrypt-validate
every one — turning the CPU work factor into a CPU-DoS vector.** The
attack does not need a valid token; it needs only the willingness to
keep submitting candidate tokens against the validation endpoint.

The existing application-layer rate limiter (`sacp-design.md` §7.5
"Rate limiting" — 30 tool calls/min/write, 60/min/read per
participant) is a complementary but **architecturally distinct**
mechanism:

- **Application-layer (existing, §7.5)**: per-PARTICIPANT, scoped
  to authenticated MCP tool calls. Runs after auth has succeeded.
  Driven by `participant_id`. Coupled to budget tracking through
  the same participant identity.
- **Network-layer (THIS spec)**: per-IP, scoped to inbound HTTP
  requests. Runs BEFORE auth — that is the entire point. Driven
  by source IP (or proxy-forwarded source). Has no participant
  context and no awareness of cost or budget.

The two layers MUST NOT share state and MUST NOT interact. Conflating
them would break sovereignty (cost tracking is per-participant;
network rate limiting is per-IP) and would break the threat model
(network limiting must run pre-auth; participant limiting requires
post-auth identity).

This spec defines **per-IP rate limiting** as a request-pipeline
middleware that:

1. **Counts** inbound requests per source IP per rolling window.
2. **Rejects** with HTTP 429 when the limit is exceeded, BEFORE
   any auth or bcrypt work occurs.
3. **Exempts** operational endpoints (`/health`, `/metrics` per
   spec 016 FR-002) from the per-IP count so that a busy
   Prometheus scraper or load balancer does not throttle itself.
4. **Audits** rejections into `admin_audit_log` and surfaces them
   through spec 016's metric counter
   (`sacp_rate_limit_rejection_total`).

This spec is **Phase 1 scope** — the MCP server on port 8750.
The Web UI rate limit landing on port 8751 reuses the same
middleware in Phase 2 (no separate spec; the Phase-2 wiring is
described in the assumptions section so that the Phase-2 cut is
not blocked).

## Clarifications

### Session 2026-05-08

All five initial-draft questions resolved. Five matched the drafted defaults with no divergence.

- **Source IP determination behind a proxy.** Trust-by-opt-in for forwarded headers. A single boolean env var `SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS` (default `false`) governs whether the middleware parses `Forwarded` (RFC 7239) or `X-Forwarded-For` headers. When `false`, the immediate peer IP is the source. No proxy-whitelist mechanism in v1 — operators who enable forwarded-header trust are responsible for ensuring the upstream proxy sanitizes inbound headers before forwarding. Codified by FR-011.
- **Auth ordering — limiter strictly before auth.** No carve-outs. The limiter is the first middleware on every non-exempt request, BEFORE any token-shaped string is inspected, BEFORE bcrypt is invoked, BEFORE TLS-internal session bookkeeping. No "first request from new client" graceful-onboarding path — once bcrypt has been called, the CPU cost has been paid, so any onboarding path that bypasses the limiter would break the threat model. Codified by FR-001 and FR-002.
- **Exempt path list.** Fixed at `/health` + `/metrics`, GET-only. Not operator-configurable in v1. A future spec may introduce a configurable set if observability tooling expands; for now, the limited surface is part of the contract. Other methods on those paths fall through to normal handling and ARE rate-limited. Codified by FR-006.
- **Limiter algorithm.** Token bucket. Steady-state requests-per-minute (`SACP_NETWORK_RATELIMIT_RPM`) plus burst capacity (`SACP_NETWORK_RATELIMIT_BURST`). Smooth burst handling and simpler operator tuning won over fixed-window's sharper rejections. Codified by FR-003.
- **IPv6 keying.** IPv6 keyed at `/64` prefix; IPv4 keyed at full `/32` (the full address). IPv6 hosts often use dynamic privacy addresses within their /64, so per-address keying would let an attacker rotate around the limiter inside a single subnet. The keyed form (not the raw IPv6 address) is what appears in audit entries. Codified by FR-004.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Per-IP rate limiting blocks a bcrypt-flood attack before bcrypt runs (Priority: P1)

An attacker submits a high-rate stream of requests with random
candidate tokens against the MCP server's auth endpoint. Each token
is structurally valid (matches the token grammar) so the auth path
proceeds to the bcrypt validation step. Without network-layer rate
limiting, the orchestrator faithfully bcrypt-hashes every candidate
— burning CPU and degrading service for every legitimate participant.

With per-IP rate limiting, the attacker's request stream is rejected
with HTTP 429 BEFORE the bcrypt path executes. The attacker exhausts
their per-IP budget; the orchestrator's CPU stays free for legitimate
work.

**Why this priority**: This is the core protection the feature
exists to deliver. Bcrypt is intentionally expensive — that's the
property that makes it useful, AND the property that makes pre-auth
flood attacks possible. Per-IP limiting is the documented, standard
defense.

**Independent Test**: Drive the MCP server's auth endpoint with a
synthetic flood (200+ requests per second per source IP, all with
syntactically valid but invalid tokens). Verify the limiter rejects
the bulk of the flood with HTTP 429, that the orchestrator's
bcrypt-validation invocation count stays bounded by the limiter's
per-window budget, and that legitimate authentication from a
different source IP completes within nominal latency.

**Acceptance Scenarios**:

1. **Given** `SACP_NETWORK_RATELIMIT_RPM=60` and a single source
   IP submits 200 requests in 60 seconds to the MCP server's
   auth endpoint, **When** the limiter evaluates each request,
   **Then** at most 60 of those requests MUST proceed to the
   bcrypt-validation path; the remaining 140 MUST be rejected
   with HTTP 429 BEFORE bcrypt is invoked.
2. **Given** the same flood is in progress from source IP A,
   **When** a legitimate request arrives from source IP B,
   **Then** the request from B MUST be processed within nominal
   latency (the limiter's per-IP scoping MUST NOT cause
   collateral damage to unrelated source IPs).
3. **Given** an HTTP 429 rejection occurs, **When** the response
   is sent, **Then** the response MUST include a `Retry-After`
   header per RFC 6585 indicating the seconds until the limiter
   would admit the next request from that IP.
4. **Given** the rate-limit env vars are unset, **When** any
   request arrives, **Then** the orchestrator MUST behave
   byte-identically to the pre-feature baseline (no limiter
   middleware, no rejections) and dispatch behavior MUST be
   unchanged.

---

### User Story 2 - Operational endpoints stay reachable; layers do not interact (Priority: P2)

A Prometheus scraper polls `/metrics` every 15 seconds; a Docker
healthcheck polls `/health` every 30 seconds. Both share an IP
with the load balancer that fronts the orchestrator. Without
exemption, those scrapes would consume the limiter's per-IP
budget and either throttle themselves or block legitimate
traffic on the same IP.

Separately, the existing application-layer per-participant rate
limiter (§7.5) MUST continue to enforce per-participant call
caps independently — neither limiter shares state with the other,
and neither gates the other.

**Why this priority**: P2 because correctness on the hot path
(US1) is the floor; P2 ensures the new limiter does not break
operability or conflate concerns. The non-interaction guarantee
between network-layer and application-layer limiters is a
strong architectural rule that this spec exists in part to
codify.

**Independent Test**: Start the orchestrator with
`SACP_NETWORK_RATELIMIT_RPM=10` (deliberately low). Drive the
limit to its threshold from a single IP. Verify (a) `/health`
and `/metrics` continue to respond on that IP, (b) the
application-layer per-participant limiter for that participant
behaves identically to before this spec — same thresholds, same
rejections, same audit shape, with zero state shared between
the two limiters.

**Acceptance Scenarios**:

1. **Given** source IP A has exhausted its per-IP budget, **When**
   IP A scrapes `/health` or `/metrics`, **Then** those requests
   MUST be served normally with no rate-limit consideration —
   the exempt path list bypasses the limiter middleware entirely.
2. **Given** participant P (authenticated, IP A) issues MCP tool
   calls at a rate below the per-IP limit but above the §7.5
   per-participant limit, **When** the application-layer limiter
   evaluates the calls, **Then** P MUST be throttled per §7.5
   independent of any network-layer state — the network-layer
   limiter MUST NOT have allowed those calls to pass any state
   to the application-layer limiter.
3. **Given** the network-layer limiter rejects a request from
   IP A, **When** the application-layer per-participant counters
   are inspected, **Then** they MUST be unchanged — a
   network-rejected request is never an application-layer event
   and never updates per-participant state.
4. **Given** participant P is at their §7.5 per-participant
   limit, **When** P submits one more request, **Then** the
   application-layer limiter MUST reject it independently of
   the network-layer state — even if P has plenty of per-IP
   budget remaining, the per-participant limit applies.

---

### User Story 3 - Rejected requests are auditable and visible in the metrics surface (Priority: P3)

An operator notices unexpected behavior in production — clients
intermittently failing, support requests up. Without auditable
rejections, the operator cannot tell whether the limiter is
firing, on which IPs, against which paths, or how often. With
audit + metrics visibility, the operator queries the audit log
and the metrics dashboard and sees the rejection pattern
immediately.

**Why this priority**: P3 because the limiter functions correctly
without operator-visible signals; visibility is the operability
layer. But it is the layer that makes "the limiter is working"
demonstrable rather than inferred.

**Independent Test**: Drive the limiter to its threshold from a
single IP. Verify the audit log captures each rejection with the
documented payload shape, that the spec 016 metric counter
`sacp_rate_limit_rejection_total` increments with
`endpoint_class="network_per_ip"`, and that the metric labels do
NOT carry the rejected request's headers, query string, or body.

**Acceptance Scenarios**:

1. **Given** the limiter rejects a request, **When** the rejection
   occurs, **Then** an `admin_audit_log` entry of action type
   `network_rate_limit_rejected` MUST be emitted with payload
   fields `(source_ip_keyed, endpoint_path, method, rejected_at,
   limiter_window_remaining_s)`. `source_ip_keyed` MUST be the
   limiter's keying form (full IPv4 or /64 IPv6 prefix), NOT
   the raw IPv6 host address.
2. **Given** spec 016's metrics endpoint is enabled, **When** a
   rejection occurs, **Then** the
   `sacp_rate_limit_rejection_total` counter MUST increment with
   labels `(endpoint_class="network_per_ip",
   exempt_match=false)` and MUST NOT include the source IP, the
   request path's query string, headers, or body content.
3. **Given** the audit-log volume from sustained flooding becomes
   noisy, **When** rejections are counted, **Then** the audit
   logger MUST coalesce: one entry per (source_ip_keyed,
   minute) carrying a `rejection_count` field rather than one
   entry per rejection. The metrics counter still increments
   per-rejection.
4. **Given** an operator queries the audit log for a flooding
   incident, **When** they filter by `network_rate_limit_rejected`
   over a window, **Then** the result MUST be sufficient to
   identify the flooding source IP(s) without consulting
   application logs.

---

### Edge Cases

- **Health/metrics scrape from a misconfigured monitoring system
  emits 1000 RPS.** Exempt paths are unbounded by design — the
  exemption is unconditional. If a misconfigured scraper
  saturates the orchestrator via exempt paths, that is an
  operator misconfiguration; the limiter is not the right place
  to defend against it. (Defense at the load-balancer layer if
  needed.)
- **Source IP genuinely shared by many legitimate clients (NAT,
  corporate proxy, VPN exit).** The limit is per-IP — clients
  behind a shared IP share the budget. This is a known limitation
  of per-IP limiting; mitigation is operator tuning of the limit,
  or a future per-token / per-fingerprint layer.
- **Burst of requests at the moment a window resets.** Token
  bucket smooths this; fixed window does not. Drafted as token
  bucket per Clarifications.
- **Source IP cannot be determined** (malformed connection,
  socket-layer anomaly). Request is rejected with HTTP 400 and
  audited as `source_ip_unresolvable`. Defaulting to "no IP" and
  letting the request through would defeat the limiter on
  malformed traffic.
- **Operational endpoint is invoked with a method that is not
  GET** (e.g., `POST /metrics`). Exempt paths are exempt only on
  expected methods (`GET /health`, `GET /metrics`); other methods
  on those paths fall through to normal handling and are
  rate-limited as usual.
- **TLS-terminating proxy injects spoofed `X-Forwarded-For`.** With
  trust-by-opt-in default, headers are ignored unless explicitly
  enabled. When enabled, the operator is responsible for ensuring
  the proxy sanitizes upstream-supplied headers before forwarding.
- **WebSocket upgrade request.** Counts as a single request at the
  upgrade moment. Subsequent traffic over the established
  WebSocket is NOT subject to per-request network-layer rate
  limiting — that traffic is application-layer and §7.5 / spec
  002 application-layer limits apply per-participant. (Note:
  Phase-2 wiring for `/ws/*` paths described in Assumptions.)
- **Bcrypt validation succeeds but the auth path then fails for
  some other reason** (token expired, participant suspended).
  The limiter has already incremented for the request; the
  outcome of auth is not the limiter's concern. The application
  layer handles auth failures separately.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The orchestrator MUST register a per-IP rate-limiting
  middleware as the FIRST middleware on every inbound non-exempt
  HTTP request to the MCP server (port 8750) when
  `SACP_NETWORK_RATELIMIT_ENABLED=true` (= LAST `add_middleware`
  call per FastAPI's reverse-order registration semantics; see
  contracts/middleware-ordering.md).
- **FR-002**: The middleware MUST run BEFORE auth, BEFORE bcrypt
  validation, BEFORE any token-shaped string is inspected. The
  ordering MUST be enforced by the middleware-registration code
  and verified by a test that asserts middleware order at
  startup.
- **FR-003**: The middleware MUST use a token-bucket algorithm with capacity and refill rate derived from `SACP_NETWORK_RATELIMIT_RPM` and `SACP_NETWORK_RATELIMIT_BURST`. Each per-IP bucket initializes with `current_tokens = SACP_NETWORK_RATELIMIT_BURST` (full bucket) on first observation; this MUST NOT permit a single fresh IP to exceed BURST in its first window.
- **FR-004**: The middleware MUST key per-IP as: full IPv4 address
  (32-bit) for IPv4 sources; /64 prefix for IPv6 sources. The
  keying form is captured in audit entries (FR-009) but the raw
  full IPv6 address is NOT logged in keying form.
- **FR-005**: When the per-IP budget is exhausted, the middleware
  MUST reject the request with HTTP 429 and a `Retry-After`
  header per RFC 6585. The response body MUST be a fixed text
  ("rate limit exceeded") and MUST NOT echo any request content.
- **FR-006**: The exempt path list MUST contain `/health` and
  `/metrics`. Exempt paths bypass the limiter middleware entirely
  and MUST NOT consume per-IP budget. Exempt-path matching MUST
  be exact-path + method-restricted (`GET` only); other methods
  on those paths fall through to normal handling.
- **FR-007**: The middleware MUST NOT share state with, read
  state from, write state to, or otherwise interact with the
  §7.5 per-participant rate limiter. The two limiters MUST be
  independently testable.
- **FR-008**: When the middleware rejects a request, the
  application layer (auth, MCP handler, participant rate-limiter,
  cost tracker) MUST NOT observe the request — the rejection
  short-circuits at the middleware boundary.
- **FR-009**: The middleware MUST emit `admin_audit_log` entries
  for rejections per US3 AS1. To bound audit-log volume during
  sustained flooding, the logger MUST coalesce per-rejection
  events into per-(source_ip_keyed, minute) summary entries with
  a `rejection_count` field.
- **FR-010**: The middleware MUST increment spec 016's
  `sacp_rate_limit_rejection_total` counter on every rejection
  with labels `(endpoint_class="network_per_ip",
  exempt_match=false)`. The metric MUST NOT include source IP,
  query string, headers, or body content in any label.
- **FR-011**: When `SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS=false` (the default), the middleware MUST use the immediate peer IP. When set to `true`, the middleware MUST parse the rightmost entry of the `Forwarded` header per RFC 7239 (in v1 there is no proxy-trust whitelist per C1 resolution; the operator's responsibility for sanitizing upstream-supplied headers makes "trusted" equivalent to "rightmost"; see [research.md §4](./research.md)) — or `X-Forwarded-For` rightmost as fallback — and use that as the source IP.
- **FR-012**: When the source IP cannot be determined for a
  request, the middleware MUST reject with HTTP 400 and audit as
  `source_ip_unresolvable`. The rejection counter MUST increment
  with `exempt_match=false`.
- **FR-013**: All five new `SACP_NETWORK_RATELIMIT_*` env vars
  MUST have validator functions in `src/config/validators.py`
  registered in the `VALIDATORS` tuple, and corresponding
  sections in `docs/env-vars.md` with the six standard fields
  BEFORE `/speckit.tasks` is run for this spec (V16 deliverable
  gate).
- **FR-014**: When all five env vars are unset, the orchestrator's
  pre-feature behavior MUST be byte-identical: no middleware
  registered, no rejections, no audit entries for network-layer
  events, and the pre-feature acceptance suite passes unmodified.
  When any env var is set to an invalid value, the orchestrator
  MUST exit at startup with a clear error.
- **FR-015**: The middleware MUST handle WebSocket upgrade
  requests as a single request at upgrade time; subsequent
  traffic over the established WebSocket is OUT OF SCOPE for
  this middleware (handled by the §7.5 / spec 002 application-
  layer limiter post-auth).

### Key Entities

- **PerIPBudget** (process-scope, in-memory) — the token-bucket
  state per source-IP keyed form:
  `(source_ip_keyed, current_tokens, last_refill_at)`. Bounded
  by `SACP_NETWORK_RATELIMIT_MAX_KEYS` (see [data-model.md §PerIPBudget](./data-model.md))
  to prevent unbounded memory growth from random source IPs.
- **NetworkRateLimitRejectedRecord** (audit) — captures
  rejections per FR-009 (with coalescing).
- **ExemptPathRegistry** — fixed list of exempt
  `(path, method)` pairs (`(GET, /health)`, `(GET, /metrics)`).
  Read-only at runtime; defined at module load.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A flood of 200 requests/second from a single IP to
  a non-exempt MCP-server endpoint with bcrypt-protected auth
  results in at most `SACP_NETWORK_RATELIMIT_RPM` bcrypt
  invocations per minute — verified by a load test capturing
  the orchestrator's bcrypt invocation count.
- **SC-002**: Legitimate authentication from a non-flooding
  source IP completes within nominal latency
  (≤ pre-feature P95) during a sustained flood from another
  source IP — verified by a test that drives a flood from IP A
  and measures auth latency from IP B.
- **SC-003**: Exempt endpoints (`GET /health`, `GET /metrics`)
  remain available at unbounded request rates from any source
  IP — verified by a test that drives those paths at high
  rate and asserts no HTTP 429 responses.
- **SC-004**: The §7.5 per-participant rate limiter behaves
  byte-identically to its pre-feature implementation — verified
  by a contract test that runs the §7.5 acceptance suite with
  the network-layer limiter active and asserts no behavior
  change.
- **SC-005**: A network-layer rejected request never reaches
  application-layer state — verified by a test that drives a
  rejection and asserts: cost tracker unchanged, participant
  rate-limit counters unchanged, conversation state unchanged,
  audit-log entries other than `network_rate_limit_rejected`
  unchanged.
- **SC-006**: With all five env vars unset, the full pre-feature
  acceptance suite passes byte-identically — verified in CI.
- **SC-007**: With any env var set to an invalid value, the
  orchestrator process exits at startup with a clear error
  message naming the offending var (V16 fail-closed gate
  observed in CI).
- **SC-008**: Audit-log volume from a 1-hour sustained flood is
  bounded by `(unique_flooding_IPs × 60 minutes)` entries — the
  per-(IP, minute) coalescing rule (FR-009) is verified.
- **SC-009**: A privacy contract test asserts that the
  `network_rate_limit_rejected` audit row and the
  `sacp_rate_limit_rejection_total` metric carry no
  raw-IP-when-IPv6, no query string, no headers, and no body
  content.

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to all orchestrator-driven topologies (1-6)
that expose HTTP/SSE surfaces**. Every Phase-1 topology uses the
MCP server on port 8750; every Phase-2 deployment additionally uses
the Web UI on port 8751. The middleware is registered once at
process start and protects all listening surfaces.

**Topology 7 (MCP-to-MCP, Phase 3+) interaction**: In topology 7
the orchestrator can shrink to a state-management role with
materially fewer or no participant-facing inbound surfaces. If the
orchestrator still exposes `/health` or `/metrics`, this feature
remains relevant (those paths are unaffected by topology). If the
orchestrator exposes no participant-facing inbound HTTP surfaces,
the middleware is registered but has no traffic to limit.

### V13 — Use Case Coverage

This feature is **operator-facing infrastructure**, like spec 016.
It serves all four use cases equally because every deployment is
exposed to the same network-layer threat:

- §1 Distributed Software Collaboration: any internet-exposed
  deployment is at baseline DoS risk.
- §2 Research Co-authorship: research-cluster deployments may
  be inside an institutional network but still need protection
  against compromised internal hosts.
- §3 Consulting Engagement: client-network deployments often
  share IPs across many users (NAT) — operator must tune the
  limit accordingly.
- §4 Open Source Coordination: public-internet-exposed
  deployments are the highest-risk case.

No use case is the priority driver — this is foundational
hardening.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts. This
spec contributes three budgets:

- **Limiter middleware overhead per request**: Constant-time
  (`O(1)`). Hash lookup on source_ip_keyed, refill computation
  via timestamp delta, bucket increment/decrement. MUST add no
  more than the V14 per-stage budget tolerance to the request
  path. Budget enforcement: routing log captures middleware
  duration on a sample of requests.
- **Per-IP-budget eviction**: When the keyed-IP map exceeds
  `SACP_NETWORK_RATELIMIT_MAX_KEYS`, eviction MUST be `O(1)`
  amortized (LRU on the key map). Budget enforcement: eviction
  duration captured in routing log.
- **Audit-log coalescing flush**: The per-(IP, minute) summary
  flush MUST run on a background timer, NOT in the request
  path. Budget enforcement: flush is asynchronous and MUST NOT
  block any request.

## Configuration (V16) — New Env Vars

Five new `SACP_NETWORK_RATELIMIT_*` env vars are introduced. Each
MUST have type, valid range, and fail-closed semantics documented
in `docs/env-vars.md` BEFORE `/speckit.tasks` is run for this spec
(per V16 deliverable gate).

### `SACP_NETWORK_RATELIMIT_ENABLED`

- **Intended type**: boolean
- **Intended valid range**: `true` / `false` (case-insensitive)
- **Fail-closed semantics**: unset means `false` (no middleware,
  pre-feature behavior preserved). Unparseable values MUST cause
  startup exit per V16.

### `SACP_NETWORK_RATELIMIT_RPM`

- **Intended type**: positive integer, requests per minute
- **Intended valid range**: `1 <= value <= 6000`. Operator picks
  based on expected legitimate-client behavior; default `60`
  (one request per second on average per IP, generous for
  human-driven MCP clients per plan.md).
- **Fail-closed semantics**: unset paired with
  `SACP_NETWORK_RATELIMIT_ENABLED=true` MUST cause startup exit
  (the limiter requires a budget to be useful).

### `SACP_NETWORK_RATELIMIT_BURST`

- **Intended type**: positive integer, tokens
- **Intended valid range**: `1 <= value <= 10000`. Burst capacity
  for the token bucket — allows short bursts above the steady-
  state rate.
- **Fail-closed semantics**: unset means default `15` (= RPM/4,
  allows ~15-second bursts above steady state per plan.md).
  Out-of-range values MUST cause startup exit per V16.

### `SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS`

- **Intended type**: boolean
- **Intended valid range**: `true` / `false`.
- **Fail-closed semantics**: unset means `false` (use immediate
  peer IP). When `true`, the operator is responsible for ensuring
  the proxy sanitizes upstream-supplied headers. Unparseable
  values MUST cause startup exit.

### `SACP_NETWORK_RATELIMIT_MAX_KEYS`

- **Intended type**: positive integer, maximum number of keyed
  source-IP entries held in the in-memory token-bucket map
- **Intended valid range**: `1024 <= value <= 1_000_000`. Default
  `100_000` per plan.md. The bound caps worst-case memory under
  flood; LRU `OrderedDict.popitem(last=False)` evicts the
  least-recently-accessed entry when the map exceeds this size.
- **Fail-closed semantics**: unset means the default (`100_000`).
  Out-of-range values MUST cause startup exit per V16.

## Cross-References to Existing Specs and Design Docs

- **`sacp-design.md` §7 (Security)** — entire chapter binds the
  spec; specific subsections below.
- **`sacp-design.md` §7.4 (Transport Security)** — names the
  HTTP/SSE surfaces (port 8750 MCP, port 8751 Web UI) and the
  TLS-terminating proxy topology that interacts with FR-011
  forwarded-headers handling.
- **`sacp-design.md` §7.5 (Hardening)** — the existing
  application-layer per-participant rate limiter that THIS spec
  layers underneath but does NOT share state with (FR-007).
- **Constitution §6.5 (Auth, Phase 1)** — bcrypt-hashing of
  static tokens; the CPU-DoS vector this spec exists to close.
- **Constitution §3 (Sovereignty)** — sovereignty is preserved:
  the network-layer limiter has no participant context, no
  ability to deduce participant identity from IP, and writes no
  participant state.
- **Spec 002 (mcp-server)** — the MCP server on port 8750 is
  the v1 surface protected by this middleware.
- **Spec 016 (prometheus-metrics) FR-002 + FR-011** — `/metrics` is in the rate-limit exemption set (spec 016 FR-002); this spec's FR-006 implements the corresponding side. The `sacp_rate_limit_rejection_total` counter is owned by spec 016 FR-011 (sourced from the §7.5 rate-limiter rejection path, one increment per rejection); spec 016's contracts/metrics.md is canonical for the counter name. This spec's contracts/metrics.md mirrors the labeling extension specific to network-layer rejections (`endpoint_class="network_per_ip"`, `exempt_match=false`) per FR-010.
- **Spec 003 (turn-loop-engine) §FR-030** — `routing_log` per-
  stage timing capture; the limiter middleware's own duration
  surfaces through this channel (V14 budget).

## Assumptions

- The Phase-2 Web UI on port 8751 will reuse this exact
  middleware. The middleware is registered process-wide, not
  per-port, so adding port 8751 in Phase 2 is a wiring change,
  not a spec change. The Phase-2 cut MAY adjust the default
  `SACP_NETWORK_RATELIMIT_RPM` value if browser-driven traffic
  patterns warrant a different default; the env var name stays
  the same.
- The token-bucket algorithm with steady-state RPM + burst
  capacity is the assumed implementation; if a fixed-window
  algorithm is preferred during `/speckit.plan`, the env-var
  surface is unaffected (only the math changes).
- IPv6 /64 keying is the assumed default. Operators with strict
  per-host requirements can request /128 keying as a future
  per-deployment override; v1 is /64 only.
- `Retry-After` semantics follow RFC 6585 — header value is
  seconds (delta) form, not HTTP-date form.
- The middleware uses the orchestrator's existing HTTP framework's
  middleware-ordering primitives (FastAPI's `add_middleware`
  registration order). The "first middleware" guarantee depends
  on this ordering being deterministic and tested at startup.
- The audit-log coalescing window of 1 minute (FR-009) balances
  log volume against forensic granularity. Operators
  investigating an active flood can rely on the metrics surface
  for per-rejection counts; the audit log is the durable record.
- Audit-log entries for `network_rate_limit_rejected` are best-effort durable across orchestrator restart: the per-(source_ip_keyed, minute) summary buckets held in the async flush task's in-memory state at shutdown are LOST. The metrics counter `sacp_rate_limit_rejection_total` retains per-rejection durability via the prometheus surface and IS the durable record of rejection counts. SC-008's volume bound assumes flush-task success; worst-case row loss is the un-flushed minute window at shutdown.
- Memory for per-IP budget map is bounded by
  `SACP_NETWORK_RATELIMIT_MAX_KEYS` × small constant per entry;
  default settled in `/speckit.plan` to bound worst-case
  memory under flood.
- Multi-worker FastAPI deployments (e.g., uvicorn `--workers N`, gunicorn) result in EACH worker holding its own independent `PerIPBudget` map; the per-IP budget is therefore effectively `RPM × N` for an N-worker deployment. Operators tuning `SACP_NETWORK_RATELIMIT_RPM` for multi-worker deployments MUST account for this; v1 ships single-worker semantics as the spec contract and treats multi-worker as an operator-tuning concern. A future amendment may introduce shared-state mechanisms (Redis, shared-memory) to consolidate per-IP budgets across workers.
- Status remains Draft until the five flagged clarifications
  resolve and the user accepts the scaffolding.
