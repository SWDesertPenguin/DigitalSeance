# Feature Specification: High-Traffic Session Mode (Broadcast Mode)

**Feature Branch**: `013-high-traffic-mode`
**Created**: 2026-05-02
**Status**: Draft (Phase 3 declared 2026-05-05; tasks + implementation in progress per Constitution §14.1)
**Input**: User description: "Phase 3 high-traffic session mode (broadcast mode) — concretizes Constitution §10 broadcast-mode capability via three orthogonal mechanisms: human-boundary batching cadence, convergence-threshold override, and observer-downgrade. Applies to topologies 1–6 (orchestrator-driven); incompatible with topology 7 per V12. Primary use cases: consulting and research co-authorship per V13."

## Overview

Constitution §10 names "broadcast mode" as a Phase 3 deliverable in the
"Relevance-based routing, broadcast mode" line. Phase 1 and Phase 2
operate the orchestrator in a strict serialized turn loop tuned for
2-participant sessions; once Phase 3 expands to 3-5 participants, the
serialized model degrades quickly when a session crosses a high-traffic
threshold. Two failure modes appear:

1. Human participants in `review_gate` mode (consulting use case)
   become saturated by per-turn approval gates, blocking the session.
2. Asynchronous human participants (research co-authorship use case)
   return to a flood of accumulated turns, with no way to compress
   the catch-up cost.

This spec defines high-traffic session mode as **three orthogonal
mechanisms** the orchestrator engages when configured thresholds are
crossed:

1. **Human-boundary batching cadence** — coalesce AI-to-human messages
   into batched deliveries on a fixed cadence rather than streaming
   every turn.
2. **Convergence-threshold override** — accept a per-session override
   of the convergence threshold (spec 004) so a high-traffic session
   can converge earlier (or be allowed to converge later) than the
   global default without redeploying.
3. **Observer-downgrade mechanism** — when participant count or turn
   rate exceeds configured thresholds, transparently downgrade an
   active participant to observer for the remainder of the
   high-traffic window, restoring active status when traffic subsides.

The three mechanisms are orthogonal: each is independently testable,
each can be enabled or disabled by its own env var, and each delivers
value on its own without the others. They compose when more than one
threshold is crossed simultaneously.

This spec **scaffolds only**. Implementation begins when the
facilitator declares Phase 3 started per Constitution §10. The spec
remains at Status: Draft until that declaration. **Phase 3 declaration
recorded 2026-05-05; this gate is satisfied. The spec stays Draft
until tasks land and implementation reaches the Implemented status
checkpoint.**

## Clarifications

### Session 2026-05-05 (Phase 3 framework / scaffolding landings)

- Phase 1 + Phase 2 (T001–T015) shipped: three SACP_HIGH_TRAFFIC_*/
  SACP_CONVERGENCE_THRESHOLD_OVERRIDE/SACP_OBSERVER_DOWNGRADE_THRESHOLDS
  env vars with V16 validators in `src/config/validators.py`; `docs/env-vars.md`
  sections with the six standard fields per FR-014 deliverable gate;
  `HighTrafficSessionConfig` + `ObserverDowngradeThresholds` frozen
  dataclasses in `src/orchestrator/high_traffic.py` with
  `resolve_from_env()` returning `None` when all three env vars unset
  (SC-005 regression contract); SC-005 regression scaffold in
  `tests/test_013_regression_phase2.py` (8 tests).
- Phase 3 US1 framework (T016–T025) shipped: `BatchEnvelope` dataclass
  + `BatchScheduler` per-session flush task in
  `src/web_ui/batch_scheduler.py`; `batch_envelope_event` builder in
  `src/web_ui/events.py`; `docs/ws-events.md` adds the new event spec;
  `_maybe_make_batch_scheduler` returns `None` when batching env unset.
  5 acceptance tests in `tests/test_013_batching.py`. T026 (routing_log
  `batch_open_ts`/`batch_close_ts` instrumentation) and BatchScheduler
  integration into the actual orchestrator dispatch path are deferred
  to Phase 6 polish.
- Phase 4 US2 framework (T027–T031) shipped: `_convergence_threshold_kwarg`
  in `src/orchestrator/loop.py` passes the override into `ConvergenceDetector`
  via the existing `threshold=` constructor parameter (no engine refactor
  per research §5). 4 tests in `tests/test_013_convergence_override.py`.
- Phase 5 US3 framework (T032–T043) shipped: `evaluate_downgrade` +
  `evaluate_restore` in `src/orchestrator/observer_downgrade.py`; priority
  heuristic per research §3 (model_tier rank > consecutive_timeouts desc
  > last_seen desc > id asc); last-human protection emits `Suppressed`
  per FR-011; audit-row payload helpers for the three new
  `admin_audit_log` action strings (no schema change per research §1).
  13 tests in `tests/test_013_observer_downgrade.py`. T044 (audit-row
  writers wired into loop turn-prep) and T045 (routing_log
  `observer_downgrade_eval_ms`) are deferred to Phase 6 polish.
- Phase 6 polish status: T046 (full SC-005 assertions) + T047 (013
  traceability section) + T048 (this Clarifications entry) shipped;
  T049 quickstart walkthrough requires a live deployment and is
  operator-side; T051 status flip Draft → Implemented gated on the
  remaining loop-integration work AND the user's declaration per
  Constitution §14 / `feedback_dont_declare_phase_done.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Human-boundary batching cadence keeps a `review_gate` consultant productive (Priority: P1)

A consultant runs a session in `review_gate` mode (consulting use
case, `docs/sacp-use-cases.md` §3) where every AI response drafted
on their side stages for human approval. When AI participants enter
a high-frequency exchange (e.g., debating a methodology question in
short turns), the consultant's approval queue grows faster than they
can process it, blocking the session.

**Why this priority**: Without batching, the consulting use case is
the first to break under high traffic — the human is *required*
to approve drafts, so the orchestrator stalls the moment they fall
behind. Batching converts a stall-on-slow-human failure mode into a
graceful "delivered together every N seconds" experience.

**Independent Test**: Launch a 3-participant session (one human in
`review_gate`, two AI). Drive AI exchanges at a rate above the
configured threshold. Verify that AI-to-human messages arrive in
batched envelopes on the configured cadence rather than per-turn,
and that no message is held longer than `cadence + 5s`.

**Acceptance Scenarios**:

1. **Given** a session with `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S=15`
   and a human participant in `review_gate` mode, **When** AI
   participants generate 4 turns in 10 seconds, **Then** the human
   receives one batched delivery containing all 4 turns within 20
   seconds (cadence + 5s scheduling slack) of the first turn's
   completion.
2. **Given** the same configuration, **When** AI participants
   generate only 1 turn in a 60-second window, **Then** the human
   still receives that turn within `cadence + 5s` of its completion
   (batching never delays a lone message past the cadence budget).
3. **Given** `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S` is unset or
   invalid at startup, **When** the orchestrator initializes,
   **Then** the orchestrator falls back to per-turn delivery
   (fail-closed = preserve current Phase 2 behavior, never delay).

---

### User Story 2 - Per-session convergence-threshold override prevents premature or delayed convergence (Priority: P2)

A research co-authorship session (`docs/sacp-use-cases.md` §2)
launches with multiple AI participants debating methodology. The
session's global `SACP_CONVERGENCE_THRESHOLD` was tuned for typical
2-participant sessions; in this 4-participant high-traffic window
the engine declares premature convergence well before consensus is
real. The facilitator needs to nudge the threshold for *this session
only* without redeploying the orchestrator.

**Why this priority**: This is a configuration-ergonomics fix layered
on the existing convergence engine (spec 004). The engine works; only
its tunability per-session is missing. P2 because the session can
still complete without it (operator can manually intervene), but the
operator burden is significant in multi-AI sessions.

**Independent Test**: Launch a session with the global convergence
threshold set to a baseline and a per-session override set higher.
Drive the AI participants to a state that would trip the global
threshold but not the override. Verify the session does not
prematurely declare convergence and continues until the override is
crossed.

**Acceptance Scenarios**:

1. **Given** global `SACP_CONVERGENCE_THRESHOLD=0.70` and per-session
   `SACP_CONVERGENCE_THRESHOLD_OVERRIDE=0.85` for session S, **When**
   session S reaches similarity 0.75, **Then** the engine does NOT
   declare convergence and the session continues.
2. **Given** the same configuration, **When** session S reaches
   similarity 0.86, **Then** the engine declares convergence using
   the override threshold and proceeds to summarization.
3. **Given** `SACP_CONVERGENCE_THRESHOLD_OVERRIDE` is set to a value
   outside `(0.0, 1.0)`, **When** the orchestrator initializes,
   **Then** the orchestrator exits at startup with a clear error
   (per V16 fail-closed semantics — invalid value MUST NOT silently
   degrade to the global default).
4. **Given** the override is unset, **When** any session loads,
   **Then** the engine reads the global `SACP_CONVERGENCE_THRESHOLD`
   exactly as today (no behavior change for sessions that don't
   opt in).

---

### User Story 3 - Observer-downgrade prevents traffic collapse when participant count or turn rate spikes (Priority: P3)

A session expands mid-flight from 3 to 5 active participants (Phase 3
permits 3-5). The combined turn rate crosses the configured
participant-count and turns-per-minute thresholds. To prevent the
session from collapsing under context-window pressure, the
orchestrator transparently downgrades the lowest-priority active
participant to observer status for the remainder of the high-traffic
window. When traffic subsides below the thresholds, the participant
is restored to active status.

**Why this priority**: P3 because the failure mode is graceful
degradation rather than a hard block — the session continues to
function with reduced active participant count even without this
mechanism (just at higher cost and lower quality). It's the most
behaviorally complex of the three mechanisms and benefits from
the other two landing first to inform threshold tuning.

**Independent Test**: Launch a 5-participant session with downgrade
thresholds set to trip at the 4-participant + high-turn-rate mark.
Drive turn rate above the threshold. Verify that exactly one
participant transitions to observer (visible in routing log + audit
event), that the downgrade is transparent to other participants
(no error, no session restart), and that the participant returns to
active status when turn rate drops below the threshold for a
sustained window.

**Acceptance Scenarios**:

1. **Given** `SACP_OBSERVER_DOWNGRADE_THRESHOLDS=participants:4,tpm:30`
   and a 5-participant session running at 35 turns/minute, **When**
   the orchestrator evaluates downgrade at turn-prep, **Then** the
   lowest-priority active participant is downgraded to observer and
   an `observer_downgrade` audit event is emitted.
2. **Given** the same configuration after a downgrade, **When** turn
   rate drops below 25 turns/minute for a sustained window (per
   threshold spec), **Then** the downgraded participant is restored
   to active status and an `observer_restore` audit event is emitted.
3. **Given** `SACP_OBSERVER_DOWNGRADE_THRESHOLDS` is unset or
   invalid, **When** any session runs, **Then** no downgrades occur
   (fail-closed = no role change, preserve current Phase 2 behavior).
4. **Given** a downgrade threshold matches but evaluation cost would
   exceed the turn-prep budget, **When** the orchestrator measures
   per-turn evaluation cost, **Then** the metric is captured into
   `routing_log` per spec 003 §FR-030 so regressions are
   diagnosable per-stage.

---

### Edge Cases

- What happens when batching cadence and a per-turn convergence
  declaration coincide? Convergence message bypasses the batch
  envelope and delivers immediately (convergence is a session-state
  change, not a participant message).
- What happens when an observer is mid-downgrade and the session
  reaches convergence? The downgrade is finalized first so the
  audit log preserves cause-and-effect, then convergence proceeds
  with the post-downgrade participant set.
- What happens when a participant being downgraded is the *only*
  human in the session? The downgrade is suppressed and an
  `observer_downgrade_suppressed` audit event is emitted (humans
  cannot be silently demoted out of the loop; consulting use case
  requires human-in-the-loop). The orchestrator continues without
  downgrading anyone for that evaluation cycle.
- What happens if the batching cadence is set lower than the
  shortest realistic AI turn time? Behavior is identical to per-turn
  delivery (each batch contains exactly one message). No error.
- What happens when convergence override conflicts with the global
  threshold direction (e.g., override < global, meaning override
  converges *earlier*)? Allowed — the override is authoritative for
  the session. Operator's explicit choice.
- What happens at session restart after a downgrade window? The
  observer-downgrade state is session-local and not persisted across
  restart; on restart the participant returns to their original
  active role, and downgrade thresholds re-evaluate from scratch.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Orchestrator MUST coalesce AI-to-human messages into
  batched deliveries when `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S` is set
  to a positive integer and the session has at least one human
  participant.
- **FR-002**: Each batched delivery MUST include all AI messages
  produced since the previous delivery, in original turn order.
- **FR-003**: No message MUST be held in a batch envelope longer
  than `cadence + 5s` (the V14 P95 latency budget). The 5s slack
  accommodates scheduler tick alignment.
- **FR-004**: Convergence/state-change messages MUST bypass batching
  and deliver immediately (out-of-band from the batch envelope).
- **FR-005**: Convergence engine (spec 004) MUST accept a per-session
  override `SACP_CONVERGENCE_THRESHOLD_OVERRIDE` and prefer the
  override over the global `SACP_CONVERGENCE_THRESHOLD` when set.
- **FR-006**: The override MUST be cached at session-start and read
  in constant time per turn (no per-turn env-var lookup).
- **FR-007**: The override value MUST be validated at startup (V16
  fail-closed) — values outside `(0.0, 1.0)` MUST cause the
  orchestrator process to exit with a clear error before binding any
  port or accepting connections.
- **FR-008**: Orchestrator MUST evaluate observer-downgrade
  thresholds at each turn-prep boundary when
  `SACP_OBSERVER_DOWNGRADE_THRESHOLDS` is set.
- **FR-009**: When thresholds are crossed, the lowest-priority
  active participant MUST be downgraded to observer and an
  `observer_downgrade` audit event emitted with reason metadata
  (which threshold tripped, current values vs configured values).
- **FR-010**: When thresholds drop below the configured floor for a
  sustained window (per threshold spec), the most-recently-downgraded
  participant MUST be restored to active status and an
  `observer_restore` audit event emitted.
- **FR-011**: A human participant MUST NOT be silently downgraded.
  If the lowest-priority active participant is the only human in the
  session, the downgrade MUST be suppressed and an
  `observer_downgrade_suppressed` audit event emitted instead.
- **FR-012**: Per-turn observer-downgrade evaluation cost MUST be
  captured in `routing_log` per spec 003 §FR-030 so regressions
  surface per-stage.
- **FR-013**: All three mechanisms MUST be independently
  enable/disable-able via their respective env vars (each
  fail-closes to its current Phase 2 behavior when unset or
  invalid).
- **FR-014**: All three new `SACP_*` env vars MUST have validator
  functions in `src/config/validators.py` registered in the
  `VALIDATORS` tuple, and corresponding sections in
  `docs/env-vars.md` with the six standard fields (Default, Type,
  Valid range, Blast radius, Validation rule, Source spec) BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable gate).
- **FR-015**: This spec's mechanisms MUST NOT alter the dispatch
  path semantics in topologies 1–6 when the relevant env var is
  unset (additive feature, no implicit defaults).

### Key Entities

- **HighTrafficSessionConfig** (per-session) — captures the override
  values resolved at session-start: cadence, convergence-threshold
  override (if set), observer-downgrade thresholds (if set). Cached
  for the session lifetime; referenced in constant time per turn.
- **BatchEnvelope** — wraps one or more AI messages destined for a
  single human recipient on a single delivery cycle. Carries the
  source turn IDs, the batch's open-time timestamp, and the
  scheduled close-time timestamp.
- **ObserverDowngradeRecord** (audit) — captures
  `(session_id, participant_id, downgrade_at, restore_at_or_null,
  trigger_threshold, trigger_value)` for each downgrade event.
- **DowngradeSuppressedRecord** (audit) — captures suppressed
  downgrades (e.g., last human protection) with the same shape minus
  `restore_at`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a 3+ participant session with one human in
  `review_gate` mode and AI exchange rate above the configured
  threshold, the human's perceived approval-queue depth stays below
  one batch worth of messages 95% of the time (no runaway queue
  growth).
- **SC-002**: P95 batched-message latency from AI turn completion to
  human delivery stays at or below `configured cadence + 5s`
  scheduling slack across a sustained 30-minute high-traffic window.
- **SC-003**: Convergence-threshold override read latency is
  indistinguishable from a constant-time field access (no per-turn
  env-var or filesystem lookup observable in the routing log).
- **SC-004**: Observer-downgrade evaluation per turn completes in
  cost proportional to participant count (O(participants)) and stays
  inside the existing turn-prep latency budget at participant counts
  up to the Phase 3 ceiling of 5.
- **SC-005**: Sessions with all three high-traffic env vars unset
  exhibit no observable behavior change versus the prior Phase 2
  release (regression test: full Phase 2 acceptance scenarios pass
  unmodified).
- **SC-006**: When any high-traffic env var is set to an invalid
  value, the orchestrator process exits at startup with a clear
  error message naming the offending var (V16 fail-closed gate
  observed in CI).
- **SC-007**: An operator can enable batching for a single session
  by setting one env var, restart the orchestrator, and observe
  batched delivery in under 5 minutes of operator effort end-to-end.

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** (the orchestrator-driven
topologies enumerated in
`docs/sacp-communication-topologies.md`):

- Topology 1: Solo Operator + Multiple AIs
- Topology 2: Multiple Humans + One Shared AI
- Topology 3: Multiple Humans + Multiple AIs (canonical Phase 3 case)
- Topology 4: Asymmetric Participation
- Topology 5: Fully Autonomous (note: batching mechanism is a no-op
  here because there are no humans on the receiving boundary)
- Topology 6: Single Human + Single AI (note: high-traffic
  thresholds will rarely trip in 1+1 sessions; mechanisms are
  available but unlikely to engage)

This feature is **incompatible with topology 7 (MCP-to-MCP, Phase
3+)**. Topology 7 removes the orchestrator from the dispatch path —
sessions operate via shared state and message brokering with no
central authority that can:

- Coalesce messages into batch envelopes (no central queue holding
  outbound messages).
- Cache and serve a per-session convergence override (no central
  engine reading the override).
- Decide and audit observer-downgrade transitions (no central
  authority over participant role state).

Per V12's "silent assumption = incomplete" rule: any future topology-7
deployment MUST explicitly disable all three high-traffic mechanisms
or substitute topology-7-native equivalents (likely a separate spec).

### V13 — Use Case Coverage

This feature primarily serves two use cases from
`docs/sacp-use-cases.md`:

- **Use Case §3 — Consulting Engagement**: Consultants in
  `review_gate` mode are the canonical victim of the per-turn
  approval-queue saturation failure mode. User Story 1 (batching
  cadence) is the direct remedy.
- **Use Case §2 — Research Paper Co-authorship**: Asynchronous
  multi-AI debate over methodology produces high-volume catch-up
  cost for time-zone-distributed researchers. User Stories 2
  (convergence override) and 3 (observer downgrade) directly serve
  this case.

Secondary applicability: Use Cases §1 (Distributed Software
Collaboration) and §4 (Open Source Project Coordination) benefit
indirectly from any high-traffic mode mechanism but are not the
priority cases driving the design.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts, with
per-stage timings captured into structured logs so regressions are
diagnosable per-stage rather than aggregate-only. This spec contributes
three budgets:

- **Human-boundary batching latency**: P95 message hold time MUST be
  at or below `configured cadence + 5s` scheduling slack. The 5s
  represents the maximum acceptable scheduler tick alignment delay
  on top of the configured cadence. Budget enforcement: per-batch
  open-time and close-time captured in `routing_log` (spec 003
  §FR-030).
- **Convergence-threshold override read**: Constant-time
  (`O(1)`). The override is resolved once at session-start and
  cached on the session config object; per-turn reads MUST be field
  accesses, not env-var or filesystem lookups. Budget enforcement:
  routing_log MUST NOT show a per-turn override-resolution stage.
- **Observer-downgrade evaluation**: Per-turn evaluation cost MUST
  be `O(participants)` and MUST stay inside the existing turn-prep
  budget at participant counts up to the Phase 3 ceiling of 5.
  Budget enforcement: per-turn downgrade-evaluation duration captured
  in `routing_log` per spec 003 §FR-030, with a regression alert
  when the stage exceeds its budget.

Cross-ref: Per V14, the validation rule is binding for all future
specs; instrumentation is implemented as part of the spec's
Phase 0–2 design phases (`/speckit.plan` work).

## Configuration (V16) — New Env Vars

Three new `SACP_*` env vars are introduced. Each MUST have type,
valid range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this spec
(per V16 deliverable gate).

### `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S`

- **Intended type**: positive integer, seconds
- **Intended valid range**: `1 <= value <= 300` (1 second to 5 minutes)
- **Fail-closed semantics**: unset, empty, or out-of-range value
  causes the orchestrator to fall back to per-turn delivery (current
  Phase 2 behavior). Out-of-range values MUST cause startup exit
  per V16, not silent fallback.
- **Documentation**: needs full `docs/env-vars.md` entry before
  `/speckit.tasks`.

### `SACP_CONVERGENCE_THRESHOLD_OVERRIDE`

- **Intended type**: float
- **Intended valid range**: `0.0 < value < 1.0` (strict bounds; 0.0
  means "always converging" and 1.0 means "never converging" — both
  are operator-error states already noted in spec 004 line 111)
- **Fail-closed semantics**: unset means use global
  `SACP_CONVERGENCE_THRESHOLD`. Set-but-out-of-range MUST cause
  startup exit (V16 — invalid value MUST NOT silently degrade to
  the global default).
- **Precedence**: When high-traffic mode is inactive, the global
  `SACP_CONVERGENCE_THRESHOLD` from spec 004 applies. When active,
  `SACP_CONVERGENCE_THRESHOLD_OVERRIDE` supersedes.
- **Documentation**: needs full `docs/env-vars.md` entry. Spec 013
  does NOT activate the reserved `SACP_CONVERGENCE_THRESHOLD` slot
  at `docs/env-vars.md:163`; that slot stays reserved and is
  referenced here only as the not-yet-bound default.

### `SACP_OBSERVER_DOWNGRADE_THRESHOLDS`

- **Intended type**: composite — likely a comma-separated key:value
  string parsed at startup (e.g., `participants:4,tpm:30`). Final
  format decided in `/speckit.plan`.
- **Intended valid range**: each key has its own range — `participants`
  must be an integer in `[2, 10]` (below 2 is meaningless; above
  10 is beyond Phase 3 scope); `tpm` (turns per minute) must be a
  positive integer in `[1, 600]`.
- **Fail-closed semantics**: unset or unparseable MUST cause no
  downgrades to occur (preserve current Phase 2 behavior). Set-but-
  out-of-range for any key MUST cause startup exit per V16.
- **Documentation**: needs full `docs/env-vars.md` entry. Composite
  format decision documented in `/speckit.plan` research.md.

## Cross-References to Existing Specs

- **Spec 003 (turn-loop-engine)** line 295 explicitly defers
  "Relevance-based and broadcast rotation modes" to Phase 3. This
  spec is part of that deferred delivery.
- **Spec 003 (turn-loop-engine)** §FR-030 defines `routing_log`
  per-stage timing capture; this spec's per-turn observer-downgrade
  evaluation and per-batch open/close-time logging hook into that
  same channel.
- **Spec 004 (convergence-cadence)** line 111 anticipated Phase 3
  bounds-checking at construction for convergence threshold
  configuration. This spec delivers per-session bounds-checked
  override.
- **Spec 007 (ai-security-pipeline)** §FR-020 defines `security_events`
  per-layer duration logging; observer-downgrade events flow through
  the audit pipeline rather than security_events because they are
  participant-state changes, not security decisions.

## Assumptions

- The Phase 3 participant ceiling stays at 5 per Constitution §10.
  Threshold default ranges (e.g., participant downgrade trigger at
  4) assume this ceiling.
- The convergence engine in spec 004 already exposes a session-level
  configuration injection point. If it does not, `/speckit.plan`
  will identify the minimal refactor needed and may amend spec 004.
- Audit event taxonomy already supports adding `observer_downgrade`,
  `observer_restore`, and `observer_downgrade_suppressed` event
  types without schema changes. If schema changes are needed, they
  will be scoped during `/speckit.plan`.
- "Lowest-priority active participant" is determined by an existing
  participant priority field. If no such field exists,
  `/speckit.plan` will identify the minimal data-model change
  needed.
- The 5s scheduling slack on top of the batch cadence is an
  initial budget; it may be tuned during instrumentation rollout in
  `/speckit.plan`. Any tightening of the slack must keep the budget
  observable in `routing_log`.
- Status remains Draft until the facilitator declares Phase 3
  started per Constitution §10. No implementation work proceeds
  before that declaration.
