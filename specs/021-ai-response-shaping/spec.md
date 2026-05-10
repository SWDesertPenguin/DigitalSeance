# Feature Specification: AI Response Shaping (Verbosity Reduction + Register Slider)

**Feature Branch**: `021-ai-response-shaping`
**Created**: 2026-05-07
**Status**: Implemented 2026-05-09 (Phase 3 declared 2026-05-05; tasks T001-T058 + T060 landed across Phases 1-6; T059 spec 011 register-slider UI alignment is deferred per memory `reminder_spec_011_amendments_at_impl_time` until the user schedules spec 011 amendments)
**Input**: User description: "Phase 3 AI response shaping. Backlog items #1 (verbosity / filler reduction) and #11 (response-style slider — casual ↔ technical/direct) attack the same axis from two angles. Two configurable dimensions: (1) length — post-output filler scoring catches hedge-to-content ratio, turn-restatement, boilerplate closings, with per-model behavioral profile and a structured turn-format delta in the system prompt that makes padding awkward; (2) register — per-session OR per-participant slider 1-5 feeding a Tier 4 delta in the prompt assembler with saved presets (Direct / Conversational / Technical / Academic). Compress-on-commit work is deferred to spec 026 (context compression). Applies to topologies 1-6 (orchestrator-mediated assembly); incompatible with topology 7 per V12. Primary use cases: consulting and research co-authorship per V13."

## Overview

Spec 008 (prompts-security-wiring) ships the four-tier delta system prompt
plus a Tier 4 hook for per-participant custom prompts. The
`fix/token-cost-reduction` PR added a one-sentence conciseness directive
to TIER_LOW; observed sessions in later Phase 1+2 shakedowns show the
real waste is structural — hedging preamble, restatement of prior turns,
boilerplate closings — and persists across all four tiers. A later
shakedown's metaethics debate produced multi-paragraph dissertation-grade replies
on the same models that earlier sessions kept terse, indicating the
register dial is session-scoped, not just model-scoped.

This spec defines **AI response shaping** as two independent,
orthogonal dimensions on the *generation* side of the bridge layer.
The dimensions compose: a session can run with a 1 (Direct) register
AND a tight filler threshold; the two controls do not interact
beyond that.

1. **Length / verbosity dimension.** A post-output **filler scorer**
   evaluates each AI draft before it enters the transcript. Three
   signal types feed a single score: hedge-to-content ratio
   (proportion of hedging tokens to substantive tokens), prior-turn
   restatement (n-gram overlap with the immediately preceding turns),
   and boilerplate closings (formulaic sign-offs that add no
   content). When the score crosses a configured threshold the
   orchestrator triggers a **bounded retry** with a tightened Tier 4
   delta ("Reply briefly and directly, no preamble, no restatement,
   no closing"). Up to two retries, hardcoded — never an infinite
   loop. Per-model behavioral profiles let the threshold and
   retry-delta wording differ across providers because verbosity
   tendencies do.
2. **Register dimension.** A facilitator-controlled session slider
   (1-5) selects among saved register presets that emit a Tier 4
   delta in the prompt assembler. The presets are: 1 (Direct,
   "Reply briefly and directly, no preamble"), 2 (Conversational,
   default mid-register), 3 (Balanced, no register-specific delta —
   tier text alone), 4 (Technical, "Use precise technical
   register; cite sources for non-obvious claims"), 5 (Academic,
   "Use formal academic register; structured argumentation;
   citations expected"). Each participant inherits the session
   slider but can override it for their own AI; overrides are
   audit-logged.

**Compression boundary.** Spec 021 attacks the *generation* side —
what gets produced in each turn. Spec 026 (context compression)
attacks the *storage* side — what gets retained in the rolling
context window after generation. The two specs share neither
pipeline nor configuration; they share only the constitutional
goal of reducing token cost. This spec MUST NOT introduce
compression of stored content. Any work touching stored-content
representation belongs to spec 026.

This spec **scaffolds only**. Implementation begins when the
facilitator schedules tasks per Constitution §14.1. The Phase 3
declaration recorded 2026-05-05 satisfies the phase gate; this
spec stays scaffold-only until tasks land and implementation
reaches Implemented status.

### Glossary

- **Shaping pipeline**: the umbrella term for everything this spec adds — filler scoring, retry orchestration, register slider, per-participant override, and the prompt-assembler Tier 4 deltas. The pipeline runs after a model produces an output and before the orchestrator persists it.
- **Filler scorer**: one component of the shaping pipeline. Computes a numeric score in `[0.0, 1.0]` from three signals (hedge ratio, restatement overlap, closing-pattern density) and triggers retry orchestration when the score exceeds a threshold.
- **Verbosity reduction**: the user-facing problem the filler scorer addresses (the spec title's first half). Not a separate component — it's the outcome the scorer + retry mechanism produce.
- **Register slider**: the facilitator-controlled selector (1-5) that emits canonical Tier 4 prompt deltas. Distinct from the filler scorer; the two operate on orthogonal dimensions (verbosity vs register).

## Clarifications

### 2026-05-07 — Resolutions

All six initial-draft questions resolved. Five matched the drafted defaults; one (retry budget) diverged.

- **Slider preset taxonomy.** Five-position taxonomy with position 3 (Balanced) emitting no register delta — tier text alone. Confirms the drafted shape. Codified by FR-007 and FR-013.
- **Retry budget.** **Up to two retries** (small-integer cap, hardcoded). Diverges from the original one-shot draft. Rationale: an over-threshold first retry can occasionally indicate the model needs a second nudge before falling through; a hardcoded cap of 2 keeps the cost bounded without an extra env var. After two over-threshold drafts the second draft is persisted and `routing_log.reason='filler_retry_exhausted'` is logged. Codified by FR-004 (revised) and SC-003 (revised).
- **Per-model behavioral profile source.** Hardcoded dict in `src/orchestrator/shaping.py`, keyed by provider family (anthropic, openai, gemini, groq, ollama, vllm). Per-model overrides land in a future amendment when session experience justifies the operator-tunable surface. Codified by FR-003.
- **Filler scorer signal aggregation.** Weighted sum of three normalized signals (hedge 0.5, restatement 0.3, closing 0.2). Weights live in the per-model profile and are tunable per provider family. Codified by FR-002.
- **`/me` surfacing of effective register.** Three new fields: `register_slider` (int 1-5), `register_preset` (one of: direct, conversational, balanced, technical, academic), `register_source` (one of: session, participant_override). Two-value source enum — when neither session nor override has been touched, the session row's slider value (defaulting to `SACP_REGISTER_DEFAULT`) is reported with `register_source='session'`. Codified by FR-010.
- **Restatement-overlap signal.** Reuse spec 004's `convergence_log.embedding` for the prior 1-3 turns; compute cosine similarity against the candidate draft's embedding. No second sentence-transformers model load. Codified by FR-001 and FR-012.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Filler scorer flags hedge-heavy drafts and triggers a tightened-delta retry (Priority: P1)

A participant's AI produces a draft with three paragraphs of
hedging preamble, restates the prior turn's central point, then
gets to a one-sentence answer. Today, the draft enters the
transcript verbatim — the participant burns tokens on filler the
session does not benefit from, and downstream summarization (spec
005) inherits the verbosity. With response shaping enabled, the
filler scorer evaluates the draft, computes a score above
`SACP_FILLER_THRESHOLD`, and the orchestrator fires a tightened
Tier 4 delta retry (up to two attempts). The first retry that
scores below threshold becomes the persisted draft; earlier
hedge-heavy drafts are dropped (never persisted) and each retry
event is logged to `routing_log` with `reason='filler_retry'`.

**Why this priority**: P1 because this is the dimension that
moves the token-cost needle today. Phase 1+2 shakedown observations
show structural padding consuming ~30-50% of output tokens on
reasoning-heavy turns; the filler scorer + retry is the only
path that catches it at generation time. Without P1, the spec
ships a register slider that is purely cosmetic.

**Independent Test**: Drive a turn with a participant whose model
is known to produce hedge-heavy output (synthesised via fixture
or recorded transcript). Assert the orchestrator dispatches the
turn, evaluates the response, computes a score above the
configured threshold, fires up to two retries with the tightened
delta, and persists the first retry whose score falls below
threshold (or the second retry's output when both retries also
exceed threshold). Verify `routing_log` rows reflect each retry
event. Verify the transcript has exactly one message for that
turn (the persisted draft, not any earlier hedge-heavy
attempt).

**Acceptance Scenarios**:

1. **Given** `SACP_RESPONSE_SHAPING_ENABLED=true` and a draft
   that scores above `SACP_FILLER_THRESHOLD`, **When** the
   orchestrator processes the response, **Then** a tightened
   Tier 4 delta retry MUST fire (up to two attempts) AND only
   the persisted draft (the first retry below threshold, or
   the second retry's output if both exceed) enters the
   transcript.
2. **Given** a draft that scores below the threshold, **When**
   the orchestrator processes the response, **Then** the
   original draft MUST enter the transcript with no retry.
3. **Given** `SACP_RESPONSE_SHAPING_ENABLED=false`, **When**
   any draft is processed, **Then** no scoring runs, no retry
   fires, and the draft enters the transcript verbatim.
4. **Given** both retries also exceed the threshold, **When**
   the second retry's evaluation completes, **Then** the
   second retry's draft MUST be persisted (not infinite-loop)
   AND `routing_log` MUST record `reason='filler_retry_exhausted'`.
5. **Given** any retry fires, **When** the routing log is
   inspected, **Then** an entry per retry MUST record the
   pre-retry score, the tightened-delta text used, the
   post-retry score, and the retry's per-stage timing
   (cross-ref spec 003 §FR-030).

---

### User Story 2 - Facilitator-set session register slider modifies all participants' Tier 4 deltas (Priority: P2)

A facilitator running a consulting session wants AI replies to
stay direct — no academic preamble, no exhaustive enumeration.
They set the session register slider to 1 (Direct). All
participants' Tier 4 deltas update on the next prompt assembly
to include the Direct preset's delta text. The change is logged
to `admin_audit_log`. Each participant's `/me` response surfaces
the new effective register so the participant (and their AI's
human partner) can see what's in effect.

**Why this priority**: P2 because the slider on its own does
not catch unforeseen filler — a model can still produce hedging
inside a Direct register if its tendencies are strong enough.
But the slider lets the facilitator set the session's tone in
one place rather than per-participant, and it composes with P1
to catch the residual padding the slider doesn't preempt.

**Independent Test**: Drive a session through facilitator-side
slider changes (1 → 5 → 3). After each change, query `/me` for
each participant and assert `register_slider`, `register_preset`,
and `register_source='session'` reflect the new value. Inspect
`admin_audit_log` for one entry per change with the actor
(facilitator), target (session), old value, new value, and
timestamp. Trigger a turn after each change and verify the
assembled prompt contains the new preset's delta text (or no
delta for slider 3).

**Acceptance Scenarios**:

1. **Given** a session with the default register (per
   `SACP_REGISTER_DEFAULT`), **When** the facilitator sets the
   slider to a new value, **Then** the session's register MUST
   update AND `admin_audit_log` MUST record the change with
   actor, target, old, new, and timestamp.
2. **Given** a session-level register change, **When** the next
   turn fires for any participant who has not set a personal
   override, **Then** the assembled prompt MUST include the
   new preset's Tier 4 delta text.
3. **Given** the facilitator sets the slider to 3 (Balanced),
   **When** a turn fires, **Then** the assembled prompt MUST
   contain no register-specific delta — tier text alone.
4. **Given** a participant queries `/me` after a session-level
   change, **When** the response is read, **Then**
   `register_slider`, `register_preset`, and
   `register_source='session'` MUST reflect the current value.

---

### User Story 3 - Per-participant register override with audit-log entry on each change (Priority: P3)

In a research co-authorship session running at register 4
(Technical), the facilitator wants one participant's AI to run
at register 5 (Academic) — that participant is the formal
write-up author and the rest are working notes contributors.
The facilitator sets a per-participant override on that
participant. The override does not affect other participants;
the affected participant's `/me` returns
`register_source='participant_override'`. Every override change
is audit-logged with actor, target participant, old value, and
new value. The override survives session pause/resume and
clears on participant departure or session deletion (cascade,
no orphan rows).

**Why this priority**: P3 because the session-level slider
covers the common case (whole-session register tone). The
per-participant override is an escape hatch for
mixed-register sessions that need finer control. Most
sessions never need it. But when needed, the rule is strict:
override is auditable, scoped to one participant, never
cross-leaks.

**Independent Test**: In a session with a session-level
register, set a per-participant override on one participant.
Verify their `/me` shows `register_source='participant_override'`
while other participants still show `register_source='session'`.
Drive turns and verify only the override-targeted participant's
prompt contains the override's delta. Verify `admin_audit_log`
has the override-set entry with all required fields. Pause and
resume the session — override survives. Remove the participant
— override row disappears (cascade).

**Acceptance Scenarios**:

1. **Given** a participant with no override, **When** an
   override is set, **Then** their `/me` MUST return
   `register_source='participant_override'` AND
   `admin_audit_log` MUST record the change.
2. **Given** a per-participant override, **When** other
   participants in the same session query `/me`, **Then** their
   responses MUST be unaffected (still
   `register_source='session'`).
3. **Given** a per-participant override, **When** the
   override-targeted participant's turn fires, **Then** the
   assembled prompt MUST include the override's preset delta
   text, NOT the session-level preset's text.
4. **Given** a session is paused and resumed, **When** any
   participant's effective register is queried, **Then** any
   pre-existing override MUST persist across the pause cycle.
5. **Given** a participant is removed from the session,
   **When** their override row is queried, **Then** the row
   MUST be gone (cascade per spec 001 §FR-011 atomic delete
   semantics).

---

### Edge Cases

- **Filler scorer raises during evaluation (regex bug, embedding
  read failure).** Score evaluation MUST fail closed: the
  original draft enters the transcript with no retry, and a
  `routing_log.reason='shaping_pipeline_error'` row is logged.
  The session continues; one bad draft does not gate the loop.
- **Retry response also raises a provider error.** Provider
  errors during retry follow the existing dispatch failure
  path (003 §FR-031 compound retry cap). The shaping retry
  consumes one attempt of the provider's compound-retry budget,
  not a separate budget.
- **Slider preset 3 (Balanced) selected with `SACP_RESPONSE_SHAPING_ENABLED=false`.**
  Both controls are independent; the master switch gates only
  the filler scorer + retry. Slider deltas always emit
  regardless of the master switch — the slider is a prompt
  composition concern, not a shaping concern.
- **Per-participant override conflicts with facilitator session
  change.** Override wins. The session change applies to all
  participants without overrides; override-holders keep their
  override until explicitly cleared.
- **`/me` queried for a participant who never had a register
  preference set.** Response returns the session's effective
  values with `register_source='session'` and the session's
  current slider value (which itself defaults to
  `SACP_REGISTER_DEFAULT` if never set).
- **Tightened-delta retry produces output IDENTICAL to the original.** This indicates the model isn't responding to the delta. Both drafts score identically; the pipeline still consumes its retry budget (up to two) and persists the final draft per FR-004's exhausted-retry rule. A `routing_log` row records the equality so operators can spot model insensitivity to the delta. The pipeline still consumes its retry budget (up to two attempts) even when the model's output is unchanged across attempts; v1 does NOT short-circuit on byte-identity because model insensitivity to a tightening delta is rare and the branch complexity isn't worth it. Operators observing high "no-progress" retry rates should tune `SACP_FILLER_THRESHOLD` upward rather than expect early-out behavior.
- **Sentence-transformers embedding pipeline (spec 004) is
  unavailable.** The restatement signal returns `0.0` (no
  detected overlap) and a warning is logged. The hedge and
  closing signals still contribute to the aggregate score; the
  scorer degrades gracefully rather than failing closed on the
  whole turn.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A **filler scorer** MUST evaluate each AI draft
  before persistence on every production dispatch path. The
  scorer MUST consume three signals: hedge-to-content ratio,
  prior-turn restatement (cosine similarity against the prior
  1-3 turns' embeddings via spec 004's pipeline), and
  boilerplate closing detection (regex against a hardcoded
  pattern list).
- **FR-002**: The filler score MUST be a weighted sum of three normalized signals (hedge ratio, restatement overlap, closing-pattern density), each in `[0.0, 1.0]`. Weights MUST sum to `1.0` and live in the per-model `BehavioralProfile`. v1 ships uniform weights `(hedge=0.5, restatement=0.3, closing=0.2)` across all provider families; only `default_threshold` varies per family. Per-family weight overrides are RESERVED future work and not part of v1.
- **FR-003**: A **per-model behavioral profile** MUST map each
  provider family (anthropic, openai, gemini, groq, ollama,
  vllm) to a default `SACP_FILLER_THRESHOLD` value plus default
  signal weights. Profiles MUST live in
  `src/orchestrator/shaping.py` as a hardcoded dict; per-model
  overrides land in a follow-up amendment.
- **FR-004**: When the aggregate filler score exceeds `SACP_FILLER_THRESHOLD` for the participant's provider family, the orchestrator MUST fire a tightened-Tier-4-delta retry. The retry budget is **up to two retries** (hardcoded cap). After the cap (2 retries) is reached without a draft scoring below threshold, the second retry's draft is persisted (it is the most recent draft at cap exhaustion). If the first retry scored below threshold, that draft is persisted and no second retry fires. `routing_log.reason='filler_retry_exhausted'` is emitted on cap-exhaustion. The cap is hardcoded — not env-tunable — to keep the worst-case per-turn dispatch latency bounded.
- **FR-005**: When the master switch `SACP_RESPONSE_SHAPING_ENABLED`
  is false, the filler scorer MUST NOT run. The original draft
  is persisted verbatim.
- **FR-006**: Each tightened-delta retry MUST consume one
  attempt of the participant's provider compound-retry budget
  (spec 003 §FR-031); the shaping pipeline does NOT introduce a
  separate budget. A retry that exhausts the compound budget
  falls through to the existing failure path (turn skipped,
  `routing_log.reason='compound_retry_exhausted'`). The shaping
  cap (FR-004, up to two retries) and the compound-retry budget
  apply jointly: shaping stops at whichever cap is reached
  first.
- **FR-007**: A **session-level register slider** MUST accept
  values 1-5 and emit a Tier 4 delta from the saved-preset
  registry into the prompt assembler (spec 008 §FR-008 Tier 4
  hook). Position 3 (Balanced) MUST emit no delta — tier text
  alone.
- **FR-008**: A **per-participant register override** MUST be settable by the facilitator; when set, it overrides the session slider for that participant alone. Other participants in the same session are unaffected. Override changes MUST be recorded in `admin_audit_log` with actor, target participant, old value, new value, and timestamp. If the facilitator submits a slider value equal to the existing `session_register.slider_value` (or the existing override value, for participant overrides), the row IS updated (`last_changed_at` advances) and an audit row IS emitted (the operator's intent to confirm the value is itself an audit-relevant event). Lifecycle operations on `participant_register_override` rows are: SET (insert or update), CLEAR (delete the row, emits `participant_register_override_cleared` audit event), and LIST. v1 does NOT introduce a facilitator-tool LIST endpoint; operators auditing live overrides query the table directly OR reconstruct the active set from `admin_audit_log` events. A future amendment MAY introduce a list endpoint if operator workflows require it.
- **FR-009**: When no `session_register` row exists for a session, the resolver returns `SACP_REGISTER_DEFAULT` with `register_source='session'`. The facilitator MAY set or update the slider value at any point during the session via the slider-set endpoint; the row is created on first set and updated thereafter. Each change is audit-logged.
- **FR-010**: The `/me` endpoint MUST return three new fields
  per response: `register_slider` (int 1-5), `register_preset`
  (one of: direct, conversational, balanced, technical,
  academic), and `register_source` (one of: session,
  participant_override). The `register_source` enum is intentionally two-valued. When no `session_register` row exists, the resolved source is reported as `session` even though the underlying value is `SACP_REGISTER_DEFAULT`; collapsing default-fallback into `session` reflects the operator-facing semantic that the slider's default IS the session-level state in the absence of an explicit set. Operators auditing whether the facilitator explicitly set a value MUST consult the audit log for `session_register_changed` rather than relying on `register_source`.
- **FR-011**: All shaping decisions (filler-score value, retry fired y/n, retry-delta text, retry score) MUST be logged to `routing_log` per spec 003 §FR-030. The per-stage timings `shaping_score_ms` and `shaping_retry_dispatch_ms` MUST be populated. One `routing_log` row is emitted per dispatch attempt: the original draft produces one row, and each shaping retry produces one additional row. The shaping fields (`shaping_score_ms`, `shaping_retry_dispatch_ms`, `filler_score`, `shaping_retry_delta_text`, `shaping_reason`) are populated per their per-row applicability rules in [data-model.md](./data-model.md).
- **FR-012**: The filler scorer MUST reuse spec 004's
  `convergence_log.embedding` rows for restatement-overlap
  detection. No second embedding-model load is permitted.
  When the spec 004 pipeline is unavailable, the restatement
  signal MUST return 0.0 and continue with the hedge + closing
  signals only.
- **FR-013**: The five-preset register registry MUST be
  hardcoded in `src/prompts/register_presets.py` keyed by
  slider value (1-5). Tier 4 delta text per preset:
  - 1 (Direct): "Reply briefly and directly. No preamble, no
    restatement, no closing."
  - 2 (Conversational): "Reply in a conversational register.
    Brief preamble acceptable; avoid academic register."
    Note: preset 2's "avoid academic register" is in tension with preset 5 (Academic) when sessions cycle between presets across turns. v1 accepts this tension as benign; flag for shakedown observation if cross-preset cycling produces inconsistent register adherence in practice.
  - 3 (Balanced): no delta — tier text alone.
  - 4 (Technical): "Use precise technical register. Cite
    sources for non-obvious claims."
  - 5 (Academic): "Use formal academic register. Structured
    argumentation with explicit citations expected."
- **FR-014**: The three new env vars (`SACP_FILLER_THRESHOLD`,
  `SACP_REGISTER_DEFAULT`, `SACP_RESPONSE_SHAPING_ENABLED`)
  MUST have validator functions in `src/config/validators.py`
  registered in the `VALIDATORS` tuple, AND corresponding
  sections in `docs/env-vars.md` with the six standard fields,
  BEFORE `/speckit.tasks` is run for this spec (V16 deliverable
  gate).
- **FR-015**: Per-participant override rows MUST cascade-delete
  when the participant or session is deleted (spec 001
  §FR-011 atomic-delete semantics). No orphan override rows
  may persist after a session delete.
- **FR-016**: The shaping pipeline (FR-001 through FR-006)
  MUST NOT introduce new compression of stored content. Any
  modification of the persisted message body, the
  `messages.content` column, or the rolling context window
  belongs to spec 026 (context compression) and is OUT OF
  SCOPE here. The retry's output replaces the original draft
  before persistence; once persisted, content is immutable per
  spec 001 §FR-008.

### Key Entities

- **FillerScorer** — pure function over a draft message,
  computing the aggregate filler score from three signals.
  Stateless except for the per-model profile lookup.
- **RegisterPreset** — frozen mapping from slider value (1-5)
  to a preset name and Tier 4 delta text. Hardcoded in
  `src/prompts/register_presets.py`.
- **SessionRegister** (per-session row) — slider value,
  set-by-facilitator-id, last-changed-at. New nullable column
  on `sessions` table (or new `session_register` table —
  decided in `/speckit.plan`).
- **ParticipantRegisterOverride** (per-participant override)
  — slider value, set-by-facilitator-id, last-changed-at.
  Cascades on participant delete and on session delete.
  Schema decided in `/speckit.plan`.
- **ShapingDecision** (transient, per-turn) — the score, the
  retry-fired flag, the retry-delta text, the retry score.
  Logged to `routing_log` per FR-011; not persisted as a
  standalone entity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With `SACP_RESPONSE_SHAPING_ENABLED=true` on a test corpus of hedge-heavy drafts (recorded from Phase 1+2 shakedown sessions), the filler scorer MUST flag the drafts as exceeding threshold AND the retry MUST produce a tighter draft with a measurable token-count reduction (target: ≥ 15% mean reduction on flagged drafts, calibrated against the recorded corpus). SC-001's reduction percentage is a tuning target, not a CI-gate-enforceable contract: validation requires a representative shakedown corpus that varies by deployment. The implementation tests the scoring + retry mechanics; SC-001's percentage MUST be re-validated by the operator at deploy-time per `quickstart.md` Step 2 (threshold tuning).
- **SC-002**: With `SACP_RESPONSE_SHAPING_ENABLED=false`, every pre-feature acceptance test MUST pass byte-identically. The master switch fully disables the shaping pipeline; nothing else changes. "byte-identical" applies at the user-facing API/transcript layer (message content, dispatch counts, cost values, audit-log content). The new `routing_log` columns added by this spec MAY exist as NULL-defaulted additions and MAY be observed by row-introspecting tests; their presence does not violate SC-002 because they carry no shaping-on values when the master switch is off.
- **SC-003**: When all retries (up to two) exceed threshold the
  pipeline MUST result in exactly one persisted message (the
  second retry's output), one `routing_log` row with
  `reason='filler_retry_exhausted'`, and no infinite loop.
  Verified by a fixture-driven test that forces both retries
  to score equally high.
- **SC-004**: Setting the session register slider MUST be
  reflected in `/me` responses for all participants without
  overrides AND in the assembled prompt's Tier 4 delta text on
  the next turn. Verified by a session-driven test that
  inspects `/me` and the prompt assembly output after each
  change.
- **SC-005**: A per-participant override MUST affect ONLY the
  override-targeted participant's prompt — verified by a
  multi-participant session test that asserts other
  participants' assembled prompts are unchanged.
- **SC-006**: All shaping decisions MUST appear in
  `routing_log` with the per-stage timings (FR-011). Verified
  by a test that drives one shaped turn and asserts the
  expected `routing_log` columns are populated.
- **SC-007**: Override row lifecycle MUST follow spec 001's
  atomic-delete contract. A session delete with an override
  in place MUST remove the override; a participant remove
  MUST remove their override. Verified by two cascade tests.
- **SC-008**: With any of the three new env vars set to an
  invalid value, the orchestrator process MUST exit at startup
  with a clear error message naming the offending var (V16
  fail-closed gate observed in CI).

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** (orchestrator-driven
topologies). The shaping pipeline runs at the orchestrator's
post-dispatch stage and the register slider feeds the
orchestrator's Tier 4 prompt assembler; both require the
orchestrator to be the sole assembler of the per-turn prompt.

This feature is **NOT applicable to topology 7 (MCP-to-MCP,
Phase 3+)**. In topology 7 each participant's client (Claude
Desktop, ChatGPT app) talks to its own provider directly; there
is no orchestrator-side prompt assembler to inject Tier 4
deltas into and no central post-output stage to run a filler
scorer at. Per V12: any topology-7 deployment MUST recognize
that this spec's shaping pipeline does not apply.

A runtime topology gate (reading a `SACP_TOPOLOGY` env var at shaping-pipeline init to skip filler-scorer initialization and register-preset registration) is documented as design forward-work in [research.md §10](./research.md) and surfaced in [quickstart.md](./quickstart.md), but is **NOT implemented in v1**. Topology 7 isn't a runnable topology in Phase 3, the `SACP_TOPOLOGY` env var doesn't ship in this spec, and the structural absence of the orchestrator-side prompt assembler makes both the filler scorer and the register-preset emitter natural no-ops in topology 7 by absence-of-call-path rather than by runtime check. If/when topology 7 ships, this spec will be amended to add the runtime gate as a follow-up FR plus task; the gate is at the consumer (shaping-pipeline init), not at the V16 validators (which run unconditionally per V16 contract).

### V13 — Use Case Coverage

This feature serves the V13 primary use cases:

- §3 Consulting Engagement
  (`docs/sacp-use-cases.md` §3) — consulting sessions value
  direct, terse replies; the filler scorer + Direct (1) preset
  is the natural pairing. The token-cost savings compound with
  consulting's typical longer-session shape.
- §2 Research Paper Co-authorship
  (`docs/sacp-use-cases.md` §2) — research sessions move
  through registers (low-formality methodology debate to
  high-formality writeup synthesis); the per-participant
  override (US3) is built for this case.

Other use cases (§1, §4, §5, §6, §7) are not the priority
drivers but inherit the feature when enabled.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts.
This spec contributes three budgets:

- **Filler scorer execution per draft**: P95 ≤ 50ms on the hot
  path. The scorer makes one embedding read (spec 004's
  precomputed `convergence_log.embedding`), one hedge-ratio pass
  over the draft text, and one closing-pattern regex match.
  Single forward pass — no per-token autoregressive cost.
  Budget enforcement: `routing_log.shaping_score_ms` captured
  per evaluation per FR-011.
- **Slider lookup**: O(1) dict access from the hardcoded
  `RegisterPreset` registry. P95 < 1ms; lookup happens once per
  prompt assembly.
- **Shaping retry dispatch (when fired)**: Each retry consumes
  one full dispatch cycle (003 §FR-030 stage timings) plus the
  scorer's evaluation cost on that retry's output. With the
  hardcoded cap of up to two retries, worst-case shaping
  overhead per turn is two extra dispatch cycles plus three
  scorer passes (original + 2 retries). Per-retry P95 latency
  MUST track the existing per-turn dispatch P95; shaping does
  not add new dispatch overhead beyond the cap. Budget
  enforcement: `routing_log.shaping_retry_dispatch_ms`
  captured per retry firing.

## Configuration (V16) — New Env Vars

Three new env vars are introduced. Each MUST have type, valid
range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this spec
(per V16 deliverable gate).

### `SACP_FILLER_THRESHOLD`

- **Intended type**: float in `[0.0, 1.0]`
- **Intended valid range**: `[0.0, 1.0]` inclusive. Values near 0.0 mean "flag almost every draft"; values near 1.0 mean "flag almost nothing." The env var when unset falls through to per-family defaults baked into `BehavioralProfile`: anthropic/openai = `0.60`, gemini/groq/ollama/vllm = `0.55`. The env var, when set, overrides the per-family default uniformly across all families. Per-family env-var overrides are RESERVED future work.
- **Fail-closed semantics**: outside `[0.0, 1.0]` MUST cause startup exit with a clear error.

### `SACP_REGISTER_DEFAULT`

- **Intended type**: int in `[1, 5]`
- **Intended valid range**: `1` (Direct), `2` (Conversational),
  `3` (Balanced), `4` (Technical), `5` (Academic). Default
  `2` (Conversational) — matches observed default tone of
  Phase 1+2 sessions.
- **Fail-closed semantics**: outside `[1, 5]` or non-integer
  MUST cause startup exit with a clear error naming the
  offending value.

### `SACP_RESPONSE_SHAPING_ENABLED`

- **Intended type**: boolean (string `true`/`false`,
  case-insensitive; integer `1`/`0` accepted per existing
  validator convention)
- **Intended valid range**: `true` or `false`. Default
  `false` for v1 — the master switch ships off so deployments
  opt in explicitly. Once SC-001's calibration target is
  validated against production traffic, the default may flip
  to `true` in a follow-up amendment.
- **Fail-closed semantics**: any non-parseable value MUST
  cause startup exit.

## Cross-References to Existing Specs and Design Docs

- **Spec 003 (turn-loop-engine) §FR-030** — `routing_log`
  per-stage timings receive `shaping_score_ms` and
  `shaping_retry_dispatch_ms`. The retry consumes the existing
  compound-retry budget per §FR-031, NOT a separate budget.
- **Spec 004 (convergence-cadence)** — restatement-overlap
  signal reads `convergence_log.embedding` for the prior 1-3
  turns. No second sentence-transformers model load. The
  embedding pipeline is the dependency this spec MUST NOT
  duplicate.
- **Spec 008 (prompts-security-wiring)** — Tier 4 delta is
  the integration point. Spec 021 specifies what deltas exist
  (the five register presets and the tightened-retry delta);
  spec 008 owns how they are wired into the prompt assembler.
- **Spec 026 (context compression, future)** — compression of
  stored content is explicitly deferred there. Spec 021
  modifies the *generated* draft before persistence; spec 026
  modifies the *persisted* representation after persistence.
  The two specs MUST NOT touch the same column or pipeline.
- **Constitution §10** — Phase 3 deliverables list. Spec 021
  is in-scope for Phase 3 by virtue of Phase-3 declaration
  recorded 2026-05-05 (see also §14.1).
- **Constitution §14.1** — Feature work workflow. This spec
  scaffolds via `/speckit.specify`; subsequent
  `/speckit.clarify`, `/speckit.plan`, and `/speckit.tasks`
  are deferred until the user schedules implementation.
- **Constitution V12** — topology applicability. Spec 021
  applies to topologies 1-6; incompatible with topology 7.
- **Constitution V13** — primary use cases consulting and
  research co-authorship per `docs/sacp-use-cases.md` §3 and §2.
- **Constitution V14** — per-stage timing budgets. Spec 021
  contributes three budgets (Performance Budgets section).
- **Constitution V16** — env-var validation at startup. Spec 021
  introduces three new vars (Configuration section).
- **Spec 001 (core-data-model) §FR-008, §FR-011** — append-only
  invariant on `messages.content` (the persisted retry output
  is immutable like any other message); atomic delete cascades
  to override rows (FR-015).
- **Spec 005 (summarization-checkpoints)** — downstream
  beneficiary. Tighter drafts at generation time mean tighter
  summarizer inputs at checkpoint time; the savings compound
  but no spec 005 change is required.

## Assumptions

- The filler-scorer threshold and weights ship with empirical
  defaults calibrated against project research observations on
  reasoning-heavy outputs (20-30% output-token reductions are
  achievable when register is tightened; this spec targets a
  more conservative ≥ 15% on flagged drafts in SC-001 to leave
  margin for variance). Calibration values are confirmed in
  `/speckit.plan` against a corpus drawn from recorded
  sessions.
- The five-preset register taxonomy (Direct, Conversational,
  Balanced, Technical, Academic) is fixed in v1. Adding new
  presets requires a future amendment with new test fixtures.
  The slider range remains 1-5; expanding to 1-N is a future
  spec with cardinality implications for prompt-cache prefix
  stability.
- Per-model behavioral profiles ship as a hardcoded dict in v1.
  An operator who needs a per-model override files a
  Constitution §14.2 amendment with the override; per-model
  overrides via env vars are out of scope until session
  experience justifies the operator-tunable surface.
- The compression boundary (FR-016) is strict: this spec does
  not modify, summarize, or compress stored content. Stored
  content lives untouched in the `messages` table per spec 001
  §FR-008. Spec 026 owns any work that changes that.
- The retry's tightened delta is fixed text per FR-013 (Direct
  preset's text). A learned per-model delta is a future spec
  enhancement; v1 ships one delta string for all retries.
- The 2-retry cap (FR-004) is hardcoded rather than env-tunable.
  Operators who need a different cap file a Constitution §14.2
  amendment; an env-var surface for the cap is out of scope
  until session experience justifies the operator-tunable
  surface.
- Phase 3 declared 2026-05-05 satisfies the phase gate; this
  spec stays scaffold-only until tasks are scheduled. No
  implementation begins on this spec until the user invokes
  `/speckit.clarify` and subsequent workflow steps.
- Status was flipped to Clarified on 2026-05-07 after the six initial-draft clarifications resolved; subsequent edits remain in scope without re-entering Draft. The "Phase 3 declared 2026-05-05" notation in the Status field is informational; it does not itself flip the spec to Implemented (per `feedback_dont_declare_phase_done.md`, the status flip is the user's call).
