# Implementation Plan: CAPCOM-Like Routing Scope (Single-AI Curated Channel)

**Branch**: `028-capcom-routing-scope` | **Date**: 2026-05-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/028-capcom-routing-scope/spec.md`

## Summary

Phase 3 routing-model expansion that adds visibility partitioning across the participant set — a category change from the existing eight routing scopes (which modulate turn frequency) to a ninth scope (`capcom`) that modulates what participants SEE. Mechanism: one alembic revision (024) adds `messages.kind`, `messages.visibility`, `sessions.capcom_participant_id`, the `participants(session_id) WHERE routing_preference='capcom'` unique partial index, and spec 005's `checkpoint_summaries.summary_scope` discriminator; a new last-step `_filter_visibility` stage in `ContextAssembler.assemble()` enforces FR-006 at the wire boundary; three facilitator-only endpoints (assign / rotate / disable) at `/sessions/:id/capcom/*` handle the role transitions transactionally; a `_validate_and_persist`-routed `capcom_relay` path flows the CAPCOM AI's curated forwarding through the spec 007 security pipeline; a two-tier summarizer (panel + capcom) emits scope-discriminated rows so the partition holds at summarization; an architectural test (`tests/test_028_architectural.py`) AST-scans `src/` for `messages.content` bypass reads and fails CI on additions outside the explicit five-entry allowlist; three WS events (`capcom_assigned`, `capcom_rotated`, `capcom_disabled`) keep all session subscribers in sync. Two new env vars (`SACP_CAPCOM_ENABLED`, `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN`) ship with V16 validators and `docs/env-vars.md` sections BEFORE `/speckit.tasks`; the master switch defaults `false` so existing deployments see no behavior change. Spec 011 UI amendments (CAPCOM badge, visibility indicator, facilitator assign UI, per-message visibility toggle) are deferred to implementation time per the `reminder_spec_011_amendments_at_impl_time` memory.

Technical approach: add the visibility filter as a pure function `_filter_visibility(messages, participant, capcom_id) -> list[ContextMessage]` invoked as the last step inside `ContextAssembler.assemble()` (`src/orchestrator/context.py`) immediately before `_secure_content` runs; the function consults the cached `capcom_participant_id` read at assemble-start from the sessions row. Add `src/web_ui/admin_capcom.py` carrying the three facilitator endpoints (`POST /sessions/:id/capcom/assign`, `POST /sessions/:id/capcom/rotate`, `DELETE /sessions/:id/capcom`); the module mounts only when `SACP_CAPCOM_ENABLED=true`. Extend `src/orchestrator/summarizer.py` (spec 005) with the two-tier emission when CAPCOM is assigned. Extend `src/web_ui/inject.py` (or equivalent inject handler) with the visibility-default selector consulting `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN` and the panel-AI-cannot-emit-capcom_only validator (INV-4). Extend `src/orchestrator/audit_labels.py` + `frontend/audit_labels.js` with the four new audit actions per the spec 029 paired-module pattern. Architectural test ships as `tests/test_028_architectural.py` per research.md §4. Migration `alembic/versions/024_capcom_routing_scope.py` ships all schema additions + indexes; `tests/conftest.py` schema mirror updates in the same task.

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. No new backend runtime dependencies. Frontend: no new third-party libraries — UI surfaces extend the existing single-file React SPA + UMD pattern; the spec 011 amendment slots are reserved for implementation-time wiring.
**Storage**: PostgreSQL 16. **One new alembic migration (024)** adds `messages.kind`, `messages.visibility`, `sessions.capcom_participant_id`, `ux_participants_session_capcom` unique partial index, `idx_messages_visibility` covering index, `checkpoint_summaries.summary_scope` discriminator, `ux_checkpoint_summaries_scope` unique index. **`tests/conftest.py` schema mirror updated in lockstep** per `feedback_test_schema_mirror` memory. No row migration logic — every existing row inherits the column DEFAULT.
**Testing**: pytest with the existing per-test FastAPI fixture (spec 012 US7). DB-bound tests follow the `tests/conftest.py` schema-mirror pattern. The architectural test (FR-019 / SC-009) is a Python-only AST scan over `src/`; runs without DB. The two-tier summarizer test exercises the spec 005 summarizer path against a fixture session containing mixed-visibility messages. The rotation transaction test verifies the unique partial index never trips on the swap sequence.
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm). Frontend changes extend `frontend/app.jsx` (CAPCOM badge on participant card, visibility indicator on transcript messages, facilitator assign/rotate/disable controls in the admin panel, per-message visibility toggle in the composer). UI work coordinates with spec 011 amendments at implementation time.
**Project Type**: Web service (single project; existing `src/` + `frontend/` + `tests/` layout).
**Performance Goals**:
- Visibility filter per dispatch P95 < 5ms for sessions with up to 1,000 messages (spec.md Performance Budgets). Implementation: O(M) list comprehension over the assembled context with one conditional check per message; participant-role + capcom_id read once at assemble-start.
- CAPCOM assignment / rotation / disable P95 < 200ms — one DB transaction with 1-2 row updates + one audit-log INSERT.
- Two-tier summarizer cost approximately 2× single-tier when CAPCOM is assigned (spec 005's existing pipeline runs twice per checkpoint). Budget falls through to spec 005 SC-002.
- WS event delivery P95 < 2s from endpoint commit to subscriber render (matches spec 022 SC-002).
**Constraints**:
- Default behavior MUST be unchanged: `SACP_CAPCOM_ENABLED=false` (default) returns HTTP 404 from all three CAPCOM endpoints AND treats every message as `visibility='public'` regardless of inputs (FR-021).
- V15 fail-closed: invalid env-var values exit at startup (V16); endpoint errors fail-closed.
- 25/5 coding standards (Constitution §6.10) + 25-line function cap.
- §4.13 [PROVISIONAL] inter-AI shorthand: the `capcom_relay` content surface IS AI-content (the CAPCOM AI's emission to the panel); the rule applies — relay content flows through spec 007's full pipeline including density-signal check (FR-019 of spec 028 + spec 004 §FR-020).
- §4.10 / V17 transcript canonicity: raw `capcom_only` messages stay in `messages` as the canonical record; the panel's view via `capcom_relay` is a derived artifact (the relay row references its source via the audit trail, not via a foreign key). Reviewers reconstruct CAPCOM-side context from the raw messages.
- §7 derived-artifact traceability / V18: `capcom_relay` rows are AI-derived from `capcom_only` source messages; the derivation method (CAPCOM AI's curated emission) is recorded by the audit envelope (every relay logged per FR-017) plus the message kind+visibility shape. Traceability is via timestamp + participant ordering, not via a per-row source-id FK.
**Scale/Scope**: Phase 3 ceiling of 5 participants per session. CAPCOM enables a 1-CAPCOM + N-panel topology where N is typically 2-4. Session message volumes follow the existing pattern; the visibility filter adds O(M) per dispatch which is well within budget at M=1000.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | CAPCOM is a routing-model addition; no participant API key, model choice, or budget surface is changed. Per-participant context-budget already scales by participant (no special CAPCOM tier — research.md §… equivalent / spec clarification #8). |
| **V2 No cross-phase leakage** | PASS | Phase 3 declared 2026-05-05. Topology 7 incompatibility flagged in spec §V12. No Phase 4 dependencies. |
| **V3 Security hierarchy** | PASS | The visibility partition is a STRUCTURAL security feature — it does not depend on a participant honoring a flag. FR-019 + the architectural test guarantee no code path bypasses the filter. `capcom_relay` content flows through spec 007's `_validate_and_persist` (FR-017) so curation is subject to the same security envelope as any AI output. |
| **V4 Facilitator powers bounded** | PASS | Three new facilitator-only endpoints (assign/rotate/disable). Each emits an `admin_audit_log` row. Facilitators cannot read `capcom_only` content directly — they see the partition via spec 010 debug-export (FR-024), which is itself audit-logged. |
| **V5 Transparency** | PASS | Audit-log records every CAPCOM lifecycle event. Routing-log captures every visibility-filter exclusion as `message_filtered_capcom_scope:excluded=<N>` (FR-023). Operators see the partition's effect per turn. |
| **V6 Graceful degradation** | PASS | Default `SACP_CAPCOM_ENABLED=false` preserves pre-feature behavior end-to-end (404 on endpoints, visibility forced public, `capcom` routing-preference rejected at write). Departure without replacement degrades to public-default (FR-022) rather than crashing the session. Disable preserves history invisibly (FR-011). |
| **V7 Coding standards** | PASS | Function bodies stay under 25 lines; new helpers respect 5-arg positional limit. The visibility filter is a single pure function; the assign/rotate/disable handlers each fit one function. |
| **V8 Data security** | PASS | `capcom_only` content is sensitive vis-à-vis non-CAPCOM AI participants — but is NOT sensitive in the at-rest encryption sense (it's still session conversation content). The partition is a routing-time invariant, not an at-rest encryption invariant. Spec 010 debug-export reflects visibility per FR-024 — non-CAPCOM views exclude `capcom_only` content even in the export. |
| **V9 Log integrity** | PASS | All log writes (`admin_audit_log`, `routing_log`) are INSERT-only. No UPDATE/DELETE. FR-010 explicitly forbids historical-attribution rewrite on rotation. |
| **V10 AI security pipeline** | PASS | `capcom_relay` flows through `_validate_and_persist` (FR-017). The CAPCOM AI is at the same trust tier as any AI participant; CAPCOM does NOT elevate trust. The relay action IS a privilege-elevating action (analogous to spec 024 promote-to-transcript) and is subject to the full pipeline plus the audit envelope (every relay logged). The 14th attack vector family (covert channel via curation) extends here; information-density signal (spec 004 FR-020 + spec 026 FR-018) applies to `capcom_relay` content. |
| **V11 Supply chain** | PASS | No new runtime dependencies. |
| **V12 Topology compatibility** | PASS | Spec §V12 enumerates topology 1-6 applicability (orchestrator owns the visibility partition); topology 7 incompatibility flagged (each MCP client controls its own context fetching; no orchestrator-side filter authority). |
| **V13 Use case coverage** | PASS | Spec §V13 maps to use cases §2 Research Co-authorship (primary), §3 Consulting Engagement (primary), §6 Decision-Making Under Asymmetric Expertise (primary). |
| **V14 Performance budgets** | PASS | Three budgets specified in spec §"Performance Budgets (V14)" — visibility filter < 5ms P95, assignment/rotation/disable < 200ms P95, two-tier summarizer ~2× single-tier. Filter timing falls through the existing context-assembly stage timing (spec 003 §FR-030); endpoint timings captured by the existing per-route latency middleware. |
| **V15 Fail-closed** | PASS | Master switch defaults false. Invalid env-var values exit at startup (V16). Panel-AI-cannot-emit-capcom_only validator returns HTTP 422 (FR-014 enforcement / INV-4). The architectural test (FR-019) fails CI on any new code path that reads `messages.content` outside the explicit allowlist. |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Two new env vars require validators + `docs/env-vars.md` sections BEFORE `/speckit.tasks` (FR-020). Validators land in this feature's task list T002-T003. |
| **V17 Transcript canonicity respected** | PASS | Raw `capcom_only` messages remain in `messages` as the canonical record. `capcom_relay` rows are AI-derived from those sources (the CAPCOM AI's curated emission) and tagged with `kind='capcom_relay'` so reviewers can distinguish derived from canonical. Rotation/disable does NOT mutate historical rows (FR-010 / FR-011 / INV-5). |
| **V18 Derived artifacts traceable** | PASS | `capcom_relay` is a derived artifact; traceability via timestamp + participant ordering in the raw transcript. The relay row's `kind='capcom_relay'` flags the derivation; reviewers walk backward through the CAPCOM AI's context-window at relay time (reconstructable from the visibility-filtered `messages` rows) to identify source content. |
| **V19 Evidence and judgment markers** | PASS | Spec uses [JUDGMENT] / drafted-as / [NEEDS CLARIFICATION] markers consistently; the 2026-05-14 clarify session resolved all 9 markers; no outstanding items. |

No violations. Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/028-capcom-routing-scope/
├── plan.md                           # This file (/speckit.plan command output)
├── research.md                       # Phase 0 output
├── data-model.md                     # Phase 1 output
├── quickstart.md                     # Phase 1 output
├── spec.md                           # Feature spec (Status: Draft, clarify session 2026-05-14 complete)
└── tasks.md                          # Phase 2 output (/speckit.tasks command - separate)
```

### Source Code (repository root)

```text
src/
├── orchestrator/
│   ├── context.py                    # extend `ContextAssembler.assemble()` with `_filter_visibility` as the last context-assembly step
│   ├── summarizer.py                 # extend with two-tier emission (panel + capcom) per FR-018
│   └── audit_labels.py               # add 4 new entries: capcom_assigned, capcom_rotated, capcom_disabled, capcom_departed_no_replacement
├── repositories/
│   ├── message_repo.py               # extend persistence to write kind + visibility; add panel-AI INV-4 validator at write-time
│   └── session_repo.py               # extend with capcom_participant_id setter helpers
├── web_ui/
│   ├── admin_capcom.py               # NEW — three facilitator endpoints (assign / rotate / disable); mounts only when SACP_CAPCOM_ENABLED=true
│   ├── inject.py                     # extend with visibility-default selector + INV-4 panel-AI validator
│   ├── events.py                     # add capcom_assigned / capcom_rotated / capcom_disabled WS emitters (broadcast to all session subscribers)
│   └── app.py                        # mount the admin_capcom router conditional on master switch
├── config/
│   └── validators.py                 # add 2 validators (SACP_CAPCOM_ENABLED, SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN)

frontend/                             # established UMD pattern per frontend_polish_module_pattern memory
├── audit_labels.js                   # mirror the 4 new entries (no scrub_value client-side)
└── app.jsx                           # extend — CAPCOM badge on participant card, visibility indicator on transcript messages, facilitator assign/rotate/disable controls, per-message visibility toggle in composer

alembic/versions/
└── 024_capcom_routing_scope.py       # NEW — single revision adding all schema changes (research.md §2)

tests/
├── test_028_migration.py             # NEW — migration shape, default values, partial-unique-index behavior
├── test_028_visibility_filter.py     # NEW — FR-006 filter behavior for panel/CAPCOM/human roles
├── test_028_inject_handler.py        # NEW — visibility default selector + INV-4 panel-AI validator
├── test_028_capcom_endpoints.py      # NEW — assign/rotate/disable shape, transactional integrity, master-switch 404
├── test_028_capcom_concurrency.py    # NEW — concurrent assign attempts; unique-index rejects second; FR-013 arrival-time attribution under rotation
├── test_028_two_tier_summarizer.py   # NEW — FR-018 panel + capcom row emission
├── test_028_capcom_relay_pipeline.py # NEW — FR-017 capcom_relay flows through _validate_and_persist
├── test_028_rotation_no_inherit.py   # NEW — FR-010 new CAPCOM context excludes prior capcom_only history; A's prior view doesn't survive
├── test_028_disable_no_promotion.py  # NEW — FR-011 historical capcom_only stays invisible after disable
├── test_028_departure_handling.py    # NEW — FR-022 capcom_departed_no_replacement on participant removal
├── test_028_routing_log_reason.py    # NEW — FR-023 message_filtered_capcom_scope reason emitted
├── test_028_debug_export.py          # NEW — FR-024 spec 010 export reflects visibility per participant
├── test_028_validators.py            # NEW — two env-var validators (SACP_CAPCOM_ENABLED, SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN)
├── test_028_architectural.py         # NEW — FR-019 AST scan; no messages.content bypass reads outside the 5-entry allowlist
├── test_028_ws_events.py             # NEW — capcom_assigned / capcom_rotated / capcom_disabled WS shapes + 2s delivery budget
└── conftest.py                       # extend — schema mirror update per feedback_test_schema_mirror

docs/
└── env-vars.md                       # add 2 new sections (V16 gate; FR-020)

scripts/
├── check_audit_label_parity.py       # existing — confirm the 4 new audit_labels entries land in both Python + JS mirrors
└── check_detection_taxonomy_parity.py # existing — allowlist the new message_filtered_capcom_scope reason
```

**Structure Decision**: Single Python service ("Option 1") consistent with the existing repo layout. Backend new module `src/web_ui/admin_capcom.py` follows the established pattern from spec 029 (`src/web_ui/admin_audit.py`) — endpoint clusters get their own module rather than crowding `app.py`. The visibility-filter is a single pure function inside `src/orchestrator/context.py` (NOT a new module) because the filter operates on the assembler's already-loaded message list and benefits from co-location with the assembler. Two-tier summarizer is a code change inside the existing `src/orchestrator/summarizer.py`. Frontend changes extend `frontend/app.jsx` per the established no-build-toolchain pattern; the `frontend/audit_labels.js` mirror gets the four new entries.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Section intentionally empty.
