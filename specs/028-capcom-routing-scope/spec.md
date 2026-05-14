# Feature Specification: CAPCOM-Like Routing Scope (Single-AI Curated Channel)

**Feature Branch**: `028-capcom-routing-scope`
**Created**: 2026-05-07
**Status**: Draft (clarify session 2026-05-14 complete; plan/tasks pending)
**Input**: User description: "CAPCOM-like routing scope. Modeled on Mission Control's CAPCOM (Capsule Communicator), a single AI plus the humans share a channel that the rest of the AIs cannot see; CAPCOM relays summarized / curated input to the larger AI panel. SIGNIFICANT routing-model expansion — adds a 9th routing scope and introduces visibility partitioning across the participant set. New routing scope `capcom`; new message subtypes `capcom_relay` (CAPCOM forwarding curated human content to the panel) and `capcom_query` (CAPCOM asking the human on behalf of the panel); message visibility scope (`public` / `capcom_only`). Single CAPCOM per session; facilitator-rotatable. The CAPCOM AI's outputs reaching the panel are subject to standard inter-AI trust tier; rotation does NOT inherit prior CAPCOM's capcom_only context. Applies to topologies 1-6 (orchestrator-mediated visibility partitioning); incompatible with topology 7. Primary use cases: research co-authorship (§2), consulting (§3), decision-making under asymmetric expertise (§6)."

## Overview

The orchestrator's current routing model treats every active AI
as a peer with symmetric visibility into the conversation. Every
AI sees every human turn; every AI sees every other AI's turn.
The eight existing routing scopes (`always`, `review_gate`,
`delegate_low`, `domain_gated`, `burst`, `observer`,
`addressed_only`, `human_only`) modulate how often a participant
takes a turn but do not partition what they SEE.

The user's brief introduces a **fundamentally different model**:
a single AI plus the humans share a channel that the rest of
the AIs cannot see. The model is named after Mission Control's
**CAPCOM** (Capsule Communicator) — historically the only voice
astronauts heard from the ground, with the rest of Mission
Control feeding through CAPCOM. The SACP analog: one AI is
designated CAPCOM; humans direct their messages to CAPCOM by
default; CAPCOM curates and relays to the larger AI panel; the
rest of the panel sees only what CAPCOM relays AND what humans
publish directly to the public scope.

This is the spec's primary architectural shift. Three concrete
mechanisms:

1. **Visibility partitioning at the message level.** Every
   message gains a `visibility` field with values `public`
   (every participant sees it) or `capcom_only` (only humans +
   the current CAPCOM AI see it). Context assembly (spec 003)
   filters messages by visibility before dispatch.
2. **A 9th routing scope `capcom`.** A participant with
   `routing_scope='capcom'` is the session's designated CAPCOM
   AI. The session row carries `capcom_participant_id`
   referencing the active CAPCOM. The DB constraint enforces
   single-CAPCOM-per-session.
3. **Two new message subtypes.** `capcom_relay` (the CAPCOM AI
   forwards curated content to the panel as a public message,
   tagged so the panel knows the source is CAPCOM-mediated) and
   `capcom_query` (CAPCOM asks a question of the humans on
   behalf of the panel; the human's response defaults to
   `capcom_only` scope).

The CAPCOM AI's view is broader than panel AIs:

- **Public messages** (every participant sees them).
- **`capcom_only` messages** (humans + the current CAPCOM AI
  see them; the panel does not).
- The CAPCOM AI's own outputs default to `public` (the panel
  sees them) UNLESS the CAPCOM AI explicitly emits a
  `capcom_query` to humans (defaults to `capcom_only`).

The panel AIs' view is narrower:

- **Public messages only.**
- This includes `capcom_relay` messages (CAPCOM's curated
  forwarding) AND humans' direct-to-public messages AND
  the panel AIs' own turns.
- The panel never sees raw `capcom_only` messages.

**CAPCOM rotation** is facilitator-controlled. Rotating the
CAPCOM role transfers `sessions.capcom_participant_id` to the
new CAPCOM AND records an `admin_audit_log` entry. **The new
CAPCOM does NOT inherit the outgoing CAPCOM's `capcom_only`
history** — those messages remain in the audit trail attributed
to the previous CAPCOM, but the new CAPCOM starts with a clean
`capcom_only` window. From the new CAPCOM's perspective,
`capcom_only` content emitted before rotation is invisible
(same as the panel's perpetual view of it). This is by design:
rotation is a privilege transfer, not a privilege accumulation;
the outgoing CAPCOM's confidential channel does not expand
across rotations.

The security envelope is non-trivial:

- **CAPCOM is a high-privilege routing scope** (cross-ref
  spec 007 §7.6 trust-tiered content model). The CAPCOM AI
  sees content the panel does not; this is a structural
  privilege.
- **`capcom_relay` is a privilege-elevating action** —
  analogous to spec 024's promote-to-transcript. CAPCOM
  curates `capcom_only` content into `public` scope; that
  curation is what the panel sees as ground truth. A
  compromised CAPCOM could relay misleading or
  steganographically-encoded content to the panel. Mitigation:
  the same envelope as spec 024 — every `capcom_relay` is
  audited, the `capcom_relay` message kind is structurally
  distinct so spec 005's summarizer + spec 011's UI can render
  the source-attribution clearly, AND `capcom_relay` content
  flows through spec 007's full security pipeline.
- **The 14th attack vector family (covert channel via
  curation)** extends here. A CAPCOM AI relaying content from
  humans to the panel could embed steganographic patterns. The
  information-density signal (spec 004 §FR-020 + spec 026 FR-018)
  applies to `capcom_relay` messages; the raw transcript stays
  canonical, so a forensic review can reconstruct the
  CAPCOM-side context that produced the relay.
- **Rotation does not transfer the confidential channel.** The
  audit trail attributes every `capcom_only` message to the
  CAPCOM-of-record at the time of writing; rotation transfers
  the role, not the historical view.

This spec is **Phase 3 scope**, sequenced after the other
routing-related Phase 3 specs (013, 014, 027). Spec 028
introduces a routing-model shift more significant than any
single prior Phase 3 mechanism — adding a visibility partition
across the participant set is a category change rather than a
scope refinement. The spec stays scaffold state until
`/speckit.clarify` runs.

## Clarifications

### Session 2026-05-14

- Q: When CAPCOM is active, do humans' messages default to `public` or `capcom_only`? → A: Facilitator-configurable per deployment via `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN` (boolean, default `false`). With the default, humans publish directly to `public` and explicitly opt messages into `capcom_only` via the UI toggle. Operators whose use case favors CAPCOM-by-default flip the var. Public-default chosen because it preserves pre-feature symmetry as the safe fallback and makes the privilege channel an explicit human action.
- Q: Can panel AIs emit `capcom_only` messages? → A: No. The `capcom_only` scope is reserved for humans and the active CAPCOM AI. Panel AI outputs are always `public`; humans see them because the human visibility tier is CAPCOM-or-broader. A panel AI cannot route around CAPCOM by emitting privileged-scope content. Validated at write time: any panel-AI emission carrying `visibility='capcom_only'` is rejected with HTTP 422.
- Q: With CAPCOM on, can a human still publish directly to `public` (bypassing CAPCOM)? → A: Yes, always. CAPCOM is a default routing channel, not a hard gate. The human UI exposes both options per-message and the default follows `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN`. This preserves human agency: humans are never structurally prevented from speaking to the panel directly.
- Q: What happens when the designated CAPCOM AI is removed mid-session without rotation? → A: Null-CAPCOM degenerate state. `sessions.capcom_participant_id` is set to NULL; future messages default to `public`; the `capcom_only` UI option is greyed; existing `capcom_only` history remains attributed to the departed CAPCOM in the audit trail and stays invisible to all AIs (FR-011 invariant). `admin_audit_log` records `capcom_departed_no_replacement`. Auto-disable was rejected because it conflates two operator intents (revoke privilege vs. disable mediation entirely); blocking departure-without-rotation was rejected as too rigid for emergency removal flows.
- Q: When CAPCOM emits a `capcom_query` to humans, the human's response defaults to which scope? → A: `capcom_only` by default. The response is structurally a reply to a CAPCOM query, so CAPCOM curates and relays. The human can override per-message to `public` via the UI toggle. The default flips to `capcom_only` regardless of `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN` because the query establishes the conversational context for the next message — the env var governs unsolicited human messages, not direct replies to CAPCOM.
- Q: A `capcom_query` is in flight when rotation happens — which CAPCOM owns the human's eventual response? → A: Arrival-time attribution. The human's response is attributed to the CAPCOM-of-record at the time the response arrives (B), not the CAPCOM that emitted the query (A). The audit trail makes the cross-rotation chain inspectable (query attributed to A; response attributed to B). Emission-time attribution was rejected because rotation transfers the entire privilege channel: routing a response to a now-non-CAPCOM AI would leak `capcom_only` content to a participant who has lost the privilege.
- Q: How is single-CAPCOM-per-session enforced? → A: DB-level unique partial index — `CREATE UNIQUE INDEX ON participants(session_id) WHERE routing_scope='capcom'`. Application-level invariants are insufficient under concurrent facilitator actions. Rotation is a transactional swap (old → non-capcom; new → capcom; both within one `BEGIN/COMMIT`) so the unique index never trips on the rotation itself.
- Q: Does CAPCOM get a special context-budget tier? → A: No. The CAPCOM AI's larger view (public + `capcom_only`) consumes more context per turn, but per-participant context-assembly priorities (spec 003 §FR-001+) already scale to each participant's declared context window. Compression (spec 026 Layer 4) applies to CAPCOM overflow the same as any other participant. Operators select a wider-context model for CAPCOM if needed; the orchestrator does not bake a separate budget tier.
- Q: Is CAPCOM identity participant-bound or account-bound (spec 023)? → A: Participant-bound in v1. `sessions.capcom_participant_id` references `participants.id` directly. Cross-session CAPCOM persistence (a returning expert AI auto-resuming as CAPCOM in subsequent engagements) is a v2 follow-up requiring its own design (account-level routing-scope binding, persistence on archive, restore-on-resume).

### Initial draft assumptions requiring confirmation

- **Default human routing direction.** Resolved 2026-05-14
  (Session above): facilitator-configurable per deployment
  via `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN` (boolean, default
  `false` — humans default to `public`). The CAPCOM-by-default
  posture remains available via the env var.
- **Panel AI direct-to-human message.** Resolved 2026-05-14
  (Session above): panel AIs are structurally forbidden from
  emitting `capcom_only`. The scope is reserved for humans and
  the active CAPCOM AI. Write-time validation rejects panel-AI
  emissions carrying `visibility='capcom_only'` with HTTP 422.
- **Human direct-to-panel bypass.** Resolved 2026-05-14
  (Session above): humans always have the option to publish
  directly to `public` even with CAPCOM active. UI exposes
  both options per-message; default follows the env var.
- **CAPCOM departure during session.** Resolved 2026-05-14
  (Session above): null-CAPCOM degenerate state.
  `sessions.capcom_participant_id` becomes NULL; future
  messages default `public`; historical `capcom_only` content
  stays attributed to the departed CAPCOM and invisible to
  all AIs (FR-011 invariant).
- **`capcom_query` response default scope.** Resolved
  2026-05-14 (Session above): `capcom_only` by default. The
  query establishes the conversational context for the reply;
  the env var (which governs unsolicited human messages)
  does not override this default.
- **In-flight messages during rotation.** Resolved 2026-05-14
  (Session above): arrival-time attribution. The human's
  response is attributed to the CAPCOM-of-record at response
  arrival time, not query emission time.
- **Single-CAPCOM enforcement.** Resolved 2026-05-14
  (Session above): DB-level unique partial index. Rotation is
  a transactional swap so the unique index never trips on the
  rotation itself.
- **CAPCOM context budget.** Resolved 2026-05-14 (Session
  above): no special treatment. Per-participant context
  priorities and compression apply uniformly; operators pick
  a wider-context model for CAPCOM if the use case demands it.
- **Persistence across archived sessions.** Confirmed
  out-of-scope; flagged as a v2 follow-up. The
  `sessions.capcom_participant_id` column is per-session, no
  cross-session bind in v1.
- **CAPCOM seeing facilitator scratch (spec 024).** Confirmed
  out-of-scope v1, v2 follow-up. CAPCOM sees only the session
  message history (filtered by visibility). Scratch remains
  facilitator-private even in CAPCOM-active sessions.
- **Conflict with spec 023 user accounts when humans rotate
  through sessions.** Resolved 2026-05-14 (Session above):
  participant-bound in v1. Cross-session CAPCOM persistence
  is a v2 follow-up requiring its own design.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Facilitator assigns one AI as CAPCOM; non-CAPCOM AIs no longer see direct human messages; CAPCOM relays curated content via capcom_relay messages (Priority: P1)

A facilitator running a 4-AI consulting session designates one
of the AIs as CAPCOM. The session's `capcom_participant_id` is
set; the participant's `routing_scope` flips to `capcom`. The
human types a question to the session. The message persists with
`visibility='capcom_only'` (per the configured default). The
context assembler runs for each panel AI's next dispatch — the
filter excludes the human's message from those AIs' context.
The CAPCOM AI's next dispatch DOES include the message. The
CAPCOM AI processes it, decides what to forward, emits a
`capcom_relay` message in `public` scope summarizing the
human's question for the panel. Panel AIs see the
`capcom_relay` (not the original human message); they respond
to the relayed content. The transcript distinguishes
`capcom_relay` from regular public messages so spec 011's UI
can render the source attribution.

**Why this priority**: P1 because this IS the spec's primary
value. Without it, no visibility partitioning exists. The
filter + the new message kind together prove the
architectural shift works.

**Independent Test**: Create a session with 4 AIs and 1 human.
Assign one AI as CAPCOM (set `routing_scope='capcom'` and
`sessions.capcom_participant_id`). Inject a human message
with `visibility='capcom_only'`. Assert the visibility filter
excludes the message from each non-CAPCOM AI's context.
Assert the CAPCOM AI's context includes the message. Drive
the CAPCOM AI's dispatch; assert it produces a `capcom_relay`
message that enters `public` scope. Drive a panel AI's
dispatch; assert its context includes the `capcom_relay` but
NOT the original human message.

**Acceptance Scenarios**:

1. **Given** a session with a CAPCOM assigned, **When** a
   human emits a message with `visibility='capcom_only'`,
   **Then** non-CAPCOM AIs' context assembly MUST exclude
   that message AND the CAPCOM AI's context assembly MUST
   include it.
2. **Given** a CAPCOM AI's dispatch, **When** the CAPCOM
   produces a `capcom_relay` message, **Then** the message
   MUST persist with `kind='capcom_relay'` AND
   `visibility='public'`.
3. **Given** a `capcom_relay` message exists, **When** any
   panel AI's context assembles, **Then** the relay MUST
   appear in that context with structural attribution to
   the CAPCOM source.
4. **Given** a session with no CAPCOM assigned (default state),
   **When** any human emits any message, **Then** the
   message MUST default to `visibility='public'` AND every AI
   MUST see it (preserves pre-feature behaviour for
   deployments that don't opt in).
5. **Given** `SACP_CAPCOM_ENABLED=false`, **When** any
   facilitator attempts to assign a CAPCOM, **Then** the
   action MUST be rejected with HTTP 404 (master switch
   gates the entire surface).
6. **Given** a single-CAPCOM-per-session invariant, **When**
   the facilitator attempts to assign a second AI as CAPCOM
   while one is already assigned, **Then** the action MUST
   be rejected with a clear error (DB-level unique constraint
   per FR-006).
7. **Given** a CAPCOM AI emits a public message that is NOT
   a `capcom_relay` (a normal turn), **When** the message
   persists, **Then** `kind` MUST default to the existing
   per-spec-003 message kind (the CAPCOM AI's regular turns
   are not auto-tagged as relays; only explicit relay actions
   are).
8. **Given** an architectural test scans for visibility-
   filter bypass paths, **When** the test runs, **Then** no
   code path under `src/` outside the context-assembly
   pipeline MUST read `messages.content` for dispatch
   purposes without applying the visibility filter
   (architectural test asserting the filter is the only
   path).

---

### User Story 2 - CAPCOM queries the human via capcom_query; the human responds; CAPCOM relays the answer to the panel (Priority: P1)

The CAPCOM AI determines the panel needs a clarification only
the human can provide. CAPCOM emits a `capcom_query` message
in `capcom_only` scope. The human sees the query in their UI
(humans always see `capcom_only`). The human responds; their
response defaults to `capcom_only` scope (per FR-016). The
CAPCOM AI's next context includes the human's response; the
panel's context does NOT. CAPCOM processes the response and
emits a `capcom_relay` summarizing the answer for the panel.
The panel receives the curated answer, not the raw exchange.

**Why this priority**: P1 because the bidirectional channel is
the second half of the CAPCOM model. US1 covers human-to-panel
flow via CAPCOM; US2 covers panel-to-human flow via CAPCOM.
Without both, the channel is asymmetric and the model breaks.

**Independent Test**: As CAPCOM, emit a `capcom_query`
message. Assert the message persists with
`kind='capcom_query'` and `visibility='capcom_only'`. Assert
the human's UI surfaces the query. Inject a human response;
assert it defaults to `visibility='capcom_only'`. Drive the
CAPCOM AI's dispatch; assert its context includes the human
response. Drive a panel AI's dispatch; assert its context
does NOT include the human response. Have CAPCOM emit a
`capcom_relay` summarizing; assert it enters public.

**Acceptance Scenarios**:

1. **Given** a CAPCOM AI's dispatch produces a query for the
   human, **When** the message persists, **Then** it MUST
   carry `kind='capcom_query'` AND `visibility='capcom_only'`.
2. **Given** a `capcom_query` exists, **When** the human's
   UI fetches their visible messages, **Then** the query
   MUST appear with structural distinction from regular
   public messages.
3. **Given** a human responds to a `capcom_query`, **When**
   the response persists, **Then** it MUST default to
   `visibility='capcom_only'` (FR-016) UNLESS the human
   explicitly overrides to `public`.
4. **Given** a `capcom_only` human response, **When** any
   panel AI's context assembles, **Then** the response MUST
   NOT appear.
5. **Given** the CAPCOM AI processes a `capcom_only` human
   response, **When** the CAPCOM emits a `capcom_relay`
   summarizing the answer, **Then** the relay MUST persist
   in `public` scope AND panel AIs' subsequent context MUST
   include it.

---

### User Story 3 - Facilitator rotates CAPCOM mid-session; the new CAPCOM starts with no capcom_only history from the prior CAPCOM (Priority: P2)

The facilitator decides the current CAPCOM AI is not the right
fit for the rest of the session and rotates the role to a
different AI. The transactional rotation: the old participant's
`routing_scope` reverts (typically `always`), the new
participant's `routing_scope` flips to `capcom`,
`sessions.capcom_participant_id` updates. The new CAPCOM's
context starts with PUBLIC HISTORY ONLY — the
`capcom_only` content emitted under the prior CAPCOM is
preserved in the audit trail attributed to the prior CAPCOM
but the new CAPCOM does NOT see it. From the new CAPCOM's
perspective, `capcom_only` content prior to rotation is as
invisible as it is to the panel. After rotation, the new
CAPCOM and the humans share a fresh `capcom_only` channel.

**Why this priority**: P2 because rotation is a maintenance
action — important for sessions where the right CAPCOM
changes mid-engagement (consulting hands off to a different
specialist; research co-authorship transitions to a new lead),
but not on the critical path for first-use. P2 because the
no-inheritance rule is the security envelope that prevents
privilege accumulation across rotations; getting it right is
non-trivial but the use case is bounded.

**Independent Test**: Drive a session with CAPCOM A active.
Emit several `capcom_only` messages between A and the human.
Rotate to CAPCOM B. Assert
`sessions.capcom_participant_id` updates to B. Drive B's
dispatch; assert B's context contains public history only —
the prior `capcom_only` exchanges are absent. Inject a new
human message defaulting to `capcom_only`; assert B sees it
on their next dispatch. Inspect `admin_audit_log`; assert
the rotation is logged AND each prior `capcom_only` message
remains attributed to A (no rewrite of historical
attribution).

**Acceptance Scenarios**:

1. **Given** a session with CAPCOM A active, **When** the
   facilitator rotates to CAPCOM B, **Then**
   `sessions.capcom_participant_id` MUST update transactionally
   AND `admin_audit_log` MUST record `action='capcom_rotated'`
   with both participant ids and timestamp.
2. **Given** rotation completes, **When** B's next context
   assembles, **Then** the context MUST contain only public
   history — `capcom_only` content prior to rotation MUST NOT
   appear.
3. **Given** rotation completes, **When** A's next context
   assembles, **Then** A is now a regular participant; their
   context MUST include public messages only (their prior
   privileged view is gone).
4. **Given** rotation completes, **When** prior
   `capcom_only` messages are inspected in
   `admin_audit_log`, **Then** their CAPCOM attribution MUST
   remain as A (no historical-attribution rewrite).
5. **Given** a `capcom_query` is in flight when rotation
   happens, **When** the human's response arrives, **Then**
   the response MUST be attributed to the CAPCOM at arrival
   time (B), per FR-013 (arrival-time attribution); the
   audit trail clearly shows the cross-rotation chain.

---

### User Story 4 - Facilitator disables CAPCOM mid-session; all AIs see all FUTURE public content; capcom_only history is preserved in audit log but invisible to non-CAPCOM AIs forever (Priority: P3)

The facilitator decides CAPCOM mediation is no longer needed.
They disable CAPCOM mode for the session. The CAPCOM
participant's `routing_scope` reverts; `sessions.capcom_participant_id`
is set to NULL. New messages default to `visibility='public'`.
All AIs (including the formerly-CAPCOM AI, now a regular
participant) see future public messages symmetrically. The
historical `capcom_only` content remains in the audit log but
is NEVER promoted to public scope — it stays attributed to
the historical CAPCOM, invisible to the panel forever.

**Why this priority**: P3 because disabling is a corner case —
sessions either run with CAPCOM throughout or never enable it.
Disabling mid-session is a recovery path for misconfiguration.
P3 because the privacy invariant (capcom_only content stays
private after disable) is what makes the disable action safe;
without it, disabling would retroactively leak privileged
content.

**Independent Test**: Drive a session with CAPCOM enabled
producing `capcom_only` history. Disable CAPCOM (facilitator
action). Assert `sessions.capcom_participant_id` becomes NULL
AND the formerly-CAPCOM participant's `routing_scope` reverts.
Drive a public human message; assert all AIs see it. Drive
each panel AI's dispatch; assert their contexts continue to
EXCLUDE the historical `capcom_only` content (no retroactive
visibility promotion).

**Acceptance Scenarios**:

1. **Given** a session with CAPCOM active, **When** the
   facilitator disables CAPCOM, **Then**
   `sessions.capcom_participant_id` MUST become NULL AND
   `admin_audit_log` MUST record `action='capcom_disabled'`.
2. **Given** CAPCOM is disabled, **When** any new message
   is emitted, **Then** the default `visibility` MUST be
   `public` (the `capcom_only` UI option MUST be hidden or
   greyed when no CAPCOM is assigned).
3. **Given** historical `capcom_only` content exists from
   the active CAPCOM period, **When** any non-CAPCOM AI's
   context assembles after disable, **Then** the historical
   `capcom_only` content MUST remain invisible (no
   retroactive promotion).
4. **Given** the formerly-CAPCOM AI's next context
   assembles after disable, **When** their context renders,
   **Then** the historical `capcom_only` content MUST be
   PRESERVED in their view (they were the CAPCOM at the
   time; their view does not retract). New `capcom_only`
   messages are no longer accepted (the scope is structurally
   unavailable when CAPCOM is disabled).

---

### Edge Cases

- **CAPCOM AI fails the security pipeline on a `capcom_relay`.**
  The relay is high-risk content (per FR-019); spec 007's
  `_validate_and_persist` flags it; the relay is staged for
  facilitator review per spec 007 §FR-005 — the same envelope
  any high-risk AI output gets. Approval re-pipelines and
  publishes; rejection drops the relay (the CAPCOM may try
  again on the next turn).
- **CAPCOM departs during an in-flight `capcom_query`.** The
  query persists in the audit log; the new CAPCOM (post-
  rotation) sees only public content; the human's response,
  if it arrives, is attributed per FR-013 to the new CAPCOM
  at arrival time. If no new CAPCOM is assigned (CAPCOM is
  disabled instead), the human's `capcom_only` response
  cannot route to any AI; it remains in the audit log and
  the human is informed via UI affordance that no CAPCOM is
  available.
- **Single-CAPCOM constraint violated by concurrent
  facilitator actions.** Two facilitators on the same
  session simultaneously assign different CAPCOMs. The DB
  unique constraint rejects the second; the second
  facilitator gets a clear error. No race condition; the
  constraint is the source of truth.
- **Panel AI emits a message that explicitly addresses the
  human.** The message persists `public`; humans see it
  (humans see all public). The CAPCOM AI sees it too. The
  panel AI is not bypassing CAPCOM — it's a public message
  the human happens to read. This is the same as any
  human-addressed AI utterance in non-CAPCOM mode.
- **A human emits a message tagged `capcom_only` when no
  CAPCOM is assigned.** The system rejects with an error
  ("no CAPCOM assigned; capcom_only scope unavailable").
  The UI hides or greys the option to prevent the error
  case.
- **Compression (spec 026) operates on a CAPCOM AI's
  outgoing window.** The CAPCOM's overflow contains
  `capcom_only` content. Compression treats this content
  the same as any other — pre-bridge, per-participant. The
  compressed segment inherits trust tier from source; the
  trust-tier wrapping (spec 026 FR-012) marks the segment
  as derived from CAPCOM-private content. The compressed
  segment is delivered to the CAPCOM's own provider only;
  it never enters another participant's context.
- **Spec 005 summarizer on a CAPCOM-active session.** The
  summarizer respects visibility: panel-summary covers
  public content only; CAPCOM-summary covers public +
  capcom_only. Two-tier summary structure (FR-018);
  storage detail settled in `/speckit.plan`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A new column `messages.visibility` MUST be
  added with values `public` (default) | `capcom_only`. All
  existing message rows on migration default to `public`
  (preserves pre-feature symmetric visibility).
- **FR-002**: A new column `messages.kind` MUST gain values
  `capcom_relay` and `capcom_query` alongside existing kinds.
- **FR-003**: A new column `sessions.capcom_participant_id`
  MUST be added (nullable, FK to `participants.id`). NULL
  means CAPCOM is not assigned for this session.
- **FR-004**: The `participants.routing_scope` enum MUST
  gain a new value `capcom`. Only participants with
  `routing_scope='capcom'` can be referenced by
  `sessions.capcom_participant_id`.
- **FR-005**: A unique partial index MUST enforce
  single-CAPCOM-per-session at the DB layer:
  `CREATE UNIQUE INDEX ON participants(session_id) WHERE
  routing_scope='capcom'`.
- **FR-006**: The context assembler (spec 003) MUST apply
  a visibility filter as the LAST step before context
  goes to the bridge. The filter:
  - For a CAPCOM participant: include all messages.
  - For any other AI participant: include only `public`
    messages.
  - For human participants: include all messages (humans
    have CAPCOM-or-broader visibility).
- **FR-007**: A new endpoint MUST allow the facilitator to
  assign a CAPCOM (path TBD in `/speckit.plan`). The action
  is transactional: set the target participant's
  `routing_scope='capcom'`, set
  `sessions.capcom_participant_id` to the participant id,
  emit `admin_audit_log` `action='capcom_assigned'`.
- **FR-008**: A new endpoint MUST allow the facilitator to
  rotate CAPCOM. The action is transactional:
  - Revert the outgoing CAPCOM's `routing_scope` to its
    pre-CAPCOM value (recorded at assignment time on the
    audit log; restore from there).
  - Set the incoming CAPCOM's `routing_scope='capcom'`.
  - Update `sessions.capcom_participant_id`.
  - Emit `admin_audit_log` `action='capcom_rotated'` with
    both participant ids.
- **FR-009**: A new endpoint MUST allow the facilitator to
  disable CAPCOM. The action: revert the current CAPCOM's
  `routing_scope` to its pre-CAPCOM value, set
  `sessions.capcom_participant_id=NULL`, emit
  `admin_audit_log` `action='capcom_disabled'`.
- **FR-010**: CAPCOM rotation MUST NOT inherit the outgoing
  CAPCOM's `capcom_only` history. The new CAPCOM's context
  starts with public history only. Historical `capcom_only`
  messages remain attributed to the prior CAPCOM in the
  audit trail; no rewrite occurs.
- **FR-011**: When CAPCOM is disabled, historical
  `capcom_only` content MUST remain invisible to non-CAPCOM
  AIs. There is no retroactive promotion to public scope.
  The `capcom_only` UI option for new messages is hidden
  when CAPCOM is unassigned.
- **FR-012**: A `capcom_relay` message MUST be emitted by
  the CAPCOM AI as a structurally distinct message kind.
  When the CAPCOM AI's dispatch produces a turn the AI
  intends as a relay, the orchestrator (or the CAPCOM-side
  prompt scaffolding) marks the message
  `kind='capcom_relay'` AND `visibility='public'`.
- **FR-013**: A `capcom_query` message MUST be emitted by
  the CAPCOM AI when it intends to ask a human a question
  on behalf of the panel. The message persists with
  `kind='capcom_query'` AND `visibility='capcom_only'`.
- **FR-014**: A human's response to a `capcom_query` MUST
  default to `visibility='capcom_only'` UNLESS the human
  explicitly overrides to `public`. The human's UI surfaces
  the override option per-message.
- **FR-015**: When CAPCOM is assigned AND the human emits a
  message via the standard inject_message path, the
  `visibility` default MUST follow
  `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN` (default `false` —
  humans default to `public`).
- **FR-016**: When CAPCOM is assigned AND the human emits a
  message in `capcom_only` scope, the message MUST persist
  with that visibility AND the context filter (FR-006) MUST
  exclude it from non-CAPCOM AIs.
- **FR-017**: A `capcom_relay` MUST flow through spec 007's
  `_validate_and_persist` security pipeline like any other
  AI output. High-risk relay content stages for facilitator
  review per spec 007 §FR-005.
- **FR-018**: Spec 005's summarizer MUST respect visibility.
  Two-tier summary structure: panel-summary covers `public`
  only; CAPCOM-summary covers `public` + `capcom_only`. The
  CAPCOM AI sees both summaries in their context; the panel
  AIs see only the panel-summary.
- **FR-019**: An architectural test MUST assert no code
  path under `src/` reads `messages.content` for dispatch
  purposes without applying the visibility filter (FR-006).
  CI fails if any new code bypasses the filter.
- **FR-020**: The two new env vars (`SACP_CAPCOM_ENABLED`,
  `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN`) MUST have validator
  functions in `src/config/validators.py` registered in the
  `VALIDATORS` tuple, AND corresponding sections in
  `docs/env-vars.md` with the six standard fields, BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable
  gate).
- **FR-021**: The master switch `SACP_CAPCOM_ENABLED` MUST
  gate the entire CAPCOM surface. When `false` (default),
  the assignment / rotation / disable endpoints return
  HTTP 404 AND the `messages.visibility` column is always
  `public` regardless of inputs.
- **FR-022**: When a CAPCOM-assigned participant is removed
  (spec 002 §FR-016 cascade) OR departs the session, the
  session's `capcom_participant_id` MUST be set to NULL AND
  `admin_audit_log` MUST record
  `action='capcom_departed_no_replacement'`. Future
  messages default to `public` until a new CAPCOM is
  assigned or the facilitator explicitly disables CAPCOM.
- **FR-023**: A new visibility filter `routing_log` reason
  `message_filtered_capcom_scope` MUST record per-turn
  visibility-filter exclusions (the count of messages
  excluded for each participant's assembly). This gives
  operators visibility into the partition's effects.
- **FR-024**: The facilitator MUST be able to view the
  full visibility-partitioned context for any participant
  via spec 010's debug-export — the export reflects
  visibility (a non-CAPCOM AI's view in the export
  excludes `capcom_only` content; the CAPCOM AI's view
  includes it). This makes the partition forensically
  inspectable.

### Key Entities

- **CAPCOMRoutingScope** — the new value `capcom` on the
  `participants.routing_scope` enum. At most one
  participant per session carries this value (FR-005).
- **MessageVisibility** — enum on `messages.visibility`
  with values `public` | `capcom_only`. Default `public`.
- **CAPCOMRelay** (message kind) — a CAPCOM AI's
  curated forwarding to the panel.
  `kind='capcom_relay'`, `visibility='public'`.
- **CAPCOMQuery** (message kind) — a CAPCOM AI's question
  to humans on behalf of the panel.
  `kind='capcom_query'`, `visibility='capcom_only'`.
- **VisibilityFilter** (context-assembly stage) — the
  last context-assembly step before bridge dispatch.
  Filters messages by participant role and message
  visibility.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With CAPCOM assigned, a non-CAPCOM AI's
  dispatched context MUST exclude `capcom_only` messages.
  Verified by an end-to-end test asserting the filter's
  effect on a multi-AI session.
- **SC-002**: With CAPCOM assigned, the CAPCOM AI's
  dispatched context MUST include `capcom_only` messages.
  Verified by the same end-to-end test asserting CAPCOM's
  view.
- **SC-003**: A `capcom_relay` MUST persist with
  `kind='capcom_relay'` AND `visibility='public'`. Verified
  by inspecting the message row.
- **SC-004**: A `capcom_query` MUST persist with
  `kind='capcom_query'` AND `visibility='capcom_only'`.
  Verified by inspecting the message row.
- **SC-005**: A human's response to a `capcom_query` MUST
  default to `visibility='capcom_only'`. Verified by an
  end-to-end test driving the query + response.
- **SC-006**: Single-CAPCOM-per-session MUST be enforced at
  the DB layer. Verified by a concurrency test that
  attempts to assign two CAPCOMs simultaneously and asserts
  one rejection.
- **SC-007**: Rotation MUST NOT make prior `capcom_only`
  content visible to the new CAPCOM. Verified by a test
  driving rotation and asserting the new CAPCOM's context
  excludes the prior `capcom_only` history.
- **SC-008**: Disable MUST preserve `capcom_only` history
  invisibly. Verified by a test driving disable then
  asserting non-CAPCOM AIs' subsequent contexts continue
  to exclude the historical `capcom_only` content.
- **SC-009**: An architectural test MUST assert all
  context-assembly paths apply the visibility filter
  (FR-019). CI fails if a new code path bypasses the
  filter.
- **SC-010**: A `capcom_relay` MUST flow through spec
  007's security pipeline. Verified by injecting a
  high-risk relay payload and asserting the review-gate
  staging fires.
- **SC-011**: Spec 005's two-tier summarizer MUST produce
  separate summaries for `public` and `capcom_only` scopes.
  Verified by a summarizer test on a CAPCOM-active session
  asserting both summary kinds.
- **SC-012**: With `SACP_CAPCOM_ENABLED=false`, the
  CAPCOM surface MUST be unreachable. Verified by an
  endpoint test asserting HTTP 404 on assignment attempts.
- **SC-013**: With any of the two new env vars set to an
  invalid value, the orchestrator process MUST exit at
  startup with a clear error message naming the offending
  var (V16 fail-closed gate observed in CI).
- **SC-014**: CAPCOM departure without replacement MUST
  set `capcom_participant_id=NULL` AND emit the
  `capcom_departed_no_replacement` audit row. Verified by
  a participant-removal test on a CAPCOM-active session.
- **SC-015**: Spec 010 debug-export MUST reflect visibility
  per participant. Verified by exporting a CAPCOM-active
  session and asserting non-CAPCOM AIs' exported views
  exclude `capcom_only` content.

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** (orchestrator-driven
topologies). The visibility partition is enforced by the
orchestrator's context-assembly pipeline; CAPCOM assignment
and rotation are orchestrator-side facilitator actions; the
single-CAPCOM constraint is a centralized DB invariant. All
require a single orchestrator to be the visibility authority.

This feature is **NOT applicable to topology 7 (MCP-to-MCP,
Phase 3+)**. In topology 7 each participant's MCP client
controls its own context fetching; there is no orchestrator-
side visibility filter. Per V12: any topology-7 deployment
MUST recognize that this spec's CAPCOM model does not apply.

### V13 — Use Case Coverage

This feature serves the V13 primary use cases:

- §2 Research Paper Co-authorship
  (`docs/sacp-use-cases.md` §2) — the lead author + one AI
  panel coordinator (CAPCOM) curates the panel's questions
  and the lead's clarifications. The CAPCOM model fits
  this naturally; it preserves the lead's bandwidth while
  letting the broader panel still see curated context.
- §3 Consulting Engagement
  (`docs/sacp-use-cases.md` §3) — engagement-lead model:
  one AI is the engagement lead in contact with the client,
  the rest of the panel is in support. The CAPCOM
  assignment matches the consulting hierarchy.
- §6 Decision-Making Under Asymmetric Expertise
  (`docs/sacp-use-cases.md` §6) — one expert speaks for
  the group; the CAPCOM model formalises that
  spokesperson role.

Other use cases (§1, §4, §5, §7) inherit the feature when
operators opt in but are not the priority drivers.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable
contracts. This spec contributes three budgets:

- **Visibility filter per dispatch**: O(1) per message, O(M)
  per dispatch where M is the message count in the
  assembled context. The filter is a single conditional
  check per message based on the participant's role and the
  message's visibility. P95 < 5ms per dispatch for sessions
  with up to 1,000 messages. Budget enforcement: per-dispatch
  timing in the routing_log per-stage timing path (spec 003
  §FR-030) — the filter contributes to the existing
  context-assembly stage timing, not a new stage.
- **CAPCOM assignment / rotation / disable**: O(1) per
  action. One DB transaction with one or two row updates +
  one audit-log write. P95 < 200ms.
- **Two-tier summarizer (FR-018)**: spec 005's existing
  pipeline runs twice per checkpoint when CAPCOM is active
  (once for public, once for public + capcom_only). The
  CAPCOM-summary cost approximately doubles the panel-
  summary cost; budget enforcement falls through to spec
  005 SC-002.

## Configuration (V16) — New Env Vars

Two new env vars are introduced. Each MUST have type, valid
range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this
spec (per V16 deliverable gate).

### `SACP_CAPCOM_ENABLED`

- **Intended type**: boolean
- **Intended valid range**: `true` | `false`. Default
  `false` (master switch ships off; operators opt in).
- **Fail-closed semantics**: any non-parseable value MUST
  cause startup exit. When `false`, the CAPCOM
  assignment / rotation / disable endpoints return HTTP
  404, the `messages.visibility` column is always `public`,
  AND the `participants.routing_scope='capcom'` value is
  rejected at write time.

### `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN`

- **Intended type**: boolean
- **Intended valid range**: `true` | `false`. Default
  `false`. When `true`, humans' messages on a CAPCOM-active
  session default to `visibility='capcom_only'`. When
  `false`, humans default to `visibility='public'` and
  must explicitly opt their messages into `capcom_only`.
- **Fail-closed semantics**: any non-parseable value MUST
  cause startup exit.

## Cross-References to Existing Specs and Design Docs

- **Spec 003 (turn-loop-engine)** — context assembly is
  extended with the visibility filter as the last step
  before bridge dispatch (FR-006). The filter is part of
  the existing context-assembly stage; no new FSM state.
- **Spec 003 (turn-loop-engine) §FR-030** — `routing_log`
  per-stage timings receive the visibility-filter
  contribution; new reason `message_filtered_capcom_scope`
  records exclusion counts per participant assembly.
- **Spec 005 (summarization-checkpoints)** — two-tier
  summary structure (FR-018). Panel-summary covers `public`
  only; CAPCOM-summary covers both visibility scopes. The
  CAPCOM participant sees the CAPCOM-summary in their
  context; panel participants see only the panel-summary.
  Storage shape (two summary rows per checkpoint vs. one
  with a discriminator) settled in `/speckit.plan`.
- **Spec 007 (ai-security-pipeline) §FR-005, §7.6** —
  CAPCOM is a high-privilege routing scope per the
  trust-tiered content model. `capcom_relay` is a
  privilege-elevating action analogous to spec 024's
  promote-to-transcript and is subject to the full
  `_validate_and_persist` security pipeline (FR-017).
  High-risk relays stage for facilitator review.
- **Spec 008 (prompts-security-wiring)** — the CAPCOM AI's
  prompt-tier scaffolding may include CAPCOM-specific
  framing (e.g., "you are the CAPCOM for this session;
  curate the panel's context"). Tier-text is settled in
  `/speckit.plan`; this spec does NOT introduce new tier
  values.
- **Spec 010 (debug-export)** — the export reflects
  visibility per participant (FR-024). Forensically the
  partition is fully inspectable.
- **Spec 011 (web-ui)** — UI affordances: CAPCOM badge on
  participant card; visibility indicator on each transcript
  message (`public` vs. `capcom_only`); facilitator UI for
  CAPCOM assignment / rotation / disable; human-side UI
  toggle for per-message visibility scope. Coordinated FR
  additions to 011 once 028's tasks are scheduled.
- **Spec 023 (user-accounts)** — CAPCOM is participant-
  bound in v1, NOT account-bound. Cross-session CAPCOM
  persistence for recurring panels is a v2 follow-up.
- **Spec 024 (facilitator-scratch)** — CAPCOM does NOT see
  facilitator scratch in v1. Extending CAPCOM visibility
  to scratch is a v2 follow-up.
- **Spec 026 (context-compression)** — compression is
  per-participant pre-bridge; the CAPCOM's overflow
  compresses the same as any participant. Trust-tier
  wrapping (spec 026 FR-012) marks compressed segments
  derived from `capcom_only` content as such; the segment
  is delivered only to the CAPCOM's own provider — never
  cross-leaked into another participant's context.
- **Spec 002 (participant-auth)** — participant-settings
  endpoint pattern. CAPCOM assignment / rotation / disable
  endpoints follow the same authorization model
  (facilitator-only, session-bound).
- **Spec 001 (core-data-model)** — schema additions:
  `messages.visibility` and `messages.kind` extensions,
  `sessions.capcom_participant_id` column,
  `participants.routing_scope` enum extension. Migration
  follows §FR-017 forward-only constraint. The unique
  partial index on `participants(session_id) WHERE
  routing_scope='capcom'` is the structural enforcement of
  single-CAPCOM-per-session.
- **Constitution §10** — phased delivery model. Spec 028
  is sequenced into Phase 3 alongside the other routing-related
  specs.
- **Constitution §14.1** — Feature work workflow.
- **Constitution V12** — topology applicability. Spec 028
  applies to topologies 1-6; incompatible with topology 7.
- **Constitution V13** — primary use cases research
  co-authorship (§2), consulting (§3), decision-making
  under asymmetric expertise (§6).
- **Constitution V14** — per-stage timing budgets. Spec 028
  contributes three budgets (Performance Budgets section).
- **Constitution V16** — env-var validation at startup.
  Spec 028 introduces two new vars (Configuration section).

## Assumptions

- The CAPCOM model is the most significant routing-model
  expansion since the project's eight-scope routing system
  shipped. It introduces visibility partitioning across the
  participant set — a category change rather than a scope
  refinement.
- Single-CAPCOM-per-session is enforced at the DB layer via
  a unique partial index. Application-level invariants are
  insufficient under concurrent facilitator actions; the DB
  is the source of truth.
- Rotation is a privilege transfer, not a privilege
  accumulation. The new CAPCOM does not inherit the prior
  CAPCOM's `capcom_only` view. The audit trail attributes
  every `capcom_only` message to the CAPCOM-of-record at
  emission time; rotation does not rewrite history.
- CAPCOM disable preserves historical `capcom_only`
  content invisibility. There is no retroactive promotion
  to public; the privilege boundary is one-way and
  permanent.
- The visibility filter is the last context-assembly stage
  before bridge dispatch. An architectural test (FR-019)
  asserts no code path bypasses the filter; CI fails on
  bypass attempts. This is the security envelope that
  makes the partition durable.
- The `capcom_relay` action is a privilege-elevating
  action analogous to spec 024's promote-to-transcript.
  The audit envelope (every relay logged) + the
  `_validate_and_persist` pipeline pass-through (FR-017)
  bound the covert-channel risk.
- The 14th attack vector family (covert channel via
  curation) extends to CAPCOM. The information-density
  signal (spec 004 FR-020 + spec 026 FR-018) applies to
  `capcom_relay` messages; raw transcripts stay canonical
  for forensic review.
- Spec 005's summarizer respects visibility (FR-018). Two-
  tier summaries preserve the partition at the
  summarization layer; without this, summarizer-side
  context leakage would silently break the partition.
- CAPCOM is participant-bound in v1, NOT account-bound.
  Cross-session CAPCOM persistence (a returning expert
  AI auto-resuming as CAPCOM in subsequent engagements) is
  a v2 follow-up.
- CAPCOM does NOT see facilitator scratch (spec 024) in v1.
  Extending CAPCOM visibility to scratch is a v2 follow-up
  that requires its own security review (the CAPCOM AI is
  not the same trust tier as the facilitator).
- Spec 028 is eligible for the standard Phase 3
  clarify/plan/tasks pass. Status remains Draft until
  clarifications resolve AND the user accepts the
  scaffolding.
