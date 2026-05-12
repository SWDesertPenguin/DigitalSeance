# Feature Specification: Facilitator Scratch Window (Notes, Summary Archive, Review-Gate Diff History)

**Feature Branch**: `024-facilitator-scratch`
**Created**: 2026-05-07
**Status**: Implementation in progress (Clarified 2026-05-12; spec 023 Implemented 2026-05-12 unblocks the account-scoped path)
**Input**: User description: "Phase 3+ human-only side-channel scratch window. Facilitators want a private space to write questions / decisions / notes, browse older summaries, and review review-gate history with diffs — WITHOUT polluting AI context. AIs do not see scratch content unless the facilitator explicitly promotes a note into the main transcript. Subsumes the deeper version of backlog item #3 (Summary + Review Gate history panel); the surface-level summary viewer is already covered by spec 011 US9. Three sub-panels: Notes (facilitator-authored markdown, AIs never see), Summary archive (browse all spec-005 checkpoints), Review-gate history (side-by-side diff for every edited draft). Promote-to-transcript action lifts a note into the conversation as a human-injected message. Account-scoped when spec 023 is in place; session-scoped fallback otherwise. Applies to topologies 1-6 (orchestrator-mediated content store); incompatible with topology 7. Primary use cases: consulting (§3), technical review and audit (§5), decision-making under asymmetric expertise (§6)."

## Overview

The current Web UI (spec 011) gives the facilitator a single
view onto the AI conversation: the live transcript, the
participant sidebar, and a banner stack. Everything the
facilitator types is destined for AI context. There is no
private space for thinking-out-loud, drafting a question
before it goes in, or recording an observation that should
NOT influence the AI conversation. Facilitator notes today
live in external tools (a separate document, the operator's
text editor) and the cross-reference between observation and
session is reconstructed manually.

A Phase 1+2 shakedown surfaced the cost of this gap: the
facilitator wanted a thinking space and ended up reading raw
debug-export JSON to revisit context that had scrolled out of
the active view. The friction is high enough that observations
go unrecorded, and the connection between observation and the
specific session moment is lost.

This spec defines a **facilitator scratch window** as a new
operator-side surface with three sub-panels:

1. **Notes.** Facilitator-authored markdown notes scoped to a
   session (and to an account when spec 023 is in place).
   Notes are stored, autosaved, edited, deleted by the
   facilitator. **AIs MUST NEVER see notes content** — notes
   are never assembled into context, never sent to a provider,
   never persisted anywhere the AI context-assembly path
   reads from. Notes are operator-private state.
2. **Summary archive.** A browseable list of every
   summarization checkpoint (spec 005) for the active session
   in chronological order. The facilitator can scroll history
   beyond the latest checkpoint, expand any past summary, and
   copy text into the Notes sub-panel. The archive reads from
   the existing `messages` table where summary checkpoints
   are persisted with `speaker_type='summary'` (spec 005
   §FR-007); no new persistence layer.
3. **Review-gate history with side-by-side diff.** A list of
   every review_gate_staged event for the session, with a
   diff renderer that shows the original AI draft alongside
   the facilitator's edited version when the facilitator
   chose `edit-and-approve`. The data is already in the
   debug-export payload (spec 010); this surface renders it
   in the live UI.

A separate action — **promote-to-transcript** — lets the
facilitator lift a note into the conversation as a human-
injected message. The promote action reuses the existing
`inject_message` MCP tool; the note becomes a normal human
turn from that point forward. **Promote-to-transcript is a
high-privilege action** because it injects facilitator-trust
content into AI context. The action MUST be guarded by a
confirmation modal showing the exact text and MUST emit a
detailed audit-log entry retaining the prior note state, so
a malicious or accidental promotion is reconstructable.

The scratch surface is **account-scoped** when spec 023
(user-accounts) is in place: notes attached to an account
survive session archive, browser tab close, and machine
restart. When spec 023 is NOT in place (or
`SACP_ACCOUNTS_ENABLED=false`), scratch content falls back
to **session-scoped**: it persists only for the lifetime of
the session and is deleted when the session is archived.
The fallback is explicit, advertised in the panel UI, so the
facilitator knows their notes are ephemeral when the
account layer is off.

This spec **scaffolds only**. Implementation begins when
the facilitator schedules tasks per Constitution §14.1
AND spec 023 reaches Status: Implemented (for the
account-scoped path). The session-scoped fallback can ship
without 023; the production target is the account-scoped
path.

## Clarifications

### Session 2026-05-12 (Resolved)

All eleven initial-draft markers resolved during full-pass clarify on 2026-05-12. FR text updated inline below; the original "Initial draft assumptions requiring confirmation" subsection is retained for historical reference. One additional clarification (shared-module reuse contract with spec 029) folded into FR-026 to make the dependency explicit.

1. **Sub-panel arrangement**. Single slide-over panel with three tabs (Notes / Summaries / Review Gate) confirmed (drafted shape stands). Closing the panel returns to the live transcript. Routes-not-tabs alternative rejected — the slide-over preserves the live-transcript-context that operators need while scratch-thinking. Three-separate-slide-overs rejected for the same reason plus screen-real-estate cost. FR-024 below pins the entry-point + route.

2. **Note format**. Markdown subset confirmed (headings, bold/italic, bullet lists, links, inline code, code blocks). Plain-text alternative rejected: facilitators paste prompt drafts that benefit from formatting. Rich-text editor rejected: the spec ships zero new persistence layers for formatting state and a WYSIWYG dependency would bloat the SPA bundle. Operators wanting tables / images paste the markdown source. FR-001 below pins the format.

3. **Note permission model**. Single-owner-no-sharing confirmed in v1. Account binds notes to one account; session-scoped fallback binds notes to the session only (no per-tab user separation). Shared scratch across facilitators in the same session is a Phase 4+ feature — the per-facilitator design does not preclude it but does not support it. FR-015 pins the binding semantics.

4. **Promote-to-transcript granularity**. One promote per click confirmed. Batch promote rejected — each promote is a high-privilege injection point and bundling them obscures the audit trail. Sequential promote-promote-promote remains supported. FR-006 pins one-at-a-time.

5. **Promote modifies the original note**. Preserve-and-mark confirmed: `promoted_at` + `promoted_message_id` populate on success; the note row remains. Delete-after-promote rejected — destroys facilitator history. Lock-after-promote rejected — re-promotion (e.g., to re-inject during a later phase) is a legitimate operator action subject to its own audit row. FR-006 pins the preserve-and-mark semantic; the re-promote flow is covered by US2 acceptance scenario 6.

6. **Review-gate diff algorithm**. Line-by-line Myers (jsdiff) confirmed as the default with a per-row word-level toggle inheriting spec 029's `DiffRenderer` component (no parallel implementation in spec 024 source). Character-level diff rejected — overwhelms on long edits. Spec 029 contracts/shared-module-contracts.md §3 + §4 are the binding contract. FR-014 below cites the contract directly.

7. **Diff size handling**. 50KB main-thread + 50-500KB Worker + >500KB raw-display confirmed as the threshold trio. The constants are inherited from `frontend/diff_engine.js`'s locked `MAIN_THREAD_BYTE_THRESHOLD` (50_000) and `WORKER_BYTE_THRESHOLD` (500_000) per spec 029 contracts/shared-module-contracts.md §4 — spec 024 MUST NOT redefine. FR-014 below pins the inheritance.

8. **Summary archive pagination**. 20 per page offset-based confirmed (smaller than spec 029's 50 because summary checkpoints render with expandable narrative previews and 50 simultaneously expanded would be unworkable). Cursor-based rejected — per-session bounded count makes offset sufficient. FR-012 pins the page size.

9. **Account-vs-session-scoped detection**. Runtime detection confirmed. The panel reads `SACP_ACCOUNTS_ENABLED` AND the authenticated session's account binding at panel-load time. If both account-mode AND the facilitator is account-authenticated, scratch is account-scoped (FK to `accounts`); otherwise session-scoped (FK to `sessions` only). The active scope is rendered as a header chip in the panel UI so the facilitator is never surprised by ephemeral-on-archive notes. FR-015 + FR-016 + FR-017 pin the semantics; FR-025 below pins the UI scope indicator.

10. **Notes encryption at rest**. Plaintext-with-disk-encryption-default confirmed. Notes are NOT API-key-class secrets; they are operator-private workspace content. Operators with at-rest-encryption requirements use full-disk encryption at the deployment level. ScrubFilter applies to audit-log payloads carrying note content (FR-020) so token-shaped substrings inside notes do not leak into log lines if the facilitator pastes a secret. FR-020 pins the ScrubFilter coverage.

11. **Phase 1+2 shakedown reference paraphrase**. The Overview reference stands without exposing the specific test session ID (matches the project memory default of not exposing test artefacts in committed specs). No change to spec text.

12. **Shared-module reuse contract with spec 029 (NEW during clarify pass 2026-05-12)**. Spec 024's review-gate diff sub-panel MUST import (a) the inline `DiffRenderer` React component from `frontend/app.jsx`, (b) the locked threshold constants `MAIN_THREAD_BYTE_THRESHOLD` + `WORKER_BYTE_THRESHOLD` from `frontend/diff_engine.js`, (c) `format_label` / `formatLabel` from `src/orchestrator/audit_labels.py` / `frontend/audit_labels.js` for any audit-adjacent labels (e.g., promote-action label in the panel's tool-tip text), and (d) `format_iso` / `formatIso` from `src/orchestrator/time_format.py` / `frontend/time_format.js` for timestamp rendering. Spec 024 MUST NOT redeclare any of these — the FR-020 architectural test enforces. FR-014 below carries the citation; the spec 011 amendment FR-046 binds the SPA-side import surface.

### Initial draft assumptions requiring confirmation
- **Sub-panel arrangement.** Drafted as: a single slide-over
  panel from the session header with three tabs (Notes /
  Summaries / Review Gate). Closing the panel returns the
  facilitator to the live transcript view. Alternatives
  considered: three separate slide-overs (more screen real-
  estate cost), three separate routes (loses the
  side-by-side-with-transcript shape). [NEEDS CLARIFICATION:
  confirm tabbed-slide-over vs. alternative arrangement.]
- **Note format.** Drafted as: markdown with a small subset
  of formatting (headings, bold/italic, bullet lists, links,
  inline code, code blocks). Rich-text features (tables,
  images, embeds) are out of scope; if a facilitator needs
  them they paste markdown source. [NEEDS CLARIFICATION:
  confirm markdown-subset vs. plain-text vs. richer.]
- **Note permission model.** Drafted as: a note belongs to
  one account (when 023 is in place) and is visible only to
  that account. No note-sharing across accounts in v1; if
  two facilitators share a session each has their own scratch.
  [NEEDS CLARIFICATION: confirm single-owner-no-sharing vs.
  per-session shared-among-facilitators model.]
- **Promote-to-transcript granularity.** Drafted as: one
  promote action lifts exactly one note. Batch promote
  (multiple notes in one action) is out of scope. The
  facilitator can promote-then-promote-then-promote if they
  want multiple notes in sequence. [NEEDS CLARIFICATION:
  confirm one-at-a-time vs. batch.]
- **Promote modifies the original note.** Drafted as: after
  a successful promote, the note is marked
  `promoted_at: <ts>` and `promoted_message_id: <id>` but
  the note row remains in scratch. The facilitator's history
  is preserved; the note's link to the resulting transcript
  message is durable. The note can be re-promoted (creating
  a second injection) but each promote emits its own audit
  trail row. [NEEDS CLARIFICATION: confirm preserve-and-mark
  vs. delete-after-promote vs. lock-after-promote.]
- **Review-gate diff algorithm.** Drafted as: line-by-line
  diff (Myers algorithm) rendered side-by-side. Character-
  level diff overwhelms on long edits; word-level diff is a
  reasonable middle ground but harder to render side-by-side
  cleanly. [NEEDS CLARIFICATION: confirm line-by-line vs.
  word-level vs. configurable.]
- **Diff size handling.** V14 budget says diffs up to 50KB
  without blocking the UI thread. Drafted as: diffs above
  50KB render in a Web Worker; UI shows a "computing diff"
  state during computation. Diffs above 500KB show only the
  raw original + edited values without a computed diff
  (rationale: at that size the diff is unreadable anyway).
  [NEEDS CLARIFICATION: confirm 50KB worker boundary +
  500KB no-diff fallback.]
- **Summary archive pagination.** Drafted as: 20 summaries
  per page, ordered chronologically (newest first by
  default; toggleable to oldest first). Cursor-based
  pagination is overkill for the per-session bounded
  count; offset is fine. [NEEDS CLARIFICATION: confirm
  20/page vs. all-at-once.]
- **Account-vs-session-scoped detection.** Drafted as: the
  panel detects scratch scope at startup by reading
  `SACP_ACCOUNTS_ENABLED` AND the authenticated session's
  account binding. If `SACP_ACCOUNTS_ENABLED=true` AND the
  facilitator is logged in via account auth, scratch is
  account-scoped; otherwise it is session-scoped. The panel
  UI displays the active scope explicitly so the
  facilitator is never surprised by ephemeral notes.
  [NEEDS CLARIFICATION: confirm runtime-detection shape vs.
  config-driven.]
- **Notes encryption at rest.** Drafted as: notes are stored
  in plaintext alongside other transcript content. They are
  not part of the AI context-assembly path (FR-001), so the
  threat model differs from API-key encryption. Operators
  with at-rest-encryption requirements use full-disk
  encryption at the deployment level. [NEEDS CLARIFICATION:
  confirm plaintext-with-disk-encryption-default vs.
  application-layer encryption.]
- **Phase 1+2 shakedown reference.** The shakedown detail is
  summarised in the Overview without citing the specific test
  session ID (matches the project memory default of not
  exposing test artefacts in committed specs). Confirm this
  paraphrase is acceptable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Facilitator writes, edits, and persists notes that AIs do not see (Priority: P1)

A facilitator running a multi-AI consulting session wants to
record a question they want to ask later, jot down an
observation about an AI's reasoning style, and draft a
follow-up prompt before deciding to send it. They open the
scratch panel from the session header, switch to the Notes
tab, type their content. The note autosaves on a 2-second
debounce. They close the panel; the live transcript view
returns. They reopen the panel later in the session; the
note is there. **At no point does the AI see the note.** A
spec 010 debug-export of the session shows the note as part
of the operator-side scratch payload (clearly partitioned
from the AI-visible transcript), but no AI message references
the note's content.

**Why this priority**: P1 because this is the spec's primary
value. Without it, the surface ships zero. The "AIs never
see" guarantee is the security envelope the entire spec
exists to enforce; verifying that the notes path does not
touch the AI context-assembly pipeline (spec 008) is the
core test.

**Independent Test**: Drive a facilitator login (account-
scoped path). Open the scratch panel. Type into the Notes
tab. Wait for autosave debounce. Close panel. Drive an AI
turn. Inspect the assembled prompt (spec 008 output) for
the AI's dispatch — assert the note content is NOT present.
Reopen the scratch panel — assert the note appears. Drive
a debug-export — assert the export contains the note in a
clearly-partitioned scratch section, NOT in the messages
array.

**Acceptance Scenarios**:

1. **Given** an authenticated facilitator on an active
   session, **When** they type into the Notes tab,
   **Then** the content MUST autosave on a 2-second debounce
   AND persist across panel close + reopen.
2. **Given** a saved note, **When** the orchestrator
   assembles AI context for any participant, **Then** the
   note content MUST NOT appear in the assembled prompt
   (verified by an architectural test asserting no path
   from `notes` reads to the context-assembly pipeline).
3. **Given** a saved note, **When** any AI's response is
   inspected, **Then** the note content MUST NOT have
   contributed to the response (verified by absence-from-
   prompt above plus a content-isolation test).
4. **Given** a session with notes, **When** the facilitator
   exports via spec 010 debug-export, **Then** the notes
   MUST appear in a clearly-partitioned `scratch` section,
   distinct from the `messages` array.
5. **Given** the facilitator deletes a note, **When** the
   delete action fires, **Then** the note MUST be removed
   from scratch storage AND a soft-delete entry MUST be
   recorded in `admin_audit_log` (the note content is
   retained in the audit log only if the operator-grade
   retention policy retains it).
6. **Given** a non-facilitator participant attempts to read
   the scratch endpoint, **When** the request fires,
   **Then** HTTP 403 MUST be returned (mirrors spec 010
   §FR-2 facilitator-only access).

---

### User Story 2 - Facilitator promotes a note to the transcript with confirmation modal and audit-log entry (Priority: P1)

The facilitator has drafted a question in the Notes tab.
After reviewing the AI conversation, they decide to send it.
They click "Promote to transcript" on the note. A
confirmation modal appears showing the EXACT text that will
be injected. They confirm. The orchestrator calls the
existing `inject_message` MCP tool with the note content as
a human turn. The note row is marked `promoted_at` and
`promoted_message_id`. An `admin_audit_log` row records the
promotion with the full prior note content (so a malicious
or accidental promote is reconstructable).

**Why this priority**: P1 because promotion IS the bridge
between scratch and AI context. Without it, scratch is a
disconnected diary. With it, scratch becomes a drafting
surface that funnels into AI context under operator
control. The confirmation modal + audit-log envelope is
why this is high-privilege and explicit; without that
guard the spec opens an injection vector against AI trust.

**Independent Test**: Authenticated facilitator with a saved
note. Click promote on the note. Assert a confirmation
modal renders with the EXACT note text. Confirm. Assert the
existing `inject_message` flow fires with the note content
as the human turn. Assert the note row has
`promoted_at: <ts>`, `promoted_message_id: <id>` populated.
Assert `admin_audit_log` has one row with
`action='facilitator_promoted_note'`, the note's prior
content (in a scrubbed/redacted form per spec 007 §FR-012
ScrubFilter), the note id, the new message id, the actor
(facilitator), and the timestamp. Drive a subsequent AI
turn — assert the AI's response context now includes the
promoted message AS a normal human turn.

**Acceptance Scenarios**:

1. **Given** a saved note, **When** the facilitator clicks
   "Promote to transcript", **Then** a confirmation modal
   MUST render showing the EXACT text that will be injected
   AND offer Cancel + Confirm options.
2. **Given** the modal is open, **When** the facilitator
   clicks Cancel, **Then** no injection MUST occur AND no
   audit-log row MUST be emitted.
3. **Given** the modal is open, **When** the facilitator
   clicks Confirm, **Then** the existing `inject_message`
   MCP tool MUST be invoked with the note content AND the
   note row MUST be marked `promoted_at` + `promoted_message_id`.
4. **Given** a successful promotion, **When**
   `admin_audit_log` is inspected, **Then** one row MUST
   exist with `action='facilitator_promoted_note'`, the
   actor (facilitator id), the note id, the resulting
   message id, the prior note content (subject to spec 007
   ScrubFilter for any embedded credentials), and the
   timestamp.
5. **Given** a promoted note, **When** the facilitator
   re-opens the scratch panel, **Then** the note MUST
   still appear (preserved) BUT visually marked as
   "promoted on <ts>" with a link to the resulting
   transcript message.
6. **Given** a promoted note, **When** the facilitator
   clicks promote again, **Then** a SECOND injection MUST
   fire AND a SECOND audit-log row MUST be emitted —
   re-promotion is allowed but each event is independently
   recorded.
7. **Given** a non-facilitator attempts to call the promote
   endpoint, **When** the request fires, **Then** HTTP 403
   MUST be returned (promote-to-transcript is
   facilitator-only).
8. **Given** the session is archived, **When** the
   facilitator attempts to promote a note from that session,
   **Then** the request MUST be rejected with HTTP 409 and
   a clear error explaining promote requires an active
   session.

---

### User Story 3 - Summary archive lets the facilitator browse past summarization checkpoints and copy text into notes (Priority: P2)

A research co-authorship session has accumulated 12
summarization checkpoints (spec 005) over a long-running
engagement. The latest is visible in the live transcript;
the previous 11 have scrolled out of view. The facilitator
opens the scratch panel, switches to the Summaries tab. A
list of all 12 checkpoints renders chronologically with the
turn range each summary covers and the first 200 characters
of each summary's narrative section. The facilitator
expands the checkpoint from turn 47-96, reads it, and
selects a passage to copy into a new note in the Notes tab.

**Why this priority**: P2 because the live UI already shows
the LATEST summary (spec 011 US9). The archive is for
revisiting OLDER summaries — important for long-running
sessions but not on the critical path for first-use.

**Independent Test**: Drive a session with at least 3
summarization checkpoints. Open scratch panel, switch to
Summaries tab. Assert all 3 checkpoints appear in
chronological order with turn range and narrative preview.
Click an older checkpoint to expand. Assert the full JSON
content (decisions, open_questions, key_positions, narrative
per spec 005 §FR-005) renders readably. Select text in the
expansion and use a copy-to-notes action. Assert a new note
is created in the Notes tab with the copied text.

**Acceptance Scenarios**:

1. **Given** a session with N summarization checkpoints,
   **When** the facilitator opens the Summaries tab,
   **Then** all N checkpoints MUST appear ordered by turn
   number AND each row MUST show turn range and a
   narrative preview.
2. **Given** an expanded summary, **When** the renderer
   completes, **Then** the four sections MUST be readable
   (decisions, open_questions, key_positions, narrative
   per spec 005 §FR-005).
3. **Given** an expanded summary, **When** the facilitator
   selects text and clicks "copy to notes", **Then** a new
   note MUST be created with the copied text AND the note
   list MUST refresh to include it.
4. **Given** a session with more than 20 checkpoints,
   **When** the Summaries tab loads, **Then** the first 20
   MUST appear with a "load more" or pagination control.

---

### User Story 4 - Review-gate history shows side-by-side diff for every edited draft in the session (Priority: P2)

A technical-review session running with the spec 007 review
gate has held three drafts for review-gate inspection over
the course of the session. The facilitator approved one
verbatim, edited one before approving, and rejected one.
The facilitator opens the scratch panel, switches to the
Review Gate tab. A list of all three review-gate events
renders. The facilitator clicks the edited one. A
side-by-side diff renderer shows the AI's original draft on
the left and the facilitator's edited version on the right
with line-level differences highlighted.

**Why this priority**: P2 because review-gate decision
review is an audit-trail concern — important for technical
review and audit (V13 §5) but not on the critical path
for first-use sessions.

**Independent Test**: Drive a session through three review-
gate events: one approve-verbatim, one edit-and-approve, one
reject. Open the Review Gate tab. Assert all three events
appear with the correct disposition. Click the
edit-and-approve event. Assert a side-by-side diff renders
with the original draft on the left, edited version on the
right, and line-level differences highlighted. Assert the
diff renderer handles a 10KB diff without blocking the UI
thread (perf check).

**Acceptance Scenarios**:

1. **Given** a session with N review-gate events, **When**
   the facilitator opens the Review Gate tab, **Then** all
   N events MUST appear with timestamp, disposition
   (approved-verbatim, edit-and-approve, reject), and
   participant id.
2. **Given** an edit-and-approve event, **When** the
   facilitator clicks it, **Then** a side-by-side diff
   MUST render with original on left, edited on right, and
   line-level differences highlighted.
3. **Given** a diff payload below 50KB, **When** the
   renderer runs, **Then** it MUST complete without
   blocking the UI thread perceptibly (P95 ≤ 100ms diff
   computation).
4. **Given** a diff payload above 50KB, **When** the
   renderer runs, **Then** the diff MUST compute in a Web
   Worker AND the UI MUST show a "computing diff" state
   during the computation.
5. **Given** a diff payload above 500KB, **When** the
   renderer runs, **Then** it MUST display the raw
   original and edited values WITHOUT a computed diff,
   with an explanation about the size limit.
6. **Given** an approve-verbatim event, **When** the
   facilitator clicks it, **Then** the renderer MUST show
   the AI's draft as-was (no diff — there is nothing to
   compare against).
7. **Given** a reject event, **When** the facilitator
   clicks it, **Then** the renderer MUST show the AI's
   rejected draft AND the rejection reason recorded by
   the facilitator at rejection time.

---

### User Story 5 - Scratch content survives session archive when account is in place (Priority: P3)

A consultant who has logged in via account auth (spec 023)
has been taking notes during a session. The session is
archived (engagement complete). The consultant logs back in
days later, navigates to the archived session from
`/me/sessions`, and opens the scratch panel. Their notes
from the active phase of the session are still there. The
review-gate history is still browseable (read-only). The
summary archive is still browseable. They can review the
notes they took during the engagement; they can NOT promote
to transcript (the session is archived; no live AI context
to inject into).

**Why this priority**: P3 because the survives-archive
behavior is what the account-scoped path adds. Without it,
spec 024 ships the session-scoped fallback only; with
spec 023 in place, scratch becomes durable across the
session lifecycle. P3 because most facilitators in
short-lived sessions don't need it; for long-running
consulting/research engagements it's important.

**Independent Test**: Authenticate via account auth (spec
023). Take notes in a session. Archive the session. Log
out, log back in. Navigate to the archived session from
`/me/sessions`. Open the scratch panel. Assert notes from
the active phase are still present. Assert the panel UI
indicates the session is archived and promote-to-transcript
is disabled. Drive a promote attempt — assert HTTP 409 per
US2 acceptance scenario.

**Acceptance Scenarios**:

1. **Given** spec 023 is in place AND the facilitator is
   logged in via account, **When** they archive a session
   they have notes in, **Then** the notes MUST persist
   beyond archive.
2. **Given** an archived session with persisted notes,
   **When** the facilitator returns to the session from
   `/me/sessions`, **Then** the notes MUST be visible AND
   the scratch panel MUST advertise the session as
   archived.
3. **Given** an archived session with persisted notes,
   **When** the facilitator attempts to promote a note,
   **Then** the request MUST be rejected with HTTP 409.
4. **Given** spec 023 is NOT in place, **When** a session
   is archived, **Then** any notes from that session MUST
   be deleted as part of the archive flow (session-scoped
   fallback).
5. **Given** `SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE`
   is set, **When** a scratch retention sweep runs after
   the configured window, **Then** notes from sessions
   archived more than the window ago MUST be purged.

---

### Edge Cases

- **Note autosave during a network blip.** The SPA buffers
  unsent changes and retries on reconnect; the panel UI
  shows a "saving..." → "saved" → "save failed" state so
  the facilitator knows the persistence status.
- **Two browser tabs open the same session's scratch.**
  Last-write-wins on conflict; the SPA shows a brief
  "note updated elsewhere" indicator on conflict
  detection. Optimistic concurrency check on save (e.g.,
  ETag or version column) prevents silent overwrites.
- **Promote attempt with empty note content.** Modal shows
  the empty content; Confirm is disabled until non-empty
  text exists.
- **Promote attempt with note content that fails 007's
  spotlight/sanitize pipeline.** The promote action runs
  through the same `_validate_and_persist` path as any
  other human turn (spec 007 §FR-013); high-risk content
  triggers the review gate the same as if the facilitator
  had typed it directly into the live UI. Promote does NOT
  bypass the security pipeline.
- **Account is deleted while a session is in flight.** The
  scratch's account binding is broken; the panel shows the
  notes as session-scoped (about to be lost on archive)
  with an explanatory message. The facilitator can copy
  the notes elsewhere before archive.
- **Session is deleted (not just archived).** Notes for
  that session are deleted regardless of account binding;
  session deletion is a hard cascade per spec 001 §FR-011.
  The notes' audit-log entries (creation, edit, delete,
  promote) survive in `admin_audit_log` per spec 001
  §FR-019.
- **Diff payload contains terminal escape sequences or
  binary data.** Renderer escapes / replaces non-printable
  characters before display; the raw bytes are still
  retrievable from spec 010 debug-export.
- **Summary archive renders a checkpoint whose JSON
  content fails to parse** (spec 005 §FR-006 retry-fallthrough
  fallback raw response). Renderer falls back to displaying
  the raw text content with a "this checkpoint did not
  produce structured JSON" indicator.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Facilitator notes MUST NEVER be assembled
  into AI context. The notes storage MUST be on a separate
  table (e.g., `facilitator_notes`) that the spec 008
  context-assembly pipeline does NOT read from. An
  architectural test MUST enforce this — failing the
  build if any code path reaches notes from a
  context-assembly entry point.
- **FR-002**: A new endpoint `GET
  /tools/facilitator/scratch?session_id=<id>` MUST return
  the scratch payload for the active session: the
  facilitator's notes, the summary archive list, and the
  review-gate history list. The endpoint is
  facilitator-only (spec 010 §FR-2 pattern).
- **FR-003**: A new endpoint `POST
  /tools/facilitator/scratch/notes` MUST create a new
  note. The endpoint is facilitator-only and session-bound
  (spec 010 §FR-3 pattern). The note's account binding is
  set when spec 023 is in place AND the facilitator is
  authenticated via account auth.
- **FR-004**: A new endpoint `PUT
  /tools/facilitator/scratch/notes/<id>` MUST update an
  existing note. Optimistic concurrency check via a
  `version` column rejects stale writes with HTTP 409.
- **FR-005**: A new endpoint `DELETE
  /tools/facilitator/scratch/notes/<id>` MUST soft-delete
  a note (mark it deleted, retain in `admin_audit_log` for
  audit-trail integrity).
- **FR-006**: A new endpoint `POST
  /tools/facilitator/scratch/notes/<id>/promote` MUST
  invoke the existing `inject_message` MCP tool with the
  note's content as a human turn AND emit an
  `admin_audit_log` row with `action='facilitator_promoted_note'`,
  the actor, the note id, the prior note content (subject
  to spec 007 §FR-012 ScrubFilter), the resulting message
  id, and the timestamp. Promote MUST be rejected on
  archived sessions (HTTP 409).
- **FR-007**: The promote action MUST be guarded by a
  client-side confirmation modal showing the EXACT text
  that will be injected. No promote MAY occur without an
  explicit user confirm action. (FR-007 is a UX
  requirement implemented by spec 011 when its tasks
  land.)
- **FR-008**: Promoted note content MUST flow through the
  existing `_validate_and_persist` security pipeline (spec
  007 §FR-013). High-risk content triggers the review
  gate the same as any other human turn. Promote does NOT
  bypass the security pipeline.
- **FR-009**: Notes MUST autosave on a 2-second debounce
  on the client side. The server-side endpoint accepts
  every save; the client throttles to limit traffic.
- **FR-010**: Note content MUST have a size cap governed
  by `SACP_SCRATCH_NOTE_MAX_KB` (default 64). Notes
  exceeding the cap are rejected with HTTP 413.
- **FR-011**: The summary archive sub-panel MUST read from
  the existing `messages` table where summary checkpoints
  are persisted with `speaker_type='summary'` (spec 005
  §FR-007). No new persistence layer.
- **FR-012**: The summary archive MUST paginate at 20
  entries per page with offset-based navigation, ordered
  by turn number descending by default.
- **FR-013**: The review-gate history sub-panel MUST read
  the review-gate-staged events from
  `admin_audit_log` (or the security_events / review_gate
  table per spec 007 §FR-005's storage decision in
  `/speckit.plan`).
- **FR-014**: The diff renderer for the review-gate sub-panel MUST reuse spec 029's inline `DiffRenderer` React component from `frontend/app.jsx` and the locked threshold constants from `frontend/diff_engine.js` (`MAIN_THREAD_BYTE_THRESHOLD = 50_000`, `WORKER_BYTE_THRESHOLD = 500_000`) per spec 029 contracts/shared-module-contracts.md §3 + §4. Spec 024 MUST NOT redeclare these constants and MUST NOT reimplement Myers-diff helpers; the spec 029 FR-020 architectural test enforces. The thresholds drive a three-mode contract: diffs ≤ 50KB render synchronously on the main thread; diffs in (50KB, 500KB] compute via the inline-blob Web Worker bootstrap; diffs > 500KB display the raw original + edited values without a computed diff plus an explanatory info bar.
- **FR-015**: When spec 023 is in place AND
  `SACP_ACCOUNTS_ENABLED=true` AND the facilitator is
  authenticated via account auth, scratch content MUST be
  account-scoped (FK to `accounts`). Otherwise scratch
  content MUST be session-scoped (FK to `sessions` only,
  no account FK).
- **FR-016**: When scratch is account-scoped, scratch
  content MUST persist beyond session archive. The
  session can be browsed (notes visible, panel
  read-only-for-promotion).
- **FR-017**: When scratch is session-scoped, scratch
  content MUST be deleted on session archive.
- **FR-018**: When `SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE`
  is set, account-scoped notes from sessions archived more
  than the window ago MAY be purged by an external
  cleanup job.
- **FR-019**: The master switch `SACP_SCRATCH_ENABLED`
  MUST gate the entire scratch surface. When `false`
  (default), the endpoints return HTTP 404 and the SPA
  does not render the scratch panel entry point.
- **FR-020**: All scratch-related actions
  (note create / edit / delete / promote) MUST emit
  `admin_audit_log` rows with actor, target note id,
  action name, and timestamp. The action content (note
  text on edit, prior text on promote) is included in the
  audit-log payload subject to spec 007 §FR-012
  ScrubFilter.
- **FR-021**: A non-facilitator attempting any scratch
  endpoint MUST receive HTTP 403 (mirrors spec 010 §FR-2
  facilitator-only access).
- **FR-022**: The three new env vars
  (`SACP_SCRATCH_ENABLED`, `SACP_SCRATCH_NOTE_MAX_KB`,
  `SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE`) MUST have
  validator functions in `src/config/validators.py`
  registered in the `VALIDATORS` tuple, AND corresponding
  sections in `docs/env-vars.md` with the six standard
  fields, BEFORE `/speckit.tasks` is run for this spec
  (V16 deliverable gate).
- **FR-023**: Scratch debug-export contribution. Spec 010
  debug-export MUST include scratch content in a
  `scratch` section clearly partitioned from the
  AI-visible `messages` array. The export shape is
  defined in `/speckit.plan`.
- **FR-024**: The scratch panel entry-point affordance MUST live as a button in the existing facilitator session header (next to the existing admin-panel toggle), gated by FR-021 facilitator-only role check AND by FR-019 master switch `SACP_SCRATCH_ENABLED=true`. The button opens the slide-over panel at the SPA route `/session/:id/scratch` with three tabs (Notes / Summaries / Review Gate). The panel preserves the live transcript view alongside (slide-over, not full-page route) so facilitators retain context while drafting.
- **FR-025**: The scratch panel header MUST display a scope chip indicating whether the active scratch is `account-scoped` (durable across session archive) or `session-scoped` (deleted on archive). The chip MUST be visible at all times the panel is open. When session-scoped, the chip MUST include a tooltip explaining the ephemeral-on-archive semantic so the facilitator never loses notes by surprise (clarify Q9).
- **FR-026**: Spec 024 MUST reuse the spec 029 shared-module contracts (`specs/029-audit-log-viewer/contracts/shared-module-contracts.md` §1, §2, §3, §4): import `format_label` / `formatLabel` for any audit-adjacent labels surfaced in the panel (e.g., the promote action's audit-row preview), import `format_iso` / `formatIso` for all timestamp rendering (note created_at / updated_at / promoted_at, summary checkpoint timestamps, review-gate event timestamps), import the inline `DiffRenderer` component from `frontend/app.jsx` and the locked threshold constants from `frontend/diff_engine.js`. Spec 024 MUST NOT redeclare any of these — the spec 029 FR-020 architectural test enforces.

### Key Entities

- **FacilitatorNote** — a note row in the
  `facilitator_notes` table. Columns: id, session_id, FK
  account_id (nullable; null when scratch is session-
  scoped), content (markdown text), created_at, updated_at,
  version (for optimistic concurrency), promoted_at
  (nullable), promoted_message_id (nullable), deleted_at
  (nullable, soft-delete).
- **PromoteAction** (audit-log row) — `admin_audit_log`
  row with `action='facilitator_promoted_note'`,
  `actor_id=<facilitator>`, target note id, prior note
  content (post-ScrubFilter), resulting message id,
  timestamp.
- **SummaryArchiveEntry** (read-side projection) — a
  rendered list-item from the existing `messages` table
  filtered by `speaker_type='summary'` and `session_id`.
  No new persistence.
- **ReviewGateEntry** (read-side projection) — a
  rendered list-item from `admin_audit_log` (or
  security_events) filtered by review-gate-related
  actions and session id. No new persistence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An architectural test MUST assert no code
  path from `facilitator_notes` reaches the spec 008
  context-assembly pipeline. CI fails if any new code
  introduces such a path.
- **SC-002**: Note autosave end-to-end (keystroke → server
  persistence) MUST complete with P95 ≤ 200ms (excluding
  the 2s client-side debounce).
- **SC-003**: Scratch panel load (initial fetch) P95 ≤ 1s
  for sessions with up to 100 notes + 50 summaries +
  20 review-gate events.
- **SC-004**: Promote-to-transcript MUST emit one
  `admin_audit_log` row per click and invoke
  `inject_message` exactly once. Verified by an
  end-to-end test driving promote and asserting both the
  audit row and the resulting message in the transcript.
- **SC-005**: Promote-to-transcript on an archived
  session MUST return HTTP 409. Verified by archiving a
  session with notes and driving the promote attempt.
- **SC-006**: Promote of a note that contains content
  that triggers spec 007's high-risk threshold MUST
  route through the review-gate the same as any other
  human turn. Verified by promoting a note containing a
  known injection pattern and asserting review-gate
  staging.
- **SC-007**: Notes MUST be facilitator-only — verified
  by a test driving each scratch endpoint with a
  non-facilitator session and asserting HTTP 403.
- **SC-008**: Scratch debug-export contribution MUST
  partition cleanly from the AI-visible messages array
  — verified by exporting a session with notes and
  asserting the `scratch` section is structurally
  distinct from `messages`.
- **SC-009**: Account-scoped scratch MUST survive
  session archive — verified by a test that authenticates
  via account, takes notes, archives session, navigates
  back from `/me/sessions`, and asserts notes still
  exist.
- **SC-010**: Session-scoped scratch (when 023 is off)
  MUST be deleted on archive — verified by a test that
  takes notes without account auth, archives the session,
  and asserts notes are gone.
- **SC-011**: Diff renderer MUST handle a 50KB diff
  without UI-thread block (P95 ≤ 100ms render). Verified
  by a perf test with a 50KB diff payload.
- **SC-012**: Diff renderer MUST handle a 500KB diff via
  raw-display-without-diff fallback. Verified by a test
  with a 500KB payload asserting the fallback UI state.
- **SC-013**: With any of the three new env vars set to
  an invalid value, the orchestrator process MUST exit
  at startup with a clear error message naming the
  offending var (V16 fail-closed gate observed in CI).

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6**
(orchestrator-driven topologies). The scratch store is
centralized at the orchestrator; the panel reads
session-scoped or account-scoped data via orchestrator-
side endpoints; promote-to-transcript invokes the
orchestrator's MCP tool. All require a single
orchestrator to be the centralized scratch authority.

This feature is **NOT applicable to topology 7
(MCP-to-MCP, Phase 3+)**. In topology 7 each
participant's MCP client is the identity boundary;
there is no orchestrator-side facilitator surface to
attach scratch to. Per V12: any topology-7 deployment
MUST recognize that this spec's scratch surface does
not apply.

### V13 — Use Case Coverage

This feature serves the V13 primary use cases:

- §3 Consulting Engagement
  (`docs/sacp-use-cases.md` §3) — consultants take
  notes alongside the AI panel; the scratch surface is
  the operator-side workspace for that thinking.
- §5 Technical Review and Audit
  (`docs/sacp-use-cases.md` §5) — auditors record
  observations without contaminating the AI conversation;
  the review-gate history sub-panel surfaces the
  decision-review trail in the live UI.
- §6 Decision-Making Under Asymmetric Expertise
  (`docs/sacp-use-cases.md` §6) — experts draft proposals
  before sharing; the Notes sub-panel + promote-to-
  transcript flow is the drafting-and-publish workflow.

Other use cases (§1, §2, §4, §7) inherit the feature
when enabled but are not the priority drivers.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable
contracts. This spec contributes four budgets:

- **Scratch panel load (initial fetch)**: P95 ≤ 1s for
  sessions with up to 100 notes, 50 summaries, and 20
  review-gate events. The query is a bounded read
  over `facilitator_notes`, `messages` (filtered by
  `speaker_type='summary'`), and `admin_audit_log`
  (filtered by review-gate actions). Budget enforcement:
  per-request timing in the access log path (spec 006
  §FR-018).
- **Note autosave round-trip**: P95 ≤ 200ms server-side.
  Client-side debounce is 2s; the server-side budget
  measures the actual save once the debounce fires.
- **Diff renderer (≤ 50KB)**: P95 ≤ 100ms on the main
  thread. Above 50KB diffs MUST run in a Web Worker;
  above 500KB diffs MUST display raw without diff.
- **Promote-to-transcript**: P95 ≤ 500ms from Confirm
  click to the resulting message appearing in the
  transcript. Includes the inject_message dispatch +
  audit-log write + WS broadcast.

## Configuration (V16) — New Env Vars

Three new env vars are introduced. Each MUST have type,
valid range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for
this spec (per V16 deliverable gate).

### `SACP_SCRATCH_ENABLED`

- **Intended type**: boolean
- **Intended valid range**: `true` | `false`. Default
  `false` (master switch ships off; operators opt in).
- **Fail-closed semantics**: any non-parseable value MUST
  cause startup exit. When `false` the scratch endpoints
  return HTTP 404 and the SPA does not render the
  scratch panel entry point.

### `SACP_SCRATCH_NOTE_MAX_KB`

- **Intended type**: positive integer (kilobytes)
- **Intended valid range**: `[1, 1024]` (1 KiB to 1 MiB).
  Default `64`.
- **Fail-closed semantics**: outside the range MUST
  cause startup exit. The cap protects against
  unbounded notes consuming DB space; raising the cap
  past 1 MiB is unsupported in v1.

### `SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE`

- **Intended type**: positive integer, or empty for
  indefinite
- **Intended valid range**: `[1, 36500]` when set; empty
  means indefinite. Default empty (matches the general
  retention posture in `docs/retention.md` §7).
- **Fail-closed semantics**: any non-integer or
  non-positive value MUST cause startup exit. The
  retention applies to account-scoped notes only;
  session-scoped notes are deleted on archive
  regardless of this value.

## Cross-References to Existing Specs and Design Docs

- **Spec 005 (summarization-checkpoints) §FR-007** —
  summary checkpoints are persisted as messages with
  `speaker_type='summary'`. The scratch summary archive
  reads this existing store; no new persistence layer.
- **Spec 011 (web-ui)** — the scratch panel is a new UI
  surface. Spec 024 defines the panel contract
  (endpoints, sub-panel shape, promote modal); spec 011
  owns the SPA wiring. A spec 011 amendment lands when
  024's tasks are scheduled.
- **Spec 023 (user-accounts)** — account-scoped scratch
  binding. Scratch content survives session archive when
  spec 023 is in place AND the facilitator is
  authenticated via account auth. Without 023, scratch is
  session-scoped and ephemeral.
- **Spec 010 (debug-export)** — review-gate events with
  `previous_value` / `new_value` are already in the
  export payload. Spec 024 adds the UI renderer that
  consumes them. The scratch payload is a new partitioned
  section in the export shape (FR-023).
- **Spec 029 (audit-log-viewer) §FR-008 / §FR-019 / §FR-020** —
  shared-component contract pinned in
  [`specs/029-audit-log-viewer/contracts/shared-module-contracts.md`](../029-audit-log-viewer/contracts/shared-module-contracts.md).
  When spec 024 reaches `/speckit.tasks`, its amendment FR-014
  (review-gate diff sub-panel) MUST cite that contract document
  and: import the inline `DiffRenderer` component from
  `frontend/app.jsx`; import the locked threshold constants
  (`MAIN_THREAD_BYTE_THRESHOLD = 50_000`,
  `WORKER_BYTE_THRESHOLD = 500_000`) from
  `frontend/diff_engine.js` rather than redefining them; reuse
  `format_label` / `formatLabel` for any audit-adjacent labels
  surfaced in the scratch panel; reuse `format_iso` /
  `formatIso` for timestamp rendering. Spec 024 MUST NOT
  reimplement Myers-diff helpers (FR-020 architectural test
  enforces).
- **Spec 008 (prompts-security-wiring)** — the
  context-assembly pipeline that scratch notes MUST NEVER
  reach (FR-001). The architectural test enforcing this
  is the security envelope of the spec.
- **Spec 007 (ai-security-pipeline) §FR-012, §FR-013** —
  ScrubFilter applies to scratch audit-log payloads
  (FR-020); the security pipeline applies to promoted
  content (FR-008). Promotion does NOT bypass either.
- **Spec 006 (mcp-server)** — the existing
  `inject_message` MCP tool is reused for promote-to-
  transcript (FR-006). No new tool is introduced.
- **Spec 001 (core-data-model) §FR-008, §FR-011, §FR-019** —
  append-only invariants on log tables; cascade-delete
  on session deletion (FR-017); admin_audit_log carve-out
  for promoted-note audit rows surviving session deletion.
- **`docs/sacp-design.md` §7.6 (AI-Specific Security)** —
  the trust-tiered content model that frames why
  promote-to-transcript is high-privilege: facilitator
  content is trusted at the highest tier; injecting
  arbitrary text into AI context bypasses the
  intermediate-tier validation that AI outputs receive.
  The confirmation modal + audit-log envelope (FR-006,
  FR-007) is the specific control matching that risk
  surface.
- **Constitution §10** — Phase 3+ deliverables. Spec 024
  is in-scope after spec 023 lands.
- **Constitution §14.1** — Feature work workflow. This
  spec scaffolds via `/speckit.specify`; subsequent
  steps are deferred.
- **Constitution V12** — topology applicability. Spec 024
  applies to topologies 1-6; incompatible with topology 7.
- **Constitution V13** — primary use cases consulting (§3),
  technical review and audit (§5), decision-making under
  asymmetric expertise (§6).
- **Constitution V14** — per-stage timing budgets. Spec 024
  contributes four budgets (Performance Budgets section).
- **Constitution V16** — env-var validation at startup.
  Spec 024 introduces three new vars (Configuration
  section).

## Assumptions

- The "AIs never see notes" guarantee (FR-001) is
  the security envelope the entire spec exists to
  enforce. The architectural test (SC-001) is the only
  durable mechanism preventing future code from
  accidentally bridging notes into context assembly.
- The promote-to-transcript action is high-privilege.
  The combination of confirmation modal (FR-007) +
  detailed audit log (FR-006) + security-pipeline
  pass-through (FR-008) is the specific envelope that
  bounds the risk; weakening any one weakens the whole
  envelope. Future amendments touching promote should
  preserve all three.
- The scratch surface is a single-facilitator workspace
  in v1. Multi-facilitator shared scratch is a future
  feature; the per-facilitator-per-session design here
  does not preclude it but does not support it either.
- The summary archive and review-gate history sub-panels
  are read-only views over existing data. Spec 024 does
  not introduce new persistence for either; it surfaces
  what's already in `messages` and
  `admin_audit_log` / security_events.
- The session-scoped fallback ensures spec 024 ships
  value even if spec 023 is delayed. The trade-off is
  loss of notes on archive when accounts are off; the
  panel UI advertises this prominently so the user is
  not surprised.
- Notes encryption at rest is not part of v1. The
  threat model differs from API-key encryption: notes
  are operator-private but not security-critical
  secrets. Operators with at-rest-encryption
  requirements use full-disk encryption at the
  deployment level.
- The scratch retention sweep
  (`SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE`) is
  operator-scheduled per the existing retention pattern
  (spec 007's `purge_security_events` shape). v1 ships
  the script; the orchestrator does not auto-purge
  in-process.
- Phase 3 declared 2026-05-05 enables but does not gate
  this spec's status flip; the user's call per
  `feedback_dont_declare_phase_done.md`. This spec
  stays scaffold-only until tasks are scheduled.
- Status remains Draft until clarifications resolve and
  the user accepts the scaffolding.
