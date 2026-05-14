# Feature Specification: Provider Failure Detection and Isolation (Bridge-Layer Circuit Breaker)

**Feature Branch**: `015-provider-failure-detection`
**Created**: 2026-05-06
**Status**: Implemented 2026-05-13
**Input**: User description: "Provider failure detection and isolation for SACP's bridge layer. When a participant's configured provider becomes unhealthy — returning errors, timing out, or otherwise failing repeatedly — SACP must detect the condition, stop sending requests to that provider for a cooldown period, and recover automatically when the provider becomes healthy again. This protects participants from cascading failures and prevents wasted token spend on calls that will fail. The mechanism must respect SACP's BYOK/sovereignty model: one participant's failures must not affect other participants, and SACP must never transparently fall back to a different provider — each participant's identity is tied to their declared model. Failures and recoveries must be visible in the audit log and in the metrics surface. Phase 1 scope. Cross-references §7 of sacp-design.md (security/reliability) and the constitution's participant-sovereignty principles."

## Overview

The orchestrator's bridge layer makes provider calls on behalf of
each participant using the participant's own API key, model, and
provider (BYOK). Today, when a participant's provider becomes
unhealthy — returning 5xx errors, timing out, hitting an authentication
problem, or producing repeated quality failures (per
`sacp-design.md` §6.6) — the orchestrator continues dispatching turn
after turn, burning the participant's tokens on calls that are
statistically certain to fail and degrading the session for every
other participant who is waiting on the failing one's turn to
complete the loop.

This spec defines **provider failure detection and isolation** as a
per-participant circuit breaker in the bridge layer that:

1. **Detects** unhealthy provider state via a configurable failure
   threshold over a rolling window (errors, timeouts, repeated
   quality failures per §6.6 detection rules).
2. **Isolates** by tripping a cooldown for *that participant only* —
   subsequent dispatch attempts during cooldown are short-circuited
   without making a network call.
3. **Recovers** automatically by probing the provider on a backoff
   schedule and restoring normal dispatch when a probe succeeds.
4. **Audits** every state transition (open, half-open probe, close)
   into `admin_audit_log` and surfaces aggregate state in the
   metrics surface so operators can see which participants are
   currently isolated and why.

The mechanism is **strictly per-participant**. Two participants
sharing the same upstream provider (e.g., both on OpenAI) get
independent circuit state; one's quota exhaustion or auth failure
does not trip the other's circuit. This preserves the V1 sovereignty
guarantees (API key isolation, model choice independence, budget
autonomy) — a participant's failures are contained to their own
identity.

The mechanism MUST NOT silently fall back to a different provider or
model. Constitutional §3 binds each participant's identity to their
declared model; a transparent fallback would substitute a different
identity into the conversation without consent. LiteLLM's built-in
ordered-fallback feature (`sacp-design.md` §6.6 "ordered model fallback
lists") MUST be disabled or scoped exclusively to fallbacks within the
*same* participant identity (e.g., a same-provider model alias). When
a participant's circuit is open, their AI's turn is skipped per the
existing §6.6 fallback policy ("skip the turn, log the failure, notify
the human, continue"); 3+ consecutive open-state turns continue to
trigger the existing auto-pause path.

## Clarifications

### Session 2026-05-14 (/speckit.analyze findings)

- Q: FR-011 "cross-identity" startup check was undefined at spec level — what constitutes a cross-identity fallback? (finding 015-C1) → A: FR-011 now defines cross-identity as any ordered-fallback list entry whose top-level LiteLLM provider key differs from the participant's declared `provider` field. Same-provider model aliases are permitted. The startup check logs `cross_identity_change_detected` and exits before port bind on mismatch.
- Q: The Assumptions block said `admin_audit_log` reuse but plan/tasks shipped three dedicated audit tables — which is authoritative? (finding 015-F1) → A: The three dedicated tables (`provider_circuit_open_log`, `provider_circuit_probe_log`, `provider_circuit_close_log`) are what shipped. The Assumptions block has been updated to match. The stale "Status remains Draft" scaffold footer has also been removed; the spec is Implemented 2026-05-13.
- Q: Does this amendment change behavior? → A: No. Doc-consistency fixes only.

### Initial draft assumptions requiring confirmation

- **Phase labeling.** The user description says "Phase 1 scope." Per
  `project_phase1_status.md`, Phase 1 closed 2026-04-20 and
  Phase 3 was declared 2026-05-05 (specs 013 + 014 in flight). Two
  reasonable interpretations: (a) this spec back-fills a Phase 1
  reliability story that was deferred (LiteLLM-managed cooldown
  exists today per §6.6 but is not surfaced through SACP's audit
  log or metrics); (b) "Phase 1" was shorthand for "minimum-viable
  scope, no dynamic-controller layering on top." Defaulted to (a)
  in this draft.
- **Failure-counting semantics.** Description says "errors, timing
  out, or otherwise failing repeatedly." Drafted as: a sliding-window
  count of (HTTP 5xx | timeout | auth failure | §6.6 quality-failure
  detection) where the threshold is a count-within-window rather than
  raw consecutive failures, so an intermittent flap does not trip
  the breaker on a single bad turn.
- **Relationship to LiteLLM's existing cooldown.** `sacp-design.md`
  §6.6 already cites "LiteLLM provides ordered model fallback lists,
  context window fallbacks, and cooldown management." Drafted as:
  SACP wraps a thin per-participant breaker layer *above* LiteLLM,
  observing LiteLLM's call outcomes; LiteLLM's own fallback list is
  configured to empty or to same-identity-only entries.

### Session 2026-05-13

All four NEEDS CLARIFICATION markers resolved autonomously per user authorization.

- **Phase labeling resolved**: Phase 1 back-fill confirmed. This spec formalizes and surfaces the reliability story that §6.6 cited but left SACP-opaque (the existing `CircuitBreaker` class tracks consecutive failures but emits no audit rows, uses no sliding window, and has no probe-recovery path). Implementation lands on the `015-provider-failure-detection` branch under the current Phase 3 work stream — no retroactive Phase 1 patch path; no sub-phase split.
- **Failure-counting semantics resolved**: Sliding-window count confirmed over consecutive-failure count. The existing implementation uses consecutive; this spec formalizes the position drafted in the initial assumptions. A sliding window prevents a single isolated bad turn from tripping the breaker during an otherwise-healthy session; the ring-buffer approach per FR-002 and the `FailureRecord` entity is the implementation shape.
- **LiteLLM delegation resolved**: SACP owns the breaker state. No delegation to LiteLLM's internal cooldown or fallback machinery. LiteLLM's ordered-fallback list is configured to empty or same-identity-only entries; SACP observes call outcomes via the `CanonicalError` categories from `src/api_bridge/litellm/errors.py` and manages transitions independently. Confirmed per FR-011.
- **Manual clear tool resolved**: Out of scope for v1. The two supported recovery paths are auto-recovery via the probe backoff schedule (US2) and the `update_api_key` fast-close path (FR-016). An operator-accessible manual-clear admin tool is a potential follow-up not tracked in this spec.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Failing provider stops draining a participant's tokens (Priority: P1)

A participant configures their AI on a provider that begins returning
5xx errors mid-session (provider-side outage). Today, the orchestrator
continues to dispatch each of that participant's turns, each call
times out after the LiteLLM timeout, the participant's token budget is
consumed on retries, and the session stalls on every turn that
participant should have produced.

**Why this priority**: This is the core protection the feature exists
to deliver. Without it, a single misbehaving provider drains a
participant's budget and blocks the loop for every other participant.
Detection + isolation is the minimum viable slice — recovery and
visibility (P2/P3) layer on top.

**Independent Test**: Configure a 2-participant session where one
participant's provider is forced to return 5xx on every call (test
double or fault-injection proxy). Drive the session through enough
turns to cross the failure threshold. Verify subsequent dispatches
for that participant short-circuit (no outbound network call observable
at the bridge layer) for the configured cooldown window, while the
other participant's turns proceed normally.

**Acceptance Scenarios**:

1. **Given** a participant whose provider returns 5xx on every call
   and `SACP_PROVIDER_FAILURE_THRESHOLD=3` over a 60s window, **When**
   the participant's third failed call within 60s completes, **Then**
   the breaker MUST trip to open state for that participant and the
   next dispatch attempt MUST be short-circuited without a network
   call.
2. **Given** the breaker is open for participant A, **When** the
   orchestrator advances to participant B's turn (different provider
   or same provider, different participant identity), **Then**
   participant B's dispatch MUST proceed normally and MUST NOT be
   affected by A's circuit state.
3. **Given** the breaker is open for participant A, **When** the
   orchestrator would have dispatched A's turn, **Then** the turn
   MUST be skipped per the existing §6.6 fallback policy (skip,
   log, notify human, continue) and the skip MUST NOT count as a
   convergence-relevant turn for spec 004's similarity engine.
4. **Given** all required env vars are unset, **When** any session
   runs, **Then** the breaker MUST be inactive and dispatch behavior
   MUST be byte-identical to the pre-feature baseline (fail-closed
   = preserve current behavior, no implicit defaults).

---

### User Story 2 - Provider recovery restores dispatch automatically (Priority: P2)

The same participant's provider recovers from its outage. Without
auto-recovery, the operator has to manually intervene (restart the
orchestrator, re-register the participant, or wait for a session
reset) before that participant's AI can take turns again. With
auto-recovery, the orchestrator probes the provider on a backoff
schedule; when a probe succeeds, the breaker closes and dispatch
resumes.

**Why this priority**: P2 because the participant *can* still
participate manually (their human can inject messages) and the
session can complete without auto-recovery (operator restart). But
this is a substantial operator-burden reduction, especially in
multi-hour sessions where transient outages are common.

**Independent Test**: Trip the breaker per US1, then flip the test
double to return 200 OK. Verify the orchestrator probes on the
configured backoff schedule, that exactly one probe call is made per
backoff tick (not per turn), and that the breaker closes after the
first successful probe — restoring normal dispatch on the
participant's next turn.

**Acceptance Scenarios**:

1. **Given** the breaker is open for participant A and
   `SACP_PROVIDER_RECOVERY_PROBE_BACKOFF=5,10,30` (seconds), **When**
   the cooldown window elapses, **Then** the orchestrator MUST issue
   exactly one probe call to the provider on each backoff tick and
   MUST NOT issue more than one probe per tick.
2. **Given** a probe succeeds, **When** the next dispatch for
   participant A occurs, **Then** the breaker MUST close, the
   dispatch MUST proceed normally, and a `provider_circuit_close`
   audit event MUST be emitted.
3. **Given** all probes within the backoff schedule fail, **When**
   the schedule exhausts, **Then** the breaker MUST remain open,
   the schedule MUST restart from its longest interval (no
   indefinite increase beyond the configured maximum), and an
   `admin_audit_log` entry MUST capture the exhausted-schedule
   state.
4. **Given** a participant updates their API key while the breaker
   is open (`update_api_key` MCP tool per `sacp-design.md` §7.1),
   **When** the new key validation succeeds, **Then** the breaker
   MUST close immediately (operator-initiated recovery) without
   waiting for the next probe tick.

---

### User Story 3 - Operators see which participants are isolated and why (Priority: P3)

A facilitator running a multi-participant session needs to know
which participants are currently isolated, when they were isolated,
and what tripped the breaker. Without visibility, an isolated
participant looks indistinguishable from a quiet participant, and
the facilitator cannot triage (is it a provider outage, an API key
problem, or just a slow human?).

**Why this priority**: P3 because the session functionally degrades
gracefully without this — US1 + US2 already protect tokens and
auto-recover. Visibility is the operational-quality slice that makes
the mechanism self-explanatory in production.

**Independent Test**: Trip the breaker for one participant in a
multi-participant session. Open the metrics surface (existing
operator dashboard / `/metrics` endpoint per current convention) and
verify a per-participant breaker-state field is present and reflects
the open state. Query the audit log and verify the
`provider_circuit_open` event with the trigger reason is present.

**Acceptance Scenarios**:

1. **Given** the breaker trips for participant A, **When** the
   trip occurs, **Then** an `admin_audit_log` entry of action type
   `provider_circuit_open` MUST be written with payload fields
   `(session_id, participant_id, trigger_reason, failure_count,
   window_seconds, opened_at)`.
2. **Given** the breaker is open for participant A, **When** an
   operator inspects the metrics surface, **Then** the surface MUST
   expose at minimum: count of currently-open breakers per session,
   per-participant open-since timestamp, and trigger-reason
   breakdown (errors / timeouts / quality-failures / auth).
3. **Given** the breaker recovers (US2), **When** the close occurs,
   **Then** a `provider_circuit_close` audit entry MUST be written
   with `(session_id, participant_id, closed_at, total_open_seconds,
   probes_attempted, probes_succeeded)`.
4. **Given** a probe is issued during recovery, **When** the probe
   completes (success or failure), **Then** a
   `provider_circuit_probe` audit entry MUST be written so the
   probe trail is visible without inferring it from breaker
   open/close state alone.

---

### Edge Cases

- **Two participants on the same provider, one's API key revoked.**
  The revoked-key participant trips the breaker on auth failures.
  The healthy-key participant is not affected — circuit state is
  keyed on `(participant_id, provider, api_key_fingerprint)`, not
  on `provider` alone.
- **Provider returns 200 OK with §6.6 quality-failure output.**
  Counts toward the failure threshold using the existing §6.6
  detection rules (empty response, repetitive n-grams, framing
  break). Quality failures and infrastructure failures share the
  same threshold counter — the breaker does not distinguish.
- **Rate limit error with `Retry-After` header.** Counts as a
  failure but the cooldown is set to `max(configured_cooldown,
  Retry-After)` so SACP respects the provider's stated retry
  guidance per §6.6.
- **Participant uses local proxy mode (per §3 sovereignty).**
  Same per-participant breaker semantics; the proxy is the
  effective provider endpoint for failure detection.
- **Operator manually clears the breaker.** Out of scope for v1 — the auto-recovery path (US2) and `update_api_key` fast-close path are the two supported recovery paths. Resolved: Session 2026-05-13.
- **Breaker open at session boundary.** Circuit state is
  session-local and not persisted across restart. On restart, the
  breaker starts closed for every participant and re-evaluates
  from the next dispatch (matches existing per-session state
  behavior).
- **Provider outage affects all participants on that provider.**
  Each participant's circuit trips independently as their own
  failure threshold is crossed. There is no aggregate "provider
  is down" state — sovereignty requires per-participant
  containment, even when the underlying outage is shared.
- **Convergence engine sees skipped turns.** A skipped turn (open
  breaker) is excluded from spec 004's similarity-window inputs
  to avoid false convergence on participant absence. The skip
  itself is captured in the routing log per spec 003 §FR-030.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The orchestrator MUST maintain per-participant circuit
  state at the bridge layer, keyed on
  `(session_id, participant_id, provider, api_key_fingerprint)`.
- **FR-002**: The breaker MUST trip to open state when the count of
  failures within the configured rolling window
  (`SACP_PROVIDER_FAILURE_WINDOW_S`) reaches or exceeds the
  configured threshold (`SACP_PROVIDER_FAILURE_THRESHOLD`).
- **FR-003**: A failure is one of: HTTP 5xx response, request
  timeout, authentication error (HTTP 401/403), rate-limit error
  (HTTP 429), or a §6.6 quality-failure detection (empty response,
  repetition above threshold, framing break).
- **FR-004**: While a breaker is open, dispatch attempts for that
  participant MUST be short-circuited at the bridge layer without
  issuing an outbound network call.
- **FR-005**: A short-circuited turn MUST be handled per the existing
  §6.6 fallback policy (skip the turn, log the failure, notify the
  human, continue). 3+ consecutive open-state turns MUST continue
  to trigger the existing auto-pause path.
- **FR-006**: The orchestrator MUST issue recovery probes on the
  configured backoff schedule (`SACP_PROVIDER_RECOVERY_PROBE_BACKOFF`)
  and MUST issue at most one probe per backoff tick per breaker.
- **FR-007**: A recovery probe MUST be a minimal-cost call (e.g.,
  the same lightweight test call used by `update_api_key` per
  §7.1). Probe responses MUST NOT enter the conversation transcript.
- **FR-008**: When a probe succeeds, the breaker MUST close on the
  next dispatch and a `provider_circuit_close` audit entry MUST be
  emitted with the fields listed in US3 AS3.
- **FR-009**: When the backoff schedule exhausts without a successful
  probe, the schedule MUST loop on its longest interval (no
  unbounded growth) and MUST emit a single audit entry per
  exhaustion cycle.
- **FR-010**: Per-participant circuit state MUST be independent —
  no participant's circuit may transition state in response to
  another participant's failures, even when sharing the same
  upstream provider endpoint.
- **FR-011**: The orchestrator MUST NOT transparently fall back to
  a different provider or model when a circuit is open. LiteLLM's
  ordered-fallback feature MUST be configured to empty or
  same-identity-only entries; this MUST be enforced as a startup
  check that fails closed if a cross-identity fallback is detected.
  A **cross-identity fallback** is any ordered-fallback list entry
  whose `provider` value (the top-level key in the LiteLLM model
  alias config, e.g. `openai`, `anthropic`, `azure`) differs from
  the participant's declared `provider` field in the `participants`
  table. Same-provider model aliases (e.g., `gpt-4o` → `gpt-4o-mini`
  under the same `openai` provider key) are same-identity and are
  permitted. The startup check iterates every registered participant's
  LiteLLM router config entry; if any fallback entry carries a
  different top-level provider key than the participant's declared
  provider, the check MUST log `cross_identity_change_detected` and
  exit the orchestrator process before binding any port.
- **FR-012**: Every breaker state transition (open, probe attempted,
  close, exhausted) MUST emit an `admin_audit_log` entry with the
  field set defined in US3.
- **FR-013**: The metrics surface MUST expose, per session: count of
  currently-open breakers, per-participant open-since timestamp
  while open, and a trigger-reason breakdown
  (errors / timeouts / quality / auth / rate_limit).
- **FR-014**: All four new `SACP_*` env vars MUST have validator
  functions in `src/config/validators.py` registered in the
  `VALIDATORS` tuple, and corresponding sections in
  `docs/env-vars.md` with the six standard fields (Default, Type,
  Valid range, Blast radius, Validation rule, Source spec) BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable gate).
- **FR-015**: When all four env vars are unset, dispatch behavior
  MUST be byte-identical to the pre-feature baseline (additive
  feature, no implicit defaults). When any var is set to an
  invalid value, the orchestrator MUST exit at startup with a
  clear error naming the offending var (V16 fail-closed).
- **FR-016**: An `update_api_key` success for a participant whose
  breaker is open MUST close the breaker immediately
  (operator-initiated fast recovery), bypassing the probe
  schedule, and MUST emit a `provider_circuit_close` audit entry
  with `trigger_reason="api_key_update"`.
- **FR-017**: Skipped turns due to open breakers MUST be excluded
  from spec 004's convergence similarity inputs and MUST be
  visible in the routing log per spec 003 §FR-030.

### Key Entities

- **CircuitState** (per participant, session-local) — captures
  `(session_id, participant_id, provider, api_key_fingerprint,
  state, opened_at, failure_window, probe_schedule_position)`.
  `state` is one of {closed, open, half_open}. Cached for the
  session lifetime; not persisted across restart.
- **FailureRecord** (rolling window) — append-only ring buffer of
  `(timestamp, failure_kind)` entries within the configured
  window. Bounded by window length × maximum credible failure
  rate to prevent unbounded growth.
- **ProviderCircuitOpenRecord** (audit) —
  `(session_id, participant_id, trigger_reason, failure_count,
  window_seconds, opened_at)`.
- **ProviderCircuitProbeRecord** (audit) —
  `(session_id, participant_id, probe_at, probe_outcome,
  probe_latency_ms, schedule_position)`.
- **ProviderCircuitCloseRecord** (audit) —
  `(session_id, participant_id, closed_at, total_open_seconds,
  probes_attempted, probes_succeeded, trigger_reason)`.
  `trigger_reason` distinguishes auto-recovery from
  api_key_update fast-close.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When a participant's provider returns persistent 5xx
  errors, that participant's token spend stops growing within
  `(failure_threshold × per_call_token_cost)` of the first failure
  — i.e., no more than `failure_threshold` failed calls are billed
  before the breaker isolates the participant.
- **SC-002**: A participant with an open breaker does not delay the
  loop for other participants — per-loop wall-clock latency for
  unaffected participants is statistically indistinguishable from a
  baseline session with no failing participant (within existing
  V14 turn-prep budget tolerance).
- **SC-003**: When a provider recovers, the affected participant
  resumes dispatch within `max_backoff_interval + 1 turn` of the
  recovery, without operator action.
- **SC-004**: An operator inspecting the metrics surface during an
  active outage can identify the affected participant(s),
  open-since timestamp, and trigger reason without consulting
  application logs.
- **SC-005**: With all four env vars unset, the full pre-feature
  acceptance suite passes unmodified (regression contract — no
  observable behavior change).
- **SC-006**: With any env var set to an invalid value, the
  orchestrator process exits at startup with a clear error
  message naming the offending var (V16 fail-closed gate observed
  in CI).
- **SC-007**: Two participants sharing the same provider but with
  different API keys exhibit fully independent circuit state — a
  contract test injects failures for one and verifies zero
  state-machine transitions on the other.
- **SC-008**: No transparent provider fallback ever occurs — a
  contract test configures a LiteLLM cross-identity fallback list
  and verifies the orchestrator refuses to start (FR-011
  startup-check).

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** (orchestrator-driven
topologies enumerated in `docs/sacp-communication-topologies.md`):

- Topology 1: Solo Operator + Multiple AIs
- Topology 2: Multiple Humans + One Shared AI
- Topology 3: Multiple Humans + Multiple AIs
- Topology 4: Asymmetric Participation
- Topology 5: Fully Autonomous
- Topology 6: Single Human + Single AI

This feature is **incompatible with topology 7 (MCP-to-MCP, Phase
3+)**. Topology 7 removes the orchestrator from the dispatch path —
provider calls happen client-side in participants' desktop clients,
so SACP has no observation point at which to track failures or
short-circuit dispatch. Per V12's "silent assumption = incomplete"
rule: any future topology-7 deployment MUST disable this mechanism
or substitute a topology-7-native equivalent (likely client-side
breaker logic with a separate spec).

### V13 — Use Case Coverage

This feature serves all four use cases from `docs/sacp-use-cases.md`
because every multi-participant session is exposed to provider
failures regardless of intent:

- **Use Case §1 — Distributed Software Collaboration**: Long-running
  sessions are most exposed to transient provider outages over
  multi-hour windows.
- **Use Case §2 — Research Paper Co-authorship**: Asynchronous
  multi-AI debate compounds wasted-token cost when one provider
  fails repeatedly while the participant is offline to notice.
- **Use Case §3 — Consulting Engagement**: Token-spend protection is
  most visible to the consultant whose budget is at risk.
- **Use Case §4 — Open Source Project Coordination**: Multiple
  contributor identities sharing the same provider rely on
  per-participant isolation to prevent one contributor's outage
  from suppressing others.

No use case is the priority driver — this is foundational
reliability, not use-case-specific.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts. This
spec contributes three budgets:

- **Breaker state lookup per dispatch**: Constant-time (`O(1)`).
  The dispatch path MUST consult breaker state via a hash lookup
  keyed on the FR-001 tuple. Budget enforcement: routing log MUST
  NOT show a per-turn breaker-resolution stage exceeding O(1)
  cost.
- **Failure recording**: `O(1)` amortized per failure (ring-buffer
  append + window trim). Budget enforcement: per-failure recording
  duration captured in the routing log.
- **Recovery probe latency**: Probes are out-of-band from the turn
  loop and MUST NOT block dispatch for any other participant.
  Budget enforcement: probe-call duration captured in
  `provider_circuit_probe` audit entries (per FR-012); probes
  taking longer than the configured probe timeout
  (`SACP_PROVIDER_PROBE_TIMEOUT_S`) count as failed probes and
  preserve the schedule.

## Configuration (V16) — New Env Vars

Four new `SACP_*` env vars are introduced. Each MUST have type,
valid range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this spec
(per V16 deliverable gate).

### `SACP_PROVIDER_FAILURE_THRESHOLD`

- **Intended type**: positive integer
- **Intended valid range**: `2 <= value <= 100` (1 would trip on
  any single failure, defeating the rolling-window intent; 100 is
  beyond credible per-window failure counts).
- **Fail-closed semantics**: unset means breaker is inactive
  (current pre-feature behavior). Out-of-range values MUST cause
  startup exit per V16.

### `SACP_PROVIDER_FAILURE_WINDOW_S`

- **Intended type**: positive integer, seconds
- **Intended valid range**: `30 <= value <= 3600` (30 seconds to
  1 hour).
- **Fail-closed semantics**: unset means breaker is inactive
  (paired with threshold; both must be set or both unset).
  Out-of-range values MUST cause startup exit per V16.

### `SACP_PROVIDER_RECOVERY_PROBE_BACKOFF`

- **Intended type**: composite — comma-separated list of seconds
  (e.g., `5,10,30,60`). Final format decided in `/speckit.plan`.
- **Intended valid range**: each entry must be in `[1, 600]`; at
  least one entry; maximum 10 entries.
- **Fail-closed semantics**: unset means no auto-recovery (breaker
  remains open until session restart or `update_api_key`).
  Unparseable or out-of-range entries MUST cause startup exit.

### `SACP_PROVIDER_PROBE_TIMEOUT_S`

- **Intended type**: positive integer, seconds
- **Intended valid range**: `1 <= value <= 30`.
- **Fail-closed semantics**: unset means probe inherits the
  configured LiteLLM call timeout. Out-of-range values MUST cause
  startup exit per V16.

## Cross-References to Existing Specs and Design Docs

- **`sacp-design.md` §6.6 (Error Handling and Resilience)** —
  defines the existing three-layer defense (prevention / detection /
  fallback), the §6.6 quality-failure detection rules reused as
  failure inputs (FR-003), and the LiteLLM ordered-fallback feature
  that this spec scopes (FR-011).
- **`sacp-design.md` §7 (Security)** — §7.1 API key lifecycle (the
  `update_api_key` fast-close path in FR-016) and the
  participant-data-isolation requirement that motivates
  per-participant circuit state.
- **Constitution §3 (Sovereignty)** — V1 sovereignty guarantees
  (API key isolation, model choice independence, budget autonomy,
  prompt privacy, exit freedom) bind FR-010 (per-participant
  isolation) and FR-011 (no transparent fallback).
- **Spec 003 (turn-loop-engine) §FR-030** — `routing_log` per-stage
  timing capture; this spec's per-turn breaker-state lookup and
  skipped-turn records hook into that channel (FR-017, V14
  budgets).
- **Spec 004 (convergence-cadence)** — convergence similarity
  inputs MUST exclude skipped turns from open breakers (FR-017).
- **Spec 007 (ai-security-pipeline) §FR-020** — `security_events`
  per-layer duration logging; circuit events flow through
  `admin_audit_log` (not `security_events`) because they are
  reliability events, not security decisions.

## Assumptions

- LiteLLM remains the bridge layer for provider dispatch in the
  scope of this spec. If a future spec replaces LiteLLM, the
  breaker abstraction defined here MUST port to the replacement
  without surfacing changes to operators.
- The metrics surface referenced in FR-013 is the existing
  operator-visible metrics endpoint; the exact field naming
  convention is settled in `/speckit.plan`. If no current metrics
  surface meets FR-013's requirements, `/speckit.plan` will scope
  the minimal surface needed.
- Three dedicated append-only audit tables ship with this spec:
  `provider_circuit_open_log`, `provider_circuit_probe_log`, and
  `provider_circuit_close_log`. These are added via one alembic
  migration (revision 022) and their DDL is mirrored in
  `tests/conftest.py` per `feedback_test_schema_mirror`. This
  supersedes the initial draft assumption that `admin_audit_log`
  would accept the four new action types without schema changes;
  the plan.md Technical Context and tasks.md are authoritative for
  the final storage shape.
- "Phase 1 scope" in the user description is interpreted as
  back-fill into the Phase 1 reliability story (LiteLLM cooldown is
  cited in §6.6 but its state is not currently surfaced through
  SACP's audit log or metrics). Confirmation of this framing is
  pending per Clarifications §"Phase labeling".
- The session-local circuit-state model (no cross-session
  persistence) is assumed sufficient for v1; per-participant
  multi-session breaker memory (e.g., "this provider has been bad
  for this participant across the last 3 sessions") is a
  potential follow-up, out of scope here.
