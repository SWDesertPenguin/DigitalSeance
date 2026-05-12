# Feature Specification: AI Participant Standby Modes (wait_for_human + always)

**Feature Branch**: `027-participant-standby-modes`
**Created**: 2026-05-07
**Status**: Implemented 2026-05-12 (Phase 3 declared 2026-05-05; clarify + plan + tasks + implementation shipped in a single full pass; spec 011 amendments FR-052..FR-059 land alongside)
**Spec Version**: 1.1.0 | **Last Amended**: 2026-05-12 | **Amended In**: Spec 027 full pass — clarify session 2026-05-12 + implementation
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

### Session 2026-05-12 (full-pass resolution)

All eight initial-draft markers resolved at the start of the full-pass clarify + plan + tasks + implement session. Resolutions below are now binding contract; downstream FR text and `/speckit.plan` artifacts encode them directly.

- **Q1 — Spec 013/014 observer-downgrade precedence.** Resolution: **standby-wins**. When a participant is eligible for both standby (gate-blocked) and observer-downgrade (traffic-shape), the standby evaluator transitions the participant to `standby` and the observer-downgrade evaluator MUST skip participants already in `standby`. Encoded in FR-026. Rationale: gate-blocked is a harder operational constraint than traffic-shape (the human-input gate cannot be cleared by changing traffic shape), and compose-as-additive (standby AND observer simultaneously) would defeat the round-robin skip-set arithmetic (a participant in two skip states is no more skipped than a participant in one).
- **Q2 — Detection signal #4 vs. spec 014/021 filler heuristic.** Resolution: **consume the signal source-of-truth that already shipped**. Spec 014's nearest "off-rails" surface in production is the `density_anomaly` signal of its DmaController. Spec 021 ships the canonical filler-scorer (`src/orchestrator/shaping.py:compute_filler_score`) consumed by the response-shaping retry pipeline. Spec 027 detection signal #4 reads **spec 021's filler-scorer aggregate output** (via `routing_log.filler_score` rows, which 021 writes per-turn). The "off-rails signal vocabulary" coordination with spec 014 (called out in the user's brief) is satisfied by: (a) re-using the same threshold env var family (`SACP_STANDBY_*` mirrors `SACP_DMA_*` shape), and (b) not double-firing when both DMA's density_anomaly AND 027's filler-stuck signal would trip on the same turn — 027's evaluator skips signal-#4 when a `density_anomaly` `routing_log` row exists for the current tick for the same participant. Encoded in FR-007.
- **Q3 — Standby exit semantics on gate clear.** Resolution: **next-tick exit**. When the gating condition clears (human reply resolves the question event, facilitator approves the review gate, proposal vote arrives), the standby evaluator clears the standby flag on the NEXT round-robin tick. The participant dispatches on their next eligible round-robin slot, NOT immediately mid-tick. Encoded in FR-011. Rationale: immediate-pre-empt would invite race conditions with concurrent in-flight dispatches and complicate the loop's per-tick FSM contract; next-tick exit is bounded by the loop's existing tick cadence (sub-second in typical configurations).
- **Q4 — Manual pause of a standby participant.** Resolution: **paused-supersedes**. A facilitator-issued pause on a standby participant transitions the participant from `status='standby'` to `status='paused'`. The standby evaluator MUST NOT re-transition a `paused` participant. On manual resume, the standby evaluator re-runs on the next tick and MAY transition the participant back to `standby` if a gate is still active. Encoded in FR-012. Rationale: facilitator authority is the higher-priority signal; the facilitator manually pausing is an explicit "do not dispatch this participant" decision that survives gate clearance.
- **Q5 — Tier 4 delta composition order.** Resolution: **fixed-additive-order**: spec 021 register-slider delta first, spec 025 conclude delta second, spec 027 wait-acknowledgment delta third. The composition operates on the existing `assemble_prompt` Tier 4 surface (`src/prompts/tiers.py`). Encoded in FR-016. Rationale: operator-configurable order is a footgun (operators reordering deltas could land in tested-but-illegal compositions); fixed order is auditable, testable end-to-end, and mirrors the order each delta SHIPPED in (021 → 025 → 027).
- **Q6 — Pivot rate-cap scope.** Resolution: **per-session, not per-participant**. A session with three AIs all in standby produces at most `SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION` pivots total across the session lifetime. Encoded in FR-019. Rationale: the pivot is a session-level rhetorical event ("the human is not coming back; pivot or self-mark observer") — capping per-participant would produce three near-identical pivot messages in a 3-AI session, which is noisier than a single session-level pivot. Per-participant rate-capping is a future amendment if operator experience reveals the per-session cap is too aggressive.
- **Q7 — Pivot message envelope.** Resolution: **`speaker_type='system'` + `kind='orchestrator_pivot'` metadata key**. The discriminator lives in the existing `messages.metadata` JSONB column (spec 001) — no new column required. Spec 005's summarizer can filter by `metadata->>'kind' = 'orchestrator_pivot'`; spec 011's UI can render pivot messages distinctly via the same key. Encoded in FR-018. Rationale: a dedicated `speaker_type='pivot'` would propagate the discriminator through every check-site that switches on speaker_type (security pipeline, summarizer, UI) — high blast radius for a single message kind.
- **Q8 — Detection signal #3 stance-similarity threshold.** Resolution: **two-condition AND** (cosine similarity > 0.8 AND new-token count < 50 against the immediately prior turn). The thresholds are not env-tunable in v1 — they are hardcoded in `src/orchestrator/standby.py` matching the values in spec 004 §FR-014 and §FR-016. Encoded in FR-006. Rationale: either-OR fires too aggressively (every short-but-novel turn would flag); operator-tunable adds an env-var surface for a behavior that should be uniform across sessions in v1. If operator experience reveals false positives, a Constitution §14.2 amendment exposes the values as env vars.
- **Q9 — Phase 1+2 shakedown paraphrase.** Resolution: **paraphrase is acceptable as-drafted**. The Overview's paraphrased shakedown observation ("an AI asks the facilitator a question…subsequent turns repeat the same stance with minor variations") carries no test session IDs, no participant names, and no provider identifiers; the paraphrase is acceptable for publication per the user-described "minimize-AI-footprint" + "no-local-references" memory rules.

### Session 2026-05-12 (consequential follow-on resolutions surfaced during plan/implement)

- **Q10 — long-term-observer storage shape.** A participant transitions to a "long-term observer" sub-state after FR-020's pivot fires for a `wait_for_human` participant. Resolution: the sub-state is a boolean flag on `participants.wait_mode_metadata` JSONB (new column added by migration `021_participant_standby_modes.py`), specifically the key `long_term_observer=true`. The participant's primary `status` remains `standby` so the round-robin skip-set arithmetic is unchanged; the UI badge variant (spec 011 FR-058) reads the JSONB flag.
- **Q11 — pivot-cycle accumulator durability.** Resolution: the consecutive-standby-cycles counter is durable per-participant per-session, persisted in `participants.standby_cycle_count` (new column). Volatile in-memory accumulator would reset on loop restart, which is exactly the case where the pivot is most valuable (the human IS absent across the restart window). Mirrors the spec-025 active-seconds durability decision.
- **Q12 — env-var prefix conformance.** All four new env vars adopt the `SACP_STANDBY_*` prefix matching the spec name. Validator function names mirror the env-var names with `validate_` prefix per the audit-batch-5 catalog convention.



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
- **FR-007**: Detection signal #4 MUST consume spec 021's
  filler-scorer aggregate output (`routing_log.filler_score`
  per spec 021 FR-002/FR-004) as its signal source rather
  than re-implementing the filler heuristic locally. The
  evaluator reads the most recent N=2 `routing_log` rows for
  the participant (matching FR-006 N=2) and trips signal #4
  when both rows carry `filler_score >= SACP_FILLER_THRESHOLD`
  (or the per-family default when the env var is unset). The
  evaluator MUST skip signal #4 for the current tick when the
  same participant has a `routing_log` row with `density_anomaly`
  recorded for this tick (spec 014's nearest-neighbour
  signal) — this is the off-rails-vocabulary coordination
  with spec 014 per the user brief, preventing double-firing
  on the same low-content pattern. Resolved per Session
  2026-05-12 Q2.
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
  discriminator stored in the existing `messages.metadata`
  JSONB column (spec 001) — no new column. Spec 005's
  summarizer filters via `metadata->>'kind' =
  'orchestrator_pivot'`; spec 011's UI renders via the same
  key. Resolved per Session 2026-05-12 Q7.
- **FR-019**: Pivot rate MUST be capped per session via
  `SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION` (default 1).
  When the cap is reached, subsequent would-have-pivoted
  conditions MUST log
  `routing_log.reason='pivot_skipped_rate_cap'` and skip
  the injection.
- **FR-020**: After a pivot fires for a `wait_for_human`-mode
  participant, the orchestrator MUST transition them to a
  long-term-observer sub-state. The participant's `status`
  remains `standby` (round-robin skip-set arithmetic
  unchanged); the sub-state is recorded as
  `long_term_observer=true` in the new
  `participants.wait_mode_metadata` JSONB column (migration
  `021_participant_standby_modes.py`). `admin_audit_log` MUST
  record `action='standby_observer_marked'`. Resolved per
  Session 2026-05-12 Q10.
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
  already in standby. Resolved per Session 2026-05-12 Q1.
- **FR-027**: The consecutive-standby-cycles counter (FR-017
  pivot trigger denominator) MUST be persisted in
  `participants.standby_cycle_count` (new column added by
  migration `021_participant_standby_modes.py`). The
  counter increments on each round-robin tick where the
  participant remained in `standby`; the counter resets to 0
  on every standby-exit transition. Volatile in-memory
  accumulation would lose state on loop restart, which is
  the exact case where the pivot is most useful (human
  absent across the restart window). Resolved per Session
  2026-05-12 Q11.
- **FR-028**: The four new env vars adopt the
  `SACP_STANDBY_*` prefix matching the spec name. Validator
  function names are `validate_standby_default_wait_mode`,
  `validate_standby_filler_detection_turns`,
  `validate_standby_pivot_timeout_seconds`,
  `validate_standby_pivot_rate_cap_per_session`. Resolved
  per Session 2026-05-12 Q12.
- **FR-029**: Five new `admin_audit_log` action labels MUST
  be registered in both `src/orchestrator/audit_labels.py`
  AND `frontend/audit_labels.js` (the CI parity gate per
  spec 029 enforces equality): `standby_entered`,
  `standby_exited`, `pivot_injected`,
  `standby_observer_marked`, `wait_mode_changed`. The
  `wait_mode_changed` label backs FR-025's facilitator
  endpoint audit row.

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

## Spec 011 Amendment Coordination (Phase 3, FR-052..FR-059)

Per the user's reminder memory (`reminder_spec_011_amendments_at_impl_time.md`), the spec 011 web-UI amendment is co-drafted with this spec's implementation rather than carried as a forward-ref. Reserved slots for this lane: **FR-052..FR-059 (8 FRs)**. Lane A (spec 024 facilitator scratch) consumes FR-042..FR-049; FR-050..FR-051 are intentionally left as a gap-buffer per the user's parallel-lane coordination memo. The eight amendments cover:

- **FR-052** — Participant card MUST render a `wait_mode` badge with two states (`wait_for_human` / `always`). The badge is gated by FR-009 role check (facilitator-only); non-facilitators MUST NOT see the badge.
- **FR-053** — Participant card MUST render a `standby` pill when the participant's `status='standby'`, distinct from the existing `paused-manual` / `paused-breaker` indicators (spec 011 FR-020). The pill consumes `participant_standby` / `participant_standby_exited` WS events. Pill copy: "Standby — awaiting <reason>" with reason from the WS payload (`awaiting_human` / `awaiting_gate` / `awaiting_vote`).
- **FR-054** — Facilitator admin panel MUST expose a `wait_mode` toggle per participant, posting to the FR-025 endpoint. The control is gated by FR-009 role check; non-facilitators MUST NOT see the toggle.
- **FR-055** — Pivot messages (rendered from `messages.metadata->>'kind' = 'orchestrator_pivot'`) MUST render with distinct styling — a banner-style affordance distinguishing them from regular participant turns and from non-pivot system messages. The renderer reads the metadata key directly; no separate API call required.
- **FR-056** — Long-term-observer participants (FR-020 sub-state, `wait_mode_metadata->>'long_term_observer' = 'true'`) MUST render a badge variant on their participant card distinct from the regular `standby` pill — copy: "Long-term observer — human absent". The badge is gated by FR-009 role check.
- **FR-057** — The participant card layout MUST tolerate the addition of the `wait_mode` badge + `standby` pill + long-term-observer badge variant without overflowing the card's bounded width on a standard 1280px-wide Phase 1+2 viewport. The renderer truncates any badge copy that exceeds 24 characters with an inline `[expand]` link.
- **FR-058** — The `participant_update` WS event payload MUST include the participant's current `wait_mode` and `wait_mode_metadata` fields so the SPA can render the badges from a state-snapshot reconnect path AND from any mid-session update without a polling refetch. Cross-ref spec 002 §FR-016 participant-update broadcast.
- **FR-059** — The four new audit-action labels from FR-029 (`standby_entered`, `standby_exited`, `pivot_injected`, `standby_observer_marked`, `wait_mode_changed`) MUST appear in the spec 029 audit-log viewer (when `SACP_AUDIT_VIEWER_ENABLED=true`) with the human-readable strings registered in `src/orchestrator/audit_labels.py` and mirrored in `frontend/audit_labels.js`. The CI parity gate enforces equality.

These amendments land alongside the spec 027 implementation in the same PR; the spec 011 `## Implementation Phases` section gains a new subsection "Phase 3d — Standby UI (ships with spec 027)" capturing the same eight FRs.

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
