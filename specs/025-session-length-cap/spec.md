# Feature Specification: Session-Length Cap with Auto-Conclude Phase

**Feature Branch**: `025-session-length-cap`
**Created**: 2026-05-07
**Status**: Draft (Phase 3 declared 2026-05-05; scaffold ships now, tasks + implementation deferred)
**Input**: User description: "Phase 3 session-length cap with auto-conclude phase. Unbounded sessions accumulate cost as transcripts grow and rarely produce clean endings; operators stop the loop under budget/context pressure and lose the chance for AIs to hand off coherent conclusions. Configurable cap turns 'ran out of budget' into 'got planned closure'. Default: no cap. Two cap dimensions (OR'd, whichever fires first): wall-clock time since loop start, total AI turn count. Presets: Short / Medium / Long / Custom. At ~80% of the configured cap, the orchestrator transitions the session into a conclude phase: a Tier 4 prompt delta tells AIs the session is wrapping and asks each for a position summary + final conclusion. After every active AI has produced a conclusion turn, the existing spec 005 summarizer fires one final time and the loop pauses. Facilitator can extend the cap or stop_loop manually at any point. Applies to topologies 1-6 (orchestrator-mediated state); incompatible with topology 7. Primary use cases: consulting (§3), research co-authorship (§2), technical review and audit (§5)."

## Overview

Today the orchestrator's turn loop has three lifecycle states:
running, paused, and stopped (per spec 003 §FR-021 lifecycle and
spec 006 §FR-007 session control). The loop runs until a
facilitator pauses or stops it, until a budget enforcer (003
§FR-028) trips, or until a context-window pressure forces a
manual intervention. None of these endings produce a coherent
conclusion: the AIs were not told the session was ending, so
their last turns are mid-thought rather than wrap-up.

A Phase 1+2 shakedown surfaced this directly: long sessions that
consumed budget faster than expected ended in a state where each
AI's last turn was a continuation rather than a closure. The
operator wanted "this session ends in 5 turns, please each give a
final position" but had no surface to express it.

This spec defines a **session-length cap** that turns implicit
endings into explicit ones. Two dimensions can be set (default:
neither):

1. **Time cap** — wall-clock seconds since `start_loop` was
   first invoked. Pause-resume cycles do not advance the
   wall-clock counter (paused time is not consumed); only
   active loop time counts.
2. **Turn cap** — count of AI turns dispatched (excludes human
   interjections and system messages, mirrors the spec 003
   FR-001 "AI turn" definition).

When both are set, **whichever fires first triggers the
conclude phase**. Either alone can be set; both can be unset
(default — no cap).

The conclude phase is a new loop state alongside running /
paused / stopped:

- **Trigger**: when elapsed time crosses
  `SACP_CONCLUDE_PHASE_TRIGGER_FRACTION` × `length_cap_seconds`
  OR turn count crosses
  `SACP_CONCLUDE_PHASE_TRIGGER_FRACTION` × `length_cap_turns`
  (default fraction: 0.80).
- **Behavior**: a Tier 4 prompt delta is appended to each
  active AI's prompt assembly:
  > "The session is approaching its conclusion. In your next
  > turn, please summarize your position to date and offer a
  > final conclusion. The orchestrator will pause the loop after
  > every participant has had a turn to wrap up."
- **Cadence**: spec 004's adaptive cadence is suspended during
  conclude phase. Each active AI gets exactly one turn (per
  the existing round-robin); after the last one, the loop
  triggers spec 005's summarizer one final time. After the
  summarizer completes (success or fail-closed per spec 005
  §FR-007), the loop transitions to **paused** with
  `routing_log.reason='auto_pause_on_cap'`.
- **Facilitator override**: at any point during conclude phase,
  the facilitator can extend the cap (returning the loop to
  running phase) or call `stop_loop` (forcing the final
  summarizer to run before the pause transition).

The cap is **strictly opt-in**. Default is no cap (preserves
the existing run-until-explicitly-stopped behavior). Setting a
cap is a per-session decision via the facilitator's
session-create or session-settings panel; operators can set
deployment-wide defaults via env vars but those defaults can
always be overridden by the facilitator on the session itself.

This spec **scaffolds only**. Implementation begins when the
facilitator schedules tasks per Constitution §14.1. The
Phase 3 declaration recorded 2026-05-05 satisfies the phase
gate; this spec stays scaffold-only until tasks land and
implementation reaches Implemented status.

## Clarifications

### Session 2026-05-07

- Q: When both time and turn caps are set, which dimension triggers the conclude phase? → A: OR semantics — whichever crosses its trigger fraction first; auto-pause at 100% also OR.
- Q: How much of the cap configuration is visible to participants? → A: Facilitator-only cap values; participants receive a WS event on conclude entry and a UI banner with remaining countdown. `/me` does not include `length_cap_*` fields.
- Q: Cap-set with new value below current elapsed (e.g., turn-cap=20 set at turn 30) — what behavior? → A: Endpoint MUST disambiguate intent before committing. Two interpretations are offered to the facilitator: (a) **absolute** — accept the value as the new total cap; elapsed already exceeds 100%, so transition immediately to conclude phase; (b) **relative** — interpret the value as N additional turns/seconds beyond current elapsed (effective cap = current_elapsed + N). The facilitator picks one. Endpoint does NOT auto-pick.
- Q: Manual `stop_loop` during conclude phase — does the final summarizer still run? → A: Yes. Orchestrator MUST run the spec 005 summarizer on the conclusions produced so far before transitioning to stopped (`routing_log.reason='manual_stop_during_conclude'`). Preserves the wrap-up-artifact promise even on early manual abort.
- Q: Conclude-turn provider error after spec 003 §FR-031 retry cap exhausted — abort or continue? → A: Skip-and-continue. The failed participant is skipped, the orchestrator proceeds to the next participant's conclude turn, and the spec 005 summarizer still fires after the last attempt (success or skip). Reuses existing dispatch-failure semantics.

### Initial draft assumptions requiring confirmation

- **Cap extension during conclude phase.** A facilitator
  extends the cap from 20 → 50 turns at turn 19 (already in
  conclude phase). Drafted as: the loop transitions back to
  running phase; the conclude prompt delta is removed from
  the next assembly; spec 004's adaptive cadence resumes. The
  event is logged with
  `routing_log.reason='conclude_phase_exited'`. [NEEDS
  CLARIFICATION: confirm clean-exit-back-to-running vs.
  stay-in-conclude-until-explicit-stop.]
- **Preset concrete values.** Drafted defaults:
  - Short: 30 minutes OR 20 turns
  - Medium: 2 hours OR 50 turns
  - Long: 8 hours OR 200 turns
  - Custom: hand-set
  These map to the V13 use case shapes: Short fits
  consulting working sessions, Medium fits research synthesis
  pushes, Long fits a full audit pass. [NEEDS CLARIFICATION:
  confirm preset values vs. operator-tunable preset table
  vs. different defaults entirely.]
- **Time-cap behavior across pause-resume.** Drafted as: the
  wall-clock counter advances only while the loop is in
  running OR conclude phase. Pause time is not consumed.
  Implementation: track an `active_seconds` accumulator
  rather than a `started_at` timestamp; increment during
  running/conclude tickets only. [NEEDS CLARIFICATION:
  confirm active-time-only vs. wall-clock-from-start
  vs. operator-configurable.]
- **Conclude phase delta tier attachment.** User input
  recommends Tier 4. Drafted as: the conclude delta is a
  Tier-4-additive block (placed after any custom_prompt and
  any spec 021 register-slider delta). It does NOT replace
  the participant's tier text or custom prompt. [NEEDS
  CLARIFICATION: confirm Tier-4-additive vs. tier-replace
  vs. operator-configurable tier attachment.]
- **Composition with spec 021 register slider.** Drafted as:
  the conclude delta and the spec 021 register delta both
  attach at Tier 4 in additive order: register delta first
  (sets tone), conclude delta second (adds wrap-up
  instruction). The register's tone applies to the conclude
  turn — a "Direct" register conclude is terse, an "Academic"
  register conclude is formal. [NEEDS CLARIFICATION: confirm
  additive composition vs. conclude-overrides-register.]
- **Phase 1+2 shakedown reference.** The shakedown is
  summarized in the Overview without citing the specific test
  session ID (matches the project memory default of not
  exposing test artefacts in committed specs). Confirm this
  paraphrase is acceptable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Facilitator sets a turn cap at session create; conclude phase fires at 80% and final summarizer runs at 100% (Priority: P1)

A facilitator creates a new technical-review session. In the
session-create modal they pick the Short preset (20-turn cap).
The loop runs normally. At turn 16 (80% of 20), the conclude
phase triggers automatically: each active AI's next dispatch
includes the Tier 4 conclude delta asking them to summarize
their position and offer a final conclusion. After every
active AI has produced a conclude turn (turns 17-N), the
orchestrator runs spec 005's summarizer one final time. The
loop transitions to paused with
`routing_log.reason='auto_pause_on_cap'`. The session is
ready for archival; the facilitator has a clean wrap-up
artifact.

**Why this priority**: P1 because this IS the spec's primary
value. Without this story, the spec ships zero. The
"transitions to conclude phase + runs final summarizer +
pauses" sequence is the entire mechanism the spec exists to
introduce.

**Independent Test**: Drive a session-create with the Short
preset (20-turn cap). Run AI turns up through 16. At the
turn-17 dispatch, assert the participant's assembled prompt
contains the Tier 4 conclude delta. Run remaining conclude
turns; assert each participant's last turn before pause
contains the conclude delta. After the last conclude turn,
assert the summarizer fires (a new message with
`speaker_type='summary'` is written). After summarizer
completes, assert the loop is paused with
`routing_log.reason='auto_pause_on_cap'`.

**Acceptance Scenarios**:

1. **Given** a session created with `length_cap_kind='turns'`
   and `length_cap_turns=20`, **When** turn 16 fires, **Then**
   the loop MUST transition to conclude phase AND
   `routing_log` MUST record
   `reason='conclude_phase_entered'` with the trigger value.
2. **Given** the session is in conclude phase, **When** any
   AI dispatch fires, **Then** the assembled prompt MUST
   contain the Tier 4 conclude delta in addition to the
   participant's existing tier text and custom prompt.
3. **Given** every active AI has produced a conclude turn,
   **When** the loop's next iteration runs, **Then** spec
   005's summarizer MUST fire AND a new message with
   `speaker_type='summary'` MUST be persisted.
4. **Given** the final summarizer has completed, **When**
   the loop's next iteration runs, **Then** the loop MUST
   transition to paused AND `routing_log` MUST record
   `reason='auto_pause_on_cap'`.
5. **Given** the loop is in conclude phase, **When** spec
   004's adaptive cadence is queried, **Then** cadence MUST
   be suspended (delays return immediately to the floor for
   responsive wrap-up).
6. **Given** no cap was set on a session, **When** any
   number of turns dispatch, **Then** no conclude phase MUST
   trigger AND the loop MUST run until manual pause/stop —
   preserving the pre-feature behavior for operators who
   don't opt in.

---

### User Story 2 - Facilitator sets a time cap mid-session; loop respects the new cap from the moment it's set (Priority: P1)

A research co-authorship session has been running for 90
minutes and has accumulated good material. The facilitator
wants to wrap in another 30 minutes. They open
session-settings, set a time cap to 2 hours (so 30 minutes
of running time remain), and submit. The loop continues
running. When elapsed time crosses 96 minutes (80% of 120
minutes), the conclude phase triggers. The same conclude →
final-summarizer → pause sequence runs.

**Why this priority**: P1 because mid-session cap-setting is
the most common case operationally. Most facilitators do not
know at session-create time when they want to wrap; they
decide as the session unfolds. Without P2, the spec's value
is constrained to the create-time decision; with P2 the
spec works for the way humans actually run sessions.

**Independent Test**: Drive a session that has been running
for 90 minutes. Set
`length_cap_kind='time', length_cap_seconds=7200` (2 hours)
via session-settings. Assert
`routing_log.reason='cap_set'` is recorded. Advance the
clock to 95 minutes; assert no conclude. Advance to 96
minutes (80% of 120); assert conclude phase triggers. Run
through to summarizer + pause as in US1.

**Acceptance Scenarios**:

1. **Given** an active session with no cap, **When** the
   facilitator sets a time cap mid-session, **Then** the
   `sessions.length_cap_*` columns MUST update AND
   `routing_log` MUST record `reason='cap_set'` with old
   and new values.
2. **Given** a time cap is set mid-session, **When**
   elapsed time crosses the trigger fraction, **Then** the
   conclude phase MUST trigger (mirrors US1 acceptance #1).
3. **Given** a time cap is set mid-session AND elapsed time
   already exceeds the trigger fraction, **When** the cap
   is committed, **Then** the conclude phase MUST trigger
   immediately (no need to wait for another tick).
4. **Given** both time and turn caps are set, **When**
   either dimension crosses its trigger fraction first,
   **Then** the conclude phase MUST trigger (OR semantics).
5. **Given** the loop has been paused for 10 minutes,
   **When** the time-elapsed accumulator is inspected,
   **Then** it MUST NOT have advanced during the pause
   (active-loop time only).

---

### User Story 3 - Facilitator extends a cap mid-conclude-phase; loop returns to normal phase (Priority: P2)

The session is in conclude phase. The facilitator looks at
the AIs' conclusion turns and decides one more round of
exchange would produce a stronger ending. They open
session-settings and bump the turn cap from 20 to 30. The
loop transitions back to running phase: the conclude delta
is removed from the next assembly, spec 004's adaptive
cadence resumes, the AIs continue normal turns. At turn 24
(80% of 30) the conclude phase triggers again.

**Why this priority**: P2 because cap extension is a
nice-to-have for the case where the operator changed their
mind. Most sessions don't need it; the original cap is the
right cap. P2 because not having it forces the operator to
either accept the wrap-up they got or stop_loop and create a
new session — both worse than just extending.

**Independent Test**: Drive a session into conclude phase
(via US1). Before the final summarizer fires, extend the cap
(e.g., 20 → 30 turns). Assert
`routing_log.reason='conclude_phase_exited'`. Assert the
next dispatch's assembled prompt does NOT contain the
conclude delta. Assert spec 004's cadence is no longer
suspended. Run through to turn 24 and assert the conclude
phase triggers again.

**Acceptance Scenarios**:

1. **Given** the loop is in conclude phase, **When** the
   facilitator extends the cap such that the trigger
   fraction is no longer crossed, **Then** the loop MUST
   transition back to running phase AND `routing_log` MUST
   record `reason='conclude_phase_exited'`.
2. **Given** the loop has exited conclude phase, **When**
   the next assembly fires, **Then** the conclude delta
   MUST NOT appear in the prompt.
3. **Given** the loop has exited conclude phase, **When**
   spec 004's cadence is consulted, **Then** adaptive
   cadence MUST be active again.
4. **Given** the loop has exited conclude phase, **When**
   elapsed crosses the new trigger fraction, **Then** the
   conclude phase MUST trigger again — multiple
   conclude-phase entries per session are valid.

---

### User Story 4 - Facilitator stops_loop manually during conclude phase; final summarizer still runs (Priority: P3)

The session is in conclude phase. After two AIs have produced
conclusion turns, the facilitator decides they have what they
need and don't want to wait for the remaining AIs to wrap up.
They click "Stop loop". The orchestrator does NOT immediately
transition to stopped; instead it runs the final summarizer
on the conclusions produced so far, persists the summary,
THEN transitions to stopped. The session has a wrap-up
artifact even with the early manual stop.

**Why this priority**: P3 because manual stop during conclude
is a corner case — the conclude phase is short by design (one
round of turns), and a facilitator who started the wrap-up is
likely to let it finish. But for the corner case where they
want to cut short, ensuring the summarizer still runs
preserves the spec's main promise: every session ending
produces a wrap-up artifact.

**Independent Test**: Drive a session into conclude phase.
After 2 of N AIs have produced conclude turns, call
`stop_loop`. Assert spec 005's summarizer fires before the
loop transitions to stopped. Assert
`routing_log.reason='manual_stop_during_conclude'` is
recorded. Assert a `speaker_type='summary'` message is
persisted before the stopped transition.

**Acceptance Scenarios**:

1. **Given** the loop is in conclude phase, **When** the
   facilitator calls `stop_loop`, **Then** spec 005's
   summarizer MUST fire on the conclusions produced so far
   BEFORE the loop transitions to stopped.
2. **Given** the summarizer has fired and completed,
   **When** the loop's next iteration runs, **Then** the
   loop MUST transition to stopped AND `routing_log` MUST
   record `reason='manual_stop_during_conclude'`.
3. **Given** the summarizer fails (per spec 005 §FR-007
   fail-closed), **When** the failure path runs, **Then**
   the loop MUST still transition to stopped — summarizer
   failure does not block stop.

---

### Edge Cases

- **Cap set with both dimensions at 0 or negative.**
  Validation rejects with HTTP 422; `length_cap_seconds`
  and `length_cap_turns` MUST be positive when set.
- **Trigger fraction set to 0.0 or 1.0.**
  Trigger fraction MUST be in `(0.0, 1.0)` exclusive.
  0.0 would mean "conclude before any turn"; 1.0 would
  mean "no conclude phase, just hard stop." Both are
  rejected.
- **Single-AI session reaches conclude phase.** The
  conclude phase produces exactly one conclude turn (the
  single AI's wrap-up) before the summarizer runs.
- **No active AIs at conclude trigger time** (every
  participant has departed or been removed). The
  summarizer runs immediately on whatever transcript
  exists; the loop pauses.
- **Cap is set during pause.** The cap is recorded; the
  trigger fraction is NOT re-evaluated until the loop
  resumes. On resume, if elapsed already crosses the
  trigger fraction, conclude phase triggers immediately.
- **Conclude phase fires while a turn is mid-dispatch.**
  The in-flight turn completes normally; the conclude
  delta applies starting from the next turn.
- **Conclude phase + interrupt queue.** Human
  interjections are still processed during conclude phase
  (interjections are not "AI turns" and don't count
  against the turn cap). Interjections appear in the
  transcript with their normal priority.
- **Cap extended past 100% during the conclusion run
  (i.e., elapsed has crossed the cap)**. The loop has
  already initiated the auto-pause; cap extension AT
  THIS POINT is treated as "I want to keep going":
  conclude phase exits, the loop returns to running, and
  the auto-pause is canceled. The summarizer that would
  have fired does NOT fire (it fires only on actual
  pause).
- **Conclude delta lengthens prompt past context window
  for some participant.** Existing context-overflow path
  applies (spec 003 FR-035 ContextWindowOverflowError);
  the participant is skipped per the existing
  fail-closed semantics; their conclude turn does not
  fire but the loop proceeds to the next AI.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `sessions` table MUST gain four new
  nullable columns: `length_cap_kind` (enum:
  `none`, `time`, `turns`, `both`),
  `length_cap_seconds` (positive integer or null),
  `length_cap_turns` (positive integer or null),
  `conclude_phase_started_at` (timestamp or null).
  Default values: `length_cap_kind='none'`, others null.
- **FR-002**: The orchestrator MUST track active loop time
  via an `active_seconds` accumulator that advances only
  while the loop is in running or conclude phase. Pause
  time MUST NOT advance the accumulator.
- **FR-003**: A new endpoint MUST allow the facilitator to
  set or update `length_cap_*` columns via session-settings
  (path TBD in `/speckit.plan`; mirrors existing
  session-settings endpoints from spec 006).
- **FR-004**: Cap-set MUST emit `routing_log.reason='cap_set'`
  with old and new values.
- **FR-005**: The orchestrator MUST evaluate the trigger
  fraction (`SACP_CONCLUDE_PHASE_TRIGGER_FRACTION`, default
  `0.80`) on every dispatch. When elapsed time OR turn
  count crosses the fraction × cap value, the loop MUST
  transition to conclude phase.
- **FR-006**: When both time and turn caps are set, the
  conclude phase MUST trigger when EITHER dimension crosses
  its trigger fraction (OR semantics, whichever fires
  first).
- **FR-007**: The conclude-phase transition MUST emit
  `routing_log.reason='conclude_phase_entered'` with the
  triggering dimension and the value at trigger time.
- **FR-008**: During conclude phase, the prompt assembler
  (spec 008) MUST inject a Tier 4 conclude delta into every
  AI's assembled prompt. The delta is hardcoded text
  (settled in `/speckit.plan`) instructing the AI to
  summarize their position and offer a final conclusion.
- **FR-009**: The conclude delta MUST be additive at Tier 4
  AFTER any participant custom_prompt and any spec 021
  register-slider delta. The delta MUST NOT replace tier
  text, custom_prompt, or register delta.
- **FR-010**: During conclude phase, spec 004's adaptive
  cadence MUST be suspended (delays return to the floor).
- **FR-011**: After every active AI has produced exactly
  one conclude turn OR been skipped after spec 003 §FR-031
  retry cap exhausted, the orchestrator MUST trigger spec
  005's summarizer one final time on the accumulated
  transcript. The summarizer call MUST happen exactly once
  per conclude-phase entry, regardless of whether any
  individual conclude turn succeeded.
- **FR-012**: After the final summarizer completes (success
  OR fail-closed per spec 005), the loop MUST transition
  to paused with `routing_log.reason='auto_pause_on_cap'`.
- **FR-013**: The facilitator MUST be able to extend the
  cap during conclude phase. When the extended cap moves
  the trigger fraction past current elapsed, the loop MUST
  transition back to running phase with
  `routing_log.reason='conclude_phase_exited'`.
- **FR-014**: When the loop exits conclude phase, the
  conclude delta MUST be removed from the next assembly
  AND spec 004's adaptive cadence MUST resume.
- **FR-015**: The facilitator MUST be able to call
  `stop_loop` during conclude phase. The orchestrator MUST
  run the final summarizer BEFORE transitioning to
  stopped, with `routing_log.reason='manual_stop_during_conclude'`.
- **FR-016**: Cap setters MUST be facilitator-only (mirrors
  spec 006 §FR-007 session-control authorization). Non-
  facilitators receive HTTP 403.
- **FR-017**: A WS event `session_concluding` MUST broadcast
  to all participants on conclude-phase entry. The event
  payload MUST include the trigger reason, the remaining
  turn count (if turn-capped), and the remaining time (if
  time-capped). UI consumers (spec 011) render a banner
  ("Session is concluding — N turns left").
- **FR-018**: A WS event `session_concluded` MUST broadcast
  to all participants on auto-pause transition. UI
  consumers update banner state.
- **FR-019**: Cap visibility is facilitator-only. The cap
  values do NOT appear in any participant's `/me`
  response. Once conclude phase fires, every participant
  sees the conclude-phase delta in their assembled prompt
  AND the WS-driven banner.
- **FR-020**: Validation: `length_cap_seconds`, when set,
  MUST be a positive integer in `[60, 86400 × 30]`
  (1 minute to 30 days). `length_cap_turns`, when set,
  MUST be a positive integer in `[1, 10000]`.
  `length_cap_kind` MUST take one of the four documented
  enum values.
- **FR-021**: Cap-set with both dimensions at zero or
  negative values MUST be rejected with HTTP 422 and a
  clear error.
- **FR-022**: Cap-set with `length_cap_kind='none'` MUST
  null both `length_cap_seconds` and `length_cap_turns`.
- **FR-023**: Three preset shapes MUST be available in the
  session-create modal: Short, Medium, Long. Default
  values:
  - Short: 30 minutes (1800 seconds) AND 20 turns
  - Medium: 2 hours (7200 seconds) AND 50 turns
  - Long: 8 hours (28800 seconds) AND 200 turns
  Custom is a fourth option allowing hand-set values.
- **FR-024**: Deployment-wide defaults MUST be settable via
  `SACP_LENGTH_CAP_DEFAULT_KIND`,
  `SACP_LENGTH_CAP_DEFAULT_SECONDS`,
  `SACP_LENGTH_CAP_DEFAULT_TURNS`. New sessions inherit
  these defaults; the facilitator can override on
  session-create.
- **FR-025**: The five new env vars
  (`SACP_LENGTH_CAP_DEFAULT_KIND`,
  `SACP_LENGTH_CAP_DEFAULT_SECONDS`,
  `SACP_LENGTH_CAP_DEFAULT_TURNS`,
  `SACP_CONCLUDE_PHASE_TRIGGER_FRACTION`,
  `SACP_CONCLUDE_PHASE_PROMPT_TIER`) MUST have validator
  functions in `src/config/validators.py` registered in
  the `VALIDATORS` tuple, AND corresponding sections in
  `docs/env-vars.md` with the six standard fields, BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable
  gate).
- **FR-026**: When the cap-set endpoint (FR-003) receives a
  new cap value below the current elapsed counter (e.g.,
  `length_cap_turns=20` set at turn 30), the orchestrator
  MUST NOT auto-pick the interpretation. The endpoint MUST
  return a 409-style disambiguation response presenting two
  intent options to the facilitator:
  - **Absolute**: accept the value as the new total cap;
    elapsed already exceeds 100%, so the next dispatch
    transitions the loop to conclude phase, runs one round
    of conclude turns, fires the final summarizer, and
    pauses with `routing_log.reason='auto_pause_on_cap'`.
  - **Relative**: interpret the submitted value as N
    additional turns/seconds beyond current elapsed
    (effective cap = `current_elapsed + submitted_value`).
    Loop continues normally; conclude phase triggers when
    elapsed crosses the trigger fraction of the effective
    cap.
  The facilitator's choice MUST be recorded in
  `routing_log.reason='cap_set'` with an additional
  `interpretation` field (`absolute` | `relative`) to
  preserve the audit trail. Spec 011 owns the SPA modal
  that presents the choice.

### Key Entities

- **SessionLengthCap** (per-session columns) — four new
  columns on the `sessions` table per FR-001. Mutable
  via the facilitator session-settings endpoint.
- **ActiveLoopAccumulator** (per-session, in-memory or
  durable) — tracks `active_seconds` advancing only
  during running/conclude phase. Implementation choice
  (in-memory vs. durable column on `sessions`) settled
  in `/speckit.plan`.
- **ConcludeDelta** (Tier 4 prompt fragment) — hardcoded
  text in `src/prompts/conclude_delta.py` injected at
  Tier 4 during conclude phase. Settled in
  `/speckit.plan`.
- **LoopState** (existing FSM) — extended with the
  conclude phase as a new state alongside running /
  paused / stopped.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A session with no cap set MUST behave
  identically to the pre-feature loop — no conclude phase,
  no summarizer trigger from this spec, no auto-pause.
  Verified by an architectural test asserting no spec 025
  code path fires when `length_cap_kind='none'`.
- **SC-002**: A session with a turn cap MUST transition to
  conclude phase at the configured trigger fraction.
  Verified by an end-to-end test driving the cap and
  asserting the FSM transition + delta injection.
- **SC-003**: A session with a time cap MUST transition to
  conclude phase at the configured trigger fraction.
  Verified by a clock-controlled test that drives elapsed
  time past the threshold.
- **SC-004**: After every active AI has produced a conclude
  turn, the summarizer MUST fire exactly once. Verified by
  a multi-AI end-to-end test asserting exactly one new
  `speaker_type='summary'` message after the last conclude
  turn.
- **SC-005**: After the summarizer completes, the loop MUST
  transition to paused with
  `routing_log.reason='auto_pause_on_cap'`. Verified by
  inspecting the loop state and routing log.
- **SC-006**: Cap extension during conclude phase MUST
  return the loop to running phase if the new trigger
  fraction is no longer crossed. Verified by a test driving
  the extension and asserting the FSM transition + delta
  removal.
- **SC-007**: Manual stop_loop during conclude phase MUST
  trigger the summarizer before the stopped transition.
  Verified by a test driving the stop and asserting the
  summarizer fires + the transition records
  `reason='manual_stop_during_conclude'`.
- **SC-008**: Pause-resume cycles MUST NOT advance the
  active-loop accumulator. Verified by a test that pauses
  the loop, advances the wall clock, resumes, and asserts
  the accumulator advanced only by the active running
  time.
- **SC-009**: Cap configuration MUST be facilitator-only.
  Verified by a test driving the endpoint with a
  non-facilitator session and asserting HTTP 403.
- **SC-010**: Cap visibility MUST be facilitator-only.
  Verified by a test asserting `/me` responses for
  non-facilitator participants do NOT contain
  `length_cap_*` fields.
- **SC-011**: WS events `session_concluding` and
  `session_concluded` MUST broadcast on phase transitions.
  Verified by a multi-client test asserting all
  participants receive both events at the right
  transitions.
- **SC-012**: Cap composition with spec 021 register
  slider MUST be additive at Tier 4. Verified by a test
  with both spec 021 and spec 025 enabled, asserting the
  assembled prompt contains both deltas in additive order.
- **SC-013**: With any of the five new env vars set to an
  invalid value, the orchestrator process MUST exit at
  startup with a clear error message naming the offending
  var (V16 fail-closed gate observed in CI).
- **SC-014**: Cap performance overhead MUST be O(1) per
  dispatch — a single comparison of elapsed vs. cap, no
  scans. Verified by a perf test asserting the cap-check
  cost is below the routing_log per-stage timing P95
  baseline.

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6**
(orchestrator-driven topologies). The cap evaluation runs
in the orchestrator's per-dispatch path; the FSM
transitions are orchestrator-state changes; the conclude
delta is injected by the orchestrator's prompt assembler;
the final summarizer is the orchestrator's spec 005
trigger. All require a single orchestrator to be the loop
authority.

This feature is **NOT applicable to topology 7
(MCP-to-MCP, Phase 3+)**. In topology 7 each
participant's MCP client drives its own dispatch; there
is no orchestrator-side loop to apply caps to. Per V12:
any topology-7 deployment MUST recognize that this spec's
length-cap mechanism does not apply.

### V13 — Use Case Coverage

This feature serves the V13 primary use cases:

- §3 Consulting Engagement
  (`docs/sacp-use-cases.md` §3) — consulting sessions
  have fixed scope (a billed hour, a working session).
  The Short preset matches consulting cadence; the
  conclude phase produces a clean wrap-up artifact for
  the engagement deliverable.
- §2 Research Paper Co-authorship
  (`docs/sacp-use-cases.md` §2) — research deliverables
  have deadlines. The Medium / Long preset matches
  research synthesis pushes; the final summarizer is the
  draft starting point for the next session's work.
- §5 Technical Review and Audit
  (`docs/sacp-use-cases.md` §5) — reviews must produce a
  conclusion artifact. Without the cap + conclude phase,
  reviews drift; with them, the conclusion is structurally
  guaranteed.

Other use cases (§1, §4, §6, §7) inherit the feature when
operators opt in but are not the priority drivers.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable
contracts. This spec contributes three budgets:

- **Cap check per dispatch**: O(1). Two comparisons
  (elapsed vs. cap, count vs. cap) plus the trigger
  fraction multiplication. Single integer ops; no I/O,
  no allocation. Budget enforcement: per-dispatch timing
  on the existing routing_log per-stage timing path
  (spec 003 §FR-030).
- **Conclude-phase transition**: O(participants). The
  transition writes one `routing_log` row, appends the
  conclude delta to each active participant's pending
  assembly, and broadcasts the WS event. P95 < 2s for
  sessions with up to 5 active participants.
- **Final summarizer trigger**: reuses spec 005's
  existing pipeline. Budget enforcement falls through to
  spec 005 SC-002 (summarizer P95). No new budget
  introduced here.

## Configuration (V16) — New Env Vars

Five new env vars are introduced. Each MUST have type,
valid range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this
spec (per V16 deliverable gate).

### `SACP_LENGTH_CAP_DEFAULT_KIND`

- **Intended type**: string enum
- **Intended valid range**: `none` | `time` | `turns` |
  `both`. Default `none` (no cap; preserves
  pre-feature behavior).
- **Fail-closed semantics**: any non-enum value MUST cause
  startup exit. The default applies to new sessions; the
  facilitator can override on session-create.

### `SACP_LENGTH_CAP_DEFAULT_SECONDS`

- **Intended type**: positive integer (seconds), or empty
- **Intended valid range**: `[60, 2592000]` (1 minute to
  30 days) when set. Default empty.
- **Fail-closed semantics**: outside the range MUST cause
  startup exit. Empty is allowed; new sessions then
  have no time-cap default.

### `SACP_LENGTH_CAP_DEFAULT_TURNS`

- **Intended type**: positive integer, or empty
- **Intended valid range**: `[1, 10000]` when set. Default
  empty.
- **Fail-closed semantics**: outside the range MUST cause
  startup exit. Empty is allowed.

### `SACP_CONCLUDE_PHASE_TRIGGER_FRACTION`

- **Intended type**: float in `(0.0, 1.0)` exclusive
- **Intended valid range**: `(0.0, 1.0)` exclusive.
  Default `0.80`.
- **Fail-closed semantics**: 0.0 or 1.0 inclusive, or
  outside `(0.0, 1.0)` MUST cause startup exit. The
  exclusive range protects against pathological
  configurations (always-conclude, never-conclude).

### `SACP_CONCLUDE_PHASE_PROMPT_TIER`

- **Intended type**: integer in `{1, 2, 3, 4}`
- **Intended valid range**: matches spec 008's tier set.
  Default `4` (Tier 4 additive). Operators with custom
  tier semantics can attach the conclude delta to a
  different tier.
- **Fail-closed semantics**: outside `{1, 2, 3, 4}` MUST
  cause startup exit.

## Cross-References to Existing Specs and Design Docs

- **Spec 003 (turn-loop-engine) §FR-021** — loop FSM
  states (running, paused, stopped). Spec 025 adds
  conclude phase as a new state alongside the existing
  three. The conclude-phase transition is a new FSM
  edge from running → conclude → paused.
- **Spec 003 (turn-loop-engine) §FR-030** — `routing_log`
  per-stage timings receive the cap-check cost; the
  cap-set / conclude-phase-entered / auto-pause-on-cap
  reasons are new entries in the routing_log reason
  enumeration.
- **Spec 003 (turn-loop-engine) §FR-031** — compound
  retry cap applies during conclude turns; a participant
  whose AI fails the conclude turn is skipped per the
  existing fail-closed semantics.
- **Spec 003 (turn-loop-engine) §FR-001** — "AI turn"
  definition. The turn cap counts AI turns only;
  human interjections and system messages are excluded.
- **Spec 004 (convergence-cadence)** — adaptive cadence
  is suspended during conclude phase (FR-010); resumes
  on conclude-phase exit (FR-014).
- **Spec 005 (summarization-checkpoints) §FR-001, §FR-007** —
  the existing summarizer pipeline is reused for the
  final summarizer trigger (FR-011). Spec 025 does not
  introduce new summarization logic.
- **Spec 006 (mcp-server) §FR-007** — session-control
  endpoints (start_loop, stop_loop, pause_loop). Spec 025
  adds the cap-set endpoint following the same
  authorization model.
- **Spec 008 (prompts-security-wiring)** — Tier 4 hook
  for prompt deltas. The conclude delta attaches at Tier
  4 (FR-008, FR-009) additive to existing tier text and
  custom_prompt.
- **Spec 011 (web-ui)** — UI affordances (cap config in
  session-create modal and session-settings panel,
  conclude-phase banner with countdown). Spec 025 defines
  the contract; spec 011 owns the SPA wiring. A spec
  011 amendment lands when 025's tasks are scheduled.
- **Spec 021 (ai-response-shaping)** — composes with
  spec 025 at Tier 4. The register-slider delta and the
  conclude delta both attach at Tier 4 in additive order
  (FR-009). When 021 lands first, 025 inherits its
  composition; when 021 lands later, 025's tier-4
  attachment is forward-compatible.
- **Spec 001 (core-data-model)** — schema additions on
  the `sessions` table (FR-001). Migration follows the
  spec 001 §FR-017 forward-only constraint.
- **Constitution §10** — Phase 3 deliverables list. Spec
  025 is in-scope for Phase 3 by virtue of Phase-3
  declaration recorded 2026-05-05.
- **Constitution §14.1** — Feature work workflow. This
  spec scaffolds via `/speckit.specify`; subsequent
  steps are deferred.
- **Constitution V12** — topology applicability. Spec
  025 applies to topologies 1-6; incompatible with
  topology 7.
- **Constitution V13** — primary use cases consulting
  (§3), research co-authorship (§2), technical review
  and audit (§5).
- **Constitution V14** — per-stage timing budgets.
  Spec 025 contributes three budgets (Performance
  Budgets section).
- **Constitution V16** — env-var validation at startup.
  Spec 025 introduces five new vars (Configuration
  section).

## Assumptions

- The default is no cap. Operators who do not opt in see
  the pre-feature behavior unchanged. The
  `SACP_LENGTH_CAP_DEFAULT_KIND='none'` default plus the
  per-session opt-in design preserves backward
  compatibility for existing deployments.
- The three preset shapes (Short / Medium / Long)
  reflect representative session shapes for the V13 use
  cases. Operators with different cadences can use the
  Custom option or override the deployment defaults.
- Pause-resume cycles do not consume the time cap. The
  rationale is that pause is operator-initiated
  exception handling; charging pause time to the cap
  would force operators to either rush back from a
  break or accept a shorter active session than they
  configured. The `active_seconds` accumulator is the
  implementation primitive.
- The conclude phase is a one-round wrap-up by design.
  Each active AI gets exactly one turn to summarize
  + conclude. Multi-round wrap-up (an iterated
  conclusion exchange) is a future feature; v1 ships
  the simpler shape.
- The final summarizer is the same spec 005 pipeline as
  every other checkpoint. No special "final summarizer"
  variant is introduced; the only difference is timing
  (after the last conclude turn rather than at the
  configured every-N-turns interval).
- Cap composition with spec 021 register slider is
  additive at Tier 4. When 021 ships first, 025
  inherits the composition; when 025 ships first, 021's
  later landing fits without amendment.
- The conclude delta is hardcoded in v1
  (`src/prompts/conclude_delta.py`). Operator-tunable
  conclude-delta text is a future feature; v1 ships
  one delta string for all conclude phases.
- `SACP_CONCLUDE_PHASE_PROMPT_TIER` allows attaching the
  conclude delta to a non-default tier for operators
  with custom tier semantics, but the recommended default
  is Tier 4 — Tier 4 is the only tier that is
  reliably present (every participant's prompt assembly
  reaches Tier 4 if they have any custom_prompt OR if
  spec 021's register slider is set).
- Phase 3 declared 2026-05-05 satisfies the phase gate;
  this spec stays scaffold-only until tasks are
  scheduled. No implementation begins until the user
  invokes `/speckit.clarify` and subsequent workflow
  steps.
- Status remains Draft until clarifications resolve and
  the user accepts the scaffolding.
