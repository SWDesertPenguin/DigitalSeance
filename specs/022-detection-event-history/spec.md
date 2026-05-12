# Feature Specification: Detection Event History Surface

**Feature Branch**: `022-detection-event-history`
**Created**: 2026-05-07
**Status**: Clarified 2026-05-10; Amended 2026-05-11 (§1 source-of-truth reversal — dedicated `detection_events` table replaces the read-side join after a schema-reality audit uncovered missing persistence; implementation in progress)
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
   mode-recommendation / mode-change), participant, time range,
   and disposition so an operator can compute per-detector noise
   rates by counting dismissed-as-false-positive events of one
   class and slice the timeline by who/when/outcome.
4. **Respects** the existing event-retention story (spec 010 already
   includes these events in the debug-export payload; spec 022 reads
   the same source rather than introducing a new persistence path).

The panel is **read-only** for stored event content. The operator
can mark an event's disposition (e.g., "false positive") via the
re-surface action's audit trail, but cannot modify the original
trigger snippet, score, or timestamp. Append-only is preserved per
spec 001 §FR-008.

This spec is **Clarified** (Session 2026-05-10). Implementation
begins when the facilitator schedules `/speckit.plan` and
`/speckit.tasks` per Constitution §14.1. The Phase 3 declaration
recorded 2026-05-05 satisfies the phase gate; this spec stays
pre-implementation until tasks land and implementation reaches
Implemented status.

## Clarifications

### Session 2026-05-11 (Amendment — reverses Session 2026-05-10 §1)

Implementation-time schema audit during spec 022 Sweep 1 (T004 index audit) revealed that the read-side-join premise in the Session 2026-05-10 §1 resolution does not match the deployed schema:

- `routing_log` has no `detector_kind`, `trigger_snippet`, or `detector_score` columns. Question (A2) and exit (A3) detection signals fire in [src/orchestrator/loop.py:1400-1424](../../src/orchestrator/loop.py#L1400-L1424) as WebSocket broadcasts only — they are not persisted to any table.
- `convergence_log` density-anomaly rows (per alembic 010_density_signal) have `(turn_number, session_id, tier, density_value, baseline_value)` and no participant attribution, trigger snippet, or standalone timestamp column.
- `admin_audit_log` uses `target_id` / `facilitator_id`, not the `target_event_id` / `actor_id` column names the §1 query plan referenced.

The Session 2026-05-10 §1 resolution was made on an incorrect schema model. This amendment **reverses §1** and adopts the alternative that was considered and rejected then: a dedicated `detection_events` table that the four detector emitters write to in parallel with their existing WS broadcasts. Rationale:

1. The original §1 rejection cited "duplicates the source of truth and breaks spec 001 §FR-008's append-only invariant." With actual persistence absent for two of the five event classes, there is no existing source of truth to duplicate — `detection_events` becomes the source of truth. The append-only invariant is preserved (no UPDATEs except the `disposition` column which tracks the latest transition; the audit trail of transitions still flows through `admin_audit_log`).
2. Dual-write coordination cost is bounded (each emit-site adds one INSERT alongside the WS broadcast; failure of the INSERT must NOT block the broadcast for backward compatibility — see updated FR-017).
3. The query surface collapses from a three-table UNION-ALL to a single `WHERE session_id = $1` lookup, simplifying both the page-load path and the cross-instance broadcast payload (the synthesized event-id from the old §1 plan becomes the table's primary key id).

This amendment commits the spec to one alembic migration (new table + indexes) plus a call-site sweep at the four detector emit sites (question, exit, density anomaly, mode events). `tests/conftest.py` raw DDL gains the mirrored schema per `feedback_test_schema_mirror`.

Downstream FRs and sections that change:

- **FR-005** clarified: event classes derive from the persisted `detection_events.event_class` column (one of the five fixed values).
- **FR-006** clarified: the synthesized event-id `<source_table>:<source_row_id>` is replaced by the integer primary key of `detection_events`. `admin_audit_log.target_id` (existing column) carries the stringified id for re-surface rows.
- **FR-009** + **FR-017** rewritten: live-update WS broadcast happens after the `detection_events` INSERT commits; FR-017 mandates the new table and the dual-write contract.
- **Key Entities — DetectionEvent** becomes a persisted entity (was: read-side projection).
- **Performance Budgets** simplified: panel-load query is now a single indexed `SELECT` rather than a three-source UNION-ALL.

The Session 2026-05-10 resolutions for §§2-8 (operator-only re-surface, fixed five-class taxonomy, four filter axes, four-value disposition, multi-instance-from-day-one, active-only re-surface, distinct mode-event classes) all stand unchanged.

### Session 2026-05-10 (Resolved)

All eight initial-draft markers resolved. FR text is updated inline below; the original "Initial draft assumptions requiring confirmation" subsection is retained for historical reference.

1. **Event source of truth**. Read-side join over existing log tables confirmed. The panel queries `convergence_log` (for `density_anomaly`), `routing_log` (for `ai_question_opened` and `ai_exit_requested`), and `admin_audit_log` (for disposition transitions and `mode_recommendation` / `mode_change` rows from spec 014). No new `detection_events` table. Rationale: append-only invariant on existing logs (spec 001 §FR-008) makes them the source of truth; a parallel table would require dual-write coordination and risk drift. The read-side join is a bounded per-session query — join cost is acceptable for v1's per-session diagnostic surface. Future high-volume cross-session analytics can introduce a materialized view as an optimization, not a source change. FR-017 stands as drafted.

2. **Re-surface semantics**. Operator-only re-surface confirmed. Re-broadcast goes to the facilitator's WS as a banner; participant AIs do not see re-surfaced events. Re-surface is a human-side decision-review tool, not an AI-side context injection. Future participant-side notifications on re-surface (if needed) are a separate feature, not v1 scope. FR-006 stands as drafted with one tightening: the WS broadcast target is the facilitator's per-session channel, not the participant's WS channel. (The drafted "over the participant's WS channel" phrasing in §Overview and the original FR-006 wording is corrected — the participant channel was the wrong target; the facilitator channel is the correct one given operator-only scope.)

3. **Event taxonomy completeness**. Fixed five-class v1 taxonomy confirmed (NOT extensible registry; NOT four-class). Per the §8 resolution below, `mode_recommendation` and `mode_change` ship as two distinct panel classes rather than merging into one. v1 ships with: `ai_question_opened`, `ai_exit_requested`, `density_anomaly`, `mode_recommendation`, `mode_change`. Future detectors (e.g., spec 021's filler-retry events, spec 015's circuit-breaker state transitions) join via a follow-up spec amendment, not via runtime registry. Rationale: extensible registry adds API + UI surface that must handle unknown classes gracefully and a parity gate beyond spec 029's existing audit-label parity; a fixed taxonomy keeps v1 predictable and the surface explicit. FR-005, FR-011, and `EventClassRegistry` are updated to the five-class set.

4. **Filter granularity in P3**. Fuller filter axis set confirmed (NOT type-only). v1 ships filter-by-type + filter-by-participant + filter-by-time-range + filter-by-disposition. Rationale: the disposition filter is load-bearing for the noise-rate analysis use case (US3) — filtering to "dismissed density_anomaly events" without disposition filtering requires manual counting in the panel. Participant filtering serves the per-AI behavior-review case. Time-range filtering serves the "what happened around turn N" reconstruction case the spec explicitly motivates. FR-011 is updated from "type-only" to the four-axis filter set; SC-006's client-side O(1) update budget extends to all four axes.

5. **Disposition vocabulary**. Four-value enum confirmed: `pending` (event fired, banner shown, no operator action yet), `banner_acknowledged` (operator clicked acknowledge), `banner_dismissed` (operator clicked dismiss without acknowledging), `auto_resolved` (underlying condition cleared without operator action — e.g., density-anomaly score dropped below threshold on the next turn). Two-value (`resolved` / `unresolved`) was rejected because it discards exactly the data the spec cites for false-positive identification (operator-engaged vs. operator-ignored vs. self-healed). FR-010 stands as drafted. The disposition filter introduced in §4 above accepts any of the four values plus `all`.

6. **Multi-instance session affinity**. Design-for-multi-instance-from-the-start confirmed (NOT single-instance v1). v1 re-surface MUST work across orchestrator instances on day one, ahead of when spec 011's `SessionStore` Redis backend was originally planned to introduce a shared store. Rationale: re-surface is a low-frequency operator action; a process-router or pub/sub layer for re-surface broadcast is cheap to add and avoids a Phase 3+ rework once multi-instance traffic arrives. The architecture pattern is: re-surface POST resolves the facilitator's currently-bound orchestrator process via a small lookup (DB-backed session→instance binding OR a pub/sub channel scoped to the session id), then forwards the WS broadcast emission to that process. Specific mechanism (DB-backed routing table, Redis pub/sub, or the simpler same-process fast path with a process-binding lookup at re-surface time) is settled in `/speckit.plan` research. This adds a new dependency-surface decision item to research.md: which broadcast mechanism, and how it integrates with the existing single-process WS broadcast path in spec 011. The §Assumptions section is updated to remove the "v1 ships single-instance" carve-out; a new Performance Budget (V14) covers the cross-instance re-surface latency target.

7. **Active-vs-archived sessions**. Active-only re-surface confirmed; read-only history on archived sessions. The archived-session panel shows the full event list but the re-surface button is disabled with an explanatory tooltip ("re-surface requires an active session"). FR-008 stands as drafted (re-surface on archived returns HTTP 409). The append-only invariant on `admin_audit_log` preserves re-surface history when an active session is later archived (US2 acceptance scenario 3 stands).

8. **Mode-change event forward compatibility**. Two distinct panel classes confirmed (NOT one merged class). Spec 014's `mode_recommendation` (advisory mode) and `mode_change` (auto-apply mode) ship as separate event-class names in the v1 taxonomy rather than merging under one `mode_change` class with a `mode_action_kind` discriminator. Rationale: the two events represent different operator-facing semantics (an advisory suggestion the facilitator can act on vs. a system-applied state change the facilitator observes); merging them under one filter type forces operators to apply a sub-filter to separate them in the per-detector noise-rate analysis case. The taxonomy in §3 above bumps from four classes to five accordingly. FR-005 and FR-015 are updated; the §Edge Cases entry on spec 014 forward-compat is rewritten; the §Cross-References to spec 014 is updated to reflect the two-class mapping.

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
2. **Given** a session with multiple events across the five
   tracked classes, **When** the panel opens, **Then** events
   MUST appear in chronological order (oldest first OR newest
   first per `/speckit.plan` decision; one ordering, not a
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
with mixed event types, participants, dispositions, and a
timeline spanning at least one hour. Exercise each filter
axis: (a) type — select one of five values, verify the
displayed set narrows; (b) participant — select one of the
session's participants, verify only their events appear;
(c) time range — narrow to a sub-window, verify only events
in that window appear; (d) disposition — select one of four
values, verify only events with that current disposition
appear. Combine two axes and verify AND semantics. Clear
all filters and verify the full event set returns.

**Acceptance Scenarios**:

1. **Given** a session with events across all five tracked
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
5. **Given** a session with events from multiple participants,
   **When** the facilitator selects a participant filter,
   **Then** the panel MUST display only events for the selected
   participant; `all participants` MUST return the full set.
6. **Given** an event timeline spanning at least one hour,
   **When** the facilitator narrows the time-range filter,
   **Then** the panel MUST display only events whose timestamps
   fall within the range; the badge contract from scenario 3
   MUST extend to time-range filtering.
7. **Given** a mixed-disposition event set, **When** the
   facilitator selects a single disposition value, **Then** the
   panel MUST display only events with that current disposition;
   the four-value enum from FR-010 plus `all` MUST be the only
   accepted inputs.
8. **Given** type, participant, time-range, and disposition
   filters all active simultaneously, **When** the panel
   renders, **Then** filters MUST compose with AND semantics
   (event survives display only if it matches ALL active
   filters).

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
- **Spec 014 mode-event mapping.** Spec 014 (Implemented
  2026-05-08) emits `mode_recommendation` (advisory mode) and
  `mode_change` (auto-apply mode) rows to `admin_audit_log`.
  Per Clarifications §8, 022 surfaces them as TWO distinct
  event classes in the v1 taxonomy with separate filter values
  and labels. Adding new mode-event types in a future spec 014
  amendment requires a corresponding 022 amendment (the
  taxonomy is fixed per Clarifications §3).
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
- **FR-005**: The endpoint MUST surface events from the five
  v1 classes: `ai_question_opened`, `ai_exit_requested`,
  `density_anomaly`, `mode_recommendation`, and `mode_change`.
  `mode_recommendation` (advisory mode signal from spec 014)
  and `mode_change` (auto-apply mode signal from spec 014) are
  distinct classes with separate filter values and separate
  panel labels — they are NOT merged under one class with a
  discriminator (per Clarifications §8).
- **FR-006**: A new HTTP endpoint MUST expose re-surface at
  `POST /tools/admin/detection_events/<event_id>/resurface`
  where `<event_id>` is the integer primary key of the
  `detection_events` table row. Re-surface re-broadcasts the
  original banner shape over the **facilitator's** per-session
  WS channel (participant AIs do NOT see the re-surfaced event,
  per Clarifications §2) AND emits an `admin_audit_log` row
  with `action='detection_event_resurface'`,
  `facilitator_id=<facilitator>`, `target_id=<event_id>`,
  `timestamp=NOW()` (column names match the existing
  `admin_audit_log` schema per the Session 2026-05-11
  amendment). The WS broadcast MUST work across orchestrator
  instances (multi-instance from v1, per Clarifications §6);
  the cross-instance routing mechanism is settled in
  `/speckit.plan` research.
- **FR-007**: Re-surface MUST be facilitator-only and
  session-bound (mirrors FR-002 + FR-003).
- **FR-008**: Re-surface MUST be rejected for archived
  sessions with HTTP 409 and a clear error explaining
  re-surface requires an active session.
- **FR-009**: The history panel MUST update via the existing
  spec 011 WS event channel when a new `detection_events` row
  is INSERTed for the active session. The broadcast emission
  happens after the INSERT commits (per Session 2026-05-11
  amendment dual-write contract). No new WS channel is
  introduced; the existing per-session broadcast (spec 006
  §FR-013, spec 011) carries the new event-list-item shape.
  The broadcast MUST work across orchestrator instances
  (multi-instance from v1, per Clarifications §6); the
  cross-instance routing mechanism is shared with re-surface
  (FR-006) and is settled in `/speckit.plan` research.
- **FR-010**: The disposition column MUST take one of four
  values: `pending`, `banner_acknowledged`, `banner_dismissed`,
  `auto_resolved`. Disposition transitions MUST be tracked as
  separate audit-log rows; the panel reads the latest row to
  determine current disposition AND can show the full
  disposition timeline on click-expand.
- **FR-011**: v1 ships four filter axes (per Clarifications §4):
  (a) **type filter** — one of the five v1 event-class names
  (`ai_question_opened`, `ai_exit_requested`, `density_anomaly`,
  `mode_recommendation`, `mode_change`) OR `all`; (b)
  **participant filter** — one of the session's participant ids
  OR `all`; (c) **time-range filter** — a `{from, to}` pair
  (either bound may be open); (d) **disposition filter** — one
  of the four values (`pending`, `banner_acknowledged`,
  `banner_dismissed`, `auto_resolved`) OR `all`. Filters compose
  with AND semantics. All four axes apply client-side once the
  per-session event set is loaded (no server-side filter
  pushdown in v1; pushdown is a future enhancement gated on the
  per-session set exceeding `SACP_DETECTION_HISTORY_MAX_EVENTS`).
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
- **FR-015**: Spec 014 mapping — when 014's emitters write
  `mode_recommendation` and `mode_change` rows to
  `admin_audit_log`, the 022 endpoint MUST surface them as
  two distinct event classes (not one merged class — per
  Clarifications §8). The mapping between 014's audit-log
  action strings and 022's panel-class names is hardcoded in
  `src/web_ui/detection_events.py`. Spec 014's implementation
  is already landed (Implemented 2026-05-08), so this is a
  v1 wire-up, not a forward-compat carve-out.
- **FR-016**: The three new env vars
  (`SACP_DETECTION_HISTORY_ENABLED`,
  `SACP_DETECTION_HISTORY_MAX_EVENTS`,
  `SACP_DETECTION_HISTORY_RETENTION_DAYS`) MUST have
  validator functions in `src/config/validators.py` registered
  in the `VALIDATORS` tuple, AND corresponding sections in
  `docs/env-vars.md` with the six standard fields, BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable
  gate). When `SACP_DETECTION_HISTORY_ENABLED=false` (default),
  both endpoints return HTTP 404 AND the SPA admin-panel
  entry-point is hidden (fail-closed master switch, mirrors
  spec 029 FR-018).
- **FR-017** (REVISED per Session 2026-05-11 amendment): A
  new `detection_events` table MUST persist every detection
  event of the five v1 classes. The four detector emit sites
  (question/exit in [src/orchestrator/loop.py](../../src/orchestrator/loop.py),
  density anomaly in [src/orchestrator/density.py](../../src/orchestrator/density.py),
  mode events in spec 014's emit sites) each INSERT one row
  into `detection_events` before issuing the existing WS
  broadcast. Dual-write contract: if the INSERT fails (e.g.,
  DB unavailable), the WS broadcast still fires (backward
  compatibility for current banner UX) and the failure is
  logged as a security-event so the gap is observable but
  not fatal. The append-only invariant on detection events
  is preserved by allowing UPDATE only on the `disposition`
  column (latest-state denormalization); transition history
  flows through `admin_audit_log` per FR-010.

### Key Entities

- **DetectionEvent** (persisted entity in the new
  `detection_events` table per Session 2026-05-11 amendment)
  — the shape returned by the FR-001 endpoint: `id` (bigint
  primary key), `session_id`, `event_class` (one of five
  fixed values), `participant_id`, `trigger_snippet`,
  `detector_score`, `turn_number` (nullable for mode events),
  `timestamp`, `disposition` (latest-state denormalization),
  `last_disposition_change_at`. Source-of-truth table for
  the five-class taxonomy; emit-sites dual-write per FR-017.
- **EventDisposition** — `pending` | `banner_acknowledged` |
  `banner_dismissed` | `auto_resolved`. Sourced from the latest
  disposition-transition row in `admin_audit_log` for the
  event id.
- **ResurfaceAction** — `admin_audit_log` row with
  `action='detection_event_resurface'`, `facilitator_id`,
  `target_id` (stringified `detection_events.id`),
  `timestamp`. Append-only per spec 001 §FR-008.
- **EventClassRegistry** (process-scope, hardcoded) — maps
  source rows to one of the five v1 panel classes
  (`ai_question_opened`, `ai_exit_requested`,
  `density_anomaly`, `mode_recommendation`, `mode_change`).
  Defined in `src/web_ui/detection_events.py`. Adding a class
  requires a spec amendment (per Clarifications §3 — fixed
  taxonomy, not extensible registry).

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
- **SC-006**: All four v1 filter axes (type, participant, time
  range, disposition) MUST update the panel in O(1) client-side
  time (no server round-trip; filtering applies over the
  already-loaded per-session event set). Verified by inspecting
  the network panel during filter toggles across all axes.
- **SC-007**: Spec 014's `mode_recommendation` and `mode_change`
  rows MUST surface in the panel as two distinct event classes
  (per Clarifications §8). Verified by running a 014 session
  with auto-apply enabled and asserting the recommendations
  appear in the panel as `mode_recommendation` class entries
  and the auto-apply changes appear as `mode_change` class
  entries.
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
- **SC-010**: Re-surface MUST succeed when the facilitator's
  WS is bound to a different orchestrator process than the one
  handling the POST (multi-instance contract per Clarifications
  §6). Verified by a test that runs two orchestrator processes
  against a shared DB, binds a facilitator's WS to process B,
  drives the re-surface POST through process A, and asserts
  the WS broadcast lands on process B's facilitator channel
  within the cross-instance Performance Budget.

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
- **Re-surface action (same-instance fast path)**: P95 ≤ 200ms
  from POST to WS broadcast emission when the facilitator's WS
  is bound to the same orchestrator process that handled the
  POST. One `admin_audit_log` INSERT plus one WS push payload
  assembly. Budget enforcement: per-request timing on the new
  endpoint.
- **Re-surface action (cross-instance)**: P95 ≤ 500ms from POST
  to WS broadcast emission when the facilitator's WS is bound
  to a different orchestrator process than the one handling
  the POST (multi-instance support per Clarifications §6).
  Budget enforcement: per-request timing on the new endpoint
  with the routing path instrumented. Cross-instance budget is
  intentionally looser than same-instance to absorb the routing
  mechanism's latency.

## Configuration (V16) — New Env Vars

Three new env vars are introduced. Each MUST have type, valid
range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this spec
(per V16 deliverable gate).

### `SACP_DETECTION_HISTORY_ENABLED`

- **Intended type**: boolean (`true` / `false`)
- **Intended valid range**: `{true, false}`. Default: `false`.
- **Fail-closed semantics**: when `false` (default), both
  `GET /tools/admin/detection_events` and
  `POST /tools/admin/detection_events/<event_id>/resurface`
  return HTTP 404 AND the SPA admin-panel entry-point ("View
  detection history") is hidden. Operators must explicitly
  enable the panel surface; mirrors spec 029's
  `SACP_AUDIT_VIEWER_ENABLED` master-switch pattern. Any value
  outside `{true, false}` MUST cause startup exit with a clear
  error.

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
- **Spec 014 (dynamic-mode-assignment)** (Implemented
  2026-05-08) — emits `mode_recommendation` and `mode_change`
  rows to `admin_audit_log`. Spec 022 surfaces them as TWO
  distinct event classes in the v1 taxonomy (per Clarifications
  §8); the mapping from 014's audit-log action strings to 022's
  class names is hardcoded in `src/web_ui/detection_events.py`
  per FR-015.
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
  scaffolds via `/speckit.specify`; clarifications resolved
  2026-05-10; `/speckit.plan` and `/speckit.tasks` are pending.
- **Constitution V12** — topology applicability. Spec 022
  applies to topologies 1-6; incompatible with topology 7.
- **Constitution V13** — primary use cases consulting (§3) and
  technical review and audit (§5).
- **Constitution V14** — per-stage timing budgets. Spec 022
  contributes three budgets (Performance Budgets section).
- **Constitution V16** — env-var validation at startup. Spec 022
  introduces two new vars (Configuration section).

## Assumptions

- The detection event source-of-truth lives in the NEW
  `detection_events` table per the Session 2026-05-11
  amendment (reverses the original §1 read-side-join
  decision). The implementation-time schema audit found that
  question/exit detections were never persisted (broadcast-
  only) and density-anomaly rows lacked participant
  attribution + trigger snippets, so there was no existing
  source of truth to read from. The new table consolidates
  the five-class taxonomy under one indexed surface; emit
  sites dual-write per FR-017.
- The five v1 event classes (`ai_question_opened`,
  `ai_exit_requested`, `density_anomaly`, `mode_recommendation`,
  `mode_change`) cover the operational diagnostic surface for
  Phase 3. Adding new classes (e.g., spec 021's filler-retry
  events, spec 015's circuit-breaker state transitions) is a
  future amendment, not v1 scope.
- The re-surface action is operator-only — the participant's
  AI does not see re-surfaced events. Re-surface is a
  human-side decision-review tool, not an AI-side context
  injection. Future participant-side notifications on
  re-surface (if needed) is a separate feature.
- Multi-instance Phase 3 deployments are supported on day one
  (per Clarifications §6 — design-for-multi-instance-from-the-
  start). Both the panel's READ surface (DB-backed) and the
  re-surface WS broadcast (cross-instance via a routing
  mechanism settled in `/speckit.plan` research) work across
  orchestrator instances in v1. Specific cross-instance
  broadcast mechanism (DB-backed session→instance binding,
  Redis pub/sub, or a hybrid) is a research item; the spec
  commits only to the contract — re-surface MUST work
  regardless of which instance the facilitator is bound to.
- The display length cap on trigger snippets (200 chars,
  client-side) is informational. The server returns the full
  snippet; UI truncation is a presentation concern, not a
  privacy/security concern (the snippet is already in the
  audit-log payload and is exposed via debug-export).
- Phase 3 declared 2026-05-05 satisfies the phase gate;
  clarifications resolved 2026-05-10 (Session above). Spec
  stays pre-implementation until `/speckit.plan` and
  `/speckit.tasks` run.
- The "Phase 3 declared 2026-05-05" notation in the Status
  field is informational; it does not itself flip the spec
  to Implemented (per `feedback_dont_declare_phase_done.md`,
  the status flip is the user's call after tasks are saturated).
