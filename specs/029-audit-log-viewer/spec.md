# Feature Specification: Human-Readable Audit Log Viewer (Shared Components for 022 + 024)

**Feature Branch**: `029-audit-log-viewer`
**Created**: 2026-05-07
**Status**: Implemented 2026-05-12 (pass 1 shared modules shipped 2026-05-11; pass 2 — viewer endpoint `GET /tools/admin/audit_log`, `audit_log_appended` WS broadcast helper, `AuditLogPanel` + inline `DiffRenderer` + filter controls in `frontend/app.jsx` — closed alongside spec 011 amendment FR-025..FR-029 traceability flip; T050 live-stack smoke and T054 worktree CLAUDE.md remain deferred per the doc-track callouts in `tasks.md`)
**Input**: User description: "Phase 3 human-readable audit log viewer. The admin_audit_log table records every facilitator action, every review-gate edit, every participant lifecycle event, every session-config change. Phase 1 ships the data; Phase 2's Web UI surfaces a summary. Operators currently run debug-export (spec 010) and parse JSON to understand what happened. Adds a live audit-log surface in the Web UI with formatted action labels, side-by-side diffs for review-gate edits, and filtering. Architectural commitment: action-label registry, diff renderer, and time formatter ship as standalone modules that specs 022 (detection event history) and 024 (facilitator scratch) consume rather than reimplement. Without that commitment, three audit-adjacent surfaces drift. With it, 029 ships first and 022/024 inherit the shared components. Applies to topologies 1-6 (orchestrator owns the audit log); incompatible with topology 7. Primary use cases: technical review and audit (§5), consulting (§3)."

## Overview

The orchestrator's `admin_audit_log` table records every meaningful
state change in a session: facilitator approvals, review-gate edits,
participant lifecycle events, session-config changes, security-pipeline
overrides, retention-policy actions. The data model is mature (spec
001 §FR-019, spec 002 §FR-014, spec 007 §FR-005); the data flow is
correct. What's missing is an operator-facing surface that renders
the rows in a form humans can read at session-review time.

A Phase 1+2 shakedown produced an 11-event audit trail across 31
turns; the facilitator reconstructed the sequence by reading raw
JSON from a `/tools/debug/export` (spec 010) response. That works for
diagnosing one session in detail; it does not scale to typical
operator workflows where audit review is part of every engagement
debrief.

This spec defines a **human-readable audit log viewer** as a new Web
UI surface AND a set of shared components that audit-adjacent specs
consume:

1. **Audit log panel.** A new route or modal at
   `/session/:id/audit` (path settled in `/speckit.plan`) renders
   `admin_audit_log` rows for the active session as a formatted
   table: timestamp, actor, action label, target, summary. Reverse-
   chronological order by default. Pagination at
   `SACP_AUDIT_VIEWER_PAGE_SIZE` rows per page (default 50).
2. **Side-by-side diff renderer.** Audit rows whose action is
   `review_gate_edit` (or any action with `previous_value` /
   `new_value` JSON columns) expand into a diff view showing the
   pre-edit content alongside the post-edit content with line-level
   differences highlighted. The renderer handles three formats:
   `json` (structured), `text` (plain), and `auto` (inspect the
   value type).
3. **Filter axes.** Actor (facilitator id or participant id),
   action type (any of the registered action labels), and time
   range. Filters apply client-side once the page-size of rows is
   loaded; server-side filter pushdown is a future enhancement.
4. **Live updates.** When a new `admin_audit_log` row is written
   for the active session, the viewer panel updates via WebSocket
   push within 2s — the same pattern spec 022 uses for detection
   events.

The architectural commitment that makes this spec earn its slot is
the **shared-component contract**:

- **Action-label registry** — a paired backend Python module
  (`src/orchestrator/audit_labels.py`) and frontend JS module
  (`frontend/audit_labels.js`) mapping audit action
  strings to human-readable labels. The backend module is the
  source of truth; the API returns formatted labels in responses;
  the frontend mirror handles client-side rendering of new actions
  before page reload. A CI gate enforces parity between the two
  modules — every backend label has a frontend mirror, no drift.
- **Diff renderer** — a single React component (inline
  `DiffRenderer` in `frontend/app.jsx` plus pure-logic helpers in
  `frontend/diff_engine.js`) accepting
  `(previousValue, newValue, format)` props. Frontend-only; the
  backend supplies the raw values from `admin_audit_log.previous_value`
  and `new_value`.
- **Time formatter** — paired backend Python utility
  (`src/orchestrator/time_format.py`) and frontend JS utility
  (`frontend/time_format.js`) for consistent timestamp
  rendering across audit-related surfaces. Backend-formatted
  timestamps appear in API responses; frontend-formatted timestamps
  appear when rendering live-pushed events that haven't been
  through the API yet.

Specs 022 (detection-event-history) and 024 (facilitator-scratch /
review-gate sub-panel) **consume** these components rather than
reimplementing them. Without that commitment, three audit-adjacent
surfaces would drift: three action-label vocabularies, three diff
renderers, three time formats. This spec ships the components
first; 022's and 024's panels integrate them when those specs reach
implementation.

This spec **scaffolds only**. Implementation begins when the
facilitator schedules tasks per Constitution §14.1. The Phase 3
declaration recorded 2026-05-05 satisfies the phase gate. This spec
ships AHEAD of 022 + 024 in the implementation sequence so the
shared components exist before downstream specs need them.

## Clarifications

### Initial draft assumptions requiring confirmation

- **Action-label registry parity gate.** Resolved 2026-05-07
  (Session below): hard CI gate. `scripts/check_audit_label_parity.py`
  runs as a required CI step; any missing or divergent key between
  the backend `LABELS` dict and the frontend `LABELS` map fails the
  build with a clear error naming the missing/divergent key. No
  warning-only mode, no runtime fallback. Build override is not
  supported.
- **Diff renderer engine.** Resolved 2026-05-08 (Session
  below): Myers line-by-line as default; word-level exposed
  as a per-row UI toggle inside the expanded row, computed
  lazily on toggle click. The same Myers library handles
  both modes (no second engine). Spec 024 FR-014 inherits
  the engine + toggle by importing the DiffRenderer module.
- **Diff size handling.** Resolved 2026-05-07 (Session below):
  thresholds are locked constants in the DiffRenderer module —
  ≤ 50KB main thread; 50KB-500KB Web Worker; > 500KB raw display.
  No per-call override, no env-var tuning. Spec 024 FR-014
  inherits the same numbers by importing the module. Future
  threshold changes require updating 029's module and propagate
  to all consumers.
- **Filter shape.** Resolved 2026-05-07 (Session below):
  client-side filtering on the loaded page (default 50 rows) at
  v1. Server-side filter pushdown is a future enhancement
  (Phase 3+). FR-013's badge counter mitigates the page-scope
  limitation by surfacing filter-hidden new events.
- **Time formatter format string.** Resolved 2026-05-07 (Session
  below): UTC-primary with locale-conversion hover. Primary
  display renders ISO-8601 in UTC with an explicit `Z` timezone
  marker; on hover, the formatter shows the same instant
  converted to the browser's locale AND a relative-time string
  ("3 minutes ago"). No env-var tuning. Forensic-default by
  intent: audit data is stored UTC, displayed UTC, with locale
  as a convenience overlay rather than primary.
- **Action-label localization.** Resolved 2026-05-11 (Session
  below): confirmed English-only v1. The label format
  ("Facilitator removed Haiku") is a single English string per
  action. i18n is a future enhancement that would need a
  per-action label-set + locale-resolution layer; introducing
  it requires a separate spec amendment triggered by a
  localization use case.
- **Sensitive-value scrubbing in the panel.** Resolved 2026-05-07
  (Session below): per-action boolean flag. The backend label
  registry's entry MAY include `scrub_value: bool`; when true,
  both `previous_value` and `new_value` render as `[scrubbed]` in
  the viewer. Full content remains available only via spec 010
  debug-export (separate authorization, separate audit trail).
  Granularity may be tightened later (e.g., per-field list) in a
  backward-compatible way without breaking consumers.
- **Sequence ordering when 029 lands ahead of 022 + 024.**
  Resolved 2026-05-08 (Session below): 029 ships its modules
  as registered components; FR-text amendments to 022 and 024
  are deferred to those specs' implementation times. To pin
  the integration surface NOW so downstream specs can plan
  against a stable contract, 029 ships
  `contracts/shared-module-contracts.md` alongside its plan
  documenting module paths, public signatures, prop interfaces,
  and threshold constants. Specs 022 and 024 cite the contract
  doc when they amend. FR-019 references the contract as the
  integration anchor.
- **WS event name and payload.** Resolved 2026-05-08
  (Session below): name is `audit_log_appended`; payload
  matches the FR-001 endpoint row shape verbatim (`id,
  timestamp, actor_id, actor_display_name, action,
  action_label, target_id, target_display_name,
  previous_value, new_value, summary` — the latter two
  already server-scrubbed when applicable per FR-014).
  Same naming convention as spec 022's `detection_event`.
- **Phase 1+2 shakedown reference.** Paraphrased without test
  session IDs per the established pattern. Confirm the
  paraphrase is acceptable.

### Session 2026-05-11

- Q: Spec 029 status — tasks.md shows 53/55 checked while Status reads "Draft, scaffold ships now, implementation deferred"; which state reflects ship reality? → A: Implementation pass 1 saturated. The shared-module foundation (`audit_labels.py` + `audit_labels.js` + `diff_engine.js` + `time_format.py` + `time_format.js` + parity gate) shipped to unblock spec 022's consumption; the audit log viewer endpoint (FR-001) + SPA panel (US1, US2, US3) is implementation-deferred to pass 2. The 53 checked tasks are the shared-module subset. Status text updated to reflect the two-track reality; full Implemented flip awaits pass 2 + viewer-panel shakedown.
- Q: Action-label localization — confirm English-only v1 (closes the [NEEDS CLARIFICATION] marker open since Session 2026-05-07)? → A: Confirmed English-only v1. FR-006 already commits to "the human-readable English label"; the shipped `audit_labels.py` + `audit_labels.js` + parity gate + spec 022's mirror module all assume English-only. i18n is a future enhancement requiring a separate spec amendment triggered by a localization use case; the current registry shape (`dict[str, dict[str, Any]]`) does not anticipate per-locale label sets. The initial-draft-assumptions block updated to "Resolved 2026-05-11".

### Session 2026-05-09

- Path corrections from implementation-time alignment with the
  established `frontend_polish_module_pattern` (UMD modules at
  `frontend/*.js` loaded ahead of `frontend/app.jsx`). The
  early draft cited `src/web_ui/static/...` paths that do not
  exist in this repo; the actual landed paths are:
  - `frontend/audit_labels.js` → `frontend/audit_labels.js`
  - `src/web_ui/static/components/DiffRenderer.tsx` → inline
    component in `frontend/app.jsx` plus pure-logic helpers in
    `frontend/diff_engine.js`
  - `frontend/time_format.js` → `frontend/time_format.js`
  These corrections cascade through Overview, FR-006, FR-008,
  FR-009, the User Story 4 acceptance scenarios, and the spec
  011 amendment FR-028. The shared-module contract document
  (`contracts/shared-module-contracts.md`) was authored against
  the corrected paths from the start.

### Session 2026-05-08

- Q: WebSocket event broadcast scope (FR-010) — facilitator-only role-filter, all-participants with full payload, all-participants with redacted payload, or defer to `/speckit.plan`? → A: Facilitator-only role-filter via `broadcast_to_session_roles(session_id, roles=["facilitator"], ...)`. Mirrors spec 011 SR-010 pattern; closes the WS leak that would otherwise contradict FR-002's facilitator-only HTTP access guarantee. Non-facilitator participants never receive `audit_log_appended` payloads.
- Q: Diff renderer engine (FR-008) — Myers line-only, Myers with word-level UI toggle, Myers with word-level prop, Patience, or defer? → A: Myers line-by-line as default, word-level exposed as a per-row UI toggle inside the expanded row. Word-level is computed lazily on toggle click; same library handles both modes. Spec 024 FR-014 inherits the same engine + toggle when it imports the module.
- Q: Action-label registry shape (FR-006 vs. FR-014) — `dict[str, str]` plus separate `SCRUB_ACTIONS` set, `dict[str, dict[str, Any]]` with embedded flags, dataclass-typed entries, or defer? → A: `dict[str, dict[str, Any]]` where each entry is `{"label": str, "scrub_value": bool}` (default `False`). Parity gate checks key-set + label parity across backend / frontend modules; `scrub_value` is backend-only (frontend renders `[scrubbed]` from server-pushed payload, not from the flag). Resolves the FR-006/FR-014 contradiction; future flags slot in without breaking the parity check.
- Q: WS event name + payload shape (FR-010) — name `audit_log_appended` confirmed; raw row vs. decorated row vs. notify-only vs. namespaced name vs. defer? → A: Name is `audit_log_appended`. Payload matches the FR-001 endpoint row shape verbatim — includes `id, timestamp, actor_id, actor_display_name, action, action_label, target_id, target_display_name, previous_value, new_value, summary` (with `previous_value` / `new_value` already replaced by `"[scrubbed]"` server-side when the action's `scrub_value` flag is true, per FR-014). The server pays the decoration cost once; the SPA renders WS-pushed rows through the same code path as API-fetched rows; including `id` lets the client deduplicate against an in-flight HTTP refetch.
- Q: 022 / 024 amendment timing (FR-019) — pre-write amendments now, defer with shared-contract doc, defer with no contract, both, or defer to plan? → A: Defer FR-text amendments to 022 / 024 implementation time; ship a `contracts/shared-module-contracts.md` document NOW alongside 029's plan that pins module paths, public signatures, prop interfaces, and threshold constants. Specs 022 and 024 cite the contract when they amend. FR-019 references the contract doc as the integration anchor; FR-020's architectural test verifies no parallel audit-action-to-label mapping exists outside 029's module.

### Session 2026-05-07

- Q: Action-label registry parity gate (FR-006) — how strictly is parity enforced between the backend Python `LABELS` dict and the frontend JS `LABELS` map? → A: Hard CI gate. `scripts/check_audit_label_parity.py` runs as a required step; missing or divergent keys fail the build with a clear error. No warning-only mode and no override.
- Q: Diff renderer size thresholds (FR-008) — match spec 024 FR-014's 50KB / 500KB exactly, or tune independently? → A: Locked module constants — 50KB / 500KB ship as constants in the DiffRenderer module with no per-call or env-var override. Spec 024 inherits them by importing; future changes propagate to all consumers.
- Q: Sensitive-value scrubbing shape (FR-014) — per-action boolean flag, per-action field list, central allow-list, or trust the facilitator-only access boundary? → A: Per-action boolean flag on registry entries (`scrub_value: bool`); when true, `previous_value` and `new_value` render as `[scrubbed]`. Full content via spec 010 debug-export only. Tightening to per-field granularity remains a backward-compatible future option.
- Q: Time formatter primary format (FR-009) — locale-primary with UTC hover, UTC-primary with locale hover, env-var tunable, or both side-by-side? → A: UTC-primary with locale + relative-time on hover. Audit data is stored UTC and displayed UTC by default; locale is a convenience overlay, not the primary. No env-var tuning.
- Q: Filter scope (FR-012) — client-side page-scoped, server-side pushdown at v1, hybrid, or no filtering at v1? → A: Client-side, page-scoped at v1 (default 50 rows). Server-side pushdown is a Phase 3+ enhancement. FR-013's badge counter alerts operators when filters hide WS-pushed events.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Facilitator opens the audit log viewer and sees a formatted table of all admin_audit_log entries for the current session in reverse-chronological order (Priority: P1)

A facilitator running a 31-turn engagement opens the audit log
viewer from the session header. The viewer renders a table with
columns: timestamp (UTC ISO-8601 with `Z` marker; locale-converted
time and relative-time appear on hover), actor
(human-readable name from the participants table when available,
otherwise the participant id), action label (e.g.,
"Facilitator removed Haiku" rather than `remove_participant`),
target (the affected participant or session attribute), summary
(a one-line description for actions that don't fit the
actor-verb-target shape). The 11 audit events from the engagement
appear in reverse-chronological order. Pagination shows
`SACP_AUDIT_VIEWER_PAGE_SIZE` rows per page (default 50). The
facilitator scans the list; the action labels make the sequence
readable without expanding any row.

**Why this priority**: P1 because this is the spec's primary
value. Without the formatted table, operators stay on raw JSON.
The reverse-chronological default + readable labels are what
turn the existing data into a usable diagnostic surface.

**Independent Test**: Drive a session that produces at least 5
audit events of varying actions
(`add_participant`, `review_gate_approve`, `remove_participant`,
`pause_loop`, `start_loop`). Open the audit log viewer. Assert
the response contains 5 rows with timestamps in reverse-
chronological order. Assert each row's `action_label` field is
a human-readable English string from the registry. Assert the
actor is rendered as a participant display name (not a UUID)
when one is available. Assert pagination metadata is present
(total count, current page, has-next-page indicator).

**Acceptance Scenarios**:

1. **Given** a session with N audit events, **When** the
   facilitator opens the viewer, **Then** the response MUST
   include up to `SACP_AUDIT_VIEWER_PAGE_SIZE` rows ordered by
   timestamp DESC AND each row MUST have a non-empty
   `action_label` string from the registry.
2. **Given** an audit row whose actor matches a participant in
   the session, **When** the row renders, **Then** the actor
   field MUST display the participant's `display_name` (not the
   raw UUID).
3. **Given** an audit row whose actor is the orchestrator (no
   participant id), **When** the row renders, **Then** the
   actor field MUST display `Orchestrator` (or the configured
   system-actor label).
4. **Given** more than `SACP_AUDIT_VIEWER_PAGE_SIZE` audit rows
   exist, **When** the viewer fetches without pagination params,
   **Then** the response MUST include the first page AND a
   `next_offset` indicator.
5. **Given** an authenticated NON-facilitator participant
   attempts to call the viewer endpoint, **When** the request
   fires, **Then** HTTP 403 MUST be returned (mirrors spec 010
   §FR-2 facilitator-only access).
6. **Given** `SACP_AUDIT_VIEWER_ENABLED=false`, **When** any
   client attempts to open the viewer, **Then** HTTP 404 MUST
   be returned (master switch gates the surface).
7. **Given** a row whose action carries the `scrub_value=True`
   flag, **When** the row renders, **Then** the value fields
   MUST display `[scrubbed]` AND the full content MUST be
   available only via spec 010 debug-export.

---

### User Story 2 - review_gate_edit entries render a side-by-side diff for previous_value vs new_value when expanded; diffs handle JSON, text, and structured content types (Priority: P1)

The facilitator clicks the expand affordance on a
`review_gate_edit` row. The DiffRenderer component receives
`previousValue=<original AI draft>`, `newValue=<facilitator-edited
content>`, `format='auto'`. The renderer inspects the values:
both are plain text, so it falls back to a line-by-line Myers
diff with side-by-side rendering. The original draft appears
in the left pane; the edited version on the right; line-level
differences are highlighted. The facilitator visually compares
the changes the facilitator made.

For a `session_config_change` row whose values are JSON, the same
expand action triggers the renderer with `format='auto'`; the
renderer detects JSON, parses both sides, and renders a structured
diff that highlights key-by-key differences. Operators reviewing
config history see exactly what changed in each setting.

**Why this priority**: P1 because the diff is the second half of
the spec's primary value. Reading "previous: <500 chars>, new:
<500 chars>" in the audit log is operationally useless. The
side-by-side diff renderer turns the raw values into a
diagnostic surface at the same zoom level as a code review.

**Independent Test**: Drive a session that produces a
`review_gate_edit` event with text values AND a
`session_config_change` event with JSON values. Open the audit
viewer; click expand on each row. Assert the DiffRenderer
component receives the correct props. Assert text values render
with line-by-line diff. Assert JSON values render with
structured key-by-key diff. Assert a 50KB+ diff payload renders
in a Web Worker. Assert a 500KB+ payload displays raw values
without diff.

**Acceptance Scenarios**:

1. **Given** a `review_gate_edit` row with text values, **When**
   the facilitator clicks expand, **Then** the DiffRenderer
   MUST receive `format='auto'` AND render a line-by-line diff
   with original on left, edited on right.
2. **Given** an audit row with JSON values, **When** the
   facilitator clicks expand, **Then** the DiffRenderer MUST
   detect JSON via `format='auto'` AND render a structured
   key-by-key diff.
3. **Given** a diff payload below 50KB, **When** the renderer
   runs, **Then** it MUST complete on the main thread without
   perceptible UI block (P95 ≤ 100ms).
4. **Given** a diff payload between 50KB and 500KB, **When**
   the renderer runs, **Then** it MUST compute in a Web Worker
   AND display a "computing diff" state.
5. **Given** a diff payload above 500KB, **When** the renderer
   runs, **Then** it MUST display the raw values WITHOUT a
   computed diff, with an explanation about the size limit.
6. **Given** an audit row whose action does NOT have
   previous/new value columns (e.g., `add_participant`),
   **When** the row is expanded, **Then** the expansion MUST
   show the row's metadata (timestamp, actor, target, full
   action text) without invoking the DiffRenderer.

---

### User Story 3 - Facilitator filters audit rows by actor, action type, and time range (Priority: P2)

The facilitator wants to see only `review_gate_edit` entries
from a specific participant in the last hour. They open the
filter controls in the viewer header and select:
- Actor: that participant id (or display name)
- Action type: `review_gate_edit` (selected from a dropdown of
  registered action labels)
- Time range: last 1 hour

The viewer applies the filter client-side to the loaded page
of rows. The displayed set narrows to matching entries. The
facilitator can clear individual filter axes or reset all.

**Why this priority**: P2 because filter-by-axis is a
nice-to-have for sessions with many audit events. Most
sessions have small enough audit logs that the unfiltered
table is readable; for high-event sessions (long engagements,
many participants, many config changes), filtering matters.
P2 because the page-scoped filter is a v1 limitation —
filtering across all rows requires server-side pushdown which
is a future enhancement.

**Independent Test**: Open the viewer for a session with mixed
audit events. Select a single action-type filter; assert only
rows of that type display. Clear; select an actor filter;
assert only that actor's rows display. Combine actor + action
type; assert the intersection. Add a time range; assert rows
outside the range are hidden.

**Acceptance Scenarios**:

1. **Given** a loaded page of audit rows, **When** the
   facilitator selects a single action-type filter, **Then**
   only rows whose action matches MUST display.
2. **Given** an active actor filter, **When** new rows arrive
   via WS push, **Then** the filtered view MUST update only
   when the new row matches the filter.
3. **Given** an active filter AND new rows that do NOT match,
   **When** the rows arrive via WS push, **Then** the
   filtered view MUST NOT update for them; the unfiltered
   count badge on the filter control MUST increment so the
   operator sees there are more events outside the current
   filter.
4. **Given** an active time-range filter, **When** the
   facilitator changes the range to a wider window, **Then**
   additional matching rows MUST appear (subject to the
   page-scope limitation — rows outside the loaded page do
   not appear without a server-side fetch).
5. **Given** all filters are cleared, **When** the operator
   clicks "Clear filters", **Then** the full loaded page
   MUST display.

---

### User Story 4 - Action-label registry, diff renderer, and time formatter are exposed as reusable modules; specs 022 and 024 consume them (Priority: P3)

Spec 022 (detection event history) and spec 024 (facilitator
scratch / review-gate sub-panel) need the same audit-adjacent
rendering capabilities. Spec 029 ships the action-label
registry, diff renderer, and time formatter as standalone
modules. When 022 and 024 implement, they import these modules
rather than reimplementing them. The CI parity gate ensures
the action-label registry stays consistent between backend and
frontend; future audit actions added by any spec must update
both.

**Why this priority**: P3 because module exposure IS the
spec's architectural commitment but doesn't ship behavior
on its own — it pays off when 022 and 024 implement. Without
this user story, spec 029 would just be the audit panel; with
it, spec 029 becomes the foundation that 022 and 024 build on.

**Independent Test**: Architectural test: assert
`src/orchestrator/audit_labels.py` exists and exports a
`LABELS` dict. Assert
`frontend/audit_labels.js` exists and exports a
`LABELS` map. Run the parity gate (`scripts/check_audit_label_parity.py`)
and assert it passes. Assert
`frontend/app.jsx` defines the inline `DiffRenderer` component
and `frontend/diff_engine.js` exports the locked threshold
constants with the documented props signature. Assert
`src/orchestrator/time_format.py` and
`frontend/time_format.js` both exist with mirroring
public APIs.

**Acceptance Scenarios**:

1. **Given** the spec is implemented, **When** the
   `src/orchestrator/audit_labels.py` module is imported,
   **Then** it MUST export a `LABELS: dict[str, dict[str,
   Any]]` mapping from action strings to entries containing
   `label: str` (and optionally `scrub_value: bool`) per
   FR-006.
2. **Given** the spec is implemented, **When** the
   `frontend/audit_labels.js` module is loaded by
   the SPA, **Then** it MUST export a `LABELS` object with
   the same keys as the Python module AND each entry's
   `label` field MUST match exactly (parity enforced by CI
   gate per FR-006; `scrub_value` is backend-only).
3. **Given** the parity gate runs in CI, **When** the
   backend module gains a new action without a frontend
   mirror, **Then** the build MUST fail with a clear error
   naming the missing key.
4. **Given** the DiffRenderer component is imported by spec
   024's review-gate sub-panel, **When** spec 024 renders a
   review-gate diff, **Then** the same renderer instance
   MUST handle the props with the same threshold semantics
   (FR-008).
5. **Given** the time formatter is imported by spec 022's
   detection-event panel, **When** spec 022 renders a
   detection event timestamp, **Then** the same formatter
   MUST produce the same display as spec 029's audit
   panel for the same timestamp value.

---

### Edge Cases

- **Audit row whose action string is not in the registry.**
  The viewer falls back to displaying the raw action string
  (e.g., `unknown_action: <raw_string>`). A WARN-level log
  entry alerts operators that an unregistered action was
  emitted. The spec's CI gate enforces parity going forward;
  unregistered actions indicate a missed registry update on
  some other spec.
- **WS push for an audit event arrives while the panel is
  closed.** The next time the panel opens, it fetches the
  current state via the standard endpoint; missed pushes are
  not lost because the audit log is the durable source of
  truth.
- **Audit row's `previous_value` is null** (e.g., the first
  setting of a config field). The DiffRenderer receives null
  for `previousValue`; it renders the new value alone with a
  "first set" indicator instead of attempting a diff against
  null.
- **Audit row's action label changes between sessions** (an
  operator updates the registry mid-deployment). The next
  panel load receives the new label; existing rendered rows
  re-render on next refresh. No retroactive rewrite of
  audit-log content.
- **Audit log retention sweep occurs while the panel is
  open.** Rows that were visible may be purged. The next WS
  push or fetch reflects the purged state; the panel does
  not retain visibility of purged rows beyond the current
  render. Operators see "row purged" indicators where they
  expected content if they were mid-review when the sweep
  ran.
- **Sensitive-value scrubbing on a row whose values are
  needed for diagnostic review.** The viewer always shows
  the scrubbed placeholder; operators with debug authorization
  use spec 010 debug-export to retrieve the raw values
  (separate authorization, separate audit trail).
- **Timezone change mid-session** (operator's browser
  timezone updates). Existing rendered timestamps stay in the
  rendered timezone until next render; new rows render in the
  current timezone.
- **Deleted participant referenced as actor or target.** The
  participant lookup returns null; the row displays the
  participant id with a "(deleted)" indicator so the audit
  trail remains forensically complete.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A new endpoint `GET
  /tools/admin/audit_log?session_id=<id>` MUST return the
  `admin_audit_log` rows for the active session in reverse-
  chronological order. The response MUST include columns:
  id, timestamp, actor_id, actor_display_name, action,
  action_label, target_id, target_display_name,
  previous_value, new_value, summary.
- **FR-002**: The endpoint MUST be facilitator-only (mirrors
  spec 010 §FR-2). Non-facilitator callers MUST receive
  HTTP 403.
- **FR-003**: The endpoint MUST be session-bound — a
  facilitator from session A cannot read session B's audit
  log (mirrors spec 010 §FR-3).
- **FR-004**: The endpoint MUST be read-only — no INSERT,
  UPDATE, or DELETE on any source row occurs as a side
  effect (mirrors spec 010 §FR-6).
- **FR-005**: Pagination MUST be offset-based with
  `SACP_AUDIT_VIEWER_PAGE_SIZE` rows per page (default 50).
  The response MUST include `next_offset` and
  `total_count` metadata.
- **FR-006**: An action-label registry MUST exist as paired
  modules: backend Python (`src/orchestrator/audit_labels.py`)
  and frontend JS (`frontend/audit_labels.js`). The
  backend module is the source of truth. The registry shape
  MUST be `dict[str, dict[str, Any]]` keyed by action string;
  each entry MUST contain `label: str` (the human-readable
  English label) and MAY contain `scrub_value: bool` (default
  `False`, backend-only — see FR-014). The frontend module
  exports the same shape minus `scrub_value`, which is not
  needed client-side because the API renders `[scrubbed]`
  server-side per FR-014. A CI gate
  (`scripts/check_audit_label_parity.py`) MUST enforce
  parity — every backend key MUST have a frontend mirror,
  and the `label` field MUST match exactly across the two
  modules. Build fails on drift.
- **FR-007**: API responses MUST include `action_label`
  (the human-readable label from the registry) alongside
  the raw `action` string. Clients render the label;
  operators searching for raw action strings can still find
  them.
- **FR-008**: A diff renderer component MUST exist as an
  inline `DiffRenderer` React component in `frontend/app.jsx`
  with pure-logic helpers in `frontend/diff_engine.js` (UMD,
  loaded ahead of `app.jsx` per `frontend_polish_module_pattern`),
  accepting `(previousValue, newValue, format)` props.
  Format values: `json` | `text` | `auto`. Diff engine MUST
  be Myers line-by-line as the default mode; the component
  MUST expose a per-row word-level toggle inside the
  expanded row that, on click, lazily recomputes the diff
  at word granularity using the same Myers library (no
  second engine, no `mode` prop on the component API).
  The renderer MUST ship size thresholds as locked module
  constants (≤ 50KB main thread; 50KB-500KB Web Worker;
  > 500KB raw display) with no per-call override and no
  env-var tuning. Spec 024 FR-014 inherits engine, mode
  toggle, and thresholds by importing the module; the
  values match exactly.
- **FR-009**: A time formatter MUST exist as paired modules:
  backend Python (`src/orchestrator/time_format.py`) and
  frontend JS (`frontend/time_format.js`). The two
  modules MUST produce identical output for the same input
  timestamp; a CI gate
  (`scripts/check_time_format_parity.py`) enforces this. The
  primary rendered format MUST be UTC ISO-8601 with an explicit
  `Z` timezone marker; the frontend module MUST additionally
  expose a hover/secondary format that converts the same instant
  to the browser's locale AND a relative-time string ("3 minutes
  ago"). No env-var tuning of the primary format.
- **FR-010**: The viewer MUST update via WebSocket push
  when a new `admin_audit_log` row is written for the
  active session. The WS event name MUST be
  `audit_log_appended`. The payload MUST match the FR-001
  endpoint's per-row shape verbatim — `{id, timestamp,
  actor_id, actor_display_name, action, action_label,
  target_id, target_display_name, previous_value, new_value,
  summary}` — with `previous_value` / `new_value` already
  replaced by `"[scrubbed]"` server-side when the action's
  `scrub_value` flag is true (per FR-014). The event MUST
  be role-filtered — broadcast only to facilitator
  subscribers via `broadcast_to_session_roles(session_id,
  roles=["facilitator"], ...)` (mirrors spec 011 SR-010);
  non-facilitator participants never receive the event
  payload. Update propagation P95 ≤ 2s from row write to
  facilitator-client render (matches spec 022 SC-002).
  The SPA MUST render WS-pushed rows through the same
  code path as API-fetched rows, deduplicating by `id`
  against any in-flight HTTP refetch.
- **FR-011**: Filtering MUST support three axes:
  - Actor (facilitator id, participant id, or `Orchestrator`)
  - Action type (any of the registered action labels)
  - Time range (start + end timestamps)
- **FR-012**: Filters MUST apply client-side to the loaded
  page of rows in v1. Server-side filter pushdown is a
  future enhancement.
- **FR-013**: A filter-control badge MUST display the count
  of unfiltered events that arrived via WS push but did not
  match the active filter, so operators see when filters
  are hiding new activity.
- **FR-014**: Action-label registry entries MAY include a
  `scrub_value: bool` flag (per FR-006's `dict[str,
  dict[str, Any]]` shape). When the flag is true on an
  action, the FR-001 endpoint MUST replace `previous_value`
  and `new_value` with the literal string `"[scrubbed]"` in
  the response payload BEFORE shipping; the SPA renders the
  scrubbed string verbatim with no client-side decision.
  The raw values remain available via spec 010 debug-export
  (separate authorization, separate audit trail). The
  scrubbing decision is server-side so non-facilitator
  defenses do not depend on a client honoring the flag.
- **FR-015**: When the action string in a row is not in
  the registry (drift between deployment and registry), the
  viewer MUST display `[unregistered: <raw_action>]` AND
  emit a WARN-level orchestrator log entry naming the
  missing action.
- **FR-016**: The `SACP_AUDIT_VIEWER_RETENTION_DAYS` env
  var MUST cap viewer-side display retention. Rows older
  than the cap are excluded from the viewer's query (but
  remain in the underlying `admin_audit_log` subject to its
  own retention sweep). Default empty (no cap; show all
  rows).
- **FR-017**: The three new env vars
  (`SACP_AUDIT_VIEWER_ENABLED`,
  `SACP_AUDIT_VIEWER_PAGE_SIZE`,
  `SACP_AUDIT_VIEWER_RETENTION_DAYS`) MUST have validator
  functions in `src/config/validators.py` registered in
  the `VALIDATORS` tuple, AND corresponding sections in
  `docs/env-vars.md` with the six standard fields, BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable
  gate).
- **FR-018**: When `SACP_AUDIT_VIEWER_ENABLED=false`, the
  viewer endpoint MUST return HTTP 404 AND the SPA MUST
  NOT render the entry-point affordance.
- **FR-019**: Specs 022 and 024 amendments MUST land
  alongside their respective implementations to add FRs
  that consume the action-label registry, diff renderer,
  and time formatter from spec 029. To pin the integration
  surface NOW so 022 and 024 can plan against a stable
  contract, spec 029 MUST ship
  `specs/029-audit-log-viewer/contracts/shared-module-contracts.md`
  alongside its `/speckit.plan` output. The contract MUST
  document module paths, public signatures, prop interfaces,
  and the locked threshold constants from FR-008. Specs 022
  and 024 cite this contract when they amend. Without the
  contract document, the amendments risk drift from spec
  029's shared components.
- **FR-020**: An architectural test MUST assert no spec
  outside 029 reimplements an audit-action-to-label
  mapping. CI fails if 022 or 024 (or any future spec)
  ships a parallel mapping.

### Key Entities

- **AuditLogEntry** (read-side projection) — a row from
  `admin_audit_log` decorated with the action label, actor
  display name, and target display name. Computed via JOINs
  in the FR-001 query.
- **AuditLabelRegistry** (paired backend+frontend) — the
  module pair mapping action strings to labels (FR-006).
- **DiffRenderer** (React component) — frontend-only diff
  visualization (FR-008).
- **TimeFormatter** (paired backend+frontend) — module pair
  for timestamp rendering (FR-009).
- **AuditLogAppendedEvent** (WS event) — broadcast on every
  new `admin_audit_log` row for the active session
  (FR-010).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The audit log viewer MUST render a session's
  audit events in reverse-chronological order with
  human-readable labels. Verified by an end-to-end test
  driving 5+ audit events and asserting the table render.
- **SC-002**: Action-label registry parity between backend
  and frontend MUST be enforced by CI. Verified by a test
  that adds a backend label without a frontend mirror and
  asserts the build fails.
- **SC-003**: A `review_gate_edit` row MUST render a
  side-by-side diff when expanded. Verified by an
  integration test driving the edit + expand + assertion
  on the rendered diff.
- **SC-004**: New audit events MUST appear in the panel
  via WS push within 2s. Verified by a multi-client test
  asserting the propagation latency.
- **SC-005**: Filter-by-action-type MUST narrow the
  displayed set client-side without a server round-trip.
  Verified by inspecting the network panel during filter
  toggles.
- **SC-006**: Spec 022's detection-event panel MUST be
  able to import the action-label registry and time
  formatter from spec 029's modules without modification.
  Verified post-022-implementation by a test asserting
  spec 022's module imports.
- **SC-007**: Spec 024's review-gate diff sub-panel MUST
  be able to import the DiffRenderer from spec 029's
  module. Verified post-024-implementation similarly.
- **SC-008**: An architectural test MUST assert no spec
  outside 029 reimplements the audit-action-to-label
  mapping (FR-020). CI fails if 022, 024, or any future
  spec ships a parallel mapping.
- **SC-009**: The viewer MUST be facilitator-only.
  Verified by a test driving the endpoint with a
  non-facilitator session and asserting HTTP 403.
- **SC-010**: With any of the three new env vars set to
  an invalid value, the orchestrator process MUST exit
  at startup with a clear error message naming the
  offending var (V16 fail-closed gate observed in CI).
- **SC-011**: Diff renderer threshold behavior (50KB main
  thread; 50KB-500KB Worker; >500KB raw) MUST match spec
  024 FR-014 exactly. Verified by a perf test driving
  payloads at each threshold.
- **SC-012**: Sensitive-value scrubbing MUST apply where
  the registry sets `scrub_value=True`. Verified by a
  test driving a token-rotate audit event and asserting
  the panel displays `[scrubbed]` while spec 010
  debug-export returns the full content.

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** (orchestrator-driven
topologies). The audit log is centralized at the orchestrator;
the viewer reads from the orchestrator's database; WS push
broadcasts come from the orchestrator's per-session subscriber
set. All require a single orchestrator to be the audit-log
authority.

This feature is **NOT applicable to topology 7 (MCP-to-MCP,
Phase 3+)**. In topology 7 each participant's MCP client is its
own audit boundary; there is no orchestrator-side `admin_audit_log`
to render. Per V12: any topology-7 deployment MUST recognize that
this spec's viewer does not apply.

### V13 — Use Case Coverage

This feature serves the V13 primary use cases:

- §5 Technical Review and Audit
  (`docs/sacp-use-cases.md` §5) — the audit log IS the
  deliverable for review/audit engagements. The viewer is the
  primary consumption surface; the diff renderer makes
  facilitator-edit history forensically inspectable.
- §3 Consulting Engagement
  (`docs/sacp-use-cases.md` §3) — post-engagement audit review
  is part of the consulting work product. The viewer
  collapses the manual JSON-parsing step into an in-UI flow.

Other use cases (§1, §2, §4, §6, §7) inherit the feature when
operators opt in but are not the priority drivers.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts.
This spec contributes four budgets:

- **Panel load (initial fetch)**: P95 ≤ 500ms for sessions
  with up to 1,000 audit events. The query is a bounded
  read on `admin_audit_log` filtered by `session_id` (indexed)
  plus participant-display-name JOINs. Pagination at 50/page.
- **WS push latency on audit append**: P95 ≤ 2s from
  `admin_audit_log` INSERT to client-rendered row. Mirrors
  spec 022 SC-002.
- **Diff renderer (≤ 50KB)**: P95 ≤ 100ms on the main
  thread. Above 50KB diffs MUST run in a Web Worker;
  above 500KB diffs MUST display raw without diff (matches
  spec 024 FR-014 exactly).
- **Filter application**: O(N) over the loaded page of
  rows where N ≤ page_size (default 50). Client-side; no
  server round-trip.

## Configuration (V16) — New Env Vars

Three new env vars are introduced. Each MUST have type, valid
range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this
spec (per V16 deliverable gate).

### `SACP_AUDIT_VIEWER_ENABLED`

- **Intended type**: boolean
- **Intended valid range**: `true` | `false`. Default
  `false` (master switch ships off; operators opt in).
- **Fail-closed semantics**: any non-parseable value MUST
  cause startup exit. When `false`, the viewer endpoint
  returns HTTP 404 and the SPA hides the entry-point.

### `SACP_AUDIT_VIEWER_PAGE_SIZE`

- **Intended type**: positive integer
- **Intended valid range**: `[10, 500]`. Default `50`.
  Below 10 produces excessive pagination friction; above
  500 risks slow panel loads on busy sessions.
- **Fail-closed semantics**: outside the range MUST cause
  startup exit.

### `SACP_AUDIT_VIEWER_RETENTION_DAYS`

- **Intended type**: positive integer, or empty for
  no cap
- **Intended valid range**: `[1, 36500]` when set; empty
  means no cap (show all rows). Default empty (matches the
  general retention posture in `docs/retention.md` §7).
- **Fail-closed semantics**: any non-integer or
  non-positive value MUST cause startup exit. The cap
  applies to viewer-side display ONLY — underlying
  `admin_audit_log` rows beyond the cap remain queryable
  via spec 010 debug-export AND are subject to their own
  retention sweep.

## Cross-References to Existing Specs and Design Docs

- **Spec 002 (participant-auth) §FR-014** — the
  `admin_audit_log` table schema. Spec 029 reads but does
  not modify the schema.
- **Spec 010 (debug-export)** — same data source. Spec 010
  exports `admin_audit_log` as part of its JSON payload;
  spec 029 surfaces the same data in a live UI. The two
  specs are complementary: 010 is a forensic-export
  surface; 029 is a live-review surface.
- **Spec 011 (web-ui)** — integration point. Spec 011
  already references the facilitator audit log in
  FR-016; spec 029 is the full implementation. A spec 011
  amendment lands when 029's tasks are scheduled.
- **Spec 022 (detection-event-history)** — consumes the
  action-label registry, diff renderer, and time formatter
  from spec 029. Spec 022's amendment lands at 022's
  implementation time.
- **Spec 024 (facilitator-scratch)** — the review-gate
  history sub-panel consumes the diff renderer from spec
  029. Spec 024's amendment lands at 024's implementation
  time.
- **Spec 001 (core-data-model) §FR-008, §FR-019** —
  append-only invariant on log tables; the
  `admin_audit_log` carve-out (Art. 17(3)(b)) is preserved
  by FR-004's read-only contract.
- **Spec 007 (ai-security-pipeline) §FR-005** —
  `review_gate_edit` is one of the audit actions whose
  diff is the most operationally interesting. The
  DiffRenderer makes the review-gate decision history
  forensically inspectable.
- **Spec 006 (mcp-server)** — per-session WS broadcast
  carries the new `audit_log_appended` event shape
  (FR-010). Reuses the existing channel rather than
  introducing a new one.
- **Constitution §10** — Phase 3 deliverables list. Spec
  029 is in-scope for Phase 3 by virtue of Phase-3
  declaration recorded 2026-05-05.
- **Constitution §14.1** — Feature work workflow. This
  spec scaffolds via `/speckit.specify`; subsequent
  steps are deferred.
- **Constitution V12** — topology applicability. Spec 029
  applies to topologies 1-6; incompatible with topology 7.
- **Constitution V13** — primary use cases technical
  review and audit (§5), consulting (§3).
- **Constitution V14** — per-stage timing budgets. Spec
  029 contributes four budgets (Performance Budgets
  section).
- **Constitution V16** — env-var validation at startup.
  Spec 029 introduces three new vars (Configuration
  section).

## Assumptions

- The `admin_audit_log` table is the single source of
  truth for audit events. Spec 029 is a read-side
  surface; no parallel storage is introduced.
- The action-label registry is the architectural commitment
  that earns spec 029 its slot. Without it, three
  audit-adjacent surfaces (029 itself, 022, 024) would
  drift; with it, drift is structurally prevented by the
  CI parity gate.
- Backend Python + frontend JS pair for action-labels and
  time-formatter (per the user's architectural decision).
  Backend module is source of truth for both pairs;
  frontend mirrors are kept in lock-step via CI parity
  gate.
- The DiffRenderer is frontend-only because it's a React
  presentation component; the backend supplies raw values
  from `admin_audit_log.previous_value` and
  `new_value`.
- Live updates via WS push (per the user's architectural
  decision) match spec 022's pattern. Audit-adjacent UIs
  share a consistent live-update story.
- Server-side filter pushdown is a future enhancement.
  v1 ships client-side page-scoped filtering; operators
  with high-event sessions accept the page-scope
  limitation until pushdown lands.
- Sensitive-value scrubbing (FR-014) provides a safety
  envelope for the live viewer surface. The full content
  remains available via spec 010 debug-export, which has
  its own audit + authorization model.
- 029 ships ahead of 022 + 024 in implementation
  sequence so the shared components exist when downstream
  specs need them. Spec 022 + 024 land amendments at
  their implementation time to add FRs that consume
  spec 029's modules (FR-019).
- Phase 3 declared 2026-05-05 satisfies the phase gate;
  this spec stays scaffold-only until tasks are
  scheduled. No implementation begins on this spec until
  the user invokes `/speckit.clarify` and subsequent
  workflow steps.
- Status remains Draft until clarifications resolve and
  the user accepts the scaffolding.
