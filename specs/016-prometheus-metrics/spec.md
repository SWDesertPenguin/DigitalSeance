# Feature Specification: Operational Observability via Prometheus-Format Metrics

**Feature Branch**: `016-prometheus-metrics`
**Created**: 2026-05-06
**Status**: Implemented 2026-05-13
**Input**: User description: "Operational observability for SACP via Prometheus-format metrics. Operators running SACP need visibility into per-participant token spend, per-provider health, per-session conversation quality (convergence drift), routing-decision patterns, and rate-limit rejections. Without these signals, debugging production sessions or diagnosing budget anomalies requires reading raw audit logs, which does not scale. The metrics surface must respect SACP's privacy and sovereignty constraints: no metric label may carry participant-private state (model name, key fragments, message content). Label cardinality must be bounded at session scope so long-running deployments do not blow out the metrics database. The /metrics endpoint participates in the rate-limit exemption set alongside /health. Phase 1 scope covers operational debugging metrics. Phase 2 extends with Web UI dashboard panels. Cross-references §7.6 (privacy boundaries) and the cost-tracking and routing subsystems already in sacp-design.md."

## Overview

Operators running SACP today rely on `admin_audit_log` queries and
ad-hoc database scans to answer routine operational questions: which
participant has the highest token spend in the last hour, which
provider is returning the most errors, are sessions converging or
drifting, is the rate limiter rejecting legitimate traffic. Each of
those questions takes minutes-to-hours of manual SQL. None of them
scale to a deployment with more than a handful of concurrent
sessions, and none of them can drive an alert.

This spec defines a **Prometheus-format `/metrics` endpoint** as the
operational observability surface for SACP. The endpoint exposes
five families of signals — token spend, provider health, conversation
quality, routing decisions, and rate-limit rejections — designed
specifically to be ingested by an external Prometheus scraper and
plotted in standard tooling (Grafana, Mimir, VictoriaMetrics).

The endpoint is **operator-facing, not participant-facing**. It is
not exposed via the MCP interface; it lives at HTTP `/metrics` on
the orchestrator and inherits the existing transport-security model
(§7.4). It MUST participate in the rate-limit exemption set
alongside `/health` so that a busy scrape interval does not
self-throttle the very signal needed to debug rate limiting.

The metric surface is **privacy- and sovereignty-bounded**. Per §7.2
participant privacy and §7.6 AI-specific security:

- No label may carry message content (the AI-specific extraction
  surface from §7.6).
- No label may carry API key material or fingerprints (§7.1
  isolation).
- No label may carry the participant's model name (cardinality
  protection — model identifiers are unbounded — and a stricter
  privacy stance than §7.2 alone).
- Label cardinality is bounded at session scope. A long-running
  deployment that creates and tears down many sessions over time
  MUST NOT cause unbounded growth in the time-series database.

This spec is the **Phase 1 scope** — operational debugging metrics
only. A separate Phase 2 spec will add Web UI dashboard panels that
consume the same `/metrics` surface (no new metric primitives,
visualization layer only).

## Clarifications

### Initial draft assumptions requiring confirmation

- **§7.6 vs §7.2 reference.** User input cites "§7.6 (privacy
  boundaries)." §7.6 in `sacp-design.md` is "AI-Specific Security"
  (trust-tiered content, jailbreak detection, system-prompt
  extraction defense); §7.2 is "Participant Privacy" (the
  public/private/facilitator-visible field model that bounds what
  may appear in labels). Drafted with cross-references to both:
  §7.2 binds label content rules and §7.6 binds the no-content-
  in-labels stance. [NEEDS CLARIFICATION: confirm this dual
  cross-reference matches the intent.]
- **Model name as label.** §7.2 lists `model choice` as a PUBLIC
  field (visible to all participants). User input groups model
  name with private state ("no metric label may carry
  participant-private state (model name, key fragments, message
  content)"). Drafted on the stricter user stance — model name is
  excluded from labels — and noted that the cardinality argument
  reinforces this regardless of privacy classification. [NEEDS
  CLARIFICATION: confirm model name is excluded from labels even
  though it is technically public per §7.2.]
- **Phase labeling.** User input says "Phase 1 scope covers
  operational debugging metrics. Phase 2 extends with Web UI
  dashboard panels." Per memory, Phase 1 closed 2026-04-20 and
  Phase 2 closed 2026-05-04 (audit window closed); Phase 3 is in
  flight. Drafted as a back-fill into the Phase 1 reliability
  story (same ambiguity as spec 015). The Phase 2 dashboard
  follow-up is recorded as a separate future spec, not
  in-scope here. [NEEDS CLARIFICATION: confirm phase placement
  and whether this lands in current Phase-3 timeline or as a
  retroactive Phase-1 patch.]
- **Authentication on `/metrics`.** Drafted as: same transport-
  security model as `/health` — TLS terminated by the orchestrator
  or upstream proxy, no application-layer auth required, network
  exposure controlled by the deployer (per §7.4 "remote access for
  participants"). [NEEDS CLARIFICATION: confirm `/metrics` does
  not require its own bearer token or scrape credential.]

### Session 2026-05-13

All four markers resolved as drafted:

1. **§7.6 vs §7.2 dual cross-reference** — accepted as drafted. Both §7.2 (Participant Privacy — field visibility model) and §7.6 (AI-Specific Security — no-message-content-in-labels) are intentionally cited. The dual cross-reference is correct; no change needed.

2. **Model name excluded from labels** — confirmed. Model name is excluded from all metric labels even though §7.2 classifies it as a public field. The cardinality argument (model identifiers are an unbounded string set) independently justifies exclusion; the user's stricter privacy stance reinforces it. FR-004 stands as written.

3. **Phase labeling** — confirmed as Phase 3 backfill. Phases 1 and 2 are closed; this spec lands in the Phase 3 timeline on the `016-prometheus-metrics` branch. The "Phase 2 Web UI dashboard" follow-up noted in user input is a separate future spec captured in local memory only; it is not in scope here.

4. **Authentication on `/metrics`** — confirmed. No bearer token or scrape credential required at the application layer. The endpoint inherits the same TLS + network-exposure model as `/health` (§7.4). Operators control access via network policy; SACP adds no additional application-layer auth gate on the metrics path.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operator diagnoses a participant token-spend anomaly without reading audit logs (Priority: P1)

A facilitator notices a participant's budget burning faster than
expected mid-session. Today, diagnosing requires `psql` against the
audit log: filter by `participant_id`, sum cost over a window,
compare across participants, look for unusual call patterns. With
Prometheus metrics, the facilitator opens a Grafana dashboard
already pointed at the orchestrator, picks the session and
participant, and sees the per-turn spend curve immediately.

**Why this priority**: Token-spend visibility is the highest-value
operational signal. Sovereign budget autonomy (Constitution §3
"budget autonomy") presumes the participant can detect anomalies
in their own spend; today that requires SQL skill the participant
may not have. Per-participant spend metrics convert "is my budget
draining unexpectedly" from a forensics question into a
plot-the-rate question.

**Independent Test**: Run a 2-participant session. Drive each
participant through 5+ turns at known token costs. Scrape `/metrics`
and verify a per-session per-participant spend counter exists, that
its rate matches the actual call pattern within the V14 latency
budget, and that no participant's metric series carries another
participant's data.

**Acceptance Scenarios**:

1. **Given** a session with two participants A and B, **When** an
   operator scrapes `/metrics`, **Then** the response MUST contain
   a `sacp_participant_tokens_total` counter with labels
   `(session_id, participant_id, direction)` where
   `direction ∈ {prompt, completion}` and the sum equals the
   audit-log sum within ±0 tokens (counter is the source of truth
   for live; audit log is the source of truth for replay).
2. **Given** the same session, **When** the operator scrapes
   `/metrics`, **Then** the response MUST contain a
   `sacp_participant_cost_usd_total` counter (or equivalent —
   final unit decided in `/speckit.plan`) for the same label set,
   and the metric MUST NOT include any label carrying model name,
   API key material, or message content.
3. **Given** a long-running deployment with sessions started and
   ended over the last 24 hours, **When** the operator scrapes
   `/metrics`, **Then** the count of distinct
   `(session_id, participant_id)` label combinations MUST stay
   bounded by the count of currently-active sessions × their
   participant counts (terminated sessions MUST drop their
   time series — see FR-006 stale-series eviction).
4. **Given** the metrics env var is unset, **When** any session
   runs, **Then** the `/metrics` endpoint MUST respond with HTTP
   404 (not registered) and the orchestrator's existing endpoints
   MUST behave byte-identically to the pre-feature baseline.

---

### User Story 2 - Operator detects a provider outage and a converging session at a glance (Priority: P2)

Two related operational questions: which provider is degrading
right now, and which sessions are healthy versus drifting. Today
both require manual log inspection. With metrics, the operator
sees a per-provider error-rate gauge and a per-session
convergence-similarity gauge — both updated on the orchestrator's
existing event hooks (no extra database load).

**Why this priority**: P2 because the per-participant breaker (spec
015) already protects budget; this layer makes the same condition
visible at the deployment level rather than per-participant. The
convergence-drift gauge is the first session-quality metric and
unblocks dashboard panels in the Phase 2 follow-up.

**Independent Test**: Run a session with one provider returning
intermittent errors (test double, 30% error rate). Scrape `/metrics`
and verify the per-provider error-rate gauge reflects the injected
rate within the scrape interval. Separately, drive a session toward
convergence; verify the per-session similarity gauge tracks the
underlying spec 004 engine's value.

**Acceptance Scenarios**:

1. **Given** a session where provider P returns HTTP 500 on 30% of
   calls over a 5-minute window, **When** the operator scrapes
   `/metrics`, **Then** the response MUST contain a
   `sacp_provider_request_total` counter with labels
   `(provider_family, outcome)` where
   `outcome ∈ {success, error_5xx, error_4xx, timeout, quality_failure}`,
   and the rate of `error_5xx` divided by the rate of total requests
   approximates 0.30 within sampling tolerance.
2. **Given** the same session, **When** the operator scrapes
   `/metrics`, **Then** the `provider_family` label MUST be a
   normalized provider category (e.g., `openai`, `anthropic`,
   `google`, `local`, `other`) — NOT a model name and NOT a
   per-API-key value. The set of normalized families MUST be
   bounded and enumerable.
3. **Given** a session running the spec 004 convergence engine,
   **When** the operator scrapes `/metrics`, **Then** the response
   MUST contain a `sacp_session_convergence_similarity` gauge with
   label `(session_id)` whose value equals the engine's last
   computed similarity score for that session.
4. **Given** the convergence engine has not yet produced a similarity
   score for a session (cold session below the spec 004 minimum
   sample threshold), **When** the operator scrapes `/metrics`,
   **Then** the gauge MUST either omit that session entirely OR
   expose a sentinel value documented in `docs/metrics.md` — the
   gauge MUST NOT report a misleading default like 0 or 1.

---

### User Story 3 - Operator audits routing decisions and rate-limit rejections (Priority: P3)

Two operational signals tied to specific subsystems: routing
decisions (the orchestrator's per-turn dispatch choices, including
relevance filters and addressed-only gates) and rate-limit
rejections (per §7.5 hardening). Both produce events today; neither
is queryable as a time series.

**Why this priority**: P3 because the underlying behavior is correct
without these metrics — they are operator-quality signals for
debugging behavioral edge cases (e.g., "why did participant C never
take a turn this session" → routing decision histogram shows C was
filtered out by routing, not silently broken).

**Independent Test**: Run a session with a routing-mode mix
(addressed-only + always-on). Scrape `/metrics` and verify a
per-decision-class counter accumulates correctly. Separately, drive
a participant past their rate limit and verify the rate-limit
rejection counter increments without exposing the participant's
identity beyond the bounded label.

**Acceptance Scenarios**:

1. **Given** a session with mixed routing modes, **When** the
   operator scrapes `/metrics`, **Then** the response MUST contain
   a `sacp_routing_decision_total` counter with labels
   `(session_id, decision_class)` where `decision_class` is drawn
   from the bounded set defined in spec 003 (e.g.,
   `dispatched`, `filtered_addressed_only`, `filtered_observer`,
   `filtered_circuit_open`, `filtered_budget_exhausted`,
   `filtered_other`).
2. **Given** a participant exceeding their per-§7.5 rate limit,
   **When** the operator scrapes `/metrics`, **Then** the response
   MUST contain a `sacp_rate_limit_rejection_total` counter with
   labels `(session_id, participant_id, endpoint_class)` where
   `endpoint_class` is drawn from a bounded set
   (`mcp_write`, `mcp_read`, `web_ui`, `metrics_unused`).
3. **Given** the rate-limiter rejects a request, **When** the
   operator inspects the metric, **Then** the request URL, query
   string, headers, and any user-supplied content MUST NOT appear
   in any label.
4. **Given** the `/metrics` endpoint itself is being scraped at a
   sustained rate, **When** the orchestrator evaluates per-request
   rate limits, **Then** scrapes against `/metrics` MUST be exempt
   per the `/health` exemption pattern (§7.5) — scrapes MUST NOT
   count toward any participant's rate limit and MUST NOT be
   subject to general per-IP throttling.

---

### Edge Cases

- **Session ends with active counters.** When a session ends, its
  metric series MUST be evicted from the registry within a
  bounded grace window (FR-006). The grace window allows a final
  Prometheus scrape to capture the terminal counter values; after
  the window, the series MUST be removed to bound cardinality.
- **Two sessions with the same participant id.** `participant_id`
  is unique per session in spec 002 — no collision possible.
  The `(session_id, participant_id)` label tuple is therefore
  globally unique within an active deployment.
- **Provider category that does not match the bounded set.** A new
  provider not in the normalized family list (e.g., a self-hosted
  model behind a custom endpoint) MUST be labelled `other`. The
  bounded set is operator-extensible via configuration in a later
  spec; for v1 the set is fixed.
- **Convergence similarity for a session that never reached the
  minimum sample threshold.** The gauge MUST omit that session
  rather than report a misleading 0.
- **High-cardinality attempt via crafted participant id.**
  Participant ids are validated by spec 002 §FR-002 and bounded
  by display-name validation (§7.5 hardening). Cardinality is
  protected by session scope (FR-005) — at deployment scale this
  is bounded by `(active_sessions × max_participants_per_session)`.
- **Scrape during a session start/end transition.** Metric reads
  are eventually consistent; a scrape mid-transition may show a
  partial state. This is acceptable per Prometheus's scrape
  semantics and MUST NOT block transition completion.
- **Operator forgets to point Prometheus at the endpoint.** The
  endpoint is silent (no log spam) when no scraper is connected
  — `/metrics` is a pull surface, not a push.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The orchestrator MUST expose an HTTP `GET /metrics`
  endpoint returning a Prometheus text-format
  (`text/plain; version=0.0.4`) response when
  `SACP_METRICS_ENABLED=true`. When unset or false, the endpoint
  MUST return HTTP 404.
- **FR-002**: The endpoint MUST participate in the rate-limit
  exemption set alongside `/health` (§7.5). Scrapes against
  `/metrics` MUST NOT count toward any participant's rate limit
  and MUST NOT be subject to per-IP throttling that would
  affect a configured Prometheus scrape interval.
- **FR-003**: The endpoint MUST emit, at minimum, the metric
  families defined in US1–US3 acceptance scenarios:
  `sacp_participant_tokens_total`,
  `sacp_participant_cost_usd_total`,
  `sacp_provider_request_total`,
  `sacp_session_convergence_similarity`,
  `sacp_routing_decision_total`,
  `sacp_rate_limit_rejection_total`. Final naming and label sets
  are settled in `/speckit.plan` against Prometheus naming
  conventions.
- **FR-004**: No metric MUST carry a label whose value contains:
  message content, system prompt content, API key material or
  fingerprint, model name, IP address, user-agent string, or
  request URL.
- **FR-005**: Label cardinality MUST be bounded at session scope.
  All session-scoped labels MUST be drawn from
  `(session_id, participant_id, decision_class, endpoint_class,
  provider_family, outcome, direction)` where each non-id label
  is drawn from a bounded enumeration documented in
  `docs/metrics.md`.
- **FR-006**: When a session ends, all metric series carrying that
  session's `session_id` label MUST be evicted from the registry
  within `SACP_METRICS_SESSION_GRACE_S` seconds (default settled
  in `/speckit.plan`). Eviction MUST be deterministic and
  observable in the routing log.
- **FR-007**: The metric surface MUST be additive. With
  `SACP_METRICS_ENABLED=false` (the default), the orchestrator's
  pre-feature behavior MUST be byte-identical: no `/metrics`
  endpoint registered, no metric collection overhead, no new
  background tasks.
- **FR-008**: All token-spend and cost metrics MUST be sourced from
  the existing cost-tracking subsystem (`sacp-design.md` cost
  tracker — see §6.5 streaming-state and §3 budget autonomy).
  No new cost computation paths MAY be introduced. The metrics
  surface MUST report the cost tracker's current state, not a
  parallel computation.
- **FR-009**: The convergence-similarity gauge MUST be sourced from
  the existing spec 004 convergence engine. The gauge MUST update
  no more than once per turn (the engine's existing computation
  cadence). No additional engine invocations MAY be introduced.
- **FR-010**: The routing-decision counter MUST be sourced from the
  existing spec 003 routing log. The counter increments at the
  same point where `routing_log` rows are written; both surfaces
  MUST agree.
- **FR-011**: The rate-limit rejection counter MUST be sourced
  from the existing §7.5 rate-limiter rejection path. The
  counter MUST increment exactly once per rejection.
- **FR-012**: All three new `SACP_METRICS_*` env vars MUST have
  validator functions in `src/config/validators.py` registered in
  the `VALIDATORS` tuple, and corresponding sections in
  `docs/env-vars.md` with the six standard fields BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable gate).
- **FR-013**: The orchestrator MUST publish a companion
  `docs/metrics.md` document enumerating every metric, its labels,
  the bounded enumerations for each label, and the cardinality
  bound. This document MUST land BEFORE `/speckit.tasks` per V16
  deliverable gate.
- **FR-014**: When `/metrics` is scraped, the response MUST be
  produced in constant-time relative to the count of active
  sessions × max participants — i.e., O(active_series). The
  endpoint MUST NOT trigger any database read on the hot path
  beyond what cost-tracking and routing already do.
- **FR-015**: The endpoint MUST NOT emit Prometheus exemplars,
  histogram buckets, or summary quantiles in v1. Counters and
  gauges only. Histograms are deferred to the Phase 2 dashboard
  follow-up if needed.

### Key Entities

- **MetricRegistry** (orchestrator-scope, in-memory) — holds all
  active metric series. Keyed on
  `(metric_name, labelset_tuple)`. Bounded by FR-005 + FR-006.
- **SessionScopedSeries** (per-session) — every metric series
  carrying a `session_id` label is bound to that session's
  lifetime. Eviction at session end per FR-006.
- **MetricsConfig** (process-scope) — captures
  `(enabled, session_grace_s, bind_addr_or_inherited)` resolved
  at startup and frozen for the process lifetime.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can answer "what is participant P's
  per-minute token spend rate over the last 15 minutes" using only
  a Prometheus query against `/metrics`, without `psql` access or
  audit-log shell pipelines.
- **SC-002**: With `SACP_METRICS_ENABLED=true` and a 15-second
  scrape interval, the orchestrator's per-turn dispatch latency
  (measured at spec 003 routing-log timing) regresses by no more
  than the V14 turn-prep budget tolerance versus a baseline run
  with metrics disabled.
- **SC-003**: After a session ends, all of that session's metric
  series are absent from `/metrics` within
  `SACP_METRICS_SESSION_GRACE_S + 1 scrape interval`.
- **SC-004**: A 24-hour deployment running 1000 sessions
  start-to-end shows a steady-state metric series count bounded by
  `(active_sessions × max_participants × per_session_metric_count)`,
  not unbounded growth — verified by a load-test contract.
- **SC-005**: With `SACP_METRICS_ENABLED=false` (default), the
  full pre-feature acceptance suite passes unmodified. No
  `/metrics` endpoint is registered.
- **SC-006**: With any `SACP_METRICS_*` env var set to an invalid
  value, the orchestrator process exits at startup with a clear
  error message naming the offending var (V16 fail-closed gate).
- **SC-007**: A privacy contract test enumerates every label on
  every metric and asserts no label value matches: a stored API
  key prefix, a known message-content fixture string, a model
  name string, or a UA/IP/URL pattern. Test MUST run in CI on
  every PR.
- **SC-008**: A scrape of `/metrics` issued at the configured
  Prometheus scrape interval is not throttled by the rate
  limiter — verified by a contract test that drives the rate
  limit to its threshold and confirms `/metrics` continues to
  respond (FR-002).

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** (orchestrator-driven
topologies). The orchestrator is the metric source — it owns the
cost-tracking, routing, convergence, and rate-limiter subsystems
that produce the underlying signals.

This feature is **incompatible with topology 7 (MCP-to-MCP, Phase
3+)** in its current form. Topology 7 removes the orchestrator from
the dispatch path, so the orchestrator-side cost tracker, routing
log, and convergence engine are not the source of truth for those
sessions. Per V12: any future topology-7 deployment MUST either
disable this metrics surface or define a topology-7-native
equivalent (likely a separate spec; the candidate signal sources
are the participants' own MCP clients, which raises sovereignty
questions for any aggregated view).

### V13 — Use Case Coverage

This feature is **operator-facing infrastructure** rather than a
participant-visible behavior. It serves all four `docs/sacp-use-cases.md`
use cases equally because deployments under any use case need
operational visibility:

- §1 Distributed Software Collaboration: long-running sessions need
  spend and convergence trend visibility.
- §2 Research Co-authorship: per-participant spend visibility is
  the primary signal for asynchronous-time-zone deployments.
- §3 Consulting Engagement: token-spend dashboards become a
  client-deliverable artefact.
- §4 Open Source Coordination: aggregated routing-decision metrics
  expose participation imbalance.

No use case is the priority driver — this is foundational
operability, not use-case-specific.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts. This
spec contributes three budgets:

- **`/metrics` endpoint latency**: P95 response time MUST be at or
  below 500ms for an active deployment of 100 sessions × 5
  participants. Budget enforcement: the endpoint's own request
  duration captured in routing log if the route is registered.
- **Per-turn metric-update overhead**: Each turn's metric updates
  (token counter increment, routing counter increment, optional
  convergence gauge update) MUST add no more than the V14
  turn-prep budget tolerance versus a baseline turn with metrics
  disabled. Budget enforcement: SC-002 contract test.
- **Session-end metric eviction**: Eviction MUST complete within
  `SACP_METRICS_SESSION_GRACE_S` (FR-006). Budget enforcement:
  the eviction event captured as a routing-log entry.

## Configuration (V16) — New Env Vars

Three new `SACP_METRICS_*` env vars are introduced. Each MUST have
type, valid range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this spec
(per V16 deliverable gate).

### `SACP_METRICS_ENABLED`

- **Intended type**: boolean (`true` / `false`)
- **Intended valid range**: exactly `true` or `false` (case-insensitive)
- **Fail-closed semantics**: unset or invalid means `false`
  (endpoint not registered). Unparseable values MUST cause
  startup exit per V16.

### `SACP_METRICS_SESSION_GRACE_S`

- **Intended type**: positive integer, seconds
- **Intended valid range**: `5 <= value <= 300` (5 seconds
  minimum to allow a final Prometheus scrape; 5 minutes maximum
  to bound cardinality).
- **Fail-closed semantics**: unset means a default settled in
  `/speckit.plan` (likely 30s — one standard scrape interval).
  Out-of-range values MUST cause startup exit per V16.

### `SACP_METRICS_BIND_PATH`

- **Intended type**: string, URL path
- **Intended valid range**: must start with `/`, must be
  alphanumeric + dashes after the slash; default `/metrics`.
- **Fail-closed semantics**: unset means `/metrics`. Path that
  collides with an existing route (e.g., `/health`) MUST cause
  startup exit per V16.

## Cross-References to Existing Specs and Design Docs

- **`sacp-design.md` §3 Sovereignty / Constitution §3** — budget
  autonomy guarantee is the privacy reason participant spend may
  appear in metrics scoped to that participant's session, but
  nothing about another participant's spend may.
- **`sacp-design.md` §6.5 (Streaming Architecture)** — the
  cost-tracking finalization point is the source of FR-008 token
  and cost counters.
- **`sacp-design.md` §7.2 (Participant Privacy)** — defines the
  public/private/facilitator-visible field model. FR-004's
  excluded-label list maps to private fields plus the
  user-stricter no-model-name stance.
- **`sacp-design.md` §7.4 (Transport Security)** — `/metrics`
  inherits the same TLS posture as `/health` and other
  orchestrator HTTP routes.
- **`sacp-design.md` §7.5 (Hardening)** — rate-limit exemption
  pattern (`/health`) extended to `/metrics` per FR-002.
- **`sacp-design.md` §7.6 (AI-Specific Security)** — the
  no-message-content-in-labels stance is reinforced by §7.6's
  trust-tiered content model: message content is the AI-specific
  injection surface and MUST NOT be retrievable through the
  metrics endpoint.
- **Spec 002 (mcp-server)** — `participant_id` uniqueness within
  a session backs the `(session_id, participant_id)` label key.
- **Spec 003 (turn-loop-engine) §FR-030** — `routing_log`
  per-stage timing capture; the routing-decision counter and
  endpoint-eviction events surface through this same channel.
- **Spec 004 (convergence-cadence)** — the convergence-similarity
  gauge reads the engine's last-computed score (FR-009).
- **Spec 015 (provider-failure-detection)** — provider-health
  signals overlap: spec 015's circuit state is exposed via
  `admin_audit_log`, while this spec exposes the per-call
  outcome counter that drives the breaker. Both surfaces are
  intentional: the breaker state is operationally relevant
  (which participants are isolated right now) and the counter
  is diagnostically relevant (what's the underlying error rate).
  No double-counting — both sources read the same dispatch
  outcome event.

## Assumptions

- The Prometheus text format is the only output format in v1.
  OpenMetrics, gRPC, and push-gateway integrations are out of
  scope.
- The metrics surface is pull-only. SACP does not push metrics to
  any external system; the deployer points a Prometheus-compatible
  scraper at the orchestrator.
- The Phase 2 Web UI dashboard panels (cited in user input) are a
  separate spec that consumes this surface. This spec does not
  define dashboard layouts, panel choice, or alerting rules.
- The `provider_family` normalization map is a fixed enumeration
  in v1; operator extensibility is a follow-up.
- Histograms (P50/P95/P99 latency) are deferred to the dashboard
  follow-up. Counters and gauges only in v1.
- "Phase 1 scope" in the user description is interpreted as
  back-fill into the Phase 1 operational story; the Phase 2 Web
  UI dashboard follow-up is captured in user-side memory rather
  than this spec. Confirmation of this framing is pending per
  Clarifications §"Phase labeling".
- Status remains Draft until the four flagged clarifications
  resolve and the user accepts the scaffolding.
