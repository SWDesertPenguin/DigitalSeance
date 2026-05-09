# Feature Specification: Dynamic Mode Assignment (Signal-Driven Controller for High-Traffic Mode)

**Feature Branch**: `014-dynamic-mode-assignment`
**Created**: 2026-05-02
**Status**: Implemented 2026-05-08 (Phase 3 declared 2026-05-05; secondary gate satisfied 2026-05-07; controller + signal sources + audit events landed via PR #326; queue-depth bug fix #328; density-anomaly observer + last_known_state audit cosmetic #330)
**Input**: User description: "Phase 3 dynamic mode assignment — the controller layer above spec 013 high-traffic mode. Watches a rolling 5-minute window of session signals (turn rate, convergence-derivative, queue depth, density-anomaly rate) and decides when to engage or disengage high-traffic mode mechanisms. Decisions are rate-capped (decisions-per-minute) and hysteresis-bounded (dwell time) to prevent flap. Defaults to advisory mode in initial Phase 3 deployment; auto-apply behind feature flag SACP_AUTO_MODE_ENABLED off by default. Applies to topologies 1–6 (orchestrator-driven); incompatible with topology 7 per V12. Primary use cases: consulting, research co-authorship, and technical review/audit per V13."

## Overview

Spec 013 (high-traffic-mode) introduced three orthogonal mechanisms —
human-boundary batching cadence, convergence-threshold override, and
observer-downgrade — that engage when their respective configured
thresholds are crossed. Each mechanism evaluates its own threshold at
its own evaluation point (per-turn for downgrade and convergence, per
batch tick for batching). That design is **static**: an operator
picks a single set of thresholds at startup and the mechanism either
is or is not engaged for the lifetime of the session.

Static thresholds work poorly in real Phase 3 sessions because traffic
shape changes mid-session:

1. A 4-participant research session begins in low-traffic methodology
   debate, jumps to high-traffic when a contentious finding surfaces,
   then settles back into slow synthesis. A static threshold either
   engages high-traffic mode for the whole session (over-engaged in
   the slow phases, hurting fidelity) or never engages (under-engaged
   during the spike, blocking the human in `review_gate`).
2. A consulting session in `review_gate` runs nominally serialized
   until two AIs latch into a tight back-and-forth. The static
   batching cadence either makes every message late (cadence too
   long for the slow phase) or fails to coalesce the burst (cadence
   too short for the spike).
3. A technical-review session shifts attention areas every ~30
   minutes (auth subsystem → data layer → frontend). Each shift
   produces a transient density anomaly that the static observer-
   downgrade threshold either ignores (missing the spike) or
   over-reacts to (downgrading a participant who would have been
   relevant to the next attention area five minutes later).

This spec defines **dynamic mode assignment** as the controller layer
that sits above spec 013's mechanisms. The controller:

- **Observes** a rolling 5-minute window of four session signals:
  turn rate (turns/minute), convergence derivative (rate of change
  of similarity score from spec 004), human-side queue depth (per
  spec 013 batching), and density anomaly rate (mid-session
  attention-area shifts).
- **Decides** at a rate-capped cadence (decisions-per-minute cap)
  whether the session should be in high-traffic mode or normal
  mode. The cap bounds the controller's own CPU cost so it cannot
  itself become a hot-path regression.
- **Applies** the decision either as an advisory recommendation
  (default) or as an automatic mode flip (gated by
  `SACP_AUTO_MODE_ENABLED`), in both cases enforcing a hysteresis
  dwell time to prevent flap-driven cost.

This spec **scaffolds only**. Implementation begins when the
facilitator declares Phase 3 started per Constitution §10, AND only
after spec 013 (high-traffic-mode) reaches Status: Implemented.
This spec remains at Status: Draft until both gates are satisfied.
**Phase 3 declaration recorded 2026-05-05; the first gate is satisfied.
The secondary gate was satisfied 2026-05-07 when spec 013 reached
Status: Implemented (Phase 3 declaration: 2026-05-05; tasks landed:
2026-05-07; FR-011 broadening amendment: 2026-05-07). Both gates are
now green; this spec is ready for `/speckit.implement` on facilitator
invocation.**

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Advisory recommendations surface to facilitator in real session (Priority: P1)

A facilitator runs a Phase 3 multi-AI session. The dynamic mode
assignment controller is deployed in **advisory mode** (the initial
Phase 3 default). As session signals evolve, the controller writes
recommendations into the audit log and an operator-visible recommendation
channel: "Recommend ENGAGE high-traffic mode (turn rate 42 tpm
exceeds threshold 30 over last 5m window)" and, later, "Recommend
DISENGAGE (turn rate dropped to 12 tpm sustained over dwell window)".
The facilitator sees the recommendation, judges whether to act on it,
and manually toggles the relevant `SACP_*` env vars from spec 013 if
they choose to. The session continues; the controller never flips
anything itself.

**Why this priority**: This is the safe, default operating mode for
initial Phase 3 deployment. Auto-apply is the harder behavior to
validate — getting advisory recommendations correct first lets the
facilitator build trust in the controller's judgment before delegating
authority to it. Without P1, the entire feature lacks a non-risky
introduction path.

**Independent Test**: Launch a 4-participant session with the
controller enabled in advisory mode and `SACP_AUTO_MODE_ENABLED`
unset. Drive turn rate above the configured threshold for at least
the 5-minute window. Verify a `mode_recommendation` audit event is
emitted with `action=ENGAGE`, the offending signal name, the
observed value, the configured threshold, and the dwell-time floor
that would govern auto-apply if it were enabled. Verify no
high-traffic mode env var has been altered and no spec-013 mechanism
has engaged.

**Acceptance Scenarios**:

1. **Given** a session with `SACP_DMA_TURN_RATE_THRESHOLD_TPM=30`,
   `SACP_DMA_DWELL_TIME_S=120`, and `SACP_AUTO_MODE_ENABLED` unset,
   **When** AI participants sustain 42 turns/minute for the full
   5-minute observation window, **Then** exactly one
   `mode_recommendation` audit event is emitted with
   `action=ENGAGE`, `trigger=turn_rate`, observed value, threshold,
   and dwell-time fields populated, and the spec-013 mechanisms
   remain in their pre-recommendation state.
2. **Given** the same configuration after an ENGAGE recommendation
   was emitted, **When** turn rate drops to 12 tpm and stays below
   the threshold for the full dwell window, **Then** exactly one
   `mode_recommendation` event with `action=DISENGAGE` is emitted.
3. **Given** the controller is unconfigured (no
   `SACP_DMA_*` thresholds set), **When** the orchestrator
   initializes, **Then** the controller is inactive (no
   recommendations emitted, no audit channel created) — fail-closed
   to current Phase 2 / spec-013-only behavior.

---

### User Story 2 - Auto-apply (behind feature flag) flips high-traffic mode without operator intervention (Priority: P2)

After the facilitator has observed advisory recommendations across
several sessions and is confident in the controller's judgment, they
set `SACP_AUTO_MODE_ENABLED=true` for a single staging deployment.
On the next session that crosses signal thresholds, the controller
not only emits the `mode_recommendation` event but also toggles the
spec-013 mechanisms (batching, convergence override, observer
downgrade) for the session, governed by the dwell-time hysteresis.

**Why this priority**: Auto-apply is the long-term operating mode
for Phase 3 — facilitators cannot babysit every session — but P2
because it depends on P1 having validated the controller's signal
interpretation. Auto-apply without prior advisory observation is a
recipe for surprising operator interventions and lost trust.

**Independent Test**: Launch a session with `SACP_AUTO_MODE_ENABLED=true`
and the same threshold/dwell configuration as Story 1. Drive turn
rate above the threshold for the observation window. Verify a
`mode_transition` audit event is emitted with `action=ENGAGE` AND
the spec-013 mechanisms (those whose env vars are set) become
active for the session. After the controller disengages, verify
the mechanisms revert and a matched `mode_transition` event with
`action=DISENGAGE` is emitted.

**Acceptance Scenarios**:

1. **Given** `SACP_AUTO_MODE_ENABLED=true` and the threshold/dwell
   configuration from Story 1, **When** turn rate sustains above
   threshold for the observation window, **Then** the controller
   engages spec-013 mechanisms for the session AND emits a
   `mode_transition` audit event with `action=ENGAGE`, `trigger`,
   observed/threshold values, and the dwell-floor timestamp at
   which the next DISENGAGE would be eligible.
2. **Given** an ENGAGE transition has occurred, **When** signal
   values drop below threshold but the dwell window has not yet
   elapsed, **Then** the controller MUST NOT disengage and MUST
   record a `mode_transition_suppressed` event with
   `reason=dwell_floor_not_reached` so the suppression is auditable.
3. **Given** an ENGAGE transition has occurred and the dwell window
   has elapsed with signal values sustained below threshold, **When**
   the next decision cycle runs, **Then** the controller disengages
   spec-013 mechanisms and emits a matched `mode_transition` with
   `action=DISENGAGE`.
4. **Given** `SACP_AUTO_MODE_ENABLED=true` but `SACP_DMA_DWELL_TIME_S`
   is unset, **When** the orchestrator initializes, **Then** the
   orchestrator MUST exit at startup with a clear error (auto-apply
   without a dwell floor would be flap-prone — V16 fail-closed).

---

### User Story 3 - Signal sources are independently testable and independently weighted (Priority: P3)

The controller observes four signal sources. Each source must be
independently configurable, independently testable, and independently
disable-able so that operators can roll out signals incrementally
(start with turn-rate-only, add convergence-derivative once
calibrated, etc.) and so that a faulty signal source does not
poison the controller's overall judgment.

**Why this priority**: P3 because the controller still works with
just one signal source enabled (turn rate is the canonical Phase 3
signal); the other three are accuracy enhancements rather than
feature requirements. Per-signal independence also gives the
operator the smallest possible blast radius when debugging a
signal-source regression: disable that one source, leave the others
running.

**Independent Test**: Launch four separate sessions, each with
exactly one of the four `SACP_DMA_*_THRESHOLD` vars set and the
others unset. For each session, drive the corresponding signal
above its threshold and verify:
(a) the `mode_recommendation` event names that signal as the
    `trigger` field;
(b) the unset signals do not appear in any audit event;
(c) disabling the configured signal mid-session (orchestrator
    restart) returns the controller to inactive state for that
    session.

**Acceptance Scenarios**:

1. **Given** only `SACP_DMA_TURN_RATE_THRESHOLD_TPM` is set and the
   other three threshold vars are unset, **When** turn rate exceeds
   the threshold for the observation window, **Then** the
   `mode_recommendation` event lists `trigger=turn_rate` and no
   other signal contributes to the decision.
2. **Given** only `SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD` is set,
   **When** the convergence-derivative magnitude exceeds the
   threshold for the observation window, **Then** the
   `mode_recommendation` lists `trigger=convergence_derivative`
   and no other signal contributes.
3. **Given** all four threshold vars are set, **When** two signals
   simultaneously cross their thresholds in the same observation
   window, **Then** the `mode_recommendation` lists both signals
   in a `triggers[]` array (order: alphabetical by signal name) and
   the audit event records each signal's observed value and
   threshold separately.
4. **Given** any signal source's underlying data feed is unavailable
   (e.g., convergence engine has not produced a derivative this
   window), **When** the decision cycle runs, **Then** that signal
   contributes nothing (does not block the cycle, does not error)
   and a `signal_source_unavailable` audit event is emitted at
   most once per dwell window per signal (rate-limited so a
   permanently unavailable source does not flood the audit log).

---

### Edge Cases

- What happens when the controller's decision cycle would exceed its
  decisions-per-minute cap? The excess decision is dropped (not
  queued) and a `decision_cycle_throttled` audit event is emitted
  at most once per dwell window. The cap is a hard CPU-cost ceiling,
  not a queue.
- What happens when an auto-apply ENGAGE transition coincides with
  spec-013's per-session config being absent (e.g.,
  `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S` unset)? The controller
  engages only the spec-013 mechanisms whose env vars ARE set;
  unset mechanisms are skipped silently (per spec 013 each mechanism
  is independently enable/disable-able). The audit event lists
  which mechanisms were engaged and which were skipped.
- What happens when signals disagree (one says ENGAGE, another says
  DISENGAGE)? Per FR-009 below, ANY signal crossing its ENGAGE
  threshold during the observation window emits an ENGAGE
  recommendation. DISENGAGE requires ALL configured signals to be
  below their thresholds for the dwell window. This asymmetry
  biases toward engagement (high-traffic mode is the safer state
  under uncertainty: it costs latency, not correctness).
- What happens when the dwell window is set very short relative to
  the observation window (e.g., dwell 30s vs window 300s)? The
  controller will appear to flap from the operator's perspective
  because the observation window is the longer signal; the dwell
  applies only to the *transition* timing. Flapping is itself an
  audit signal — operators should detect it from the transition
  log and lengthen dwell. No automatic fix; this is a configuration
  hazard documented in `docs/env-vars.md`.
- What happens when auto-apply has flipped the session into
  high-traffic mode and the session converges before DISENGAGE?
  Convergence terminates the session — the DISENGAGE transition is
  not emitted (no need to revert mechanisms in a session that is
  already wrapping up). The audit log shows the final mode at
  convergence time.
- What happens at session restart while a `mode_transition` was
  pending? Controller state (the rolling signal window) is
  session-local and not persisted across restart. On restart the
  session begins in normal mode regardless of pre-restart state;
  the controller re-accumulates its 5-minute signal window from
  scratch. Spec-013 env vars resume their configured semantics
  (operator-set values still apply; controller-applied auto-apply
  state does not survive restart).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The controller MUST observe session signals over a
  rolling 5-minute window. The window MUST be implemented as a
  bounded ring buffer (or equivalent) so per-cycle CPU cost is
  bounded by window depth, not session age.
- **FR-002**: The controller MUST run its decision cycle at a
  rate not exceeding the configured decisions-per-minute cap
  (initial cap: 12 decisions/minute = one decision every 5
  seconds). Excess decisions MUST be dropped, not queued.
- **FR-003**: The controller MUST observe four independent signal
  sources: (a) turn rate (turns/minute over the observation
  window), (b) convergence derivative (rate of change of the spec
  004 similarity score), (c) human-side queue depth (per spec 013
  batching), (d) density anomaly rate (per-window count of
  attention-area shifts; definition refined in `/speckit.plan`).
- **FR-004**: Each signal source MUST be independently
  configurable via its own `SACP_DMA_*_THRESHOLD` env var. A signal
  whose threshold is unset MUST contribute nothing to the
  decision (not zero, not infinity — *absent*).
- **FR-005**: The controller MUST emit a `mode_recommendation`
  audit event whenever its decision differs from the
  most-recently-emitted recommendation for that session, in BOTH
  advisory and auto-apply modes.
- **FR-006**: When `SACP_AUTO_MODE_ENABLED=true`, the controller
  MUST also engage or disengage the spec-013 mechanisms whose env
  vars are configured for the session, and MUST emit a
  `mode_transition` audit event matching the recommendation.
- **FR-007**: Auto-apply transitions MUST be governed by a
  hysteresis dwell time (`SACP_DMA_DWELL_TIME_S`): once a
  transition has occurred, the next opposite transition MUST NOT
  fire until the dwell window has elapsed AND the underlying
  signal condition has been sustained for the full window.
- **FR-008**: When auto-apply suppresses a transition due to dwell,
  the controller MUST emit a `mode_transition_suppressed` audit
  event with `reason=dwell_floor_not_reached` so the suppression
  is auditable.
- **FR-009**: ENGAGE asymmetry — an ENGAGE recommendation/transition
  fires when ANY configured signal crosses its threshold during
  the observation window. A DISENGAGE recommendation/transition
  fires only when ALL configured signals are below their
  thresholds for the entire dwell window.
- **FR-010**: When `SACP_AUTO_MODE_ENABLED=true` but
  `SACP_DMA_DWELL_TIME_S` is unset, the orchestrator MUST exit at
  startup with a clear error naming both vars (auto-apply without
  a dwell floor is flap-prone — V16 fail-closed).
- **FR-011**: When `SACP_AUTO_MODE_ENABLED` is unset (advisory mode),
  the controller MUST NOT alter spec-013 env vars or invoke spec-013
  mechanism activation paths. Recommendations are advisory only.
- **FR-012**: Per-decision-cycle controller evaluation cost MUST be
  captured in `routing_log` per spec 003 §FR-030 so regressions
  surface per-stage. Per-signal evaluation cost SHOULD be captured
  separately so a faulty signal source can be identified by its
  cost profile.
- **FR-013**: `signal_source_unavailable` audit events MUST be
  rate-limited to at most once per dwell window per signal, so a
  permanently unavailable source does not flood the audit log.
- **FR-014**: All five new `SACP_DMA_*` env vars (the four
  threshold vars and the dwell-time var) MUST have validator
  functions in `src/config/validators.py` registered in the
  `VALIDATORS` tuple, and corresponding sections in
  `docs/env-vars.md` with the six standard fields (Default, Type,
  Valid range, Blast radius, Validation rule, Source spec) BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable gate).
  `SACP_AUTO_MODE_ENABLED` (the auto-apply feature flag) is the
  sixth env var introduced by this spec and is subject to the same
  V16 deliverable gate.
- **FR-015**: This spec MUST NOT alter the dispatch path semantics
  in topologies 1–6 when no `SACP_DMA_*` thresholds are configured
  (additive feature, controller is inactive when unconfigured).
- **FR-016**: This spec MUST NOT alter spec-013's mechanism
  semantics — the controller can only toggle whether spec-013's
  configured mechanisms engage; it cannot reconfigure their
  thresholds, override their fail-closed semantics, or change
  their evaluation logic.

### Key Entities

- **SessionSignals** (per-session, in-memory) — a bounded ring
  buffer holding the rolling 5-minute observation window for
  each of the four signal sources. Each entry carries a timestamp
  and the signal's instantaneous value at that timestamp.
- **ModeRecommendation** — the controller's per-cycle decision:
  `(session_id, decision_at, action, triggers[], dwell_floor_at)`.
  Emitted to the audit log in both advisory and auto-apply modes.
- **ModeTransition** (audit) — emitted only in auto-apply mode when
  a recommendation is acted upon: same shape as ModeRecommendation
  plus `engaged_mechanisms[]` and `skipped_mechanisms[]` (the
  spec-013 mechanisms whose env vars were/were not configured).
- **ModeTransitionSuppressed** (audit) — emitted when auto-apply
  would have fired a transition but the dwell floor blocked it:
  `(session_id, suppressed_at, action, reason, eligible_at)`.
- **ControllerState** (per-session, in-memory) — the controller's
  current view of the session: most-recent recommendation, time
  of last transition (for dwell calculation), per-signal-source
  health flags. Not persisted across restart.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In advisory mode, the controller produces a
  `mode_recommendation` event within 5 seconds (one decision-cycle
  tick at the cap) of any configured signal crossing its threshold
  for the observation window. Measured via injection test on the
  signal feed.
- **SC-002**: In auto-apply mode, no `mode_transition` event fires
  within `SACP_DMA_DWELL_TIME_S` seconds of the previous
  `mode_transition` event for the same session. Measured by audit
  log scan over a 30-minute synthetic-signal test.
- **SC-003**: Per-decision-cycle controller evaluation cost stays
  under 50ms P95 at the Phase 3 ceiling of 5 participants with
  all four signal sources active. Measured via routing_log
  per-stage timing capture (spec 003 §FR-030).
- **SC-004**: Sessions with no `SACP_DMA_*` env vars set exhibit
  no observable behavior change versus the spec-013-only baseline
  (regression test: full spec-013 acceptance scenarios pass
  unmodified).
- **SC-005**: When auto-apply is enabled but configured invalidly
  (any threshold out of range, or dwell time unset/invalid), the
  orchestrator process exits at startup with a clear error message
  naming the offending var (V16 fail-closed gate observed in CI).
- **SC-006**: An operator can enable advisory-mode recommendations
  for the controller by setting one threshold env var, restart the
  orchestrator, and observe `mode_recommendation` events in the
  audit log within 5 minutes of operator effort end-to-end.
- **SC-007**: ENGAGE asymmetry verified by test: when any single
  configured signal crosses its threshold and the others remain
  below, the controller emits ENGAGE within one decision cycle.
- **SC-008**: DISENGAGE asymmetry verified by test: when all
  configured signals drop below their thresholds, the controller
  does NOT emit DISENGAGE until the full dwell window has elapsed
  with all signals sustained below.
- **SC-009**: Decisions-per-minute cap verified by stress test:
  driving signals to oscillate at a rate exceeding the cap
  produces at most `cap * minutes_observed` recommendations,
  with the excess accounted for by `decision_cycle_throttled`
  events (rate-limited per FR-013).

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** — the same set as spec
013, for the same reason: the controller observes session signals
that exist only when there is a central orchestrator capable of
producing them.

- Topology 1: Solo Operator + Multiple AIs
- Topology 2: Multiple Humans + One Shared AI
- Topology 3: Multiple Humans + Multiple AIs (canonical Phase 3 case)
- Topology 4: Asymmetric Participation
- Topology 5: Fully Autonomous (note: the queue-depth signal is a
  no-op here because there are no humans on the receiving boundary;
  the other three signals remain valid)
- Topology 6: Single Human + Single AI (note: signals will rarely
  cross thresholds in 1+1 sessions; controller is available but
  unlikely to engage)

This feature is **incompatible with topology 7 (MCP-to-MCP, Phase
3+)**. Topology 7 removes the orchestrator from the dispatch path,
which simultaneously removes:

- The signal sources (turn rate, convergence derivative, queue
  depth, density anomalies are all derived from orchestrator-side
  state).
- The action authority (the controller's auto-apply path engages
  spec-013 mechanisms via the orchestrator; topology 7 has no
  central authority to engage them).

Per V12's "silent assumption = incomplete" rule: any future topology-7
deployment MUST explicitly disable this controller (no `SACP_DMA_*`
thresholds set) or substitute a topology-7-native equivalent
(likely a separate spec).

### V13 — Use Case Coverage

This feature primarily serves three use cases from
`docs/sacp-use-cases.md`:

- **Use Case §3 — Consulting Engagement**: The static spec-013
  batching cadence forces the operator to choose between cadence
  too long for slow phases and cadence too short for traffic
  spikes. The controller dynamically toggles batching only when
  the spike condition is observed. User Stories 1 and 2 are the
  direct remedy.
- **Use Case §2 — Research Paper Co-authorship**: Mid-session
  traffic-shape changes (slow methodology debate → contentious
  finding burst → slow synthesis) are exactly the pattern the
  rolling-window controller is designed for. User Stories 1 and 2
  apply directly; the convergence-derivative signal (Story 3) is
  particularly valuable here because methodology-debate convergence
  shapes are distinctive.
- **Use Case §5 — Technical Review and Audit**: Long-running
  technical reviews shift attention areas (auth → data layer →
  frontend) every ~30 minutes. Each shift produces a transient
  density anomaly that the controller's density-anomaly signal
  source (Story 3) is designed to detect, allowing high-traffic
  mode to engage precisely during attention shifts and disengage
  during steady-state review of a single area. This is the third
  primary use case driving the controller's signal selection,
  beyond the two that drove spec 013.

Secondary applicability: Use Cases §1 (Distributed Software
Collaboration), §4 (Open Source Project Coordination), and §6
(Decision-Making Under Asymmetric Expertise) benefit indirectly
from any signal-driven mode controller but are not the priority
cases driving the design.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts,
with per-stage timings captured into structured logs. This
controller's performance contracts are framed around three V14
budgets specific to its decision-loop nature:

- **Rolling observation window cost**: Per-signal-source
  per-decision-cycle cost MUST be bounded by window depth
  (`O(window_entries)`), not by session age. The window is
  implemented as a bounded ring buffer per FR-001. Budget
  enforcement: routing_log MUST NOT show controller evaluation
  cost growing with session duration.
- **Decisions-per-minute cap**: The controller's decision cycle
  MUST run at a rate not exceeding the configured cap (initial:
  12 decisions/min). This is the controller's CPU-cost ceiling
  per V14 — without the cap, the controller could itself become
  a hot-path regression. Budget enforcement: per-cycle wall-clock
  interval captured in routing_log; `decision_cycle_throttled`
  event when the cap fires (rate-limited per FR-013).
- **Hysteresis dwell time**: The dwell window prevents flap-driven
  cost (each transition implicates spec-013 mechanism activation/
  deactivation, which has its own per-stage cost budgets per spec
  013's V14 section). Budget enforcement: `mode_transition` and
  `mode_transition_suppressed` events are matched in the audit log;
  any transition fired before its dwell floor is a regression.

Cross-ref: Per V14, the validation rule is binding for all future
specs; instrumentation is implemented as part of the spec's
Phase 0–2 design phases (`/speckit.plan` work).

## Configuration (V16) — New Env Vars

This spec introduces six new `SACP_*` env vars: five threshold/
dwell-time vars (the V16-mandatory set per the spec input) plus
the auto-apply feature flag. Each MUST have type, valid range, and
fail-closed semantics documented in `docs/env-vars.md` BEFORE
`/speckit.tasks` is run for this spec (per V16 deliverable gate).

### `SACP_DMA_TURN_RATE_THRESHOLD_TPM`

- **Intended type**: positive integer, turns per minute
- **Intended valid range**: `1 <= value <= 600` (1 tpm is the
  trivial floor; 600 tpm is 10/sec, well above any realistic
  Phase 3 ceiling)
- **Fail-closed semantics**: unset means turn-rate signal does not
  contribute to controller decisions (controller still functions
  with other signals if any are configured). Set-but-out-of-range
  MUST cause startup exit per V16.
- **Documentation**: needs full `docs/env-vars.md` entry before
  `/speckit.tasks`.

### `SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD`

- **Intended type**: float (absolute magnitude of the per-window
  derivative of the spec-004 similarity score)
- **Intended valid range**: `0.0 < value <= 1.0` (values above 1.0
  cannot trip — similarity is bounded in [0, 1] so its derivative
  per-window is bounded in [-1, 1])
- **Fail-closed semantics**: unset means convergence-derivative
  signal does not contribute. Set-but-out-of-range MUST cause
  startup exit per V16.
- **Cross-ref**: Depends on spec 004's similarity score being
  exposed for derivative computation. If spec 004 does not expose
  this, `/speckit.plan` will identify the minimal hook needed and
  may amend spec 004.
- **Documentation**: needs full `docs/env-vars.md` entry.

### `SACP_DMA_QUEUE_DEPTH_THRESHOLD`

- **Intended type**: positive integer (count of pending messages
  in the human-side batch queue per spec 013)
- **Intended valid range**: `1 <= value <= 1000` (lower bound is
  1; upper bound is a sanity ceiling — queue depths above 1000
  indicate a different failure mode than mode assignment can
  address)
- **Fail-closed semantics**: unset means queue-depth signal does
  not contribute. Set-but-out-of-range MUST cause startup exit
  per V16.
- **Cross-ref**: Depends on spec 013's batching mechanism exposing
  queue depth observability. Soft dependency: this signal is a
  no-op if spec 013's batching is unconfigured for the session.
- **Documentation**: needs full `docs/env-vars.md` entry.

### `SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD`

- **Intended type**: positive integer (count of detected
  attention-area shifts per observation window)
- **Intended valid range**: `1 <= value <= 60` (one shift per
  window is the trivial floor; 60 shifts in a 5-minute window
  means one every 5 seconds, a sanity ceiling)
- **Fail-closed semantics**: unset means density-anomaly signal
  does not contribute. Set-but-out-of-range MUST cause startup
  exit per V16.
- **Cross-ref**: Density-anomaly definition is refined in
  `/speckit.plan`. Initial heuristic: detect statistically
  significant shifts in turn-content topic embeddings across
  consecutive sub-windows. Concrete algorithm chosen in plan.
- **Documentation**: needs full `docs/env-vars.md` entry.

### `SACP_DMA_DWELL_TIME_S`

- **Intended type**: positive integer, seconds
- **Intended valid range**: `30 <= value <= 1800` (30s is the
  practical floor below which dwell offers no flap protection;
  30 minutes is a sanity ceiling — dwell longer than this
  effectively disables DISENGAGE for typical sessions)
- **Fail-closed semantics**: unset is allowed in advisory mode
  (no transitions fire, so no dwell needed). Unset is a startup
  error when `SACP_AUTO_MODE_ENABLED=true` per FR-010.
  Set-but-out-of-range MUST cause startup exit per V16.
- **Documentation**: needs full `docs/env-vars.md` entry.

### `SACP_AUTO_MODE_ENABLED`

- **Intended type**: boolean (`true`/`false`)
- **Intended valid range**: `true` or `false`. Unset is treated
  as `false` — the safe default for initial Phase 3 deployment.
- **Fail-closed semantics**: any value other than `true` or `false`
  MUST cause startup exit per V16. The default-`false` semantics
  ensure that deploying this spec to production WITHOUT operator
  opt-in produces only advisory recommendations, never automatic
  transitions.
- **Documentation**: needs full `docs/env-vars.md` entry. The
  doc MUST explicitly call out that `SACP_AUTO_MODE_ENABLED=true`
  in production requires prior advisory-mode validation per the
  Story 1 / Story 2 priority ordering.

## Cross-References to Existing Specs

- **Spec 013 (high-traffic-mode)** — this spec is the controller
  layer above 013. The relationship is one-way: 014 toggles 013's
  mechanisms via its env vars / config interface; 013 has no
  knowledge of 014. 013 must reach Status: Implemented before this
  spec's `/speckit.plan` begins.
- **Spec 003 (turn-loop-engine)** §FR-030 defines `routing_log`
  per-stage timing capture; this spec's per-decision-cycle and
  per-signal-source evaluation cost logging hook into that same
  channel.
- **Spec 004 (convergence-cadence)** provides the similarity score
  whose derivative is one of the four signal sources. This spec
  may require a minimal observability hook on spec 004 (exposing
  the similarity score for derivative computation); identified
  in `/speckit.plan`.
- **Spec 007 (ai-security-pipeline)** §FR-020 defines
  `security_events` per-layer duration logging; mode transitions
  flow through the audit pipeline rather than security_events
  because they are mode-state changes, not security decisions.
- **Constitution §10** — Phase 3 deliverable. Implementation does
  not begin until the facilitator declares Phase 3 started.

## Assumptions

- Spec 013 (high-traffic-mode) lands first as Draft (already
  drafted, expected to reach Implemented during Phase 3 startup).
  This spec depends on 013's mechanism set and env-var interface.
- The Phase 3 participant ceiling stays at 5 per Constitution §10.
  The 50ms P95 evaluation budget (SC-003) assumes this ceiling.
- Spec 004 will expose its similarity score for derivative
  computation. If it does not, `/speckit.plan` identifies the
  minimal hook and may amend spec 004.
- The density-anomaly definition is initial-heuristic only at
  spec time; the concrete algorithm (likely topic-embedding shift
  detection across consecutive sub-windows) is decided in
  `/speckit.plan`. Until then, the density-anomaly signal source
  is a placeholder shape, not a contract.
- The 5-minute observation window and 12-decisions-per-minute cap
  are initial budgets; both may be tuned during instrumentation
  rollout in `/speckit.plan`. Any tightening must keep the
  budgets observable in `routing_log`.
- The audit event taxonomy already supports adding
  `mode_recommendation`, `mode_transition`,
  `mode_transition_suppressed`, `decision_cycle_throttled`, and
  `signal_source_unavailable` event types without schema changes.
  If schema changes are needed, scoped during `/speckit.plan`.
- Initial Phase 3 deployment defaults to advisory mode
  (`SACP_AUTO_MODE_ENABLED` unset/false). Auto-apply is enabled
  per-deployment by operator opt-in only after advisory-mode
  observation has built confidence in the controller's signal
  interpretation.
- Status remains Draft until the facilitator declares Phase 3
  started per Constitution §10 AND spec 013 reaches Status:
  Implemented. No implementation work proceeds before both gates
  are satisfied.
