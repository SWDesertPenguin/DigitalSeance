# Feature Specification: Detection Event History Surface

**Feature Branch**: `022-detection-event-history`
**Created**: 2026-05-07
**Status**: Draft (Phase 3 declared 2026-05-05; scaffold ships now, tasks + implementation deferred)
**Input**: User description: "Phase 3 detection event history surface. Spec 004's A2 question-tracker and A3 exit-detection signals (and density_anomaly) fire correctly during sessions but the live UI surfaces only the current banner — once dismissed an event is invisible. The audit log has the data; the operator-facing surface does not. Spec 022 adds a detection-event history panel that lists all ai_question_opened, ai_exit_requested, density_anomaly, and (when 014 lands) mode_change events for the active session, with the option to re-surface a previously dismissed banner for re-evaluation. Applies to topologies 1-6 (orchestrator-mediated event stream); incompatible with topology 7 per V12. Primary use cases: consulting (§3) where event review is part of the engagement deliverable, and technical review and audit (§5) where every routing decision must be reviewable."

## Overview

Spec 004 (convergence-cadence) emits three classes of detection event
during normal session operation: `ai_question_opened` when an AI's
output contains an unresolved question (A2 tracker),
`ai_exit_requested` when an AI signals readiness to wrap (A3 detector),
and `density_anomaly` (FR-020) when an AI's output is high-word-count
but low-semantic-load. Each event surfaces a banner in the live Web UI
(spec 011). Once a banner is acknowledged or dismissed, the event
disappears from the operator's view. The audit log retains it, but
the only retrieval path today is `/tools/debug/export` (spec 010) —
high-friction, requires JSON parsing, off the live-session path.

Two operational gaps follow from this:

1. **No after-the-fact decision review.** A facilitator who notices a
   downstream effect ("the AI started restating itself on turn 14")
   wants to ask "did A3 fire? what was the trigger snippet? did I
   dismiss it?" — and has no in-UI answer. They must request a
   debug export and grep.
2. **No false-positive identification surface.** The detectors are
   heuristic. An observed homoglyph-injection turn in a Phase 1+2
   shakedown produced a candidate exit signal that may have been a
   false positive (Cyrillic look-alikes resembling an English exit
   phrase). Confirming or refuting this requires the trigger
   snippet alongside the detector's score and disposition — which
   the live UI does not retain.

This spec defines a **detection event history panel** as a new
operator-facing surface that:

1. **Lists** every detection event for the active session in
   chronological order, with the event type, the participant
   involved, the trigger snippet (the message excerpt that fired
   the detector), the detector's score (where applicable), the
   timestamp, and the disposition (banner acknowledged / banner
   dismissed / auto-resolved / pending).
2. **Re-surfaces** a previously dismissed banner on operator
   demand. Re-surface is a logged action — it appears in
   `admin_audit_log` with actor, target event id, and timestamp.
3. **Filters** by event type (question / exit / density-anomaly /
   mode-change) so an operator can compute per-detector noise
   rates by counting dismissed-as-false-positive events of one
   class.
4. **Respects** the existing event-retention story (spec 010 already
   includes these events in the debug-export payload; spec 022 reads
   the same source rather than introducing a new persistence path).

The panel is **read-only** for stored event content. The operator
can mark an event's disposition (e.g., "false positive") via the
re-surface action's audit trail, but cannot modify the original
trigger snippet, score, or timestamp. Append-only is preserved per
spec 001 §FR-008.

This spec **scaffolds only**. Implementation begins when the
facilitator schedules tasks per Constitution §14.1. The Phase 3
declaration recorded 2026-05-05 satisfies the phase gate; this
spec stays scaffold-only until tasks land and implementation
reaches Implemented status.

## Clarifications

### Initial draft assumptions requiring confirmation

- **Event source of truth.** Drafted as: the panel reads from the
  existing log tables — `convergence_log` (for density_anomaly),
  `routing_log` (for question/exit detector decisions per spec 003
  §FR-030), and `admin_audit_log` (for cross-cutting state changes
  including re-surface). No new `detection_events` table. A nullable
  `event_class` column already exists in some schemas; a thin
  read-side join surfaces the unified event stream. [NEEDS
  CLARIFICATION: confirm read-side join over existing tables vs. a
  dedicated `detection_events` table that emitters write to in
  parallel with the existing log paths.]
- **Re-surface semantics.** User input says "re-surface a previously
  dismissed banner for re-evaluation." Drafted as: re-surface
  re-broadcasts the original banner shape over the participant's
  WS channel as if the event had just fired, AND emits an
  `admin_audit_log` row with `action='detection_event_resurface'`,
  `target_event_id=<id>`, `actor_id=<facilitator>`. The participant's
  AI does NOT see the re-surfaced event — re-surface is operator-
  only. [NEEDS CLARIFICATION: confirm operator-only re-surface vs.
  optional broadcast to the affected participant's MCP client.]
- **Event taxonomy completeness.** Drafted as: v1 ships the four
  classes named in the brief — `ai_question_opened`,
  `ai_exit_requested`, `density_anomaly`, and (gated on spec 014
  shipping) `mode_change`. Future detectors (e.g., spec 021's
  filler-retry events, spec 015's circuit-breaker state transitions)
  join the surface only via a follow-up amendment that adds them
  to the taxonomy. [NEEDS CLARIFICATION: confirm the four-class v1
  taxonomy vs. an extensible registry that future detectors can
  register into without spec amendment.]
- **Filter granularity in P3.** Drafted as: filter-by-type only in
  v1 (question / exit / density-anomaly / mode-change). Filter-by-
  participant, filter-by-time-range, filter-by-disposition are
  Phase 3+ enhancements. [NEEDS CLARIFICATION: confirm type-only
  v1 vs. a fuller filter axis set.]
- **Disposition vocabulary.** Drafted as four values:
  `pending` (event fired, banner shown, no operator action yet),
  `banner_acknowledged` (operator clicked acknowledge),
  `banner_dismissed` (operator clicked dismiss without acknowledging),
  `auto_resolved` (the underlying condition cleared without operator
  action — e.g., density anomaly score dropped below threshold on
  the next turn). [NEEDS CLARIFICATION: confirm the four-value
  enum vs. a reduced two-value (resolved / unresolved) shape.]
- **Multi-instance session affinity.** Spec 011's clarification
  notes Phase 1 single-instance topology with WS termination at
  the same orchestrator process. The history panel reads from the
  shared DB and so works in multi-instance Phase 3, but re-surface
  WS broadcast requires reaching the participant's currently-bound
  process. Drafted as: re-surface is single-instance-only in v1;
  multi-instance re-surface lands when spec 011's `SessionStore`
  Redis backend lands (Phase 3+ trigger). [NEEDS CLARIFICATION:
  confirm v1 single-instance constraint vs. designing for
  multi-instance from the start.]
- **Active-vs-archived sessions.** Drafted as: the panel surfaces
  events for the active session by default. For archived sessions
  the panel reads from the same tables but disables the re-surface
  action (an archived session has no live WS to broadcast to).
  [NEEDS CLARIFICATION: confirm the active-only re-surface
  constraint.]
- **Mode-change event forward compatibility.** Spec 014 emits
  `mode_recommendation` (advisory mode) and `mode_change` (auto-
  apply mode) events to `admin_audit_log`. Drafted as: 022 reads
  both event types as a single `mode_change` class on the panel
  (mode_recommendation rows show as advisory entries, distinguished
  by a `mode_action_kind` field). [NEEDS CLARIFICATION: confirm
  the two-event-types-one-panel-class merge vs. keeping them as
  distinct panel classes.]

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Facilitator opens the history panel and sees all detection events for the current session in chronological order (Priority: P1)

A facilitator running a multi-AI session notices the conversation
took an unexpected turn around turn 14 — one AI started restating
its prior position. They want to know whether a detector fired
around that point (was the divergence prompt triggered? did A3
mark an exit-request that got auto-dismissed?) and what triggered
it. They open the new history panel from the session header,
which lists every detection event for the session in
chronological order with type, participant, trigger snippet,
detector score, timestamp, and disposition. They scroll back to
the turn-14 region and find the answer in seconds.

**Why this priority**: P1 because this is the entire reason the
spec exists. Without history visibility the operator-side
diagnostic loop requires `/tools/debug/export` + JSON grep —
hours of friction for what should be a click. Phase 1+2
shakedowns produced multiple decision-review questions; an
in-UI panel resolves them at observation time, not in a
follow-up triage session.

**Independent Test**: Drive a session that fires at least one
event of each tracked class (one `ai_question_opened`, one
`ai_exit_requested`, one `density_anomaly`). Open the history
panel via the session-header entry point. Assert the panel
shows three rows in chronological order, each with the
expected type, the expected participant id, a non-empty
trigger snippet, the detector score, the original timestamp,
and a disposition.

**Acceptance Scenarios**:

1. **Given** a session with at least one `ai_question_opened`
   event, **When** the facilitator opens the history panel,
   **Then** the panel MUST list the event with type, participant,
   trigger snippet, detector score, timestamp, and disposition.
2. **Given** a session with multiple events across the four
   tracked classes, **When** the panel opens, **Then** events
   MUST appear in chronological order (oldest first OR newest
   first per `/speckit.clarify` decision; one ordering, not a
   mix).
3. **Given** a session with no detection events yet,
   **When** the panel opens, **Then** an empty-state message
   MUST render (NOT a blank panel) explaining no events have
   been detected yet.
4. **Given** an event whose trigger snippet exceeds a display
   length cap, **When** the panel renders, **Then** the snippet
   MUST be truncated with an explicit `...` indicator AND a
   click-to-expand affordance.
5. **Given** the facilitator is viewing the panel, **When** a
   new detection event fires for the same session, **Then** the
   panel MUST update via WS push within 2s of the event firing
   (live-update; no manual refresh).

---

### User Story 2 - Facilitator re-surfaces a dismissed event for re-evaluation, with audit-log entry (Priority: P2)

The facilitator is reviewing the history panel and finds a
`banner_dismissed` event from earlier in the session that they
now want a second look at. They click the event row and select
"Re-surface banner". The original banner (same shape as when
it first fired) reappears in the live UI for re-evaluation.
The re-surface action is logged to `admin_audit_log` so the
forensic trail records who re-opened the case. The operator
can re-acknowledge, re-dismiss, or take whatever action the
banner offered the first time.

**Why this priority**: P2 because the panel without re-surface
is still useful for diagnostic review (P1 covers that). Re-
surface adds the workflow loop — converting "I see this event
in history" into "I'm re-evaluating this event right now"
without leaving the UI. P2 because for many sessions the
dismissed-by-mistake case is rare; for sessions where it's
common, re-surface saves a manual reconstruction.

**Independent Test**: In a session with a `banner_dismissed`
event, click re-surface from the history panel. Verify the
banner reappears with identical content (event type, trigger
snippet, score) to its first appearance. Verify
`admin_audit_log` has one row with
`action='detection_event_resurface'`, the actor (facilitator
id), the target (event id), and the timestamp. Verify the
event's disposition in the panel updates to reflect the
re-surfaced status (still resolvable, but the original
dismissal is preserved alongside the re-surface entry — the
audit trail shows both events).

**Acceptance Scenarios**:

1. **Given** a `banner_dismissed` event, **When** the
   facilitator clicks re-surface, **Then** the original
   banner MUST reappear in the live UI with identical content
   AND `admin_audit_log` MUST record the re-surface with
   actor, target event id, and timestamp.
2. **Given** a re-surfaced event, **When** the operator
   acknowledges or dismisses the new banner, **Then** the
   panel MUST track this as a separate disposition transition
   (not a mutation of the original disposition row).
3. **Given** an active-session event is re-surfaced,
   **When** the underlying session is later archived, **Then**
   the re-surface history MUST persist in `admin_audit_log`
   alongside the original dismissal.
4. **Given** a facilitator attempts re-surface on an archived
   session, **When** the click fires, **Then** the action
   MUST be rejected with a clear error explaining re-surface
   requires an active session.
5. **Given** a non-facilitator participant attempts to call
   the re-surface endpoint, **When** the request arrives,
   **Then** it MUST be rejected with HTTP 403 (mirrors spec
   010 §FR-2 facilitator-only access).

---

### User Story 3 - Facilitator filters the history by event type for noise-rate analysis (Priority: P3)

After running a session for an hour, a facilitator wants to
know how often the `density_anomaly` detector fired and what
proportion of those events the operator marked as
false-positive (banner_dismissed). They open the history
panel, click the type filter, select `density_anomaly`. The
panel filters to show only those events. They count visually
or read the disposition column to compute the dismissal rate
for the session. They cross-check this against other event
types by toggling the filter.

**Why this priority**: P3 because filter-by-type is a
nice-to-have for operators who do detector tuning; most
operator-side review is "what happened around turn N", which
P1 chronological view answers. P3 makes per-detector noise
analysis cheap (no manual counting) but is not on the critical
path for P1's diagnostic loop.

**Independent Test**: Open the history panel for a session
with mixed event types. Click the type filter and select
one type. Verify only events of that type appear. Toggle
to "all types" and verify all events return. Toggle to a
different type and verify the displayed set updates.

**Acceptance Scenarios**:

1. **Given** a session with events across all four tracked
   classes, **When** the facilitator selects a single type
   filter, **Then** the panel MUST display only events of
   that type.
2. **Given** an active filter, **When** new events fire that
   match the filter, **Then** they MUST appear in the
   filtered view via the same WS push as US1's live-update
   contract.
3. **Given** an active filter, **When** new events fire that
   do NOT match the filter, **Then** the filtered view MUST
   NOT update for them; the unfiltered count (small badge
   on the filter control) MUST increment so the operator
   sees there are more events outside the current filter.
4. **Given** the operator clears the filter, **When** the
   "all types" option is selected, **Then** all events MUST
   return to the panel in the original chronological order.

---

### Edge Cases

- **Session deleted while history panel is open.** WS push
  closes the panel with an explanatory message; the panel does
  not attempt to re-fetch from a deleted session.
- **Event row click on an event whose source row has been
  purged** (per `SACP_DETECTION_HISTORY_RETENTION_DAYS` post-
  archive cleanup). Panel renders the row as last seen but
  the re-surface action is disabled with an explanatory
  tooltip ("source row purged after retention window").
- **Spec 014 lands and emits `mode_recommendation` events.**
  Per the Clarifications question, those events surface in the
  panel's `mode_change` class with a `mode_action_kind=advisory`
  attribute. Forward-compatible without a 022 amendment.
- **Re-surface called on an event whose original banner
  shape is incompatible with current UI state** (e.g., the UI
  was updated and the banner type was renamed). The
  re-surfaced banner falls back to a generic detection-event
  banner rendering the type, snippet, and score; a warning is
  logged.
- **Detector emits an event for a participant who has
  departed the session.** The event MUST still appear in the
  history panel (the event is a session-scoped fact, not a
  participant-scoped one). The trigger-snippet column may
  show the participant's id but their display name lookup
  may return "(departed)".
- **Two events fire on the same turn for the same participant.**
  Both appear as separate rows in the history panel with the
  same turn number; chronological ordering uses the event's
  emission timestamp, not the turn number.
- **The detector's score is null** (e.g., a binary detector
  that just fires without a numeric score). The score column
  renders as "—" rather than "0.0" to distinguish absence
  from a low score.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A new HTTP endpoint MUST expose the detection
  event history for the active session at `GET
  /tools/admin/detection_events?session_id=<id>` (path subject
  to `/speckit.clarify` confirmation against existing
  `/tools/admin/*` patterns). The response MUST include every
  detection event for the session with the columns: event id,
  event type, participant id, trigger snippet, detector score
  (nullable), timestamp, disposition.
- **FR-002**: The endpoint MUST be facilitator-only (mirrors
  spec 010 §FR-2 controller-only access). Non-facilitator
  callers MUST receive HTTP 403 with the same error code
  shape as spec 010's `facilitator_only`.
- **FR-003**: The endpoint MUST be session-bound — a
  facilitator from session A cannot read session B's events.
  Mirrors spec 010 §FR-3 session-id-on-token check.
- **FR-004**: The endpoint MUST be read-only — no INSERT,
  UPDATE, or DELETE on detection-event source rows occurs as
  a side effect (mirrors spec 010 §FR-6 / §SC-007).
- **FR-005**: The endpoint MUST surface events from the four
  v1 classes: `ai_question_opened`, `ai_exit_requested`,
  `density_anomaly`, and `mode_change`. The
  `mode_change` class MUST include both spec 014's
  `mode_recommendation` (advisory) and `mode_change`
  (auto-apply) audit-log entries; the panel surfaces them
  with a `mode_action_kind` discriminator.
- **FR-006**: A new HTTP endpoint MUST expose re-surface at
  `POST /tools/admin/detection_events/<event_id>/resurface`.
  Re-surface re-broadcasts the original banner shape over
  the participant's WS channel AND emits an
  `admin_audit_log` row with
  `action='detection_event_resurface'`, `actor_id=<facilitator>`,
  `target_event_id=<id>`, `timestamp=NOW()`.
- **FR-007**: Re-surface MUST be facilitator-only and
  session-bound (mirrors FR-002 + FR-003).
- **FR-008**: Re-surface MUST be rejected for archived
  sessions with HTTP 409 and a clear error explaining
  re-surface requires an active session.
- **FR-009**: The history panel MUST update via the existing
  spec 011 WS event channel when a new detection event fires
  for the active session. No new WS channel is introduced;
  the existing per-session broadcast (spec 006 §FR-013, spec
  011) carries the new event-list-item shape.
- **FR-010**: The disposition column MUST take one of four
  values: `pending`, `banner_acknowledged`, `banner_dismissed`,
  `auto_resolved`. Disposition transitions MUST be tracked as
  separate audit-log rows; the panel reads the latest row to
  determine current disposition AND can show the full
  disposition timeline on click-expand.
- **FR-011**: Filter-by-type MUST accept one of the four v1
  event-class names OR `all`. Other filter axes (participant,
  time range, disposition) are deferred — implementing them
  in v1 is out of scope.
- **FR-012**: The panel MUST display the trigger snippet up
  to a documented display length cap (target: 200 characters
  visible, full snippet on click-expand). The cap is enforced
  client-side; the server returns the full snippet so the
  expand action is local (no second fetch).
- **FR-013**: When `SACP_DETECTION_HISTORY_MAX_EVENTS` is
  set to a positive integer, the endpoint MUST return at most
  that many events for the active session — newest first.
  When unset (default), the endpoint returns all events for
  the session. Pagination beyond the cap is deferred.
- **FR-014**: When `SACP_DETECTION_HISTORY_RETENTION_DAYS` is
  set to a positive integer, archived-session events older
  than that retention window MAY be purged by an external
  cleanup job (operator-scheduled per spec 007's purge
  pattern). The endpoint MUST return events that remain;
  purged events are not re-fetched.
- **FR-015**: Spec 014 forward-compat — when 014 lands and
  emits `mode_recommendation` and `mode_change` events to
  `admin_audit_log`, the 022 endpoint MUST surface them
  without a spec 022 amendment. The mapping between
  014's event names and 022's panel-class name (`mode_change`)
  is hardcoded in `src/web_ui/detection_events.py`.
- **FR-016**: The two new env vars
  (`SACP_DETECTION_HISTORY_MAX_EVENTS`,
  `SACP_DETECTION_HISTORY_RETENTION_DAYS`) MUST have
  validator functions in `src/config/validators.py` registered
  in the `VALIDATORS` tuple, AND corresponding sections in
  `docs/env-vars.md` with the six standard fields, BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable
  gate).
- **FR-017**: The endpoint MUST NOT introduce a new
  persistence path for detection events. The four event
  classes are already written by spec 003 / 004 / 014 to
  `routing_log`, `convergence_log`, and `admin_audit_log`;
  spec 022 reads those tables. A read-side join in
  `src/web_ui/detection_events.py` produces the unified
  event stream (alternative considered: a `detection_events`
  table written in parallel by emitters; rejected because it
  duplicates the source of truth and breaks spec 001
  §FR-008's append-only invariant — see Clarifications Q1).

### Key Entities

- **DetectionEvent** (read-side projection, not a persisted
  entity) — the unified shape returned by the FR-001 endpoint:
  event id (synthesized from source-row id + event class),
  event type, participant id, trigger snippet, detector score,
  timestamp, disposition. Computed via a read-side join over
  `routing_log`, `convergence_log`, and `admin_audit_log`.
- **EventDisposition** — `pending` | `banner_acknowledged` |
  `banner_dismissed` | `auto_resolved`. Sourced from the latest
  disposition-transition row in `admin_audit_log` for the
  event id.
- **ResurfaceAction** — `admin_audit_log` row with
  `action='detection_event_resurface'`, `actor_id`,
  `target_event_id`, `timestamp`. Append-only per spec 001
  §FR-008.
- **EventClassRegistry** (process-scope, hardcoded) — maps
  source rows to one of the four v1 panel classes
  (`ai_question_opened`, `ai_exit_requested`,
  `density_anomaly`, `mode_change`). Defined in
  `src/web_ui/detection_events.py`. Adding a class requires a
  spec amendment.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A facilitator on a session with at least one
  event of each tracked class MUST be able to open the panel
  and see all events in chronological order in a single
  interaction, no manual `/tools/debug/export` call required.
  Verified by an end-to-end test that drives the events,
  opens the panel, and asserts the displayed set.
- **SC-002**: A new detection event firing during an open
  panel MUST appear in the panel within 2s via WS push. P95
  measured against synthetic load of 10 events/minute on the
  same session.
- **SC-003**: The re-surface action MUST emit one
  `admin_audit_log` row per click and re-broadcast the
  original banner shape. Verified by a test that drives
  re-surface and asserts both the audit row content and the
  WS broadcast payload.
- **SC-004**: Re-surface attempt by a non-facilitator MUST
  return HTTP 403 with the `facilitator_only` error code.
  Mirrors spec 010 §SC-002.
- **SC-005**: Re-surface attempt on an archived session MUST
  return HTTP 409 with a clear error. Verified by a test
  that archives a session and drives the re-surface attempt.
- **SC-006**: Filter-by-type MUST update the panel in O(1)
  client-side time (no server round-trip). Verified by
  inspecting the network panel during filter toggles.
- **SC-007**: When 014 lands and emits its event types, the
  panel MUST surface them without a 022-side change.
  Verified post-014 by running a 014 session with auto-apply
  enabled and asserting the recommendations and changes
  appear in the panel as `mode_change` class entries.
- **SC-008**: With any of the two new env vars set to an
  invalid value, the orchestrator process MUST exit at
  startup with a clear error message naming the offending
  var (V16 fail-closed gate observed in CI).
- **SC-009**: The endpoint MUST be read-only. Verified by a
  test that drives the endpoint and asserts no
  INSERT/UPDATE/DELETE occurs against `routing_log`,
  `convergence_log`, or `messages` (the only allowed write
  is the `admin_audit_log` row produced by re-surface,
  which is FR-006's explicit forensic write — not an event
  source-row mutation).

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** (orchestrator-driven
topologies). The detection event history panel reads from the
orchestrator's centralized log tables and re-surfaces banners
over the orchestrator's WS broadcast channel. Both require the
orchestrator to be the central event collector and broadcast
hub.

This feature is **NOT applicable to topology 7 (MCP-to-MCP,
Phase 3+)**. In topology 7 each participant's client talks
directly to its own provider; there is no centralized event
stream and no orchestrator-side WS to re-broadcast on. Per V12:
any topology-7 deployment MUST recognize that this spec's
history panel does not apply.

### V13 — Use Case Coverage

This feature serves the V13 primary use cases:

- §3 Consulting Engagement
  (`docs/sacp-use-cases.md` §3) — consulting deliverables often
  include "what decisions did the orchestrator make and why."
  The history panel is the primary surface for that question.
  A consulting facilitator can demonstrate the orchestrator's
  detection coverage as part of the engagement summary.
- §5 Technical Review and Audit
  (`docs/sacp-use-cases.md` §5) — technical-review sessions
  treat every routing decision as auditable. The panel
  collapses the audit-log review step into a single in-UI
  pane.

Other use cases (§1, §2, §4, §6, §7) inherit the feature when
enabled but are not the priority drivers.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts.
This spec contributes three budgets:

- **Panel load (initial fetch)**: P95 ≤ 500ms for sessions
  with up to 1,000 detection events. The query is a bounded
  read-side join over `routing_log`, `convergence_log`, and
  `admin_audit_log` filtered by `session_id` (indexed). No
  cross-session joins. Budget enforcement: per-request timing
  captured in the existing access-log path (spec 006 §FR-018
  per-tool latency logs).
- **WS push latency on event emission**: P95 ≤ 100ms from
  source-table INSERT to client-rendered row. Reuses spec 011's
  existing per-session broadcast — no new hot-path overhead.
  Budget enforcement: comparison against spec 011's existing
  WS push baseline; regression flagged if 022's wiring adds
  measurable latency.
- **Re-surface action**: P95 ≤ 200ms from POST to WS broadcast
  emission. One `admin_audit_log` INSERT plus one WS push
  payload assembly. Budget enforcement: per-request timing
  on the new endpoint.

## Configuration (V16) — New Env Vars

Two new env vars are introduced. Each MUST have type, valid
range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this spec
(per V16 deliverable gate).

### `SACP_DETECTION_HISTORY_MAX_EVENTS`

- **Intended type**: positive integer, or empty for unbounded
- **Intended valid range**: `[1, 100000]` when set; empty
  means no cap. Default: empty (unbounded for active session).
- **Fail-closed semantics**: any non-integer or non-positive
  integer value MUST cause startup exit with a clear error.
  The cap protects against a runaway-detector scenario
  consuming unbounded UI memory; operators raising this value
  should monitor panel-load latency.

### `SACP_DETECTION_HISTORY_RETENTION_DAYS`

- **Intended type**: positive integer, or empty for indefinite
- **Intended valid range**: `[1, 36500]` when set; empty
  means indefinite retention. Default: empty (matches the
  general retention posture in `docs/retention.md` §7).
- **Fail-closed semantics**: any non-integer or non-positive
  integer value MUST cause startup exit. The retention
  window applies to archived sessions only — active-session
  events are never purged regardless of this value (mirrors
  the rolling-window-with-archive-cutoff pattern in spec 007's
  `SACP_SECURITY_EVENTS_RETENTION_DAYS`).

## Cross-References to Existing Specs and Design Docs

- **Spec 003 (turn-loop-engine) §FR-030** — `routing_log`
  per-stage timings include detector firing decisions;
  spec 022 reads these for `ai_question_opened` and
  `ai_exit_requested` events.
- **Spec 004 (convergence-cadence) §FR-020** — density-anomaly
  signals are written to `convergence_log` with
  `tier='density_anomaly'`. Spec 022 reads these rows for
  the `density_anomaly` panel class.
- **Spec 006 (mcp-server) §FR-013** — per-session WS broadcast
  carries new event-list-item shapes for live-update; spec 022
  reuses the channel rather than introducing a new one.
- **Spec 010 (debug-export)** — facilitator-only access pattern
  (§FR-2), session-bound check (§FR-3), and read-only contract
  (§FR-6 / §SC-007) are mirrored in spec 022 FR-002, FR-003,
  FR-004. The debug export already includes the same event
  rows; spec 022 surfaces them in the live UI rather than
  introducing a separate export.
- **Spec 011 (web-ui)** — the history panel is a new UI
  surface. Spec 022 defines the panel contract (endpoint
  shape, event-list shape, re-surface action); spec 011 owns
  the panel's wiring into the React SPA and the WS event
  channel integration. A spec 011 amendment lands when 022's
  tasks are scheduled.
- **Spec 029 (audit-log-viewer) §FR-019 / §FR-020** —
  shared-component contract pinned in
  [`specs/029-audit-log-viewer/contracts/shared-module-contracts.md`](../029-audit-log-viewer/contracts/shared-module-contracts.md).
  When spec 022 reaches `/speckit.tasks`, its amendment FR(s)
  MUST cite that contract document and:
  reuse `format_label` / `formatLabel` from the action-label
  registry for any audit-adjacent labels surfaced in the
  detection-event panel; reuse `format_iso` / `formatIso` from
  the time formatter for timestamp rendering; bind the
  `audit_log_appended` WS handler pattern (role-filter,
  decorated payload) when 022 introduces its own
  `detection_event` broadcast. Spec 022 MUST NOT reimplement
  these helpers inline (FR-020 architectural test enforces).
- **Spec 014 (dynamic-mode-assignment)** — when 014 lands and
  emits `mode_recommendation` and `mode_change` events,
  spec 022's `mode_change` class surfaces them. Forward-
  compatible per FR-015.
- **Spec 001 (core-data-model) §FR-008, §FR-019** — append-only
  invariant on log tables; the `admin_audit_log` carve-out for
  the re-surface forensic record (FR-006).
- **Spec 007 (ai-security-pipeline) §FR-015** — the
  `security_events` retention pattern that
  `SACP_DETECTION_HISTORY_RETENTION_DAYS` mirrors structurally.
- **Constitution §10** — Phase 3 deliverables list. Spec 022
  is in-scope for Phase 3 by virtue of Phase-3 declaration
  recorded 2026-05-05 (see also §14.1).
- **Constitution §14.1** — Feature work workflow. This spec
  scaffolds via `/speckit.specify`; `/speckit.clarify`,
  `/speckit.plan`, and `/speckit.tasks` are deferred.
- **Constitution V12** — topology applicability. Spec 022
  applies to topologies 1-6; incompatible with topology 7.
- **Constitution V13** — primary use cases consulting (§3) and
  technical review and audit (§5).
- **Constitution V14** — per-stage timing budgets. Spec 022
  contributes three budgets (Performance Budgets section).
- **Constitution V16** — env-var validation at startup. Spec 022
  introduces two new vars (Configuration section).

## Assumptions

- The detection event source-of-truth lives in existing log
  tables (`routing_log`, `convergence_log`, `admin_audit_log`).
  Spec 022 is a READ-side aggregation, not a parallel write
  path. Adding a new `detection_events` table would duplicate
  the source of truth and risk drift; the read-side join is
  the right cost trade-off given the bounded per-session
  query shape.
- The four v1 event classes cover the operational diagnostic
  surface for Phase 3. Adding new classes (e.g., spec 021's
  filler-retry events, spec 015's circuit-breaker state
  transitions) is a future amendment, not v1 scope.
- The re-surface action is operator-only — the participant's
  AI does not see re-surfaced events. Re-surface is a
  human-side decision-review tool, not an AI-side context
  injection. Future participant-side notifications on
  re-surface (if needed) is a separate feature.
- Multi-instance Phase 3 deployments may have re-surface
  routing constraints. v1 ships single-instance; multi-
  instance re-surface lands when spec 011's `SessionStore`
  Redis backend lands. The panel's READ surface works in
  multi-instance from day one (DB-backed); re-surface WS
  broadcast does not.
- The display length cap on trigger snippets (200 chars,
  client-side) is informational. The server returns the full
  snippet; UI truncation is a presentation concern, not a
  privacy/security concern (the snippet is already in the
  audit-log payload and is exposed via debug-export).
- Phase 3 declared 2026-05-05 satisfies the phase gate; this
  spec stays scaffold-only until tasks are scheduled. No
  implementation begins on this spec until the user invokes
  `/speckit.clarify` and subsequent workflow steps.
- Status remains Draft until clarifications resolve and the
  user accepts the scaffolding. The "Phase 3 declared
  2026-05-05" notation in the Status field is informational;
  it does not itself flip the spec to Implemented (per
  `feedback_dont_declare_phase_done.md`, the status flip is
  the user's call).
