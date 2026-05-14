---

description: "Task list for spec 029 — Human-Readable Audit Log Viewer"
---

# Tasks: Human-Readable Audit Log Viewer

**Input**: Design documents from `/specs/029-audit-log-viewer/`
**Prerequisites**: plan.md (loaded), spec.md (4 user stories — US1 P1, US2 P1, US3 P2, US4 P3), research.md (15 sections), data-model.md, contracts/audit-log-endpoint.md, contracts/ws-events.md, contracts/shared-module-contracts.md, quickstart.md

**Tests**: INCLUDED. The spec has 12 Success Criteria (SC-001..SC-012) framed as enforceable contracts; plan.md and research.md cite specific test files for FR coverage; spec 011 Phase F Playwright is the established e2e framework. Tests ship alongside implementation per the spec 025 precedent.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- All file paths are absolute or relative to the 029 worktree (`S:\GitHub\digitalseance-029\`)

## Path Conventions

- Backend Python: `src/orchestrator/`, `src/repositories/`, `src/web_ui/`, `src/config/`
- Frontend (CDN-loaded React SPA, no build toolchain per spec 011 FR-002): `frontend/*.jsx`, `frontend/*.js`
- Tests: `tests/` (pytest) and `tests/frontend/` (Node-runnable per `frontend_polish_module_pattern`)
- CI scripts: `scripts/`
- Docs: `docs/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Env-var validators + docs/env-vars.md sections (V16 deliverable gate per FR-017) + admin_audit_log index verification.

- [X] T001 Add three new sections to `docs/env-vars.md` for `SACP_AUDIT_VIEWER_ENABLED`, `SACP_AUDIT_VIEWER_PAGE_SIZE`, `SACP_AUDIT_VIEWER_RETENTION_DAYS` with the six standard fields each (purpose, type, default, valid range, fail-closed semantics, blast radius), per V16 contract and spec FR-017
- [X] T002 [P] Add three validators to `src/config/validators.py` (boolean parser for `_ENABLED`, integer-range parser for `_PAGE_SIZE` [10..500], integer-or-empty parser for `_RETENTION_DAYS` [1..36500]); register them in the `VALIDATORS` tuple
- [X] T003 [P] Add validator tests in `tests/test_029_validators.py` covering valid values, out-of-range, malformed, and the empty-default behavior for `_RETENTION_DAYS`
- [X] T004 Verify `admin_audit_log(session_id, timestamp DESC)` index exists in `src/database/`; if missing, add an alembic migration `alembic/versions/NNNN_audit_log_session_timestamp_index.py` (and mirror in `tests/conftest.py` raw DDL per `feedback_test_schema_mirror` memory)

**Checkpoint**: Env vars valid at startup; admin_audit_log query plan supports the FR-001 endpoint's WHERE+ORDER+LIMIT.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Action-label registry, time formatter, parity gates. Every user story depends on these — they MUST exist before any US tasks start.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 [P] Create `src/orchestrator/audit_labels.py` with `LABELS: dict[str, dict[str, Any]]` seeded from research.md §9 (21 entries; `rotate_token` and `revoke_token` carry `scrub_value=True`); export `format_label(action) -> str` and `is_scrub_value(action) -> bool` helpers per shared-module-contracts.md §1
- [X] T006 [P] Create `src/orchestrator/time_format.py` with `format_iso(dt: datetime) -> str` (millisecond-precision UTC ISO-8601 with `Z` marker; rejects naive datetimes with `ValueError`) and `format_iso_or_none(dt | None)` per shared-module-contracts.md §2
- [X] T007 [P] Create `frontend/audit_labels.js` (UMD) mirroring the backend `LABELS` keys + `label` strings (no `scrub_value`); export `LABELS` and `formatLabel(action)` (returns `[unregistered: <action>]` fallback) per shared-module-contracts.md §1
- [X] T008 [P] Create `frontend/time_format.js` (UMD) with `formatIso(timestamp)`, `formatLocale(timestamp)`, `formatRelative(timestamp)` per shared-module-contracts.md §2; output of `formatIso` MUST byte-equal `format_iso` for the same UTC instant
- [X] T009 [P] Create `scripts/check_audit_label_parity.py` per research.md §4: import the Python module, parse the JS module's `LABELS = {...}` literal with a small state-machine parser, compare key-set + label-string parity, exit 1 with a structured error on drift
- [X] T010 [P] Create `scripts/check_time_format_parity.py` per research.md §5: invoke both modules against fixed timestamp fixtures (epoch, DST transition, microsecond-precision, naive-rejected, invalid-input); assert byte-equal output
- [X] T011 Wire `scripts/check_audit_label_parity.py` and `scripts/check_time_format_parity.py` into the CI workflow (likely `.github/workflows/ci.yml` or the equivalent); both gates MUST be required-passing checks
- [X] T012 [P] Add `tests/test_029_action_label_registry.py` with: registry shape coverage (every entry has `label: str`), `scrub_value` default-False semantics, `format_label` fallback, `is_scrub_value` lookup, parity-gate failure-mode test (synthetic drift case)
- [X] T013 [P] Add `tests/test_029_time_format_parity.py` with: backend `format_iso` output for fixed UTC instants, `ValueError` on naive datetime, parity-script-passes happy path (Node invocation if Node is available; else mark xfail with rationale)
- [X] T014 [P] Add `tests/frontend/test_audit_labels.js` (Node-runnable) per `frontend_polish_module_pattern`: module loads, exports shape correct, `formatLabel` fallback works
- [X] T015 [P] Add `tests/frontend/test_time_format.js` (Node-runnable): `formatIso` output byte-equals fixed expectations, `formatLocale` produces non-empty string, `formatRelative` handles past + future + zero-delta

**Checkpoint**: Foundation ready — registry + formatter exist on both sides with CI parity enforcement; user story implementation can now begin in parallel.

---

## Phase 3: User Story 1 - Audit Log Viewer Surface (Priority: P1) 🎯 MVP

**Goal**: Facilitator opens the audit panel from the admin panel and sees a formatted, paginated, reverse-chronological table of `admin_audit_log` rows with human-readable labels, decorated display names, scrub-on-output for sensitive actions, and live WS push for new audit events. Master switch + facilitator-only auth + retention cap behave per spec.

**Independent Test**: Drive a session producing 5+ audit events of varying actions (`add_participant`, `review_gate_approve`, `remove_participant`, `pause_loop`, `start_loop`). As facilitator, open the audit panel. Assert: rows in reverse-chrono order; each row carries a non-empty `action_label` from the registry; participant display names render (not UUIDs); pagination metadata present; new audit events arrive via WS push within 2s; non-facilitator gets 403; master switch off returns 404.

### Tests for User Story 1

- [X] T016 [P] [US1] Endpoint contract covered by the union of `tests/test_029_audit_log_endpoint.py` (DB-bound: ordering, pagination metadata, retention cap, cross-session isolation, scrub at endpoint, unregistered fallback at endpoint), `tests/test_029_admin_endpoint_helpers.py` (auth resolver, _resolve_limit out-of-range 400, master-switch parser, retention parser), and `tests/test_029_audit_log_view.py` (decorate_row: orchestrator-actor display name, deleted-participant substitute)
- [X] T017 [P] [US1] WS contract covered by `tests/test_029_audit_broadcast.py` (envelope shape, role-filter to facilitator, scrub over WS, durability-on-broadcast-failure) and `tests/test_029_audit_log_endpoint.py` (within-2s emission, dedup-on-id end-to-end via log_admin_action + endpoint pair)
- [X] T018 [P] [US1] Scrub coverage in `tests/test_029_audit_log_endpoint.py::test_rotate_token_row_returns_scrubbed_at_endpoint` + `::test_spec010_debug_export_path_returns_raw_values` (forensic-walkability invariant: endpoint scrubbed, debug-export raw); WS-side scrub in `tests/test_029_audit_broadcast.py::test_broadcast_applies_scrub_for_sensitive_action`
- [X] T019 [P] [US1] Unregistered fallback covered by `tests/test_029_audit_log_endpoint.py::test_unregistered_action_renders_fallback_label_and_logs_warning` (DB-bound endpoint + caplog WARN assertion) and `tests/test_029_action_label_registry.py` (format_label fallback unit-level)

### Implementation for User Story 1

- [X] T020 [US1] Extend `src/repositories/log_repo.py` with `get_audit_log_page(session_id, offset, limit, retention_cap_days) -> AuditLogPage` per data-model.md and research.md §6; build the query with two LEFT JOINs to `participants`, the retention WHERE clause when set, ORDER BY timestamp DESC, parallel COUNT(*); apply server-side scrub via `audit_labels.is_scrub_value(action)` before returning
- [X] T021 [US1] Create `src/mcp_server/tools/admin.py` (sibling to `tools/debug.py`; `/tools/...` paths live on the MCP server, not `web_ui`) with the `GET /tools/admin/audit_log` route per contracts/audit-log-endpoint.md: validate `session_id` UUID, enforce facilitator-only auth via existing FastAPI dependency, enforce session-binding (caller's session matches param), enforce master switch (mount-time skip when `SACP_AUDIT_VIEWER_ENABLED=false`), bound `limit` to env-var max, return 400 on out-of-range params
- [X] T022 [US1] Mount the admin router in `src/mcp_server/app.py` conditionally: include the router only when `SACP_AUDIT_VIEWER_ENABLED=true`; when false, callers receive HTTP 404 from the absence of the route (matches spec FR-018 "MUST be returned" semantics)
- [X] T023 [US1] Extend `src/repositories/log_repo.py:log_admin_action(...)` with an optional `broadcast_session_id: UUID | None` parameter; when set, after the INSERT commits, call the broadcast helper from `src/web_ui/events.py` per research.md §7
- [X] T024 [US1] Add `audit_log_appended` broadcast helper in `src/web_ui/events.py`: takes session_id + decorated row; calls `broadcast_to_session_roles(session_id, roles=["facilitator"], event="audit_log_appended", payload=decorated_row)`; wraps errors so a broadcast failure does NOT propagate to the INSERT call site (durability invariant)
- [X] T025 [US1] Identify all existing `log_admin_action(...)` call sites in the codebase (grep for `log_admin_action`); for each call site that emits a facilitator-visible audit row (per the registry seed in research.md §9), add the `broadcast_session_id` argument so live audit events broadcast going forward
- [X] T026 [US1] Add the `AuditLogPanel` React component to `frontend/app.jsx`: mount at route `/session/:id/audit`; fetch `/tools/admin/audit_log?session_id=<id>&offset=0&limit=50` on mount; render a table with columns timestamp / actor / action label / target / summary; reverse-chronological order; pagination controls (next/previous) consuming `next_offset` and `total_count`; gate the route with FR-009 role check
- [X] T027 [US1] Add the "View audit log" button to the facilitator admin panel in `frontend/app.jsx`; button is gated by `SACP_AUDIT_VIEWER_ENABLED` (probed via a `/tools/admin/audit_log` HEAD or via `/me` response carrying the env-var visibility); navigate to `/session/:id/audit` on click; matches spec 011 amendment FR-025
- [X] T028 [US1] Wire the `audit_log_appended` WS event handler in `frontend/app.jsx`: when the panel is mounted, prepend new rows; dedup against `Set<row.id>`; render through the same code path as API-fetched rows; when panel is NOT mounted, silently drop (panel re-fetches on open per FR-005)
- [X] T029 [US1] Playwright e2e in `tests/e2e/test_029_audit_panel.py` (`test_us1_panel_renders_rows_with_english_labels`, `test_us1_panel_paginates`, `test_us1_master_switch_hides_button_and_404s_route`); skip-gated on `SACP_RUN_E2E=1` per `tests/e2e/conftest.py` and the master-switch test additionally on `SACP_RUN_E2E_MASTER_SWITCH_OFF=1`

**Checkpoint**: Facilitator can open the audit log panel, see formatted reverse-chrono rows with English labels, paginate, watch new audit events arrive via WS push within 2s, and a non-facilitator gets locked out. The MVP is independently testable here.

---

## Phase 4: User Story 2 - Side-by-Side Diff Renderer (Priority: P1)

**Goal**: `review_gate_edit` rows (and any action with `previous_value` / `new_value` columns) expand into a side-by-side diff. Renderer handles JSON, text, and `auto` formats. Size thresholds dispatch correctly: ≤50KB main thread, 50KB-500KB Web Worker, >500KB raw display. Per-row word-level toggle is available.

**Independent Test**: Drive a session producing a `review_gate_edit` event with text values AND a `session_config_change` event with JSON values. Open the audit panel; click expand on each row. Assert: text values render with line-by-line Myers diff; JSON values render with structured key-by-key diff; word-level toggle re-renders at word granularity; 50KB+ payload renders via Worker (with "computing diff" placeholder); 500KB+ payload displays raw without diff.

### Tests for User Story 2

- [X] T030 [P] [US2] Add `tests/frontend/test_diff_engine.js` (Node-runnable): import `frontend/diff_engine.js`; test `chooseDiffMode` threshold transitions at 50,000 / 500,000 chars; test `diffLinesSync` against synthetic line-edit fixtures; test `diffWordsSync` against synthetic word-edit fixtures; test `diffJson` mode by invoking through `format='auto'` route
- [X] T031 [P] [US2] Playwright e2e in `tests/e2e/test_029_audit_panel.py` (`test_us2_review_gate_edit_row_expands_to_diff`, `test_us2_word_level_toggle_recomputes`, `test_us2_value_less_row_expands_to_metadata_only`); skip-gated on `SACP_RUN_E2E=1`
- [X] T032 [P] [US2] Add perf test in `tests/frontend/test_diff_perf.js` (Node-runnable): generate 50KB / 500KB synthetic diff inputs; measure main-thread `diffLinesSync` latency; assert P95 ≤ 100ms on the ≤50KB tier (CI hardware reference per research.md §13)

### Implementation for User Story 2

- [X] T033 [P] [US2] Add the `diff@5.x` (jsdiff) library reference to `frontend/index.html` per research.md §2: `<script src="https://cdn.jsdelivr.net/npm/diff@5/dist/diff.min.js" integrity="sha384-..." crossorigin="anonymous">` with the SRI integrity attribute generated for the pinned version; pin in the script tag (no version float)
- [X] T034 [P] [US2] Create `frontend/diff_engine.js` (UMD) per shared-module-contracts.md §3: export `MAIN_THREAD_BYTE_THRESHOLD = 50_000`, `WORKER_BYTE_THRESHOLD = 500_000`, `chooseDiffMode(byteSize)`, `diffLinesSync(prev, next, format)`, `diffWordsSync(prev, next)`, `async diffLinesViaWorker(prev, next, format)`; the worker bootstrap uses an inline Blob URL per research.md §2 + §3 (with chunked-yield fallback when `Worker`/`Blob` unavailable)
- [X] T035 [US2] Add the `DiffRenderer` React component inline in `frontend/app.jsx` per data-model.md "DiffRenderer component shape": accept `(previousValue, newValue, format='auto')` props; handle null-previous "first set" indicator; handle `[scrubbed]` short-circuit; format autodetect via JSON.parse probing; size-threshold dispatch via `DiffEngine.chooseDiffMode`; per-row word-level toggle as in-row UI affordance
- [X] T036 [US2] Wire row-expansion in `AuditLogPanel` (within `frontend/app.jsx`) to mount `<DiffRenderer ...>` ONLY for rows whose `previous_value !== null OR new_value !== null` AND not both `[scrubbed]`; for rows without diffable values, expand to plain row metadata (timestamp, actor, target, full action text); matches spec 011 amendment FR-028
- [X] T037 [US2] Wire `[scrubbed]` short-circuit display per spec 011 amendment FR-029: when either value is the literal `[scrubbed]` string, render placeholders without invoking the diff engine

**Checkpoint**: Operators can open the audit panel, expand a `review_gate_edit`, see a real diff. Word-level toggle works. Large payloads route to Worker / raw correctly. Sensitive `[scrubbed]` rows render as placeholders, never as raw.

---

## Phase 5: User Story 3 - Filter Controls (Priority: P2)

**Goal**: Facilitator filters audit rows by actor, action type, and time range. Filters apply client-side to the loaded page (v1 limitation per FR-012). Filter-control badge displays the count of WS-pushed events that didn't match the active filter.

**Independent Test**: Open the panel for a session with mixed audit events. Select a single action-type filter; assert only matching rows display. Clear; select an actor filter; assert only that actor's rows. Combine actor + action type; assert intersection. Add time range; assert outside-range rows are hidden. While a filter is active, drive a non-matching audit event; assert badge increments to "(1 hidden)" and the row does NOT appear; clear the filter; assert the hidden row appears.

### Tests for User Story 3

- [X] T038 [P] [US3] Playwright e2e in `tests/e2e/test_029_audit_panel.py` (`test_us3_filter_narrows_visible_set`, `test_us3_filter_badge_increments_for_hidden_ws_push`); skip-gated on `SACP_RUN_E2E=1`

### Implementation for User Story 3

- [X] T039 [P] [US3] Add filter-control UI in `AuditLogPanel` (within `frontend/app.jsx`): three controls (actor dropdown sourced from session participants + "Orchestrator" option + facilitator id; action-type dropdown sourced from `AuditLabels.LABELS` keys; time-range start/end inputs); a "Clear filters" button
- [X] T040 [P] [US3] Implement client-side filter logic in `AuditLogPanel`: a pure function `applyFilters(rows, filters)` that returns the filtered subset; default rendering uses `applyFilters(rawRows, currentFilters)`; filter state lives in `useState` (no localStorage persistence per research.md §12)
- [X] T041 [US3] Implement the filter-control badge counter per FR-013 + research.md §12: a `useState` integer that increments when an `audit_log_appended` event arrives but the new row does NOT match `currentFilters`; counter resets on filter clear or filter change; badge renders `(N hidden)` next to the filter controls when N > 0
- [X] T042 [US3] Add unit tests for `applyFilters` in `tests/frontend/test_filter_logic.js` (Node-runnable) covering: single axis match, multi-axis intersection, time-range edge cases, empty filter set returns full input

**Checkpoint**: Filter narrows the visible set; badge surfaces hidden activity; clear restores. Operators with high-event sessions can scope their review.

---

## Phase 6: User Story 4 - Shared Component Architectural Commitment (Priority: P3)

**Goal**: The action-label registry, diff renderer, time formatter, and threshold constants are exposed as reusable modules with a stable public surface. Specs 022 and 024 cite `contracts/shared-module-contracts.md` when they amend at their own implementation times. An architectural test enforces FR-020: no spec outside 029 reimplements an audit-action-to-label mapping.

**Independent Test**: Run `pytest tests/test_029_architectural.py` — passes when only `src/orchestrator/audit_labels.py` and `frontend/audit_labels.js` declare audit-action mappings. Synthesize a violating module under `src/orchestrator/` (or `frontend/`) with an overlapping mapping — test fails with a clear error naming the offending file. Verify `contracts/shared-module-contracts.md` exists, lists the four module paths, documents the public surface for each, and pins the threshold constants.

### Tests for User Story 4

- [X] T043 [P] [US4] `tests/test_029_architectural.py` walks `src/orchestrator/` (AST) and `frontend/` (regex); flags any module-level dict/object whose keys overlap >=2 registered audit actions; the synthetic-violation test confirms it fires correctly

### Implementation for User Story 4

- [X] T044 [US4] Verified `contracts/shared-module-contracts.md` against landed signatures (every cited path exists on disk; every public symbol matches the implementation surface; threshold constants pinned 50,000 / 500,000); change-log row added 2026-05-09
- [X] T045 [US4] New `docs/audit-registry-workflow.md` documents the registry update flow (backend LABELS entry, frontend mirror, scrub flag justification, call-site `broadcast_session_id` wiring, parity-gate enforcement, related tests)
- [X] T046 [US4] Forward-reference notes added in `specs/022-detection-event-history/spec.md` "Cross-References" section and `specs/024-facilitator-scratch/spec.md` "Cross-References" section, both citing `contracts/shared-module-contracts.md` with the per-spec consumer expectations
- [X] T047 [US4] `tests/test_029_contract_freshness.py` asserts every cited path is on disk + cited in the contract; the frontend mirror contains every backend audit-action key verbatim; the threshold tokens "50,000" / "500,000" appear in both the contract and the module

**Checkpoint**: The shared-component contract is documented, tested, and cited by downstream specs. The architectural commitment of FR-019 / FR-020 is structurally enforced — future audit-adjacent specs that try to ship parallel mappings hit the CI gate.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Spec-text path corrections, full-walkthrough validation, security scanning, doc cross-references.

- [X] T048 Spec.md FR-006 / FR-008 / FR-009 path strings updated — `src/web_ui/static/audit_labels.js` → `frontend/audit_labels.js`; `src/web_ui/static/components/DiffRenderer.tsx` → inline component in `frontend/app.jsx` plus pure-logic helpers in `frontend/diff_engine.js`; `src/web_ui/static/time_format.js` → `frontend/time_format.js`. Added a 2026-05-09 entry in `## Clarifications` noting the implementation-time alignment with `frontend_polish_module_pattern`
- [X] T049 Spec 011 FR-028 updated to cite `frontend/app.jsx` (component) plus `frontend/diff_engine.js` (helpers); paths now match T048
- [ ] T050 Run the full quickstart.md smoke test (Steps 1-9) end-to-end against a running orchestrator; confirm every assertion passes; capture any deltas as follow-up tickets — DEFERRED: requires a live stack and a manually-driven facilitator session; ride along with the next operator deploy or schedule a dedicated smoke-test session. **Re-trigger condition**: any subsequent change to `src/mcp_server/tools/admin.py::get_audit_log`, `frontend/app.jsx::AuditLogPanel`, `frontend/diff_engine.js`, or the `audit_log_appended` WS payload shape. The `tests/e2e/test_029_audit_panel.py::test_us1_*` / `test_us2_*` / `test_us3_*` suite covers US1/US2/US3 implicitly under `SACP_RUN_E2E=1`; the live-stack smoke remains the canonical operator-side acceptance check and is not substituted by the e2e gate.
- [X] T051 Pre-commit hooks (gitleaks + 2MS + ruff + bandit + standards-lint) run automatically on the commits that landed this branch; daily automated scans cover the full-history check at 03:00 / 03:30 — fresh `pre-commit run --all-files` invocation pinned to the closing commit before push
- [X] T052 [P] `docs/ws-events.md` carries the `audit_log_appended` entry (PR #337 merged 2026-05-08); reviewed against `feedback_synthesis_docs_local_first` — entry is high-level (event name, role-filter, payload pointer, latency budget) without recon-rich payload schemas
- [X] T053 [P] FR-to-test traceability rows added in `docs/traceability/fr-to-test.md` covering FR-001..FR-020; every FR cites the test file(s) and notes the coverage tier; spec 011 FR-025..FR-029 inherit coverage via the FR-028 + FR-029 audit-panel-rendering tests already attributed in the 029 section
- [ ] T054 Worktree-local `CLAUDE.md` (auto-generated by `update-agent-context.ps1`) — DEFERRED: review at PR-merge time. Repo-root `CLAUDE.md` already carries the spec 029 entry from earlier scaffold; worktree file may add nothing new
- [X] T055 FR-020 architectural test runs cleanly from a fresh `uv run pytest tests/test_029_architectural.py` invocation — passes, the synthetic-violation test confirms the gate fires correctly

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion (T002 validators must be in place before runtime config loads); blocks all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational — needs `audit_labels` (for label rendering), `time_format` (for timestamp display), and the parity gates (for CI sanity)
- **User Story 2 (Phase 4)**: Depends on Foundational + User Story 1 (DiffRenderer mounts INSIDE the panel from US1; cannot independently test the diff without an audit panel to expand a row in)
- **User Story 3 (Phase 5)**: Depends on Foundational + User Story 1 (filter controls live INSIDE the panel from US1); independent of US2 (filter logic doesn't touch the diff renderer)
- **User Story 4 (Phase 6)**: Depends on Foundational only — the architectural test runs against the modules from Phase 2; the contract document audit runs against the shipped modules. Independent of US1 / US2 / US3 in terms of behavior (it's a structural commitment)
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies (refined)

- **US1 (P1)**: Foundational only; serves as the MVP
- **US2 (P1)**: US1 (panel must exist for diff to mount inside); independent of US3 / US4
- **US3 (P2)**: US1 (panel must exist for filter to mount on); independent of US2 / US4
- **US4 (P3)**: Foundational only; runs in parallel with all other US work

### Within Each User Story

- Tests written alongside implementation (per project convention; tests included for SC enforcement)
- Backend modules (T020-T025) before frontend SPA wiring (T026-T028)
- Pure-logic frontend modules (T034) before React-component wiring (T035-T037)
- Filter UI (T039-T040) before badge counter (T041; depends on filter logic existing)

### Parallel Opportunities

- All Phase 1 [P] tasks can run in parallel: T002, T003 (validators + tests)
- All Phase 2 [P] tasks can run in parallel: T005-T010, T012-T015 (registry, formatter, parity gates, tests — all touching different files)
- US1 tests T016-T019 [P] can run in parallel (different test files)
- US2 tests T030-T032 [P] can run in parallel
- US3 test T038 is the only test in that story (single Playwright file)
- US4 test T043 [P] is independent
- Polish tasks T052, T053 [P] can run in parallel
- **Across stories**: once Foundational completes, US4 can run in parallel with US1; US2 + US3 must wait for US1's panel scaffold

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Launch all foundational module work in parallel:
Task: "Create src/orchestrator/audit_labels.py with LABELS seed + helpers"          # T005
Task: "Create src/orchestrator/time_format.py with format_iso"                       # T006
Task: "Create frontend/audit_labels.js (UMD)"                                        # T007
Task: "Create frontend/time_format.js (UMD)"                                         # T008
Task: "Create scripts/check_audit_label_parity.py"                                   # T009
Task: "Create scripts/check_time_format_parity.py"                                   # T010

# Then in parallel test work:
Task: "Add tests/test_029_action_label_registry.py"                                  # T012
Task: "Add tests/test_029_time_format_parity.py"                                     # T013
Task: "Add tests/frontend/test_audit_labels.js"                                      # T014
Task: "Add tests/frontend/test_time_format.js"                                       # T015
```

## Parallel Example: User Story 1 Tests

```bash
# Launch all US1 test files in parallel (different files, no shared state):
Task: "Add tests/test_029_audit_log_endpoint.py covering 11 contract test cases"     # T016
Task: "Add tests/test_029_ws_event.py covering 6 contract test cases"                # T017
Task: "Add tests/test_029_scrub.py covering server-side scrub at endpoint AND WS"    # T018
Task: "Add tests/test_029_unregistered_action.py covering [unregistered: <raw>] + WARN log"  # T019
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (env vars + validators + index check)
2. Complete Phase 2: Foundational (registry + formatter + parity gates + their tests)
3. Complete Phase 3: User Story 1 (endpoint + panel + admin button + WS push)
4. **STOP and VALIDATE**: Run quickstart.md Steps 1-2 + Step 9; assert all checkpoints
5. Demo to facilitator-test-account; bank the win

The MVP is the operational improvement: operators stop running debug-export to read audit JSON and start reading the formatted panel. That alone is the spec's primary value.

### Incremental Delivery

1. Setup + Foundational → Foundation ready (all CI gates green)
2. US1 → MVP shipped (operators can read the audit log in the SPA)
3. US2 → Diff renderer (review-gate forensics become inspectable at code-review zoom level)
4. US3 → Filters (high-event sessions become navigable)
5. US4 → Shared-component machinery (specs 022 + 024 inherit the contracts cleanly)
6. Polish → Path corrections + smoke test + scanners + doc cross-refs

Each story adds value without breaking previous stories. US4 can run in parallel with US1-US3 if staffing allows.

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together (~1-2 days; mostly module + test scaffolding)
2. Once Foundational is done:
   - Developer A: US1 (backend endpoint + admin panel button + panel route)
   - Developer B: US4 (architectural test + contract doc audit; parallel from day 1)
3. After US1's panel scaffold lands:
   - Developer A: US3 (filter controls inside the panel)
   - Developer B: US2 (DiffRenderer inside the panel)
4. Polish tasks taken by whoever finishes their story first

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- US1 is the MVP boundary — stop and validate there before US2/US3/US4
- Verify tests pass before considering a task complete (per project convention; spec 025's tasks were marked `[X]` only after tests landed)
- Commit after each task or logical group; per memory `feedback_no_auto_push` — do NOT auto-push, ask before publishing
- Per memory `reminder_spec_011_amendments_at_impl_time` — the spec 011 amendment for 029 is already drafted on this branch; bundle it with the clarify+plan+tasks commit per the spec 025 precedent
- Per `feedback_audits_as_local_action_plans` — if the security scanner step (T051) surfaces findings that aren't in scope here, track them in `AUDIT_PLAN.local.md` rather than expanding this branch's scope
- Per `feedback_no_local_refs_in_prs` — when authoring the eventual PR body, list only what's IN the PR (do not enumerate held-back files, gitignored drafts, or out-of-scope deferrals)
- Total task count: 55 (T001-T055)
