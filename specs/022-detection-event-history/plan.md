# Implementation Plan: Detection Event History Surface

**Branch**: `022-detection-event-history` | **Date**: 2026-05-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/022-detection-event-history/spec.md`

## Summary

Phase 3 facilitator-only detection-event history surface delivered as a four-part mechanism: (1) a read-only endpoint `GET /tools/admin/detection_events` returning a unified event stream computed by a read-side JOIN over `routing_log` (question/exit detector decisions per spec 003 §FR-030), `convergence_log` (density-anomaly signals per spec 004 §FR-020), and `admin_audit_log` (spec 014 mode events + disposition transitions + re-surface rows), gated by FR-002 facilitator-only authorization and a new `SACP_DETECTION_HISTORY_ENABLED` master switch; (2) a re-surface endpoint `POST /tools/admin/detection_events/<event_id>/resurface` that emits a `detection_event_resurface` row to `admin_audit_log` and re-broadcasts the original banner shape over the facilitator's per-session WS channel — operator-only, participant AIs are NOT addressees per Clarifications §2; (3) a four-axis client-side filter set (type / participant / time-range / disposition) composing with AND semantics over the loaded per-session event set per Clarifications §4; (4) a cross-instance WS broadcast layer that routes both live-update and re-surface payloads to whichever orchestrator process holds the facilitator's WS, per Clarifications §6 — design-for-multi-instance from day one rather than waiting on spec 011's eventual Redis backend. The v1 event taxonomy is a fixed five-class set (`ai_question_opened`, `ai_exit_requested`, `density_anomaly`, `mode_recommendation`, `mode_change`) per Clarifications §3 + §8; spec 014's already-landed (2026-05-08) `mode_recommendation` and `mode_change` rows surface as two distinct classes, not one merged class. Two new `SACP_*` env vars + V16 validators land before `/speckit.tasks`. No alembic migration — the surface is a read-side projection.

Technical approach: extend `src/repositories/log_repo.py` with `get_detection_events_page(session_id, ...)` that runs a single UNION-ALL of three per-source SELECTs (one per source table) over `session_id` with a stable `(timestamp, source_table_priority, source_row_id)` ordering, plus a LEFT JOIN to `admin_audit_log` for the latest disposition-transition row per event id; introduce `src/web_ui/detection_events.py` for the new endpoint pair (GET + POST resurface) to keep `app.py` readable; reuse `src/orchestrator/audit_labels.py` (spec 029's action-label registry) for the resurface action label and reuse `src/orchestrator/time_format.py` (spec 029's UTC formatter) for timestamp rendering — neither helper is reimplemented inline per spec 029 FR-019/FR-020 architectural test; emit the `detection_event_appended` WS event from `src/web_ui/events.py` immediately after each source-row INSERT (call-site sweep), role-filtered through the same `broadcast_to_session_roles` helper spec 029 uses; introduce a thin `src/web_ui/cross_instance_broadcast.py` module that resolves the facilitator's currently-bound process and forwards WS broadcast emissions to it — mechanism choice (DB-backed session→instance binding vs. Redis pub/sub vs. process-binding table) is settled in [research.md §1](./research.md); add two validators (`SACP_DETECTION_HISTORY_ENABLED`, `SACP_DETECTION_HISTORY_MAX_EVENTS`, `SACP_DETECTION_HISTORY_RETENTION_DAYS`) to `src/config/validators.py`; document each in `docs/env-vars.md` per V16. Frontend: extend `frontend/app.jsx` with the `DetectionHistoryPanel` React component plus four filter controls; add `frontend/detection_event_taxonomy.js` as a UMD module holding the five-class fixed registry mirroring the backend hardcoded map (parity gate analogous to spec 029's audit-label parity); reuse `frontend/audit_labels.js` (spec 029) for the resurface action label and `frontend/time_format.js` (spec 029) for client-side time rendering. A spec 011 amendment lands at task time wiring the SPA admin-panel entry-point, panel route, filter controls, and re-surface affordance (per `reminder_spec_011_amendments_at_impl_time.md`).

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. No new backend runtime dependencies for the panel surface. The cross-instance broadcast mechanism (Clarifications §6 + [research.md §1](./research.md)) MAY introduce one new dependency depending on the chosen mechanism — DB-backed routing requires nothing; Redis pub/sub requires `redis-py` v5.x. Final choice and pin land at task time. Frontend: no new third-party libraries — the panel uses native React + the existing UMD pattern.
**Storage**: PostgreSQL 16. **No schema changes** to existing tables. The cross-instance broadcast mechanism MAY add a `session_instance_bindings` table (DB-backed routing) OR rely on Redis pub/sub without a new table (research.md §1 decides). If a new table is added, one alembic migration ships + the `tests/conftest.py` schema-mirror update per `feedback_test_schema_mirror`. Read-side surface against `routing_log` + `convergence_log` + `admin_audit_log` with display-name JOIN to `participants`; bounded per-session UNION-ALL with composite ORDER BY. Event cap (`SACP_DETECTION_HISTORY_MAX_EVENTS`) applied as a `LIMIT` on the page query; retention cap (`SACP_DETECTION_HISTORY_RETENTION_DAYS`) applied as a `WHERE timestamp >= NOW() - INTERVAL` clause for archived sessions only.
**Testing**: pytest with the existing per-test FastAPI fixture (spec 012 US7). DB-gated tests follow the `tests/conftest.py` schema-mirror pattern. Frontend pure-logic modules tested under `tests/frontend/` via Node (per `frontend_polish_module_pattern`). Cross-instance behavior tested via a two-process pytest fixture that runs two orchestrator processes against a shared DB (or DB + Redis depending on the §1 decision). E2E covered via the spec 011 Phase F Playwright framework, including a two-tab scenario for cross-instance re-surface.
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm). Frontend extends `frontend/app.jsx` + one new UMD module under `frontend/`.
**Project Type**: Web service (single project; existing `src/` + `frontend/` + `tests/` layout).
**Performance Goals**:
- Panel load (initial fetch) P95 ≤ 500ms at sessions with up to 1,000 detection events. Three-source UNION-ALL with composite ORDER BY over `session_id`-indexed predicates; LEFT JOIN to participants (PK lookup); LEFT JOIN to admin_audit_log disposition-transition rows.
- WS push latency (live-update) P95 ≤ 100ms from source-table INSERT to facilitator-client render (matches spec 022 §V14 budget).
- Re-surface (same-instance) P95 ≤ 200ms POST → WS broadcast emission.
- Re-surface (cross-instance) P95 ≤ 500ms POST → WS broadcast emission on the receiving instance.
- Filter application: O(N) over the loaded page where N ≤ `SACP_DETECTION_HISTORY_MAX_EVENTS` (default unbounded for active session). Client-side; no server round-trip.
**Constraints**:
- Default behavior MUST be unchanged: `SACP_DETECTION_HISTORY_ENABLED=false` (default) returns HTTP 404 from both endpoints AND hides the SPA panel entry-point (FR-001-equivalent architectural test, mirrors spec 029 FR-018).
- V15 fail-closed: invalid env-var values exit at startup (V16); endpoint errors fail-closed (return 5xx with structured error, do not silently degrade to partial display).
- 25/5 coding standards (Constitution §6.10) + 25-line function cap.
- §4.13 [PROVISIONAL] inter-AI shorthand: this spec touches no AI-content surface — clears the rule trivially.
- §4.10 / V17 transcript canonicity: read-only on `routing_log`, `convergence_log`, `admin_audit_log` (all append-only log tables, NOT the conversation transcript). FR-004 enforces read-only on source rows; FR-006's re-surface write is an explicit forensic append, not a mutation.
- §7 derived-artifact traceability / V18: `event_class` and `disposition` are display-time derivations from the canonical source rows; the class-mapping logic IS the derivation method, captured in `src/web_ui/detection_events.py` and visible in research.md. The raw source-row id and source-table name accompany the derived event class in every API/WS payload so reviewers can walk back to the canonical row.
**Scale/Scope**: Phase 3 ceiling of 5 participants per session. Detection-event volume per session typically < 30 (Phase 1+2 shakedown produced 11 audit events across 31 turns; detection-specific subset is a fraction of that). High-event sessions may reach the low hundreds. Pagination + filter scope handle that range without server-side pushdown (FR-011 v1 limitation). Cross-instance traffic is low-frequency by design (re-surface is operator-initiated, not per-turn).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | Detection-event history is operator-side data. No participant API key, model choice, budget, or prompt content is exposed. Facilitator-only access (FR-002) preserves the existing isolation boundary. |
| **V2 No cross-phase leakage** | PASS | Phase 3 declared 2026-05-05. No Phase 4 capabilities required; topology 7 incompatibility flagged in spec §V12 (orchestrator owns the unified event stream). |
| **V3 Security hierarchy** | PASS | Facilitator-only endpoints (FR-002, FR-007); session-bound check (FR-003); role-filtered WS broadcast scope (only facilitator subscribers receive `detection_event_appended` per the spec 029 pattern); cross-instance routing uses the same auth gates on the receiving instance (NOT a privilege-escalation hop). |
| **V4 Facilitator powers bounded** | PASS | Read-only viewer (FR-004 explicit). Re-surface is an operator decision-review action that appends an audit row but does NOT mutate source rows or transcript content. Mirrors spec 010 §FR-2 facilitator-only access. |
| **V5 Transparency** | PASS | The detection-event surface IS a transparency surface; the panel makes the existing audit trail navigable. Re-surface actions are themselves logged (FR-006) so the forensic trail records who re-opened the case. |
| **V6 Graceful degradation** | PASS | Default `SACP_DETECTION_HISTORY_ENABLED=false` preserves pre-feature behavior (HTTP 404, no SPA affordance). Unregistered source-row event-class mappings render `[unregistered: <raw_action>]`, never crash the panel. Empty-state UI for sessions with no detection events. |
| **V7 Coding standards** | PASS | Function bodies stay under 25 lines; new helpers respect 5-arg positional limit. Cross-instance broadcast module factored to keep individual functions small. |
| **V8 Data security** | PASS | Trigger snippets are already in `routing_log` / `convergence_log` payloads (existing append-only state) and exposed via spec 010 debug-export under the same facilitator authorization. The panel adds a navigable surface, not new persistence. No additional sensitive content surfaces. |
| **V9 Log integrity** | PASS | FR-004 enforces read-only on source rows. The only allowed write is the `admin_audit_log` re-surface row (FR-006), which is an append, not a mutation. The viewer endpoint runs under the application DB role (INSERT/SELECT-only on log tables per Constitution §6.2). |
| **V10 AI security pipeline** | PASS | No AI content involvement. Trigger snippets are operator-facing display values; trust tiers, spotlighting, and output validation do not apply at the panel boundary. |
| **V11 Supply chain** | PASS-ON-DELIVERY | At most one new backend dependency if cross-instance broadcast lands on Redis pub/sub (research.md §1 decides). If Redis is chosen, `redis-py` pinned to v5.x with hash-lock in `uv.lock` per Constitution §6.3. No new frontend dependencies. |
| **V12 Topology compatibility** | PASS | Spec §V12 enumerates topology 1-6 applicability (orchestrator owns the centralized event stream); topology 7 incompatibility flagged (each MCP client is its own event boundary). |
| **V13 Use case coverage** | PASS | Spec §V13 maps to use cases §3 Consulting (primary) and §5 Technical Review and Audit (primary). Both rely on operator-facing post-hoc decision review. |
| **V14 Performance budgets** | PASS | Five budgets specified in spec §"Performance Budgets (V14)" (panel-load, WS push, same-instance re-surface, cross-instance re-surface, filter-application). Structured-log instrumentation hooks land in the new endpoint module and the cross-instance broadcast module. |
| **V15 Fail-closed** | PASS | Master switch defaults false (operator opt-in); invalid env-var values cause startup exit (V16). Cross-instance routing failures return 5xx with structured error — NOT a silent fallback to same-instance-only (which would mask the multi-instance contract). |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Three new env vars require validators + `docs/env-vars.md` sections BEFORE `/speckit.tasks` (FR-016). Validators land in this feature's task list. |
| **V17 Transcript canonicity respected** | PASS | Spec is read-only on `routing_log`, `convergence_log`, `admin_audit_log` (all distinct append-only logs, NOT the conversation transcript). FR-004 enforces the contract. Re-surface writes one forensic row; no transcript mutation, compression, or canonical replacement. |
| **V18 Derived artifacts traceable** | PASS | `event_class` and `disposition` are display-time derivations from canonical source rows. The class-mapping registry IS the derivation method. Every API/WS payload carries the source-row id + source-table name alongside the derived event-class label, so reviewers can walk from label back to the canonical source. |
| **V19 Evidence and judgment markers** | PASS | Spec uses [JUDGMENT] / drafted-as / [NEEDS CLARIFICATION] markers consistently; Session 2026-05-10 resolved all eight initial-draft markers (three notable departures: full filter axes, multi-instance from start, distinct mode-event classes). Historical draft section preserved. |

No violations. Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/022-detection-event-history/
├── plan.md                              # This file (/speckit.plan command output)
├── research.md                          # Phase 0 output — load-bearing §1 is cross-instance broadcast mechanism
├── data-model.md                        # Phase 1 output — read-side projection shape (no new persisted entities)
├── quickstart.md                        # Phase 1 output — end-to-end smoke test (panel open, live-update, filter, re-surface, two-tab cross-instance)
├── contracts/                           # Phase 1 output
│   ├── detection-events-endpoint.md     # GET /tools/admin/detection_events shape + auth + filter params
│   ├── resurface-endpoint.md            # POST /tools/admin/detection_events/<event_id>/resurface shape + cross-instance routing
│   └── ws-events.md                     # detection_event_appended + detection_event_resurfaced event shapes + role-filter + cross-instance contract
├── spec.md                              # Feature spec (Status: Clarified 2026-05-10)
└── tasks.md                             # Phase 2 output (/speckit.tasks command - NOT created here)
```

### Source Code (repository root)

```text
src/
├── orchestrator/
│   ├── audit_labels.py                  # REUSE — spec 029's action-label registry; add `detection_event_resurface` entry
│   └── time_format.py                   # REUSE — spec 029's UTC ISO-8601-with-Z formatter; no changes
├── repositories/
│   └── log_repo.py                      # extend with get_detection_events_page(session_id, filters, max_events) returning the UNION-ALL projection
├── web_ui/
│   ├── detection_events.py              # NEW — GET /tools/admin/detection_events + POST .../resurface endpoints; class-mapping registry; auth + master-switch gating
│   ├── cross_instance_broadcast.py      # NEW — facilitator → instance routing for detection_event_appended + detection_event_resurfaced; mechanism per research.md §1
│   ├── events.py                        # add detection_event_appended emitter (role-filtered to facilitator; cross-instance via cross_instance_broadcast)
│   └── app.py                           # mount the new detection_events router
├── config/
│   └── validators.py                    # add 3 validators (SACP_DETECTION_HISTORY_ENABLED, _MAX_EVENTS, _RETENTION_DAYS)

frontend/                                 # established UMD pattern per frontend_polish_module_pattern memory
├── detection_event_taxonomy.js          # NEW — UMD; mirrors src/web_ui/detection_events.py 5-class registry; parity gate (analogous to spec 029 audit-label parity)
├── audit_labels.js                      # REUSE — spec 029's; add `detection_event_resurface` mirror entry
├── time_format.js                       # REUSE — spec 029's; no changes
└── app.jsx                              # extend — add DetectionHistoryPanel React component + 4 filter controls + re-surface affordance + admin-panel "View detection history" entry-point (spec 011 amendment FRs)

scripts/
└── check_detection_taxonomy_parity.py   # NEW — required CI step; parse frontend module, compare 5-class key-set parity with backend registry (analogous to spec 029's audit-label parity gate)

tests/
├── test_022_detection_events_endpoint.py    # NEW — FR-001..FR-005 endpoint shape, 5-class taxonomy, facilitator-only auth, master-switch 404
├── test_022_resurface_endpoint.py           # NEW — FR-006..FR-008 re-surface POST shape, audit-row emission, archived-session 409, facilitator-only 403
├── test_022_filter_composition.py           # NEW — FR-011 four-axis AND composition, all-axes-active scenarios
├── test_022_ws_events.py                    # NEW — FR-009 detection_event_appended emission, role-filter scope, 2s budget; FR-006 re-surface broadcast shape
├── test_022_cross_instance_broadcast.py     # NEW — SC-010 two-process scenario; cross-instance budget
├── test_022_validators.py                   # NEW — three env-var validators
├── test_022_taxonomy_registry.py            # NEW — 5-class registry shape; class-mapping for spec 014 audit-log action strings; unregistered fallback
├── test_022_architectural.py                # NEW — no parallel class-mapping outside src/web_ui/detection_events.py; spec 029 helper reuse
└── frontend/
    ├── test_detection_event_taxonomy.js     # NEW — Node-runnable; module loads, 5 classes exported, parity-gate failure-mode synthetic drift
    └── test_detection_history_panel.js      # NEW — Node-runnable; filter composition over a fixed event set fixture

docs/
└── env-vars.md                          # add 3 new sections (V16 gate; FR-016)
```

**Structure Decision**: Single Python service ("Option 1") consistent with the existing repo layout. Backend endpoints cluster in `src/web_ui/detection_events.py` (new) to keep `app.py` readable; the cross-instance broadcast mechanism lives in its own `src/web_ui/cross_instance_broadcast.py` module so the mechanism choice (research.md §1) is replaceable without rewriting the endpoint. Frontend ships under `frontend/` as UMD per the established `frontend_polish_module_pattern` (memory note 2026-05-07). The DetectionHistoryPanel JSX component lives inline in `frontend/app.jsx` (single-file SPA per spec 011 FR-002); the five-class taxonomy registry factors out to `frontend/detection_event_taxonomy.js` so it remains Node-testable and parity-checkable against the backend. Spec 029's already-shipped `frontend/audit_labels.js` and `frontend/time_format.js` are reused — NOT duplicated — per spec 029 FR-019/FR-020 architectural test (which extends to this spec).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Section intentionally empty.
