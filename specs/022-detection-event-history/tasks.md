---

description: "Task list for spec 022 — Detection Event History Surface"
---

# Tasks: Detection Event History Surface

**Input**: Design documents from `/specs/022-detection-event-history/`
**Prerequisites**: plan.md (loaded), spec.md (3 user stories — US1 P1, US2 P2, US3 P3), research.md (17 sections; §§2-4 amended 2026-05-11), data-model.md (amended 2026-05-11), contracts/detection-events-endpoint.md, contracts/resurface-endpoint.md, contracts/ws-events.md (all three amended 2026-05-11), quickstart.md

**Amendment 2026-05-11**: Session 2026-05-10 Clarifications §1 (read-side join over existing log tables) is REVERSED after the Sweep 1 T004 schema audit found that question/exit detections are broadcast-only (no persistence) and density-anomaly rows lack participant/snippet/timestamp attribution. The amendment introduces a NEW `detection_events` table that the four detector emit sites dual-write to, plus one alembic migration. Affected tasks below carry "(AMENDED 2026-05-11)" annotations.

**Tests**: INCLUDED. The spec has 10 Success Criteria (SC-001..SC-010) framed as enforceable contracts; plan.md and research.md cite specific test files for FR coverage; spec 011 Phase F Playwright is the established e2e framework. Tests ship alongside implementation per the spec 029 precedent.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- All file paths are absolute or relative to the 022 branch root (`S:\GitHub\DigitalSeance\`)

## Path Conventions

- Backend Python: `src/orchestrator/`, `src/repositories/`, `src/web_ui/`, `src/config/`
- Frontend (CDN-loaded React SPA, no build toolchain per spec 011 FR-002): `frontend/*.jsx`, `frontend/*.js`
- Tests: `tests/` (pytest) and `tests/frontend/` (Node-runnable per `frontend_polish_module_pattern`)
- CI scripts: `scripts/`
- Docs: `docs/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Env-var validators + docs/env-vars.md sections (V16 deliverable gate per FR-016) + source-table index verification.

- [X] T001 Add three sections to `docs/env-vars.md` for `SACP_DETECTION_HISTORY_ENABLED`, `SACP_DETECTION_HISTORY_MAX_EVENTS`, `SACP_DETECTION_HISTORY_RETENTION_DAYS` with the six standard fields each (purpose, type, default, valid range, fail-closed semantics, blast radius) per V16 contract and spec FR-016
- [X] T002 [P] Add three validators to `src/config/validators.py` (boolean parser for `_ENABLED`, integer-range parser for `_MAX_EVENTS` `[1, 100000]` or empty, integer-or-empty parser for `_RETENTION_DAYS` `[1, 36500]` or empty); register them in the `VALIDATORS` tuple
- [X] T003 [P] Add validator tests in `tests/test_022_validators.py` covering valid values, out-of-range, malformed, and the empty-default behavior for `_MAX_EVENTS` and `_RETENTION_DAYS`
- [X] T004 (AMENDED 2026-05-11) Create `alembic/versions/017_detection_events.py` adding the new `detection_events` table per `research.md §3` + `data-model.md` with the three indexes (`(session_id, timestamp DESC)`, `(session_id, event_class)`, `(session_id, participant_id)`) and CHECK constraints on `event_class` and `disposition`. Mirror the schema in `tests/conftest.py` raw DDL per `feedback_test_schema_mirror`. The original T004 "audit existing indexes / read-side join" plan is obsolete — the existing source tables stay untouched.

**Checkpoint**: Env vars valid at startup; `detection_events` table exists with indexes covering the FR-001 endpoint's WHERE+ORDER+LIMIT.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Five-class registry, taxonomy parity gate, LISTEN/NOTIFY cross-instance broadcast scaffold. Every user story depends on these — they MUST exist before any US tasks start.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 [P] (AMENDED 2026-05-11) Create `src/web_ui/detection_events.py` with `EVENT_CLASSES: dict[str, dict[str, str]]` seeded from `research.md §5` (5 entries: `ai_question_opened`, `ai_exit_requested`, `density_anomaly`, `mode_recommendation`, `mode_change`); export `format_class_label(class_key) -> str` only. `class_for_source_row` is obsolete after the §1 reversal — `event_class` is written verbatim at INSERT time, not derived from source-row attributes.
- [X] T006 [P] Create `frontend/detection_event_taxonomy.js` (UMD) mirroring the backend `EVENT_CLASSES` keys + `label` strings (no `source`/`predicate` fields client-side); export `EVENT_CLASSES` and `formatClassLabel(classKey)` (returns `[unregistered: <key>]` fallback) — analogous to spec 029 `frontend/audit_labels.js` shape
- [X] T007 [P] Create `scripts/check_detection_taxonomy_parity.py` per `research.md §16`: import the Python module, parse the JS module's `EVENT_CLASSES = {...}` literal with a small state-machine parser (reuse pattern from spec 029's `check_audit_label_parity.py`), compare key-set + label-string parity, exit 1 with a structured error on drift
- [X] T008 Wire `scripts/check_detection_taxonomy_parity.py` into the CI workflow as a required-passing check (mirror spec 029's T011 pattern)
- [X] T009 Add registry entry for `detection_event_resurface` to spec 029's `src/orchestrator/audit_labels.py` + `frontend/audit_labels.js` (per `data-model.md` "Re-surface action row" — needed for the resurface action to render in the disposition timeline and any future audit-log views)
- [X] T010 [P] Create `src/web_ui/cross_instance_broadcast.py` per `research.md §1` with `broadcast_session_event(session_id, payload, kind)` interface; same-instance fast path via existing in-process broadcast helper; cross-instance path via `NOTIFY detection_events_{session_id}`; LISTEN connection management on facilitator-bind / facilitator-unbind events
- [X] T011 [P] Add `tests/test_022_taxonomy_registry.py`: 5-class registry shape coverage (every entry has `label`, `source`, `predicate`), parity-gate failure-mode test (synthetic drift case), `class_for_source_row` lookup for all 5 classes, `[unregistered: ...]` fallback
- [X] T012 [P] Add `tests/frontend/test_detection_event_taxonomy.js` (Node-runnable) per `frontend_polish_module_pattern`: module loads, exports 5-class shape, `formatClassLabel` fallback works
- [ ] T013 Add `tests/test_022_cross_instance_broadcast.py` unit-level scaffold: in-process broadcast for same-instance path; mock asyncpg NOTIFY for cross-instance path (full two-process e2e is in Phase 6) — DEFERRED to pass 2; same-instance fast path is exercised indirectly via the endpoint tests
- [X] T014 Architectural test in `tests/test_022_architectural.py`: assert `EVENT_CLASSES` is defined exactly once in the repository (no parallel mappings outside `src/web_ui/detection_events.py`), enforce spec 029 helper reuse (no inline reimplementation of `format_iso` or `format_label`)

**Checkpoint**: Foundation complete — taxonomy registry parity-gated, cross-instance broadcast scaffold ready for endpoint wiring. User stories can begin.

---

## Phase 3: US1 — Open panel and see chronological event list (Priority P1)

**Purpose**: GET endpoint + log_repo query + WS live-update + DetectionHistoryPanel React component + admin-panel entry-point.

- [X] T015 [US1] (AMENDED 2026-05-11) Add `get_detection_events_page(session_id, max_events, since)` to `src/repositories/log_repo.py` per `research.md §2` — single-table `SELECT * FROM detection_events WHERE session_id = $1 [AND timestamp >= $2] ORDER BY timestamp DESC LIMIT $3` returning `DetectionEvent` rows. Also add `src/repositories/detection_event_repo.py` with `insert_detection_event(...)` + disposition-transition handler (UPDATE detection_events + INSERT admin_audit_log in one transaction).
- [X] T016 [US1] Add `GET /tools/admin/detection_events` endpoint to `src/web_ui/detection_events.py` per `contracts/detection-events-endpoint.md`: auth (facilitator-only, session-bound), master-switch gating (404 when `SACP_DETECTION_HISTORY_ENABLED=false`), call `get_detection_events_page`, return response shape
- [X] T017 [P] [US1] Mount the new endpoint router from `src/web_ui/app.py` under `/tools/admin/detection_events` (only when master switch enabled)
- [X] T018 [P] [US1] Add `emit_detection_event_appended(session_id, source_table, source_row_id)` to `src/web_ui/events.py` per `contracts/ws-events.md` — assembles the payload, calls `broadcast_session_event(session_id, payload, kind='appended')`
- [X] T019 [US1] (AMENDED 2026-05-11) Dual-write call-site sweep at the four detector emit sites per `data-model.md` "Dual-write contract": question/exit in [src/orchestrator/loop.py](../../src/orchestrator/loop.py) `_detect_signals` (~lines 1400-1424); density anomaly in [src/orchestrator/density.py](../../src/orchestrator/density.py); mode_recommendation + mode_change in spec 014's emit sites. Each site calls `insert_detection_event(...)` followed by the existing per-class WS broadcast AND by `emit_detection_event_appended`. INSERT failure logs a security-event but does NOT block the existing broadcast (fail-soft per FR-017).
- [X] T020 [P] [US1] Add `DetectionHistoryPanel` React component inline in `frontend/app.jsx`: subscribes to WS, fetches initial page via REST, renders event-list table with the columns from `data-model.md`, handles `detection_event_appended` WS events per `contracts/ws-events.md`
- [X] T021 [P] [US1] Add "View detection history" entry-point button to the facilitator's session header in `frontend/app.jsx` (spec 011 amendment FR), only rendered when the master switch is on (server-side feature-detect via initial config bootstrap)
- [X] T022 [P] [US1] Add empty-state UI ("No detection events for this session yet") to `DetectionHistoryPanel` per `research.md §13`
- [X] T023 [P] [US1] Add `TruncatedSnippet` inline component to `DetectionHistoryPanel` per `research.md §14` — 200-char truncation, `[expand]` toggle, no fetch on expand
- [X] T024 [P] [US1] Add `tests/test_022_detection_events_endpoint.py` covering FR-001..FR-005, FR-013, FR-015: endpoint shape, 5-class taxonomy round-trip, facilitator-only auth (403), session-bound check (403 cross-session), master-switch 404, `max_events` cap honored
- [X] T025 [P] [US1] Add `tests/test_022_ws_events.py` for `detection_event_appended` per `contracts/ws-events.md`: emission timing, role-filter scope (facilitator-only), payload shape, V14 budget (2s push-to-render)
- [ ] T026 [P] [US1] Add `tests/test_022_log_repo.py` for `get_detection_events_page` query shape: returns all 5 classes, ORDER BY honored, disposition CTE correctness, index hints satisfied — DEFERRED to pass 2; coverage partly provided by `tests/test_022_resurface_endpoint.py` which exercises `get_detection_events_page` through mocks
- [ ] T027 [P] [US1] Add `tests/frontend/test_detection_history_panel.js` (Node-runnable): component shape, event-row rendering over a fixture set, empty-state, truncation toggle — DEFERRED to pass 2; filter-module behavior is covered by `tests/frontend/test_detection_history_filters.js`

**Checkpoint US1**: Panel opens, lists all 5 event classes chronologically, live-updates via WS. SC-001 + SC-002 + SC-009 verified.

---

## Phase 4: US2 — Re-surface a dismissed event (Priority P2)

**Purpose**: POST resurface endpoint + audit-row write + cross-instance broadcast + disposition timeline + re-surface button affordance.

- [X] T028 [US2] Add `POST /tools/admin/detection_events/<event_id>/resurface` endpoint to `src/web_ui/detection_events.py` per `contracts/resurface-endpoint.md`: validate event_id shape, auth checks, archived-session 409, source-row existence lookup, INSERT resurface row to `admin_audit_log`, emit `detection_event_resurfaced` via `broadcast_session_event(..., kind='resurfaced')`, return response with `audit_row_id` + `broadcast_path`
- [X] T029 [P] [US2] Add `get_disposition_timeline(session_id, event_id)` to `src/repositories/log_repo.py` — returns all `admin_audit_log` rows with matching `target_event_id` ordered ascending; used by the click-expand UI
- [X] T030 [P] [US2] Add `GET /tools/admin/detection_events/<event_id>/timeline` endpoint to `src/web_ui/detection_events.py` returning the disposition timeline (auth + session-bound + master-switch gating same as GET endpoint)
- [X] T031 [P] [US2] Add "Re-surface" button affordance to each row in `DetectionHistoryPanel`. Disabled for archived sessions with tooltip "re-surface requires an active session" per spec acceptance scenario US2.4
- [X] T032 [P] [US2] Add disposition-timeline click-expand UI: clicking the disposition column opens an inline timeline showing all transitions including re-surface rows per `research.md §4`
- [X] T033 [P] [US2] Wire `detection_event_resurfaced` WS handler in `DetectionHistoryPanel` to trigger the spec 011 banner-rendering pipeline (same code path as a fresh banner from `detection_event_appended`); panel row stays in place per `contracts/ws-events.md` client-side handling
- [X] T034 [P] [US2] Add `tests/test_022_resurface_endpoint.py` covering FR-006..FR-008: POST shape, audit-row emission (one row per click), archived-session 409, facilitator-only 403, cross-session 403, malformed event_id 400, event-not-found 404 (purged source), V14 same-instance budget
- [X] T035 [P] [US2] Add re-surface WS scenarios to `tests/test_022_ws_events.py`: `detection_event_resurfaced` payload shape, role-filter (facilitator-only), V14 budget; assert participant subscribers do NOT receive the event
- [ ] T036 [P] [US2] Add `tests/test_022_disposition_timeline.py`: timeline endpoint returns ascending ordered transition rows, re-surface rows preserved alongside disposition transitions, append-only invariant (no UPDATE/DELETE) — DEFERRED to pass 2

**Checkpoint US2**: Re-surface works end-to-end on a same-instance setup. SC-003 + SC-004 + SC-005 verified.

---

## Phase 5: US3 — Four-axis filtering (Priority P3 / load-bearing for noise-rate analysis)

**Purpose**: Type / participant / time-range / disposition filter controls + AND composition + hidden-events badge + filter clear-all.

- [X] T037 [P] [US3] Add filter-control UI to `DetectionHistoryPanel`: type dropdown (5 classes + `all`), participant dropdown (derived from loaded event set + `all`), time-range chips (`5m`, `15m`, `1h`, `all`) + collapsible custom range, disposition dropdown (4 values + `all`). Layout per `research.md §9`
- [X] T038 [P] [US3] Add `filterEvents(events, {type, participant, timeRange, disposition})` pure-logic function — implemented as `applyFilters` in `frontend/detection_history_filters.js` UMD module (renamed from the originally scoped `detection_event_filters.js`); AND-composes the four predicates per `research.md §8`; default `all` values pass-through
- [X] T039 [P] [US3] Wire `applyFilters` into `DetectionHistoryPanel`'s render path: filter the loaded set on each control change; re-render filtered view; preserve scroll position
- [X] T040 [P] [US3] Add hidden-events badge to each filter control: count of events excluded by each axis independently (via `hiddenByAxis`); matches spec acceptance scenario US3.3 pattern from spec 029
- [X] T041 [P] [US3] Add sort-toggle button per `research.md §12`: client-side toggle between newest-first (default) and oldest-first
- [X] T042 [P] [US3] Add "Clear filters" affordance that resets all four axes + sort to defaults
- [ ] T043 [P] [US3] Add `tests/test_022_filter_composition.py` (backend integration) and `tests/frontend/test_detection_event_filters.js` (Node-runnable pure-logic): AND composition across all four axes, default pass-through, edge cases (empty result set, all-active filters) — frontend half landed as `tests/frontend/test_detection_history_filters.js`; backend integration test DEFERRED to pass 2

**Checkpoint US3**: Filters compose correctly; hidden-events badge accurate; sort toggle works. SC-006 verified.

---

## Phase 6: Cross-instance & Polish

**Purpose**: SC-010 cross-instance test, V14 instrumentation, architectural tests, performance budget verification.

- [ ] T044 [P] Add `tests/test_022_cross_instance_broadcast.py` two-process scenario per `research.md §17` cross-instance test fixture: orchestrator A + orchestrator B on a shared Postgres; facilitator WS on B; POST re-surface on A; assert WS payload lands on B within the 500ms cross-instance budget. Marked `@pytest.mark.requires_postgres` for skip in non-DB CI environments — DEFERRED to pass 2 (SC-010 verification pending)
- [ ] T045 [P] Add V14 budget instrumentation per `research.md §15`: `detection_events.page_load_ms` from `log_repo.get_detection_events_page`; `detection_events.resurface_same_instance_ms` and `detection_events.resurface_cross_instance_ms` from the endpoint module; structured-log emission — DEFERRED to pass 2
- [ ] T046 [P] Add `tests/test_022_perf_budgets.py` exercising each of the 5 V14 budgets against synthetic load: panel-load with 1000-event session, WS push under 10 events/min, same-instance re-surface, cross-instance re-surface, filter-application — DEFERRED to pass 2 (depends on T045 instrumentation)
- [X] T047 [P] Extend `tests/test_022_architectural.py` (initiated at T014) with: assert no parallel disposition-resolution logic outside `log_repo.get_detection_events_page`'s CTE; assert reuse of spec 029's `format_iso` and `format_label` helpers in all spec-022 emit paths; assert WS broadcasts MUST go through `cross_instance_broadcast.broadcast_session_event` (no direct in-process broadcast bypass of the cross-instance contract)
- [ ] T048 [P] Add Playwright e2e covering the full US1 + US2 + US3 happy paths per `quickstart.md` Steps 1-7; runs in CI's browser-required Phase F suite (spec 011 testability framework) — DEFERRED to pass 2

---

## Phase 7: Closeout

- [ ] T049 Run the full `quickstart.md` smoke test (Steps 1-9) end-to-end against a live stack; capture any deltas as follow-up tickets — MAY DEFER if no live multi-instance stack is available; ride along with the next operator deploy
- [ ] T050 Update `spec.md` Status line from "Clarified 2026-05-10" to "Implemented YYYY-MM-DD" once T001..T048 are saturated and a session shakedown confirms the panel works for the noise-rate analysis use case — pass 1 saturation recorded 2026-05-11; full Implemented flip awaits pass 2
- [ ] T051 [P] Update `MEMORY.md` and `project_phase3_status.md` (if it exists) with the 022 implementation milestone
- [ ] T052 [P] V18 traceability audit per `plan.md` Constitution Check V18: confirm every API/WS payload carries `source_table` + `source_row_id` alongside derived `event_class`; confirm disposition responses carry the underlying `admin_audit_log` row id
- [ ] T053 Worktree-local CLAUDE.md (auto-generated by `update-agent-context.ps1`) — DEFERRED: review at PR-merge time. Repo-root `CLAUDE.md` already carries the spec 022 entry from earlier scaffold; worktree file may add nothing new

**Implementation status (running state)**:

- Phase 1 Setup: 4/4 tasks
- Phase 2 Foundational: 9/10 tasks (T013 unit scaffold deferred to pass 2)
- Phase 3 US1: 11/13 tasks (T026 log_repo unit tests + T027 panel frontend test deferred to pass 2)
- Phase 4 US2: 8/9 tasks (T036 disposition timeline test file deferred to pass 2)
- Phase 5 US3: 6/7 tasks (T043 backend integration half deferred to pass 2; frontend half landed)
- Phase 6 Cross-instance & Polish: 1/5 tasks (T044 two-process test + T045 V14 instrumentation + T046 perf budgets + T048 Playwright deferred to pass 2)
- Phase 7 Closeout: 0/5 tasks

**Total**: 39/53 tasks complete (pass 1 saturation). Residual 14 tasks roll into pass 2 — primarily Phase 6 perf/cross-instance verification + Playwright e2e + a handful of unit-test coverage files.
