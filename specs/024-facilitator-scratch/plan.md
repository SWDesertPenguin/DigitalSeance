# Implementation Plan: Facilitator Scratch Window

**Branch**: `024-facilitator-scratch` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/024-facilitator-scratch/spec.md`

## Summary

Phase 3+ facilitator-only scratch surface delivered as a four-part mechanism: (1) a new `facilitator_notes` table with nullable account FK plus six endpoints (scratch payload GET + notes CRUD + promote) gated by `SACP_SCRATCH_ENABLED` master switch and FR-021 facilitator-only authorization, (2) an architectural test (`tests/test_024_architectural.py`) enforcing that no module reaches `facilitator_notes_repo` from the spec 008 context-assembly path, (3) a promote-to-transcript handler reusing the existing `_validate_and_persist` + `_broadcast_human_message` path (spec 006 / spec 007 / spec 008 unchanged), with one audit row per click carrying the prior note content post-ScrubFilter, (4) a scratch panel SPA route at `/session/:id/scratch` shipping as three tabs (Notes / Summaries / Review Gate) that reuse spec 029''s `DiffRenderer` component for the Review Gate sub-panel (no parallel diff implementation). Three new `SACP_*` env vars + V16 validators land before `/speckit.tasks`. A spec 011 amendment FR-042..FR-049 wires the SPA.

Technical approach: introduce `src/scratch/` as the new feature module containing the `FacilitatorNotesRepository` + `ScratchService` + scratch-panel HTTP router; ship one alembic migration adding `facilitator_notes` table; extend `tests/conftest.py` with the mirrored DDL per the schema-mirror invariant; extend `src/config/validators.py` with three new validators and register in `VALIDATORS`; document each in `docs/env-vars.md` per V16; extend `src/orchestrator/audit_labels.py` + `frontend/audit_labels.js` with five new scratch action entries; ship the five SPA pieces as the spec 011 amendment FR set; add the architectural test extending spec 029''s parity gate.

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. No new backend runtime dependencies. Frontend: zero new third-party libraries — spec 024 reuses spec 029''s `DiffRenderer` + `frontend/diff_engine.js` per spec 029 contracts/shared-module-contracts.md §3.
**Storage**: PostgreSQL 16. One new alembic migration (`019_facilitator_notes.py`) adds the `facilitator_notes` table with nullable account FK + version + soft-delete + promoted-marker columns. Schema-mirror in `tests/conftest.py` updated alongside the migration in the same task.
**Testing**: pytest with the existing per-test FastAPI fixture. DB-gated tests follow the `tests/conftest.py` schema-mirror pattern. Frontend pure-logic Node tests under `tests/frontend/`. E2E tests skip-gated by `SACP_RUN_E2E=1`.
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm).
**Project Type**: Web service (single project; existing `src/` + `frontend/` + `tests/` layout).
**Performance Goals**:
- Scratch panel load (initial fetch) P95 <= 1s for sessions with up to 100 notes + 50 summaries + 20 review-gate events.
- Note autosave round-trip P95 <= 200ms server-side (excluding the 2s client-side debounce).
- Diff renderer P95 <= 100ms on the main thread for payloads <= 50KB (inherits spec 029 budget).
- Promote-to-transcript P95 <= 500ms from Confirm click to message appearing in transcript.
**Constraints**:
- Default behavior MUST be unchanged: `SACP_SCRATCH_ENABLED=0` (default) returns HTTP 404 from every scratch endpoint AND hides the SPA entry-point button (FR-019; SC-013 V16 fail-closed contract).
- V15 fail-closed: invalid env-var values exit at startup (V16); architectural test (FR-001 / SC-001) fails the build if any code path reaches `facilitator_notes` from context assembly.
- 25/5 coding standards (Constitution §6.10) + 25-line function cap.
- §4.10 / V17 transcript canonicity: notes are operator-private workspace state, NOT canonical transcript content.
**Scale/Scope**: Phase 3 ceiling of 5 participants per session; typical scratch usage: <= 30 notes per active session, < 5 promote events per session.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | Notes are operator-side workspace state. No participant API key, model choice, budget, or AI-context content is exposed. |
| **V2 No cross-phase leakage** | PASS | Phase 3 declared 2026-05-05. No Phase 4 capabilities required; topology 7 incompatibility flagged. |
| **V3 Security hierarchy** | PASS | Two security envelopes: FR-001 architectural test + FR-006 promote-to-transcript routes through `_validate_and_persist`. |
| **V4 Facilitator powers bounded** | PASS | Scratch endpoints mirror spec 010 §FR-2 facilitator-only authorization. Promote reuses existing inject_message dispatch. |
| **V5 Transparency** | PASS | Every scratch action emits an `admin_audit_log` row per FR-020. Five new actions added to the spec 029 registry. |
| **V6 Graceful degradation** | PASS | Default `SACP_SCRATCH_ENABLED=0` preserves pre-feature behavior. Session-scoped fallback preserves value when spec 023 is off. |
| **V7 Coding standards** | PASS | Function bodies stay under 25 lines; ASCII-only Python source. |
| **V8 Data security** | PASS | Notes are operator-private workspace content, NOT API-key-class secrets. ScrubFilter applies to audit-log payloads. |
| **V9 Log integrity** | PASS | FR-020 routes every scratch event through `admin_audit_log` (append-only). Soft-delete preserves the row. |
| **V10 AI security pipeline** | PASS | Promote-to-transcript flows through `_validate_and_persist` per FR-008. Notes never reach AI context per FR-001. |
| **V11 Supply chain** | PASS | No new runtime dependencies. Spec 029''s `diff@5.x` is reused without parallel pin. |
| **V12 Topology compatibility** | PASS | Topology 1-6 applicable; topology 7 incompatible. |
| **V13 Use case coverage** | PASS | Use cases §3 Consulting, §5 Technical Review and Audit, §6 Decision-Making Under Asymmetric Expertise. |
| **V14 Performance budgets** | PASS | Four budgets specified. Diff renderer budget inherits from spec 029. |
| **V15 Fail-closed** | PASS | Master switch defaults `0`; invalid env-var values cause startup exit. Architectural test fails the build on isolation breaks. |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Three new env vars require validators + `docs/env-vars.md` sections BEFORE `/speckit.tasks` (FR-022). |
| **V17 Transcript canonicity respected** | PASS | Notes are operator-private workspace state; promote creates a normal human turn via the existing path. |
| **V18 Derived artifacts traceable** | PASS | The promote audit row captures `previous_value=<prior note content post-ScrubFilter>` + `new_value=<resulting message id>`. |
| **V19 Evidence and judgment markers** | PASS | Spec uses [JUDGMENT] / drafted-as / [NEEDS CLARIFICATION] markers consistently; clarify session resolved all eleven markers. |

No violations. (Note: a "V20 Sub-25-line bodies" row was removed on 2026-05-14 — V20 does not exist in the Constitution v0.9.0; the 25-line limit is covered by V7.) Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

- `specs/024-facilitator-scratch/plan.md` (this file)
- `specs/024-facilitator-scratch/research.md` (Phase 0)
- `specs/024-facilitator-scratch/data-model.md` (Phase 1)
- `specs/024-facilitator-scratch/quickstart.md` (Phase 1)
- `specs/024-facilitator-scratch/contracts/scratch-endpoints.md`
- `specs/024-facilitator-scratch/contracts/notes-table.md`
- `specs/024-facilitator-scratch/contracts/env-vars.md`
- `specs/024-facilitator-scratch/spec.md`
- `specs/024-facilitator-scratch/tasks.md` (Phase 2)

### Source Code (repository root)

New top-level package `src/scratch/` keeps the feature module isolated and makes the FR-001 architectural test trivial. The promote handler lives inside `src/scratch/promote.py` to keep the spec 006 surface stable; the handler imports the participant helper functions directly.

Key new paths:
- `src/scratch/__init__.py` / `repository.py` / `router.py` / `service.py` / `promote.py`
- `src/models/facilitator_note.py`
- `alembic/versions/019_facilitator_notes.py`
- `frontend/scratch_notes.js` (UMD pure-logic helpers)
- `tests/test_024_*.py` (architectural, migration, repo, endpoints, promote, validators, master-switch-off, scope-detection, audit-labels)
- `tests/frontend/test_scratch_notes.js`
- `tests/e2e/test_024_scratch_panel.py`
- `scripts/scratch_retention_sweep.py`

Extended files:
- `src/orchestrator/audit_labels.py` + `frontend/audit_labels.js` (five new entries)
- `src/config/validators.py` (three new validators + VALIDATORS tuple registration)
- `tests/conftest.py` (mirror facilitator_notes DDL)
- `tests/test_029_architectural.py` (extend with threshold-constant freshness check)
- `docs/env-vars.md` (three new sections)
- `docs/traceability/fr-to-test.md` (add ## 024-facilitator-scratch section)
- `specs/011-web-ui/spec.md` (amendment FR-042..FR-049)

## Complexity Tracking

*No constitutional violations. Section retained for traceability.*
