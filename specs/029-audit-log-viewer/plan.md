# Implementation Plan: Human-Readable Audit Log Viewer

**Branch**: `029-audit-log-viewer` | **Date**: 2026-05-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/029-audit-log-viewer/spec.md`

## Summary

Phase 3 facilitator-only audit-log surface delivered as a five-part mechanism: (1) a paginated read-only endpoint `GET /tools/admin/audit_log` returning decorated `admin_audit_log` rows (with display-name JOINs and registry-driven action labels) gated by FR-002 facilitator-only authorization and FR-018's `SACP_AUDIT_VIEWER_ENABLED` master switch; (2) an action-label registry `dict[str, dict[str, Any]]` paired backend Python + frontend JS modules with a hard CI parity gate enforcing key-set + label-string equality across the two; (3) a time-formatter pair (backend Python + frontend JS) producing identical UTC ISO-8601 with `Z` marker output for the same input timestamp, with a second CI parity gate; (4) a frontend `DiffRenderer` React component using Myers line-by-line as default with a per-row word-level toggle and locked size thresholds (≤50KB main thread, 50KB-500KB Web Worker via inline blob, >500KB raw display); (5) a role-filtered `audit_log_appended` WebSocket event delivered only to facilitator subscribers via `broadcast_to_session_roles(...)` carrying the same decorated row shape as the FR-001 endpoint. Sensitive `previous_value`/`new_value` are scrubbed server-side at endpoint and broadcast time when the registry entry's `scrub_value` flag is true (FR-014), so non-facilitator clients neither see the row over WS nor receive raw content if a server bug were to ever route the payload to them. Three new `SACP_*` env vars + V16 validators land before `/speckit.tasks`. A spec 011 amendment (already drafted on this branch) wires the SPA: entry-point button in the facilitator admin panel, panel route `/session/:id/audit`, filter controls, row-expansion-to-DiffRenderer, scrub-display fallback. Per FR-019, this spec ships `contracts/shared-module-contracts.md` to pin module paths, signatures, props, and threshold constants so specs 022 and 024 can amend at their own implementation times against a stable contract.

Technical approach: extend `src/repositories/log_repo.py` with a paginated decorated-row query against `admin_audit_log` (LEFT JOINs to `participants` for display names); introduce `src/orchestrator/audit_labels.py` as the action-label registry (single source of truth, `dict[str, dict[str, Any]]` with `label` + optional `scrub_value`); introduce `src/orchestrator/time_format.py` as the backend timestamp formatter producing ISO-8601-with-`Z`; ship the paired frontend modules as UMD files `frontend/audit_labels.js` and `frontend/time_format.js` (per the established `frontend_polish_module_pattern` precedent — NOT `src/web_ui/static/...` as the spec drafted, which doesn't match the no-build-toolchain CDN pattern in spec 011 FR-002); add the `DiffRenderer` JSX component to `frontend/app.jsx` (the main SPA) with a sibling `frontend/diff_engine.js` UMD module holding pure-logic Myers diff helpers and the size-threshold worker bootstrap; add the audit-log endpoint via a new `src/web_ui/admin_audit.py` module to keep `app.py` readable; emit `audit_log_appended` from `src/web_ui/events.py` immediately after `admin_audit_log` INSERT, role-filtered through the existing `broadcast_to_session_roles` helper from `src/web_ui/websocket.py`; ship `scripts/check_audit_label_parity.py` and `scripts/check_time_format_parity.py` as required CI steps; add three validators (`SACP_AUDIT_VIEWER_ENABLED`, `SACP_AUDIT_VIEWER_PAGE_SIZE`, `SACP_AUDIT_VIEWER_RETENTION_DAYS`) to `src/config/validators.py`; document each in `docs/env-vars.md` per V16. No alembic migration — the read-side surface adds no columns to existing tables.

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. No new backend runtime dependencies. Frontend: one new UMD-compatible Myers diff library — proposed `diff@5.x` (jsdiff) loaded via the existing CDN pattern (jsdelivr/unpkg) with SRI integrity attribute. Selection rationale + alternative considered in [research.md §2](./research.md).
**Storage**: PostgreSQL 16. **No schema changes.** Read-side surface against the existing `admin_audit_log` table (spec 002 §FR-014) with display-name JOINs to `participants`. Pagination is offset-based (`SACP_AUDIT_VIEWER_PAGE_SIZE` default 50). Retention cap (`SACP_AUDIT_VIEWER_RETENTION_DAYS`) applied via `WHERE timestamp >= NOW() - INTERVAL` in the query, default empty (no cap).
**Testing**: pytest with the existing per-test FastAPI fixture (spec 012 US7). DB-gated tests follow the `tests/conftest.py` schema-mirror pattern; no schema additions in this spec, so the mirror is unchanged. Frontend pure-logic modules tested under `tests/frontend/` via Node (per `frontend_polish_module_pattern`). Diff renderer worker behavior tested via Playwright under the spec 011 Phase F testability framework (the same browser-required path SR-001a uses).
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm). Frontend extends the existing single-file React SPA at `frontend/app.jsx` plus three new UMD modules under `frontend/`.
**Project Type**: Web service (single project; existing `src/` + `frontend/` + `tests/` layout).
**Performance Goals**:
- Panel load (initial fetch) P95 ≤ 500ms at sessions with up to 1,000 audit events. Single indexed `WHERE session_id = $1 ORDER BY timestamp DESC LIMIT $2 OFFSET $3` plus two LEFT JOINs to `participants` (PK lookup); both traces captured into structured logs per V14.
- WS push latency P95 ≤ 2s from `admin_audit_log` INSERT to facilitator-client render (matches spec 022 SC-002).
- Diff renderer P95 ≤ 100ms on the main thread for payloads ≤ 50KB; 50KB-500KB runs in a Web Worker; >500KB displays raw without computed diff.
- Filter application: O(N) over the loaded page where N ≤ page_size (default 50). Client-side; no server round-trip.
**Constraints**:
- Default behavior MUST be unchanged: `SACP_AUDIT_VIEWER_ENABLED=false` (default) returns HTTP 404 from the route AND hides the SPA admin-panel button (FR-018; SC-009-equivalent architectural test).
- V15 fail-closed: invalid env-var values exit at startup (V16); endpoint errors fail-closed (return 5xx with structured error, do not silently degrade to unfiltered display).
- 25/5 coding standards (Constitution §6.10) + 25-line function cap.
- §4.13 [PROVISIONAL] inter-AI shorthand: this spec touches no AI-content surface — clears the rule trivially.
- §4.10 / V17 transcript canonicity: read-only on `admin_audit_log` (a separate append-only log table, NOT the conversation transcript). FR-004 enforces read-only contract.
- §7 derived-artifact traceability / V18: `action_label` is a display-time derivation from the canonical `action` string; the registry mapping IS the derivation method, captured at write time alongside the action string in the response. The raw `action` field always accompanies the label in the API response so audit reviewers can walk back to the canonical value.
**Scale/Scope**: Phase 3 ceiling of 5 participants per session. Audit-event volume per session typically < 50 (Phase 1+2 shakedown produced 11 events across 31 turns); high-event sessions may reach the low hundreds. Pagination + filter scope handle that range without server-side pushdown (FR-012 v1 limitation).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | Audit log is operator-side data. No participant API key, model choice, budget, or prompt content is exposed. The viewer's facilitator-only access (FR-002) preserves the existing isolation boundary. |
| **V2 No cross-phase leakage** | PASS | Phase 3 declared 2026-05-05. No Phase 4 capabilities required; topology 7 incompatibility flagged in spec §V12 (orchestrator owns the audit log). |
| **V3 Security hierarchy** | PASS | Two security improvements landed at clarify time: server-side scrubbing on FR-001 endpoint output AND on FR-010 WS broadcast payload, role-filtered broadcast scope to facilitator subscribers only. Defenses don't depend on a client honoring a flag (matches §4.9 secure-by-design). |
| **V4 Facilitator powers bounded** | PASS | Read-only viewer endpoint (FR-004 explicit). No new admin powers. Authorization mirrors spec 010 §FR-2 facilitator-only access. |
| **V5 Transparency** | PASS | The audit log IS the transparency surface; the viewer makes it readable. FR-015 emits a WARN-level orchestrator log entry when an unregistered action is encountered, so registry drift is observable in operator logs. |
| **V6 Graceful degradation** | PASS | Default `SACP_AUDIT_VIEWER_ENABLED=false` preserves pre-feature behavior (HTTP 404, no SPA affordance). Diff renderer gracefully falls back to raw display above 500KB. Unregistered actions render `[unregistered: <raw_action>]`, never crash the panel. |
| **V7 Coding standards** | PASS | Function bodies stay under 25 lines; new helpers respect 5-arg positional limit. |
| **V8 Data security** | PASS | `previous_value` / `new_value` content is sensitive when the registry sets `scrub_value=true` (e.g., token rotations); FR-014 enforces server-side substitution to `"[scrubbed]"` before the value reaches the wire. Raw values remain available only via spec 010 debug-export (separate authorization, separate audit trail). |
| **V9 Log integrity** | PASS | FR-004 enforces read-only on `admin_audit_log`. No INSERT, UPDATE, or DELETE side effects. The viewer endpoint runs under the application DB role which is INSERT/SELECT-only on log tables (Constitution §6.2). |
| **V10 AI security pipeline** | PASS | No AI content involvement. The spec's content surface is operator-side audit data, not transcript content; trust tiers, spotlighting, and output validation do not apply. |
| **V11 Supply chain** | PASS-ON-DELIVERY | One new frontend dependency (`diff@5.x` via CDN with SRI integrity per spec 011 SR-001) — pin specific version + hash at task time. No new backend dependencies. |
| **V12 Topology compatibility** | PASS | Spec §V12 enumerates topology 1-6 applicability (orchestrator owns the audit log); topology 7 incompatibility flagged (each MCP client is its own audit boundary). |
| **V13 Use case coverage** | PASS | Spec §V13 maps to use cases §5 Technical Review and Audit (primary) and §3 Consulting (secondary). |
| **V14 Performance budgets** | PASS | Four budgets specified in spec §"Performance Budgets (V14)" with structured-log instrumentation hooks (panel-load query traced, WS push latency traced, diff-renderer threshold transitions traced, filter-application is client-side). |
| **V15 Fail-closed** | PASS | Master switch defaults false (operator opt-in); invalid env-var values cause startup exit (V16). Diff renderer thresholds are locked module constants — no per-call override path that could fail-open. |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Three new env vars require validators + `docs/env-vars.md` sections BEFORE `/speckit.tasks` (FR-017). Validators land in this feature's task list. |
| **V17 Transcript canonicity respected** | PASS | Spec is read-only on `admin_audit_log` (a distinct append-only log, NOT the conversation transcript). FR-004 enforces the contract. No transcript mutation, compression in place, or canonical replacement. |
| **V18 Derived artifacts traceable** | PASS | `action_label` is a display-time derivation from the canonical `action` string. The registry mapping (action → label) IS the derivation method; both the canonical `action` and the derived `action_label` ship in every API/WS payload, so reviewers can walk from label back to source action verbatim. |
| **V19 Evidence and judgment markers** | PASS | Spec uses [JUDGMENT] / drafted-as / [NEEDS CLARIFICATION] markers consistently; clarify session 2026-05-08 resolved 5 highest-impact markers (including one new security gap not in the original draft); 1 outstanding (English-only v1 localization, low impact, deferred). |

No violations. Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/029-audit-log-viewer/
├── plan.md                           # This file (/speckit.plan command output)
├── research.md                       # Phase 0 output
├── data-model.md                     # Phase 1 output
├── quickstart.md                     # Phase 1 output
├── contracts/                        # Phase 1 output
│   ├── audit-log-endpoint.md         # GET /tools/admin/audit_log shape + auth + pagination
│   ├── ws-events.md                  # audit_log_appended event shape + role-filter
│   └── shared-module-contracts.md    # FR-019 anchor for specs 022 / 024 to cite
├── spec.md                           # Feature spec (Status: Draft, clarify session 2026-05-08 complete)
└── tasks.md                          # Phase 2 output (/speckit.tasks command - NOT created here)
```

### Source Code (repository root)

```text
src/
├── orchestrator/
│   ├── audit_labels.py               # NEW — LABELS: dict[str, dict[str, Any]] registry; source of truth for action → {label, scrub_value}
│   └── time_format.py                # NEW — UTC ISO-8601-with-Z formatter; pairs with frontend/time_format.js for parity
├── repositories/
│   └── log_repo.py                   # extend with get_audit_log_page(session_id, offset, limit, retention_cap_days) returning decorated rows
├── web_ui/
│   ├── admin_audit.py                # NEW — GET /tools/admin/audit_log endpoint; auth + pagination + scrub-on-output
│   ├── events.py                     # add audit_log_appended emitter (role-filtered to facilitator subscribers)
│   └── app.py                        # mount the new admin_audit router
├── config/
│   └── validators.py                 # add 3 validators (SACP_AUDIT_VIEWER_ENABLED, _PAGE_SIZE, _RETENTION_DAYS)

frontend/                              # established UMD pattern per frontend_polish_module_pattern memory
├── audit_labels.js                   # NEW — UMD; mirrors src/orchestrator/audit_labels.py {key: {label}} (no scrub_value client-side)
├── time_format.js                    # NEW — UMD; mirrors src/orchestrator/time_format.py + secondary locale + relative-time formatters
├── diff_engine.js                    # NEW — UMD; Myers line + word diff helpers, size-threshold worker bootstrap (inline blob)
└── app.jsx                           # extend — add DiffRenderer React component, AuditLogPanel route, admin-panel "View audit log" button (spec 011 FR-025..FR-029 wiring)

scripts/
├── check_audit_label_parity.py       # NEW — required CI step; AST-parse frontend module, compare key-set + label string parity
└── check_time_format_parity.py       # NEW — required CI step; same fixed-input timestamp through both modules; assert equal output

tests/
├── test_029_audit_log_endpoint.py    # NEW — FR-001..FR-005 endpoint shape, pagination, facilitator-only auth, master-switch 404
├── test_029_action_label_registry.py # NEW — FR-006 registry shape; scrub_value default; CI gate failure mode
├── test_029_time_format_parity.py    # NEW — FR-009 cross-module identical output for fixed timestamps
├── test_029_ws_event.py              # NEW — FR-010 audit_log_appended emission, role-filter scope, payload shape, 2s budget
├── test_029_scrub.py                 # NEW — FR-014 server-side scrubbing at endpoint AND at WS broadcast
├── test_029_validators.py            # NEW — three env-var validators
├── test_029_unregistered_action.py   # NEW — FR-015 [unregistered: <raw>] display + WARN log
├── test_029_architectural.py         # NEW — FR-020 no parallel mapping outside src/orchestrator/audit_labels.py
└── frontend/
    ├── test_audit_labels.js          # NEW — Node-runnable; module loads, exports LABELS, label fields are strings
    ├── test_time_format.js           # NEW — Node-runnable; primary + secondary + relative formatters
    └── test_diff_engine.js           # NEW — Node-runnable; Myers line + word; threshold helpers (worker bootstrap not exercised in Node)

docs/
└── env-vars.md                       # add 3 new sections (V16 gate; FR-017)
```

**Structure Decision**: Single Python service ("Option 1") consistent with the existing repo layout. Backend modules cluster in `src/orchestrator/` per the project's established convention for utility-domain modules (mirrors `src/orchestrator/length_cap.py` from spec 025). Frontend modules ship under `frontend/` as UMD per the established `frontend_polish_module_pattern` (memory note 2026-05-07) — this corrects the spec's drafted `src/web_ui/static/...` paths, which don't match the no-build-toolchain CDN pattern in spec 011 FR-002. The DiffRenderer JSX component lives inline in `frontend/app.jsx` rather than a separate JSX file because the SPA is single-file by spec 011 FR-002; pure-logic helpers (Myers diff over text/JSON, threshold detection, worker bootstrap) factor out to `frontend/diff_engine.js` so they remain Node-testable. The new admin-audit endpoint earns its own `src/web_ui/admin_audit.py` module rather than crowding `app.py` (which is already substantial).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Section intentionally empty.
