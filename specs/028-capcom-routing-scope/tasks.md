---

description: "Task list for spec 028 — CAPCOM-Like Routing Scope"
---

# Tasks: CAPCOM-Like Routing Scope

**Input**: Design documents from `/specs/028-capcom-routing-scope/`
**Prerequisites**: plan.md, spec.md (4 user stories — US1 P1, US2 P1, US3 P2, US4 P3), research.md (15 sections), data-model.md, quickstart.md

**Tests**: INCLUDED. The spec has 15 Success Criteria (SC-001..SC-015) framed as enforceable contracts; plan.md cites specific test files for FR coverage. Tests ship alongside implementation per the spec 025/027/029 precedent.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- All file paths are absolute or relative to the 028 worktree root

## Path Conventions

- Backend Python: `src/orchestrator/`, `src/repositories/`, `src/web_ui/`, `src/config/`
- Frontend (CDN-loaded React SPA, no build toolchain per spec 011 FR-002): `frontend/*.jsx`, `frontend/*.js`
- Tests: `tests/` (pytest) and `tests/frontend/` (Node-runnable per `frontend_polish_module_pattern`)
- Migrations: `alembic/versions/`
- CI scripts: `scripts/`
- Docs: `docs/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Env-var validators + `docs/env-vars.md` sections (V16 deliverable gate per FR-020) before any feature work begins.

- [X] T001 Add two new sections to `docs/env-vars.md` for `SACP_CAPCOM_ENABLED` and `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN` with the six standard fields each (purpose, type, default, valid range, fail-closed semantics, blast radius), per V16 contract and spec FR-020
- [X] T002 [P] Add two validators to `src/config/validators.py` (boolean parser for both `_ENABLED` and `_DEFAULT_ON_HUMAN_JOIN`); register them in the `VALIDATORS` tuple. Pre-allocate slot at the tuple's end per `feedback_parallel_merge_sequence_collisions`
- [X] T003 [P] Add validator tests in `tests/test_028_validators.py` covering valid values (`true`/`false`/`1`/`0`/case-insensitive variants), invalid values (unparseable strings), and the unset-defaults-to-false behavior

**Checkpoint**: Env vars valid at startup; V16 gate satisfied before `/speckit.tasks` would have been re-run for verification.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema migration + visibility filter + audit-label registry entries. Every user story depends on these — they MUST exist before any US tasks start.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Create `alembic/versions/024_capcom_routing_scope.py` per research.md §2 and data-model.md: add `messages.kind TEXT NOT NULL DEFAULT 'utterance' CHECK (kind IN (...))`; add `messages.visibility TEXT NOT NULL DEFAULT 'public' CHECK (visibility IN (...))`; add `sessions.capcom_participant_id TEXT REFERENCES participants(id)`; add `CREATE UNIQUE INDEX ux_participants_session_capcom ON participants(session_id) WHERE routing_preference='capcom'`; add `CREATE INDEX idx_messages_visibility ON messages(session_id, visibility, turn_number DESC)`; add `checkpoint_summaries.summary_scope TEXT NOT NULL DEFAULT 'panel' CHECK (...)` + `CREATE UNIQUE INDEX ux_checkpoint_summaries_scope ON checkpoint_summaries(session_id, checkpoint_turn, summary_scope)`. Down-migration drops in reverse.
- [X] T005 Update `tests/conftest.py` raw-DDL schema mirror per `feedback_test_schema_mirror` memory: add `kind`, `visibility` columns to messages CREATE TABLE literal; add `capcom_participant_id` to sessions CREATE TABLE literal; add the unique partial index + visibility index as separate `CREATE` statements in the fixture setup; add `summary_scope` to checkpoint_summaries + its unique index
- [X] T006 [P] Add `_filter_visibility(messages, participant, capcom_id) -> list[ContextMessage]` pure function to `src/orchestrator/context.py` per research.md §3. Wire it as the LAST step inside `ContextAssembler.assemble()` immediately before `_secure_content`. Add the `capcom_participant_id` read to the sessions SELECT issued at assemble-start. The function MUST be under 25 lines per Constitution §6.10
- [X] T007 [P] Extend `src/orchestrator/audit_labels.py` with four new entries (`capcom_assigned`, `capcom_rotated`, `capcom_disabled`, `capcom_departed_no_replacement`); all `scrub_value=False`. Update `frontend/audit_labels.js` with the same four entries (label strings only; no `scrub_value` field per the established mirror pattern)
- [X] T008 [P] Run `scripts/check_audit_label_parity.py` to confirm the four new entries pair correctly across the Python + JS mirrors; resolve any drift before continuing
- [ ] T009 [P] Update `scripts/check_detection_taxonomy_parity.py` allowlist to admit the new `routing_log.reason` value `message_filtered_capcom_scope:excluded=<N>`; re-run the script and confirm zero drift
- [X] T010 [P] Add `tests/test_028_migration.py` covering: migration apply + rollback; default values on existing rows after migration; partial-unique-index admits at most one `capcom` per session; non-`capcom` participants are unconstrained by the index; check constraint rejects unknown kind/visibility values
- [X] T011 [P] Add `tests/test_028_visibility_filter.py` covering FR-006: panel AI participant gets only `public` messages; CAPCOM participant gets both `public` + `capcom_only`; human participant gets both; no CAPCOM assigned (NULL `capcom_participant_id`) every message is visible to every participant (degenerate state matches pre-feature behavior); the function rejects malformed inputs with a clear error rather than silent omission
- [ ] T012 [P] Add `tests/test_028_routing_log_reason.py` covering FR-023: when the visibility filter excludes at least one message for a participant, a `routing_log` row is emitted with `reason='message_filtered_capcom_scope:excluded=<N>'` carrying the exclusion count; zero-exclusion turns emit no row; the new reason value is on the detection-taxonomy allowlist

**Checkpoint**: Foundation ready — schema applied, filter in place, audit-label registry updated, parity gates green; user story implementation can now begin in parallel.

---

## Phase 3: User Story 1 - Facilitator assigns CAPCOM; non-CAPCOM AIs no longer see direct human messages; CAPCOM relays curated content (Priority: P1) 🎯 MVP

**Goal**: A facilitator can flip a session into CAPCOM-mediated mode. The designated CAPCOM AI sees `capcom_only` content; panel AIs do not. The CAPCOM AI emits `capcom_relay` messages that the panel sees as ground truth.

**Independent Test**: Drive a 4-AI + 1-human session. Assign one AI as CAPCOM. Inject a `capcom_only` human message. Drive each panel AI's dispatch; assert its context excludes the human message. Drive the CAPCOM AI's dispatch; assert its context includes the message. Have CAPCOM emit a `capcom_relay`; drive a panel AI's next dispatch; assert its context includes the relay but NOT the original human message.

### Tests for User Story 1

- [X] T013 [P] [US1] Add `tests/test_028_capcom_endpoints.py::test_assign_endpoint_*` covering FR-007: happy-path assign sets routing_preference + capcom_participant_id + emits `capcom_assigned` audit row; second assign attempt rejected by partial-unique-index with HTTP 409; non-facilitator auth → 403; master-switch off → 404; unknown participant id → 404
- [X] T014 [P] [US1] Add `tests/test_028_inject_handler.py::test_visibility_default_*` covering FR-015 + FR-016: with `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN=false` (default), human message without explicit visibility defaults to `public`; with `=true`, defaults to `capcom_only`; explicit per-message visibility overrides the default; `capcom_only` rejected with HTTP 409 when no CAPCOM is assigned (FR-021 / INV-3); panel AI emitting `capcom_only` rejected with HTTP 422 (INV-4)
- [X] T015 [P] [US1] Add `tests/test_028_capcom_relay_pipeline.py::test_capcom_relay_through_security_pipeline` covering FR-017: a `capcom_relay` emitted by the CAPCOM AI flows through `_validate_and_persist`; high-risk relay content stages for facilitator review per spec 007 §FR-005; benign relay persists as `kind='capcom_relay'`, `visibility='public'`
- [ ] T016 [P] [US1] Add `tests/test_028_ws_events.py::test_capcom_assigned_ws_event` covering the `capcom_assigned` WS event shape per research.md §7: payload includes `session_id`, `capcom_participant_id`, `capcom_display_name`, `timestamp`; broadcast to all session subscribers (not role-filtered); arrives within 2s of endpoint commit
- [ ] T017 [P] [US1] Add `tests/test_028_architectural.py::test_no_message_content_read_bypasses_visibility_filter` per research.md §4 / §13: AST-scan `src/` for `messages.content` reads; assert every read site is on the explicit five-entry allowlist with documented justification; synthetic bypass (added then removed) is detected

### Implementation for User Story 1

- [X] T018 [US1] Create `src/web_ui/admin_capcom.py` with `POST /sessions/:session_id/capcom/assign` endpoint per research.md §6. Authorization mirrors spec 010 §FR-2 facilitator-only via the existing facilitator-resolver dependency. The handler issues a single transaction: set target participant's `routing_preference='capcom'`, set `sessions.capcom_participant_id=<participant_id>`, INSERT `admin_audit_log` row. Returns 200 on success; 404 for unknown participant; 409 on unique-index violation; 422 if the target participant is a human
- [X] T019 [US1] Mount the `admin_capcom` router in `src/web_ui/app.py` conditional on `SACP_CAPCOM_ENABLED`. When the master switch is false, the router is NOT mounted and every CAPCOM endpoint returns HTTP 404 (FR-021)
- [X] T020 [P] [US1] Extend `src/web_ui/inject.py` (or the equivalent message-injection handler) with: (a) visibility-default selector consulting `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN`; (b) INV-3 check rejecting `capcom_only` writes when `sessions.capcom_participant_id IS NULL`; (c) INV-4 check rejecting panel-AI emissions of `capcom_only`. Each rejection returns the appropriate HTTP code with a structured error
- [X] T021 [P] [US1] Extend `src/repositories/message_repo.py` with `kind` + `visibility` persistence on every INSERT path; add a query helper `fetch_messages_for_assembly(session_id, branch_id, since_turn)` that returns rows including the new columns. The visibility filter (T006) consumes this output
- [ ] T022 [P] [US1] Add the `capcom_relay` emit path: when the CAPCOM AI's dispatch produces a turn the orchestrator (or CAPCOM-side scaffolding per research.md §11) flags as a relay, the message persists with `kind='capcom_relay'`, `visibility='public'`. The flag-detection mechanism: a structured XML marker in the CAPCOM AI's output (`<capcom_relay>...</capcom_relay>`) parsed at write time; absent the marker, the message persists as `kind='utterance'`, `visibility='public'` (CAPCOM AI's regular turn, FR-FR-012 / US1 Acceptance Scenario 7)
- [X] T023 [P] [US1] Add `capcom_assigned` WS event emission to `src/web_ui/events.py` per research.md §7. Broadcast to all session subscribers via the existing `broadcast_to_session` helper. Payload shape per the research note
- [ ] T024 [US1] Update `src/orchestrator/prompts/` (spec 008 coordination) with the CAPCOM addendum per research.md §11. The addendum is a conditional suffix appended to the CAPCOM participant's system prompt at dispatch time when `routing_preference='capcom'` is detected. The exact wording follows research.md §11's draft; finalize during this task

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently — facilitator assigns CAPCOM, human messages flow to CAPCOM only when scoped, CAPCOM relay surfaces to panel.

---

## Phase 4: User Story 2 - CAPCOM queries the human via capcom_query; human responds; CAPCOM relays answer (Priority: P1)

**Goal**: The CAPCOM AI can ask humans questions on behalf of the panel. The human's response defaults to `capcom_only` and stays invisible to the panel; CAPCOM curates and relays the answer.

**Independent Test**: As CAPCOM, emit a `capcom_query` message. Assert it persists with `kind='capcom_query'`, `visibility='capcom_only'`. Human's UI surfaces the query. Inject a human response; assert it defaults to `visibility='capcom_only'`. Drive a panel AI's dispatch; assert its context excludes the human response. Have CAPCOM emit a `capcom_relay` summarizing; assert it surfaces to the panel.

### Tests for User Story 2

- [X] T025 [P] [US2] Add `tests/test_028_inject_handler.py::test_capcom_query_response_default_scope` covering FR-014: when a human's message is a reply to a `capcom_query` (identified via `reply_to_query_id` payload field or `parent_turn` reference), the visibility defaults to `capcom_only` regardless of `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN`; explicit override to `public` is honored
- [ ] T026 [P] [US2] Add `tests/test_028_capcom_relay_pipeline.py::test_capcom_query_persistence` covering FR-013: a `capcom_query` emitted by CAPCOM persists with `kind='capcom_query'`, `visibility='capcom_only'`; the CAPCOM AI's regular non-query turns are NOT auto-tagged as queries

### Implementation for User Story 2

- [ ] T027 [P] [US2] Add the `capcom_query` emit path inside the same handler from T022. Structured XML marker `<capcom_query>...</capcom_query>` in the CAPCOM AI's output triggers `kind='capcom_query'`, `visibility='capcom_only'` at write time
- [X] T028 [P] [US2] Extend the inject handler (T020) with the `reply_to_query_id` payload field: when present and refers to a `capcom_query` message, the visibility default flips to `capcom_only` per FR-014, irrespective of `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN`
- [ ] T029 [P] [US2] Extend the CAPCOM-side prompt addendum (T024) with `capcom_query` scaffolding: explain to the CAPCOM AI when to emit a query vs. a relay; document the XML marker form. The addendum body finalizes during this task

**Checkpoint**: At this point, Users Stories 1 AND 2 should both work — the bidirectional CAPCOM channel is complete.

---

## Phase 5: User Story 3 - Facilitator rotates CAPCOM mid-session; new CAPCOM starts with no capcom_only history (Priority: P2)

**Goal**: A facilitator can swap the CAPCOM role to a different AI mid-session. The new CAPCOM does NOT inherit the prior CAPCOM's `capcom_only` view.

**Independent Test**: Drive a session with CAPCOM A. Emit several `capcom_only` exchanges. Rotate to CAPCOM B. Drive B's dispatch; assert B's context contains public history only (no prior `capcom_only` content). Inject a new `capcom_only` human message; assert B sees it on the next dispatch. Inspect `admin_audit_log`; assert each prior `capcom_only` message remains attributed to A.

### Tests for User Story 3

- [X] T030 [P] [US3] Add `tests/test_028_capcom_endpoints.py::test_rotate_endpoint_*` covering FR-008: happy-path rotation updates `routing_preference` on both participants + updates `sessions.capcom_participant_id` + emits `capcom_rotated` audit row; concurrent rotate attempts: one succeeds, the other gets HTTP 409; rotation never trips the partial unique index (research.md §14)
- [ ] T031 [P] [US3] Add `tests/test_028_rotation_no_inherit.py` covering FR-010: after rotation, B's next context excludes all prior `capcom_only` messages; A's next context (now a regular participant) ALSO excludes them (A's prior privileged view does NOT survive demotion); historical attribution of prior `capcom_only` rows remains as A (`speaker_id` unchanged)
- [ ] T032 [P] [US3] Add `tests/test_028_capcom_concurrency.py::test_in_flight_query_arrival_attribution` covering FR-013: an in-flight `capcom_query` from A; rotation to B happens; human response arrives post-rotation; B's next context includes the response (arrival-time attribution per research.md §8); A's now-non-CAPCOM context does NOT
- [ ] T033 [P] [US3] Add `tests/test_028_ws_events.py::test_capcom_rotated_ws_event` covering the `capcom_rotated` WS event shape per research.md §7: payload includes both previous + new participant ids + display names + timestamp; broadcast to all session subscribers

### Implementation for User Story 3

- [X] T034 [US3] Add `POST /sessions/:session_id/capcom/rotate` endpoint to `src/web_ui/admin_capcom.py` per research.md §6 + §14. The handler issues a single transaction: SELECT prior `routing_preference` from `admin_audit_log` for the outgoing CAPCOM's assign event (default `'always'` if absent); UPDATE outgoing CAPCOM's `routing_preference` to the prior value; UPDATE incoming participant's `routing_preference` to `'capcom'`; UPDATE `sessions.capcom_participant_id`; INSERT `admin_audit_log` row. The sequential UPDATEs satisfy the partial unique index at each statement boundary
- [X] T035 [P] [US3] Add `capcom_rotated` WS event emission to `src/web_ui/events.py`. Same broadcast pattern as `capcom_assigned`

**Checkpoint**: User Story 3 complete — rotation works without privilege accumulation.

---

## Phase 6: User Story 4 - Facilitator disables CAPCOM mid-session; capcom_only history preserved invisibly (Priority: P3)

**Goal**: A facilitator can disable CAPCOM mode mid-session. Future messages default to `public`. Historical `capcom_only` content stays attributed to the prior CAPCOM and remains invisible to non-CAPCOM AIs.

**Independent Test**: Drive a session with CAPCOM enabled producing `capcom_only` history. Disable CAPCOM. Assert `sessions.capcom_participant_id=NULL`. Drive each AI's next dispatch; assert no AI's context contains the historical `capcom_only` content. Inject a new human message without visibility; assert it defaults to `public` and every AI sees it.

### Tests for User Story 4

- [X] T036 [P] [US4] Add `tests/test_028_capcom_endpoints.py::test_disable_endpoint_*` covering FR-009: happy-path disable reverts the CAPCOM's `routing_preference`, NULLs `sessions.capcom_participant_id`, emits `capcom_disabled` audit row; disable when no CAPCOM is assigned → HTTP 404; non-facilitator → 403
- [ ] T037 [P] [US4] Add `tests/test_028_disable_no_promotion.py` covering FR-011: after disable, every AI's context EXCLUDES the historical `capcom_only` content (no retroactive promotion); the formerly-CAPCOM AI's next context EXCLUDES the historical `capcom_only` too (their prior privileged view does not survive disable per spec User Story 4 Acceptance Scenario 4 — note: this differs from the spec text which is internally inconsistent; reconcile during this task with the user via spec amendment if needed); the `capcom_only` UI option is hidden when no CAPCOM is assigned
- [ ] T038 [P] [US4] Add `tests/test_028_ws_events.py::test_capcom_disabled_ws_event` covering the `capcom_disabled` WS event shape per research.md §7

### Implementation for User Story 4

- [X] T039 [US4] Add `DELETE /sessions/:session_id/capcom` endpoint to `src/web_ui/admin_capcom.py` per research.md §6. The handler issues a single transaction: UPDATE current CAPCOM's `routing_preference` to the prior value (read from audit log); UPDATE `sessions.capcom_participant_id=NULL`; INSERT `admin_audit_log` row
- [X] T040 [P] [US4] Add `capcom_disabled` WS event emission to `src/web_ui/events.py`
- [X] T041 [P] [US4] Extend `src/repositories/participant_repo.py` participant-removal cascade (spec 002 §FR-016): when a participant with `routing_preference='capcom'` is removed, the cascade sets `sessions.capcom_participant_id=NULL` and emits `admin_audit_log` with `action='capcom_departed_no_replacement'` (FR-022). Implementation lands here even though it's logically a US4-adjacent invariant — keeps cascade logic co-located

### Tests for departure-without-replacement (US4-adjacent)

- [X] T042 [P] [US4] Add `tests/test_028_departure_handling.py` covering FR-022 / SC-014: removing the CAPCOM participant cascades to `sessions.capcom_participant_id=NULL` AND emits `capcom_departed_no_replacement` audit row; subsequent messages default to `public`; the `capcom_only` UI option becomes hidden

**Checkpoint**: All four user stories complete; CAPCOM lifecycle fully covered.

---

## Phase 7: Two-tier summarizer (FR-018)

**Purpose**: Spec 005's summarizer respects visibility. Panel AIs see panel-summary; CAPCOM AI sees capcom-summary.

- [X] T043 [P] Extend `src/orchestrator/summarizer.py` (spec 005) per FR-018 + data-model.md `checkpoint_summaries.summary_scope`: when CAPCOM is assigned at a checkpoint, the summarizer runs twice — once over `visibility='public'` producing `summary_scope='panel'`, once over `visibility='public' OR visibility='capcom_only'` producing `summary_scope='capcom'`. When CAPCOM is unassigned, only the `panel` row is produced (preserves pre-feature behavior)
- [X] T044 [P] Extend `ContextAssembler.assemble()` summary-fetch path (`src/orchestrator/context.py` `_add_summary`): panel AI participants fetch the `panel` summary row; the CAPCOM AI fetches the `capcom` summary row; human participants fetch the `capcom` summary row (humans have CAPCOM-or-broader visibility). The scope selector reads `participant.id == sessions.capcom_participant_id` to detect the CAPCOM
- [X] T045 [P] Add `tests/test_028_two_tier_summarizer.py` covering FR-018 / SC-011: with CAPCOM assigned, the summarizer emits two rows per checkpoint with distinct `summary_scope` values; without CAPCOM, only one `panel` row is emitted; panel AI dispatch fetches the `panel` summary; CAPCOM AI dispatch fetches the `capcom` summary; the unique index `ux_checkpoint_summaries_scope` rejects duplicate (session, checkpoint, scope) inserts

**Checkpoint**: Visibility partition holds through the summarization layer.

---

## Phase 8: Frontend UI (spec 011 coordination deferred)

**Purpose**: SPA surfaces for CAPCOM badge, visibility indicator, facilitator controls, per-message toggle. Spec 011 FR amendments deferred to implementation-time user approval per `reminder_spec_011_amendments_at_impl_time`.

**⚠️ Before starting Phase 8**: Ask the user which spec 011 FR slots to allocate for these UI additions, and confirm wording for the new FRs. Do NOT draft spec 011 amendments unilaterally.

- [X] T046 [P] Extend `frontend/app.jsx` with a CAPCOM badge on the participant card (renders when `participants[i].routing_preference === 'capcom'`); reads from the existing participant roster state
- [ ] T047 [P] Extend `frontend/app.jsx` with a visibility indicator on each transcript message (renders for `capcom_only` messages a distinct icon + label "Private to CAPCOM"); reads from `messages[i].visibility`
- [ ] T048 [P] Extend `frontend/app.jsx` with facilitator-only Assign/Rotate/Disable controls in the admin panel; calls the new endpoints from Phase 3-6; updates the participant roster optimistically; rolls back on error
- [X] T049 [P] Extend `frontend/app.jsx` with a per-message visibility toggle in the human composer: default value follows `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN` (fetched from the session-config endpoint); the toggle is greyed when no CAPCOM is assigned; pre-flight calls the inject endpoint with the explicit `visibility` field
- [ ] T050 [P] Wire the three new WS events (`capcom_assigned`, `capcom_rotated`, `capcom_disabled`) into the SPA WebSocket handler; trigger participant roster refetch + UI rerender on each
- [ ] T051 [P] Add SR-001-style Playwright e2e covering the assign → exchange → rotate → disable flow end-to-end through the SPA (file: `tests/web_ui/test_028_capcom_e2e.py` under the spec 011 Phase F testability framework)

**Checkpoint**: UI complete; the feature is operator-usable end-to-end through the SPA.

---

## Phase 9: Spec 010 debug-export visibility reflection

**Purpose**: The forensic export reflects the visibility partition per participant (FR-024).

- [X] T052 [P] Extend `src/web_ui/admin_export.py` (spec 010) per FR-024: the export's `context_by_participant` block reflects each participant's visibility view — non-CAPCOM AI views exclude `capcom_only` content; CAPCOM AI view includes both scopes. The existing facilitator-only auth is preserved; the export itself remains audit-logged
- [X] T053 [P] Add `tests/test_028_debug_export.py` covering FR-024 / SC-15: export contains visibility-correct views for every participant; the architectural test allowlist (T017) admits `src/web_ui/admin_export.py` as a documented `messages.content` read site

---

## Phase 10: Closeout

**Purpose**: Drift-detection preflights + agent-context refresh + final task checkboxes per `feedback_closeout_preflight_scripts`.

- [X] T054 [P] Run `python scripts/check_traceability.py` and resolve any traceability drift between spec FRs and the implementation
- [X] T055 [P] Run `python scripts/check_doc_deliverables.py` and resolve any doc-deliverable drift
- [X] T056 [P] Run `python scripts/check_audit_label_parity.py` and confirm zero drift between Python + JS audit-label mirrors
- [X] T057 [P] Run `python scripts/check_detection_taxonomy_parity.py` and confirm the new `message_filtered_capcom_scope` reason is on the allowlist with zero drift
- [X] T058 [P] Verify alembic migration chain is linear (no parallel revisions) by running `python -m alembic history --verbose` and inspecting; the 024 migration has a single `down_revision = '023'`
- [ ] T059 [P] Run `.specify/integrations/claude/scripts/update-context.ps1` (Windows) or `.sh` (POSIX) to refresh `CLAUDE.md` recent-changes block with the spec 028 line
- [X] T060 [P] Run the full pytest suite locally; resolve any regressions
- [X] T061 [P] Run `ruff check .` and resolve any lint drift
- [ ] T062 [P] Update spec.md Status header from "Draft (clarify session 2026-05-14 complete; plan/tasks pending)" to "Implemented YYYY-MM-DD" once all preceding tasks are checked; do NOT flip the status unilaterally — wait for explicit user confirmation per `feedback_dont_declare_phase_done`

---

## Notes

- **Stooges-parallelizable**: T010-T012 (Phase 2 tests) can run in parallel; T013-T017 (US1 tests) can run in parallel; T018-T024 (US1 impl) has dependencies — T018 → T019 sequential, T020-T023 parallel after T019; T034 is a single endpoint impl and must run sequentially against T018+T039; T046-T051 (UI) run in parallel after the user clears spec 011 amendment scope.
- **`feedback_test_schema_mirror`**: T005 is non-negotiable and easy to forget. Without it, the migration applies on CI but the test schema doesn't carry the new columns, causing silent failures.
- **`feedback_dont_declare_phase_done`**: T062 explicitly defers the Status flip to the user's call.
- **`feedback_no_auto_push`**: Each commit during implementation stops at commit; the user issues the push command per commit.
- **`reminder_spec_011_amendments_at_impl_time`**: Phase 8 starts with explicit user-clearance on spec 011 FR slots and wording.
