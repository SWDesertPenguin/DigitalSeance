# Tasks: Facilitator Scratch Window

**Branch**: `024-facilitator-scratch` | **Date**: 2026-05-12 | **Plan**: [plan.md](./plan.md)

Tasks grouped by user story per `speckit_workflow.md` conventions. Each task cites a test or implementation file.

## Phase 0 — Setup

### T001 — V16 env vars + validators + docs

- Add `validate_scratch_enabled`, `validate_scratch_note_max_kb`, `validate_scratch_retention_days_after_archive` to `src/config/validators.py`.
- Register all three in the `VALIDATORS` tuple.
- Add three new sections to `docs/env-vars.md` mirroring `contracts/env-vars.md`.
- Add `tests/test_024_validators.py` exercising syntactic validation + boundary conditions.
- Run `scripts/check_env_vars.py` and confirm exit 0.

### T002 — Alembic migration 019_facilitator_notes

- Create `alembic/versions/019_facilitator_notes.py` with `down_revision = ''018_compression_log''`.
- Upgrade: CREATE TABLE `facilitator_notes` + three partial indexes per `contracts/notes-table.md`.
- Downgrade: DROP TABLE.
- Mirror the DDL block in `tests/conftest.py`.
- Run `scripts/check_schema_mirror.py` and confirm exit 0.
- Test: `tests/test_024_migration_019.py` — table shape, FK ON DELETE behavior, index existence.

### T003 — Audit-label registry: five new entries

- Extend `src/orchestrator/audit_labels.py` `LABELS` dict with the five action keys per `data-model.md`.
- Extend `frontend/audit_labels.js` `LABELS` object with the same five entries.
- Run `scripts/check_audit_label_parity.py` and confirm exit 0.
- Test: `tests/test_024_audit_labels.py`.

## Phase 1 — Foundational

### T004 — FacilitatorNote model + repository

- `src/models/facilitator_note.py` dataclass.
- `src/scratch/__init__.py` (empty re-export module).
- `src/scratch/repository.py` — `FacilitatorNotesRepository` with: `create_note`, `update_note` (OCC on `version`), `soft_delete_note`, `find_for_session_with_scope`, `find_by_id`, `mark_promoted`.
- Test: `tests/test_024_notes_repo.py`.

### T005 — Architectural test (FR-001 / SC-001)

- `tests/test_024_architectural.py` with two-layer enforcement:
  - Layer 1 (static): walk `src/orchestrator/`, `src/prompts/`, `src/api_bridge/`, `src/operations/`; assert NO import references `src.scratch.repository`.
  - Layer 2 (runtime): monkey-patch `FacilitatorNotesRepository` to raise on read; drive a single AI turn; assert no exception.
- Extend `tests/test_029_architectural.py` with a check that no module other than `frontend/diff_engine.js` declares the threshold constants.

## Phase 2 — US1 (Notes write + persist + isolate from AI)

### T006 — Scratch service + audit-emit envelope

- `src/scratch/service.py` — `ScratchService` composing the repository + `LogRepository.log_admin_action`.
- ScrubFilter applies via the existing `log_admin_action` envelope.

### T007 — Scratch HTTP router

- `src/scratch/router.py` with five endpoints (six counting `/summaries`) per `contracts/scratch-endpoints.md`.
- Mount in `src/run_apps.py` conditional on `SACP_SCRATCH_ENABLED=1`.
- Test: `tests/test_024_scratch_endpoints.py` covering 401 / 403 / 404 / 409 / 413 / 422.

### T008 — Master-switch-off canary

- Test: `tests/test_024_master_switch_off.py` — with `SACP_SCRATCH_ENABLED=0`, every scratch endpoint returns HTTP 404.

### T009 — Account-vs-session scope detection

- Repository `find_for_session_with_scope` queries with `(session_id, account_id)` where `account_id` comes from `SessionStore`.
- Test: `tests/test_024_scope_detection.py`.

### T010 — SPA scratch panel + Notes tab

Spec 011 amendment FR-042..FR-044.

- Add to `frontend/app.jsx`: `ScratchPanel` slide-over, entry-point button, route handler, `NotesTab` with 2s autosave, scope chip header.
- New `frontend/scratch_notes.js` UMD module with: `debounceAutosave`, `serializeNote`, `renderMarkdownSubset`.
- Frontend tests: `tests/frontend/test_scratch_notes.js`.

## Phase 3 — US2 (Promote-to-transcript + confirmation + audit row)

### T011 — Promote handler + reuse inject_message path

- `src/scratch/promote.py` `PromoteHandler.promote(note_id, current_participant)`:
  1. Load the note (404 if missing / cross-tenant).
  2. Check session is active (HTTP 409 archived).
  3. Reject empty content (HTTP 422).
  4. Invoke `_try_persist_injection` from `src/mcp_server/tools/participant.py`.
  5. On success, call `_broadcast_human_message`.
  6. Mark the note `promoted_at` + `promoted_message_id`.
  7. Emit `admin_audit_log` row with `action=''facilitator_promoted_note''`.
- Add `POST /tools/facilitator/scratch/notes/<note_id>/promote` to the router.
- Tests: `tests/test_024_promote.py` covering happy path, archived 409, empty 422, re-promote emits second audit row.

### T012 — SPA promote modal + transcript wiring

Spec 011 amendment FR-045 + FR-046.

- Extend `NotesTab` with a "Promote to transcript" affordance per row.
- New `PromoteConfirmModal` component.
- E2E: `tests/e2e/test_024_scratch_panel.py::test_us2_promote_flow`.

## Phase 4 — US3 (Summary archive)

### T013 — Summary archive list + click-to-expand + copy-to-notes

Spec 011 amendment FR-047.

- `SummariesTab` reads from the FR-002 payload''s `summaries` array.
- Pagination at 20/page; click-to-expand renders the four structured sections per spec 005 §FR-005.
- "Copy to notes" action creates a new note pre-populated with the selected text.

## Phase 5 — US4 (Review-gate history with diff)

### T014 — Review-gate tab + DiffRenderer reuse

Spec 011 amendment FR-048.

- `ReviewGateTab` reads from the FR-002 payload''s `review_gate_events` array.
- Click-to-expand wires `previous_value` + `new_value` into spec 029''s `<DiffRenderer format="text">`.
- Approve-verbatim renders the AI draft as-was. Reject renders the rejected draft + reason.
- Test extension: `tests/test_029_architectural.py` — assert no spec 024 module redeclares the threshold constants.

## Phase 6 — US5 (Account-scoped survives archive)

### T015 — Archived-session affordances + retention sweep script

Spec 011 amendment FR-049.

- SPA: when the session is archived, render the scratch panel in read-only mode for promote (button disabled with tooltip).
- New `scripts/scratch_retention_sweep.py` — operator-scheduled.
- E2E: `tests/e2e/test_024_scratch_panel.py::test_us5_survives_archive_account_scoped`.

## Phase 7 — Closeout

### T016 — Traceability matrix

- Add `## 024-facilitator-scratch` section to `docs/traceability/fr-to-test.md` with one row per FR (FR-001..FR-026).
- Run `scripts/check_traceability.py` and confirm exit 0.

### T017 — Spec 011 amendment co-draft

Add new clarification session `### Session 2026-05-12 (spec 024 facilitator-scratch amendment)` to `specs/011-web-ui/spec.md` plus eight new FRs FR-042..FR-049 to the Functional Requirements section.

### T018 — All six closeout preflights pass

Run all six preflights and confirm each exits 0:
- `scripts/check_env_vars.py`
- `scripts/check_traceability.py`
- `scripts/check_schema_mirror.py`
- `scripts/check_doc_deliverables.py`
- `scripts/check_audit_label_parity.py`
- `scripts/check_time_format_parity.py`

### T019 — Status flip

Flip the spec 024 status header to `Implemented 2026-05-12`.

## Deferrals

- **Multi-facilitator shared scratch** (Phase 4+).
- **Application-layer encryption for notes-at-rest** (operators use full-disk encryption).
- **In-process retention sweep scheduler** (v1 ships the script).
- **Cursor pagination for summary archive** (offset suffices).
- **Batch promote** (sequential promote-promote-promote remains supported).
