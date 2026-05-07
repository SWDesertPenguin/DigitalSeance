# Feature Specification: AI Participant Standby Modes (wait_for_human + always)

**Feature Branch**: `027-participant-standby-modes`
**Created**: 2026-05-07
**Status**: Draft (Phase 3 declared 2026-05-05; scaffold ships now, tasks + implementation deferred)
**Input**: User description: "Phase 3 AI participant standby modes. When a turn is gated on human input (AI has asked a question awaiting facilitator answer; review-gate awaiting approval; proposal awaiting vote), AIs currently keep producing filler turns that burn tokens without advancing the conversation. Adds a third participant state alongside paused (manual, sticky) and circuit_open (failure, requires reset): standby — auto-managed by the orchestrator based on a participant-configured wait_mode. Two modes per AI: wait_for_human (default — orchestrator skips dispatch until gating condition clears) and always (AI keeps taking turns with a Tier 4 acknowledgment delta). Auto-pivot mechanism after N consecutive standby cycles injects a system-level pivot message offering to redirect the panel or self-mark observer. Applies to topologies 1-6 (orchestrator-mediated dispatch FSM); incompatible with topology 7. Primary use cases: research co-authorship (§2), decision-making under asymmetric expertise (§6), consulting (§3)."

## Overview

The orchestrator's per-participant lifecycle today carries five
status values: `active` (dispatching normally), `pending` (joined,
awaiting facilitator approval), `paused` (manually paused by the
facilitator — sticky until manual resume), `removed` (departed),
and `circuit_open` (failure-driven via spec 015 circuit breaker —
requires reset). None of these model the case the user description
calls out: **the AI is healthy, the participant is not paused, but
the next turn is structurally pointless because it's gated on a
human reply that hasn't arrived.**

A Phase 1+2 shakedown surfaced the operational shape directly:
an AI asks the facilitator a question
via `ai_question_opened`; the facilitator does not reply
immediately; the AI's next turn produces a low-content "still
waiting" reply that burns tokens without advancing the session.
Subsequent turns repeat the same stance with minor variations.
The orchestrator has no signal to distinguish "this AI is
productively waiting" from "this AI is failing"; the existing
`pause_participant` is manual and sticky, the existing
`circuit_open` is failure-driven and requires reset. Neither
fits the "blocked on human, not failed" reality.

This spec defines a **standby state** as the auto-managed
counterpart to paused / circuit_open:

- **Auto-entry**: the orchestrator marks a participant standby
  when one of four detection signals fires AND the participant's
  `wait_mode='wait_for_human'`. No facilitator action required.
- **Auto-exit**: the orchestrator clears standby when the gating
  condition resolves (human replies, review-gate clears, vote
  arrives). No facilitator action required.
- **Skipped from dispatch**: a standby participant is skipped
  from the round-robin (spec 003 §FR-005) the same way a paused
  one is. No turn produced, no tokens spent.
- **Distinct from paused**: not manual, not sticky. The
  facilitator can still manually pause a standby participant
  (paused supersedes standby) or resume one out of standby
  (resume forces standby evaluation to clear regardless of
  gating condition).
- **Distinct from circuit_open**: not failure-driven. A standby
  participant's circuit-breaker state is unaffected; the
  participant exits standby cleanly without a circuit reset.

Each AI participant carries a `wait_mode` configuration:

1. **`wait_for_human`** (default) — when any detection signal
   trips, the participant transitions to standby. The next
   eligible dispatch is suppressed; the participant produces no
   turn until the gate clears.
2. **`always`** — the participant remains in `active` regardless
   of detection signals. Their next turn dispatches with a Tier 4
   acknowledgment delta in the prompt:
   > "An unresolved condition awaits human input. In your next
   > turn, briefly acknowledge the unmet wait, state the
   > assumption you are making in the human's absence, then
   > proceed with what you can advance now."

The detection signals (any one trips standby in wait_for_human
mode):

1. **Unresolved `ai_question_opened`** — the AI's own previous
   turn emitted a question event (spec 004 detector) AND the
   event is still in the unresolved set.
2. **Pending `review_gate_staged`** — a review-gate event for
   this AI's draft is still pending facilitator approval (spec
   007 §FR-005).
3. **Proposal awaiting vote** — a `proposal_*` event awaits
   this AI's vote AND the AI's last N turns repeat the same
   waiting stance (cosine similarity > 0.8 against the prior
   turn, < 50 tokens of new content). The repetition guard
   prevents standby from firing the moment a proposal opens —
   it fires when the AI is observably stuck.
4. **Repeated low-content filler heuristic** — N consecutive
   turns scoring above the configured filler threshold (cross-
   reference spec 021's filler scorer infrastructure). This
   signal **overlaps with backlog item #8 (auto-pause
   off-rails)**; coordinate with spec 014's signal vocabulary
   to keep the off-rails detector and the standby detector
   from double-firing on the same pattern.

The auto-pivot mechanism handles "the human is not coming back
soon" cases:

- The orchestrator counts consecutive standby cycles per
  participant (a "cycle" is one round-robin pass where the
  participant was eligible but skipped).
- After `SACP_STANDBY_FILLER_DETECTION_TURNS` consecutive
  cycles AND `SACP_STANDBY_PIVOT_TIMEOUT_SECONDS` elapsed since
  the gating signal opened, the orchestrator injects a single
  system-level pivot message into the transcript:
  > "No human reply received in T seconds. Either pivot to a
  > related sub-topic the panel can advance independently, or
  > self-mark as observer until the human returns."
- In `always` mode, pivot is automatic — the AI's next turn
  responds to the pivot offer.
- In `wait_for_human` mode, the AI is in standby and not
  dispatching; the pivot serves as a self-mark-observer
  invitation handled by the orchestrator on the AI's behalf
  (the participant transitions to a long-term observer state
  until the human returns).
- Pivot rate is capped per session
  (`SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION`, default 1) so a
  prolonged human absence produces one pivot message, not a
  flood.

This spec **scaffolds only**. Implementation begins when the
facilitator schedules tasks per Constitution §14.1. The Phase 3
declaration recorded 2026-05-05 satisfies the phase gate; this
spec stays scaffold-only until tasks land and implementation
reaches Implemented status.

## Clarifications

### Initial draft assumptions requiring confirmation

- **Coordination with spec 013/014 observer-downgrade.** Spec
  013 introduces an `observer_downgrade` mechanism that
  transparently downgrades an active participant to observer
  during high-traffic windows. Spec 027's standby is a
  different state with a different trigger (gate-blocked vs.
  traffic-shape). Drafted as: standby and observer-downgrade
  are independent states; if both fire on the same participant,
  standby wins (gate-blocked takes precedence over traffic-
  shape) and the observer-downgrade evaluation skips
  participants already in standby. [NEEDS CLARIFICATION:
  confirm standby-wins precedence vs. observer-downgrade-wins
  vs. compose-as-additive (participant could be standby AND
  observer simultaneously).]
- **Detection signal #4 vs. spec 014's off-rails detector.**
  The user's brief notes the filler heuristic "overlaps with
  backlog #8 / 014 signal additions." Drafted as: spec 027
  consumes spec 014's off-rails signal as one of its inputs,
  rather than re-implementing the filler heuristic
  independently. The signal source-of-truth lives in 014;
  spec 027 reads it and applies the wait_mode behavior.
  [NEEDS CLARIFICATION: confirm signal-consumption vs.
  independent-detection.]
- **Standby exit semantics on review-gate clear.** A
  participant is in standby because their review-gate event
  is pending. The facilitator approves the gate. Drafted as:
  the orchestrator polls the unresolved-gates set on every
  round-robin tick; the moment the gate clears, the
  participant exits standby and dispatches on the NEXT
  eligible round-robin slot (not immediately mid-tick).
  [NEEDS CLARIFICATION: confirm next-tick exit vs.
  immediate-pre-empt.]
- **Manual pause of a standby participant.** A facilitator
  manually pauses a participant who is currently standby.
  Drafted as: paused supersedes standby (paused is sticky;
  standby is auto-managed). The participant exits standby
  and enters paused; on manual resume, standby evaluation
  re-runs and may transition the participant back to standby
  if the gate is still active. [NEEDS CLARIFICATION:
  confirm paused-supersedes vs. paused-and-standby-coexist.]
- **`always` mode delta composition with spec 021 / spec 025
  Tier 4 deltas.** The `always`-mode acknowledgment delta is
  Tier 4. Drafted as: Tier 4 deltas compose additively in a
  fixed order (spec 021 register slider first, spec 025
  conclude delta second, spec 027 wait-acknowledgment third).
  Each delta operates orthogonally on the same prompt
  surface. [NEEDS CLARIFICATION: confirm fixed-additive-order
  vs. operator-configurable-order.]
- **Pivot rate-cap scope.** Drafted as: the rate cap is
  per-session, not per-participant. A session with three
  AIs all in standby produces at most
  `SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION` pivots total
  across the session lifetime. Per-participant rate-capping
  is a future enhancement. [NEEDS CLARIFICATION: confirm
  per-session vs. per-participant rate cap.]
- **Pivot message envelope.** The pivot is an
  orchestrator-emitted system message in the transcript.
  Drafted as: the message persists with `speaker_type='system'`
  AND a new `kind='orchestrator_pivot'` discriminator on the
  message row (or in the message metadata) so spec 005's
  summarizer and spec 011's UI can render pivot messages
  distinctly. [NEEDS CLARIFICATION: confirm
  speaker_type='system' + kind discriminator vs. dedicated
  speaker_type='pivot'.]
- **Detection signal #3 stance-similarity threshold.** Drafted
  as: cosine similarity > 0.8 against the immediately prior
  turn AND < 50 tokens of new content. Both conditions must
  hold. The 0.8 threshold borrows spec 004 §FR-014 convergence
  semantics; the 50-token threshold mirrors spec 004 §FR-016
  short-output handling. [NEEDS CLARIFICATION: confirm the
  two-condition AND vs. either-OR vs. operator-tunable.]
- **Phase 1+2 shakedown reference.** The shakedown detail is
  paraphrased without test session IDs. Confirm the paraphrase
  is acceptable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Participant in `wait_for_human` mode self-marks standby when ai_question_opened is unresolved; loop skips it; standby clears when human replies (Priority: P1)

A participant configured with the default
`wait_mode='wait_for_human'` produces a turn that emits an
`ai_question_opened` event (spec 004's question detector). The
facilitator does not respond immediately. On the next round-
robin pass, the orchestrator's standby evaluator finds the
unresolved question event for this participant and transitions
them to `status='standby'`. A `participant_standby` WS event
broadcasts with `reason='awaiting_human'` and `since_turn=N`.
The participant is skipped from dispatch on this and subsequent
ticks. Other participants (including humans, including AIs in
`always` mode, including AIs without unresolved gates) continue
to dispatch normally. When the facilitator finally answers via
human injection (which resolves the question event), the
orchestrator's standby evaluator clears the standby flag on the
NEXT round-robin tick. The participant transitions back to
`active` and dispatches on their next eligible slot. A
`participant_standby_exited` WS event fires.

**Why this priority**: P1 because this is the spec's primary
value. Without this, AIs continue to burn tokens on filler
"still waiting" turns. The wait_for_human-mode auto-skip is the
mechanism that converts the existing problem into a no-cost
state. Detection of the gating condition + auto-skip is the
critical-path deliverable.

**Independent Test**: Drive a session with one participant
configured `wait_mode='wait_for_human'`. Have that participant
emit a turn that fires `ai_question_opened` per spec 004.
Advance the loop by one round-robin tick. Assert the
participant's status flips to `standby`. Assert the next tick's
dispatch skips the participant. Assert other participants
continue normally. Inject a human reply that resolves the
question event. Assert on the next tick the standby clears and
the participant returns to `active`. Drive another tick and
assert the participant dispatches.

**Acceptance Scenarios**:

1. **Given** a participant with `wait_mode='wait_for_human'`
   AND an unresolved `ai_question_opened` event for that
   participant, **When** the standby evaluator runs, **Then**
   the participant's status MUST flip to `standby` AND
   `admin_audit_log` MUST record `action='standby_entered'`
   with the triggering reason.
2. **Given** a participant in `standby`, **When** the round-
   robin dispatcher selects the next participant, **Then** the
   standby participant MUST be skipped AND no turn MUST be
   produced for them.
3. **Given** a participant in `standby`, **When** a
   `participant_standby` WS event broadcasts, **Then** the
   payload MUST include `participant_id`, `reason`
   (`awaiting_human` | `awaiting_gate` | `awaiting_vote`),
   and `since_turn`.
4. **Given** a participant in `standby` because of an
   `ai_question_opened` event, **When** the human replies
   via inject_message AND the question event resolves,
   **Then** on the next round-robin tick the participant MUST
   exit standby AND `admin_audit_log` MUST record
   `action='standby_exited'` AND a `participant_standby_exited`
   WS event MUST fire.
5. **Given** a participant in `standby` because of a pending
   `review_gate_staged` event, **When** the facilitator
   approves the review gate, **Then** the participant MUST
   exit standby on the next tick.
6. **Given** a participant in `standby`, **When** the
   facilitator manually pauses them, **Then** the participant
   MUST transition to `paused` (paused supersedes standby);
   on manual resume, standby evaluation MUST re-run.
7. **Given** a participant whose only un-paused state would
   be `circuit_open` (provider failures), **When** the
   standby evaluator runs, **Then** circuit_open MUST take
   precedence — standby evaluation skips participants in
   circuit_open.

---

### User Story 2 - Participant in `always` mode keeps taking turns when blocked, with the acknowledgment delta in the system prompt (Priority: P2)

A participant configured with `wait_mode='always'` produces a
turn that emits `ai_question_opened`. Unlike US1, the
orchestrator does NOT mark them standby. On the next round-
robin tick, dispatch fires for this participant. The bridge
layer's prompt assembler (spec 008) appends a Tier 4
acknowledgment delta to the participant's prompt instructing
them to acknowledge the unmet wait, state their assumption,
and proceed. The participant's turn produces forward-progress
content (with the acknowledgment) rather than filler. The
gating condition still exists; subsequent ticks continue to
attach the acknowledgment delta until the gate clears.

**Why this priority**: P2 because the wait_for_human mode (US1)
covers the default case for most operators. The always mode
exists for sessions where progress despite human absence is
preferable to silence (research co-authorship long pushes
where the AI panel can advance methodology debate while
waiting for the lead author's clarification). P2 because most
sessions don't need it; for the sessions that do, the
acknowledgment delta is the security envelope (the AI's
output explicitly notes the assumption it made in the human's
absence, so the human can correct on return).

**Independent Test**: Drive a session with one participant
configured `wait_mode='always'`. Have that participant emit a
turn that fires `ai_question_opened`. Advance the loop. Assert
the participant's status remains `active`. Assert the next
turn's dispatched prompt contains the Tier 4 acknowledgment
delta. Inspect the participant's response — assert it
includes an explicit acknowledgment of the unmet wait per the
delta's instruction.

**Acceptance Scenarios**:

1. **Given** a participant with `wait_mode='always'` AND an
   unresolved gating signal, **When** the round-robin
   dispatcher selects them, **Then** their status MUST remain
   `active` AND a turn MUST dispatch normally.
2. **Given** an `always`-mode participant with an unresolved
   gating signal, **When** the prompt assembler runs for their
   next dispatch, **Then** the assembled prompt MUST include
   the Tier 4 acknowledgment delta.
3. **Given** an `always`-mode participant whose gating signal
   has cleared, **When** the next dispatch fires, **Then** the
   acknowledgment delta MUST NOT appear (the delta is
   conditional on the unresolved-gate state).
4. **Given** an `always`-mode participant AND spec 021's
   register slider is set AND spec 025's conclude-phase delta
   is also active, **When** the prompt assembles, **Then** all
   three Tier 4 deltas MUST be present in the documented
   additive order (register, conclude, wait-acknowledgment).
5. **Given** an `always`-mode participant whose response does
   NOT include an acknowledgment of the unmet wait, **When**
   the response is inspected, **Then** the response is still
   persisted (the delta is an instruction, not a hard
   constraint); the operator-side observation falls to spec
   021's filler scorer if the response is uninformative.

---

### User Story 3 - Orchestrator injects pivot after N consecutive standby cycles in `wait_for_human` mode; AI self-marks observer (Priority: P3)

A participant has been in `standby` for N consecutive round-
robin cycles (default
`SACP_STANDBY_FILLER_DETECTION_TURNS=5`) AND
`SACP_STANDBY_PIVOT_TIMEOUT_SECONDS` (default 600 = 10 min)
have elapsed since the gating event opened. The orchestrator
checks the per-session pivot rate cap; if the cap allows
another pivot, the orchestrator injects a single system-level
pivot message into the transcript with `speaker_type='system'`
and `kind='orchestrator_pivot'`. The message text reads
something like:
> "No human reply received in 10 minutes. Either pivot to a
> related sub-topic the panel can advance independently, or
> self-mark as observer until the human returns."

In `wait_for_human` mode, the participant is in standby and not
dispatching. The orchestrator interprets the pivot on their
behalf: the participant transitions to a long-term observer
state (a sub-state of standby with a different audit-log
flavor), still skipped from dispatch but now flagged as
"awaiting human return without active wait" — which surfaces
in spec 011's UI differently (a less-urgent badge).

**Why this priority**: P3 because the pivot is for prolonged
human absences. Most sessions resolve the gating condition
within minutes; the pivot is for the case where the human is
genuinely gone (lunch, end of day, multi-day async return).
P3 because the user-visible difference between "the participant
is on standby" and "the participant is on long-term observer
standby" is small; it surfaces in spec 011 styling and
operator dashboards, not in the conversation itself.

**Independent Test**: Drive a session with one
`wait_for_human`-mode participant in standby. Advance the loop
through N+1 standby cycles AND past the pivot timeout. Assert
the orchestrator injects exactly one pivot message into the
transcript with the configured shape. Assert the participant
transitions to a long-term-observer sub-state. Assert
`admin_audit_log` records `action='pivot_injected'` AND
`action='standby_observer_marked'`. Drive further cycles and
assert no second pivot is injected (rate cap).

**Acceptance Scenarios**:

1. **Given** a participant in `standby` for N consecutive
   cycles AND the timeout elapsed, **When** the standby
   evaluator runs, **Then** the orchestrator MUST inject one
   pivot message AND `admin_audit_log` MUST record
   `action='pivot_injected'`.
2. **Given** the pivot has been injected for a session,
   **When** another standby participant in the same session
   reaches its threshold, **Then** the pivot rate cap MUST
   be checked AND no additional pivot MUST inject (default
   cap of 1).
3. **Given** an `always`-mode participant reaches the same
   threshold, **When** the pivot evaluator runs, **Then** the
   pivot MUST inject as a system message AND the
   `always`-mode participant's next dispatch MUST process the
   pivot via the acknowledgment delta path (the AI responds
   to the pivot offer).
4. **Given** the pivot has been injected for a
   `wait_for_human`-mode participant, **When** the next
   round-robin tick runs, **Then** the participant MUST
   transition to the long-term-observer sub-state AND
   `admin_audit_log` MUST record
   `action='standby_observer_marked'`.
5. **Given** a long-term-observer participant, **When** the
   gating condition finally clears, **Then** the participant
   MUST exit observer + standby cleanly back to `active` on
   the next tick — observer is not sticky any more than
   standby is.

---

### Edge Cases

- **Participant has `wait_mode='wait_for_human'` AND emits an
  `ai_question_opened` for THEMSELVES** (a question they want
  the orchestrator to ignore). The standby evaluator does not
  distinguish self-targeted vs. human-targeted questions. v1
  treats every unresolved question as a gating signal; if
  this produces false positives, the question detector (spec
  004) is the right place to refine target tagging.
- **Multiple gating signals fire simultaneously** (an AI has
  both an unresolved question AND a pending review-gate).
  Standby fires on the first signal; the WS event reason
  reflects the first-firing signal. When the first signal
  clears, the evaluator re-runs and standby may persist if
  the second signal is still unresolved.
- **Participant departs the session while in standby.** The
  participant's row transitions to `removed`; standby state
  is cleared as part of the departure flow (spec 002 §FR-016
  cascade). The unresolved gating event for that participant
  remains in the audit log but no longer affects loop state.
- **`always`-mode participant's response after the
  acknowledgment delta still produces filler.** Spec 021's
  filler scorer flags the response; the standby evaluator
  notes the filler turn but does NOT auto-transition the
  always-mode participant to standby (`always` mode is
  intentionally opt-out of standby). The operator can manually
  switch the participant to `wait_for_human` mode if the
  filler pattern persists.
- **The pivot message itself contains content that triggers
  spec 007's security pipeline.** The pivot text is hardcoded
  in `src/orchestrator/standby.py` (or equivalent) and
  pre-validated; it is structurally a system message and
  inherits system-tier trust per spec 007 §7.6. If a future
  amendment changes the pivot text, that amendment runs the
  text through the security pipeline as part of CI.
- **Pivot timeout reached but rate cap exhausted.** The
  evaluator notes the would-have-pivoted condition in
  `routing_log` with `reason='pivot_skipped_rate_cap'` so
  operators see when the cap is biting. The participant
  remains in standby; the long-term-observer transition
  does NOT fire automatically when the rate cap blocks the
  pivot.
- **Standby evaluator runs while the loop is paused.** The
  evaluator skips paused loops; standby state does not
  advance during pause. On resume, the evaluator re-runs and
  may transition the participant to standby per current gates.
- **Detection signal #3 fires on the same turn as the
  proposal opens.** The repetition guard (last-N-turns
  similarity) prevents this — N must be at least 2 for the
  similarity check to have a baseline. v1 hardcodes N=2;
  larger windows are an operator-tunable enhancement if
  false-positive rate is too high.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A new `participants.wait_mode` column MUST be
  added with values `wait_for_human` (default) | `always`.
  Existing participant rows default to `wait_for_human` on
  migration.
- **FR-002**: The `participants.status` enum MUST gain a new
  value `standby` alongside the existing values (`active`,
  `pending`, `paused`, `removed`, `circuit_open`).
- **FR-003**: A standby evaluator MUST run as part of the
  round-robin tick (spec 003 §FR-005) before participant
  selection. The evaluator inspects each
  `wait_mode='wait_for_human'` participant for any of the
  four detection signals.
- **FR-004**: Detection signal #1 MUST identify any
  participant with an unresolved `ai_question_opened` event
  (spec 004's question detector) emitted by their own prior
  turn.
- **FR-005**: Detection signal #2 MUST identify any
  participant with a pending `review_gate_staged` event for
  their draft (spec 007 §FR-005).
- **FR-006**: Detection signal #3 MUST identify any
  participant whose `proposal_*` event awaits their vote AND
  the participant's last 2 turns satisfy
  (cosine_similarity > 0.8 AND new_token_count < 50). The
  similarity computation reuses spec 004's
  sentence-transformers pipeline.
- **FR-007**: Detection signal #4 MUST consume spec 014's
  off-rails signal (the filler heuristic) rather than
  reimplementing it. Signal-source-of-truth is in 014; spec
  027 reads it.
- **FR-008**: When any detection signal fires for a
  participant in `wait_mode='wait_for_human'`, the evaluator
  MUST transition the participant to `standby` AND emit
  `admin_audit_log` `action='standby_entered'` with the
  triggering signal name.
- **FR-009**: A standby participant MUST be skipped from
  round-robin dispatch (no turn produced, no tokens spent).
- **FR-010**: A `participant_standby` WS event MUST broadcast
  on every standby-entry transition with payload
  `{participant_id, reason: "awaiting_human"|"awaiting_gate"|
  "awaiting_vote", since_turn}`.
- **FR-011**: When all detection signals clear for a
  participant in standby, the evaluator MUST transition them
  back to `active` on the next tick AND emit
  `admin_audit_log` `action='standby_exited'` AND a
  `participant_standby_exited` WS event.
- **FR-012**: `paused` MUST supersede `standby`. A facilitator
  manually pausing a standby participant transitions them to
  `paused`; on manual resume, the standby evaluator re-runs
  and may transition them back to `standby` if a gate is
  still active.
- **FR-013**: `circuit_open` MUST take precedence over
  `standby`. Participants in `circuit_open` are NOT subject
  to standby evaluation.
- **FR-014**: Participants with `wait_mode='always'` MUST
  NOT be transitioned to `standby` regardless of gating
  signals. Their dispatch fires normally with the
  acknowledgment delta added when any gate is unresolved.
- **FR-015**: The `always`-mode acknowledgment delta MUST be
  injected at Tier 4 (spec 008's tier-4 hook) when any
  detection signal would have fired in `wait_for_human` mode.
  Delta text is hardcoded in `src/prompts/standby_ack_delta.py`
  (settled in `/speckit.plan`).
- **FR-016**: The `always`-mode delta MUST compose additively
  with spec 021's register-slider delta and spec 025's
  conclude-phase delta. Documented order: register first,
  conclude second, wait-acknowledgment third.
- **FR-017**: An auto-pivot mechanism MUST inject a system-
  level pivot message into the transcript when a participant
  has been in standby for N consecutive cycles
  (`SACP_STANDBY_FILLER_DETECTION_TURNS`, default 5) AND
  `SACP_STANDBY_PIVOT_TIMEOUT_SECONDS` (default 600) have
  elapsed since the gating event opened.
- **FR-018**: The pivot message MUST be persisted with
  `speaker_type='system'` AND a `kind='orchestrator_pivot'`
  discriminator (column or metadata field, settled in
  `/speckit.plan`). The discriminator distinguishes pivot
  messages from other system messages for spec 005
  summarizer + spec 011 UI.
- **FR-019**: Pivot rate MUST be capped per session via
  `SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION` (default 1).
  When the cap is reached, subsequent would-have-pivoted
  conditions MUST log
  `routing_log.reason='pivot_skipped_rate_cap'` and skip
  the injection.
- **FR-020**: After a pivot fires for a `wait_for_human`-mode
  participant, the orchestrator MUST transition them to a
  long-term-observer sub-state (still standby, but with
  `kind='long_term_observer'` flag). `admin_audit_log` MUST
  record `action='standby_observer_marked'`.
- **FR-021**: A long-term-observer participant MUST exit
  cleanly back to `active` when their gating condition
  clears (no manual reset required).
- **FR-022**: The pivot text is hardcoded in v1 and pre-
  validated through spec 007's security pipeline at module
  import time. Any future amendment that changes the text
  MUST run the new text through the same validation in CI.
- **FR-023**: Standby evaluator overhead MUST be O(1) per
  participant per tick — a constant-time lookup against
  the unresolved-gates set per participant. No scans across
  the message store.
- **FR-024**: The four new env vars
  (`SACP_STANDBY_DEFAULT_WAIT_MODE`,
  `SACP_STANDBY_FILLER_DETECTION_TURNS`,
  `SACP_STANDBY_PIVOT_TIMEOUT_SECONDS`,
  `SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION`) MUST have
  validator functions in `src/config/validators.py` registered
  in the `VALIDATORS` tuple, AND corresponding sections in
  `docs/env-vars.md` with the six standard fields, BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable
  gate).
- **FR-025**: A facilitator MUST be able to set or change a
  participant's `wait_mode` mid-session via a new endpoint
  (path TBD in `/speckit.plan`; mirrors existing
  participant-settings endpoints from spec 002). Changes
  emit `admin_audit_log` rows with actor, target, old, new,
  timestamp.
- **FR-026**: Standby state changes MUST coordinate with
  spec 013/014 observer-downgrade evaluation: standby takes
  precedence (gate-blocked outranks traffic-shape).
  Observer-downgrade evaluator MUST skip participants
  already in standby.

### Key Entities

- **WaitMode** — enum on `participants.wait_mode` with values
  `wait_for_human` | `always`.
- **StandbyState** — virtual state on
  `participants.status='standby'` plus the long-term-observer
  sub-state via a separate flag (column or metadata). Auto-
  managed by the orchestrator; not facilitator-settable
  directly.
- **DetectionSignal** (transient) — one of four signal types
  the standby evaluator inspects per participant per tick.
  Sourced from spec 004 (question, density), spec 007
  (review_gate), 014 (off-rails).
- **PivotMessage** — system message persisted with
  `speaker_type='system'` and `kind='orchestrator_pivot'`.
  Hardcoded text; pre-validated through security pipeline.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A `wait_for_human`-mode participant with an
  unresolved gating signal MUST be skipped from dispatch
  (zero turns produced, zero tokens spent during the standby
  window). Verified by an end-to-end test driving the gate
  and asserting no dispatch fires for the participant.
- **SC-002**: An `always`-mode participant with an unresolved
  gating signal MUST dispatch normally with the
  acknowledgment delta in the prompt. Verified by an
  end-to-end test asserting both the dispatch and the delta's
  presence in the assembled prompt.
- **SC-003**: Standby evaluation MUST be O(1) per participant
  per tick. Verified by a perf test asserting evaluator
  cost is below the routing_log per-stage timing P95
  baseline.
- **SC-004**: Standby exit MUST happen on the next tick after
  the gating condition clears. Verified by a multi-tick
  test driving gate-clear and asserting the exit transition
  occurs on the immediately-following tick.
- **SC-005**: Per-session pivot rate cap MUST be honoured.
  Verified by a multi-participant standby test that drives
  the threshold for two participants and asserts only one
  pivot fires.
- **SC-006**: Standby precedence over observer-downgrade
  MUST be enforced. Verified by an integration test with
  spec 013 observer-downgrade enabled, driving a participant
  into both standby and observer-downgrade conditions, and
  asserting standby is the active state.
- **SC-007**: Tier 4 delta composition MUST be additive in
  the documented order. Verified by a test with spec 021
  register slider, spec 025 conclude phase, and spec 027
  always-mode delta all active simultaneously, asserting all
  three deltas appear in the assembled prompt in the
  documented order.
- **SC-008**: Pivot message MUST persist with
  `kind='orchestrator_pivot'`. Verified by a pivot-trigger
  test asserting the message row's discriminator field.
- **SC-009**: Long-term-observer transition MUST exit cleanly
  back to `active` when the gate clears. Verified by a test
  driving the observer transition and the subsequent gate
  clear.
- **SC-010**: With any of the four new env vars set to an
  invalid value, the orchestrator process MUST exit at
  startup with a clear error message naming the offending
  var (V16 fail-closed gate observed in CI).
- **SC-011**: A `wait_mode` change via the new endpoint MUST
  emit one `admin_audit_log` row with the change details.
  Verified by an end-to-end test asserting the row content.

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** (orchestrator-driven
topologies). The standby state is an orchestrator-side
participant FSM; the standby evaluator runs in the
orchestrator's per-tick loop; the pivot message is emitted
through the orchestrator's transcript persistence path. All
require a single orchestrator to be the participant-state
authority.

This feature is **NOT applicable to topology 7 (MCP-to-MCP,
Phase 3+)**. In topology 7 each participant's MCP client is
its own dispatch authority; there is no orchestrator-side
participant FSM to apply standby to. Per V12: any topology-7
deployment MUST recognize that this spec's standby modes do
not apply.

### V13 — Use Case Coverage

This feature serves the V13 primary use cases:

- §2 Research Paper Co-authorship
  (`docs/sacp-use-cases.md` §2) — research sessions run
  asynchronously over weeks. AIs in `wait_for_human` mode
  cleanly stand by during the lead author's absence rather
  than burning tokens on filler. AIs in `always` mode
  continue methodology debate while waiting for the lead's
  clarification, with the acknowledgment delta surfacing
  the assumption.
- §3 Consulting Engagement
  (`docs/sacp-use-cases.md` §3) — consulting sessions often
  gate on client approval (proposal voting, review-gate
  approvals). Standby keeps the AI panel quiet during
  approval windows.
- §6 Decision-Making Under Asymmetric Expertise
  (`docs/sacp-use-cases.md` §6) — expert-advisory sessions
  gate decisions on the expert's input. AIs await the
  expert in standby rather than producing speculative
  filler.

Other use cases (§1, §4, §5, §7) inherit the feature when
operators opt in but are not the priority drivers.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts.
This spec contributes three budgets:

- **Standby evaluator per participant per tick**: O(1).
  Constant-time lookups against the unresolved-gates set
  for each participant. P95 < 1ms per participant. Budget
  enforcement: per-tick timing on the routing_log per-stage
  timing path (spec 003 §FR-030).
- **Pivot injection (when fired)**: O(1). One
  `admin_audit_log` write + one transcript message persist
  + one WS broadcast. Rate-capped at
  `SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION` per session
  lifetime. P95 < 100ms.
- **Standby state transition (entry/exit)**: O(1). One
  `participants.status` update + one `admin_audit_log`
  write + one WS broadcast. P95 < 50ms.

## Configuration (V16) — New Env Vars

Four new env vars are introduced. Each MUST have type, valid
range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this
spec (per V16 deliverable gate).

### `SACP_STANDBY_DEFAULT_WAIT_MODE`

- **Intended type**: string enum
- **Intended valid range**: `wait_for_human` | `always`.
  Default `wait_for_human`.
- **Fail-closed semantics**: any non-enum value MUST cause
  startup exit. The default applies to new participants;
  facilitators can override per participant.

### `SACP_STANDBY_FILLER_DETECTION_TURNS`

- **Intended type**: positive integer
- **Intended valid range**: `[2, 100]`. Default `5`. Below
  2 makes the repetition guard meaningless; above 100 makes
  the pivot trigger effectively unreachable.
- **Fail-closed semantics**: outside the range MUST cause
  startup exit.

### `SACP_STANDBY_PIVOT_TIMEOUT_SECONDS`

- **Intended type**: positive integer (seconds)
- **Intended valid range**: `[60, 86400]` (1 minute to 1
  day). Default `600` (10 minutes).
- **Fail-closed semantics**: outside the range MUST cause
  startup exit.

### `SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION`

- **Intended type**: positive integer
- **Intended valid range**: `[0, 100]`. Default `1`. Zero
  disables auto-pivot entirely (operators who want pure
  standby with no orchestrator intervention).
- **Fail-closed semantics**: outside the range MUST cause
  startup exit.

## Cross-References to Existing Specs and Design Docs

- **Spec 003 (turn-loop-engine) §FR-005** — round-robin
  dispatcher. Spec 027 adds the standby evaluator as a
  pre-selection step in the tick. Standby participants are
  skipped via the existing skip-set mechanism.
- **Spec 003 (turn-loop-engine) §FR-021** — loop FSM states.
  Spec 027 adds `standby` as a participant-level sub-state
  (not a loop-level state); the loop FSM is unchanged.
- **Spec 003 (turn-loop-engine) §FR-030** — `routing_log`
  per-stage timings. Spec 027 adds `standby_eval_ms` to the
  per-tick stage timings.
- **Spec 004 (convergence-cadence)** — question detector
  (`ai_question_opened`) is detection signal #1 source.
  Sentence-transformers pipeline is reused for detection
  signal #3's stance-similarity computation.
- **Spec 005 (summarization-checkpoints)** — pivot messages
  with `kind='orchestrator_pivot'` are distinguishable from
  human or AI messages. Spec 005 may filter or include them
  in the summarizer corpus per its policy (settled in
  `/speckit.plan`).
- **Spec 007 (ai-security-pipeline) §FR-005, §7.6** —
  review_gate_staged events are detection signal #2 source.
  Pivot text inherits system-tier trust per the trust-tiered
  content model; pre-validated through the security
  pipeline.
- **Spec 008 (prompts-security-wiring)** — Tier 4 hook for
  the always-mode acknowledgment delta. Composes with spec
  021 register delta and spec 025 conclude delta in the
  documented additive order.
- **Spec 011 (web-ui)** — UI affordances: `wait_mode` badge
  on participant card, `standby` pill on participant card,
  pivot message rendered with distinct styling, long-term-
  observer badge variant. Coordinated FR additions to 011
  once 027's tasks are scheduled.
- **Spec 013 (high-traffic-mode)** — observer-downgrade
  precedence: standby (gate-blocked) outranks observer-
  downgrade (traffic-shape). FR-026 enforces this.
- **Spec 014 (dynamic-mode-assignment)** — off-rails signal
  source. Detection signal #4 consumes 014's signal rather
  than reimplementing the filler heuristic. Coordinated
  signal vocabulary.
- **Spec 015 (provider-failure-detection)** — `circuit_open`
  precedence: circuit_open outranks standby (FR-013). A
  participant in circuit_open does not undergo standby
  evaluation.
- **Spec 021 (ai-response-shaping)** — Tier 4 register-delta
  composition. Spec 027's always-mode delta attaches at
  Tier 4 in additive order with spec 021's register delta.
- **Spec 025 (session-length-cap)** — Tier 4 conclude-delta
  composition. Spec 027's always-mode delta composes with
  spec 025's conclude delta in the documented additive
  order.
- **Spec 002 (participant-auth)** — participant-settings
  endpoint pattern. The new `wait_mode` setter mirrors the
  existing participant-settings shape.
- **Spec 001 (core-data-model)** — schema additions:
  `participants.wait_mode` column, `participants.status`
  enum extension, new audit-log action names. Migration
  follows §FR-017 forward-only constraint.
- **Constitution §10** — Phase 3 deliverables list. Spec 027
  is in-scope for Phase 3 by virtue of Phase-3 declaration
  recorded 2026-05-05.
- **Constitution §14.1** — Feature work workflow.
- **Constitution V12** — topology applicability. Spec 027
  applies to topologies 1-6; incompatible with topology 7.
- **Constitution V13** — primary use cases research
  co-authorship (§2), decision-making under asymmetric
  expertise (§6), consulting (§3).
- **Constitution V14** — per-stage timing budgets. Spec 027
  contributes three budgets (Performance Budgets section).
- **Constitution V16** — env-var validation at startup.
  Spec 027 introduces four new vars (Configuration section).

## Assumptions

- Standby is the auto-managed counterpart to the existing
  `paused` (manual, sticky) and `circuit_open` (failure,
  requires reset) states. The orchestrator handles standby
  entry and exit transparently; facilitators see the state
  in the UI but do not need to manage it.
- The four detection signals are stable enumerations in
  v1. Adding a fifth signal type requires a future
  amendment with new test fixtures.
- The `always` mode is opt-in per participant. Operators
  with use cases where AI progress despite human absence
  is preferred (research methodology debate, exploratory
  technical review) opt in on a per-AI basis. The default
  is `wait_for_human` because token-cost preservation is
  the more common operational preference.
- The acknowledgment delta in `always` mode is fixed text
  in v1 (`src/prompts/standby_ack_delta.py`). Operator-
  tunable delta text is a future enhancement.
- The pivot message text is fixed and pre-validated through
  the security pipeline. The pivot is a hardcoded
  orchestrator-emitted utterance, not a translated or
  AI-generated message — so the security pipeline runs
  once at module import, not per pivot.
- Coordination with spec 014's off-rails signal vocabulary
  is critical to avoid double-firing on the same low-content
  pattern. Detection signal #4 reads 014's signal rather
  than reimplementing it (FR-007).
- The pivot rate cap is per-session, not per-participant,
  in v1. A session with three AIs reaching threshold
  produces one pivot. Per-participant rate-capping is a
  future enhancement if operator experience reveals the
  per-session cap is too aggressive.
- Standby + observer-downgrade precedence (standby wins) is
  the right default because gate-blocked is a harder
  constraint than traffic-shape. Operators who prefer the
  inverse can argue for it via a future amendment.
- Phase 3 declared 2026-05-05 satisfies the phase gate;
  this spec stays scaffold-only until tasks are scheduled.
  No implementation begins on this spec until the user
  invokes `/speckit.clarify` and subsequent workflow steps.
- Status remains Draft until clarifications resolve and the
  user accepts the scaffolding.
