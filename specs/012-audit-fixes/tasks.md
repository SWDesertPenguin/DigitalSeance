---

description: "Task list for feature 012-audit-fixes implementation"
---

# Tasks: Pre-Phase-3 Audit Cross-Cutting Deliverables

**Input**: Design documents from `/specs/012-audit-fixes/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: This feature DELIVERS test infrastructure (corpora, traceability, schema-mirror gate, integration marker, per-test app fixture). Tests of those deliverables are in scope as feature work, not as TDD verification of unrelated tasks. Per-deliverable meta-tests are listed inline within each user story.

**Organization**: Tasks are grouped by user story. Each story is independently testable per its spec acceptance scenarios.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Directory scaffolding and pytest configuration shared by all user stories.

- [X] T001 [P] Create `tests/fixtures/` directory with `.gitkeep`
- [X] T002 [P] Create `tests/integration/` directory with `__init__.py`
- [X] T003 [P] Create `docs/adr/` directory with placeholder `.gitkeep`
- [X] T004 [P] Create `docs/traceability/` directory with placeholder `.gitkeep`
- [X] T005 [P] Create `src/config/` directory with `__init__.py` (empty for now; T013/T014 populate it)
- [X] T006 Add `[tool.pytest.ini_options] markers = ["integration: requires real Postgres + orchestrator + LiteLLM"]` to `pyproject.toml` (FR-015 first half)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema additions used by US4 (override_reason) and US6 (per-stage timing columns) plus the conftest mirror that gates everything from US7's schema-mirror CI.

**CRITICAL**: No US4 or US6 implementation tasks can begin until this phase completes.

- [X] T007 Create alembic migration `alembic/versions/008_security_events_instrumentation.py` adding `route_ms`, `assemble_ms`, `dispatch_ms`, `persist_ms`, `advisory_lock_wait_ms` to `routing_log` + `layer_duration_ms`, `override_reason`, `override_actor_id` to `security_events` per [data-model.md](./data-model.md). All columns nullable; `downgrade()` body is `pass` (forward-only invariant).
- [X] T008 Update `tests/conftest.py` raw DDL to mirror the new columns from T007 (the schema-mirror CI gate from US7 will enforce this drift class going forward).

**Checkpoint**: Foundation ready — user stories can begin.

---

## Phase 3: User Story 1 - Hand-curated test corpora unblock detector regression coverage (Priority: P1) — MVP

**Goal**: Publish hand-curated `tests/fixtures/benign_corpus.txt` and `tests/fixtures/adversarial_corpus.txt` so detector regression tests across 007 / 008 / every perf checklist can land.

**Independent Test**: A new test imports both corpus files, asserts non-empty + expected category headers; the existing 007 sanitizer regression tests can be re-pointed at the corpora and continue to pass.

### Implementation for User Story 1

- [X] T009 [P] [US1] Create `tests/fixtures/benign_corpus.txt` with `# CATEGORY:` headers covering 7 benign categories (collaboration-prose, technical-prose, code-discussion, credential-placeholders, pure-script-non-latin, markdown-without-images, html-without-src) per [research.md](./research.md) Decision 4 (FR-001).
- [X] T010 [P] [US1] Create `tests/fixtures/adversarial_corpus.txt` with `# CATEGORY:` headers covering 18 adversarial categories: Round02 Cyrillic homoglyph (per `docs/red-team-runbook.md` incident), every sanitizer pattern group (ChatML, role markers, Llama [INST], HTML comments, override phrases, new-instructions, from-now-on), every supported credential pattern as separate categories (OpenAI, Anthropic, Gemini, Groq, JWT, Fernet), exfil markers (markdown-images, html-src, data-urls), and jailbreak phrases (FR-002).
- [X] T011 [P] [US1] Add `tests/test_corpus_fixtures.py` (placed flat under `tests/` matching repo convention) — 6 tests: structural checks (expected categories, non-empty), 3 detector smoke-tests (sanitizer / exfiltration / jailbreak categories trigger their respective detectors), strict 0% FPR guard against benign corpus.
- [X] T012 [US1] T012's "update one existing 007 test to consume the corpus" deliverable is satisfied by the 3 detector smoke-tests added in T011 — these consume the corpora by category and exercise the security pipeline end-to-end. Restructuring existing 007 test files is deferred to the 007-testability cluster (`fix/007-testability` per AUDIT_PLAN cluster index) where it naturally belongs.

**Checkpoint**: US1 functional. Corpus files exist; downstream detector regression work can begin.

---

## Phase 4: User Story 2 - Every SACP_* env var validated at startup (Priority: P1)

**Goal**: Implement V16 startup config validation across all SACP_* env vars; publish `docs/env-vars.md` catalog.

**Independent Test**: Set `SACP_CONVERGENCE_THRESHOLD=2.0` (or any other invalid value), start the app, assert non-zero exit before port bind. Run `python -m src.run_apps --validate-config-only` with valid config, assert exit code 0; with invalid, assert exit 1 with failing var name on stderr.

### Implementation for User Story 2

- [X] T013 [P] [US2] Create `src/config/validators.py` with per-var `validate_<var>() -> ValidationFailure | None` for the 10 actually-consumed SACP_* vars + `ConfigValidationError` exception holding `failures: list[ValidationFailure]` + `iter_failures()` generator + `VALIDATORS` tuple. Returning Optional[failure] (instead of raising per-validator) lets `validate_all()` aggregate every failure in a single pass (FR-004).
- [X] T014 [US2] Add `validate_all() -> None` orchestrator in `src/config/__init__.py` that drains `iter_failures()` and raises `ConfigValidationError` with the full list when non-empty (no early-exit per contracts/config-validator-cli.md).
- [X] T015 [US2] Modify `src/run_apps.py` to call `validate_all()` BEFORE `asyncio.run(_run())`; add `--validate-config-only` CLI flag via argparse — exits 0 on success ("config validation: OK (N vars validated)") / 1 on failure ("config validation: FAIL" + per-var reasons on stderr) per [contracts/config-validator-cli.md](./contracts/config-validator-cli.md). Inline (non-flag) invocation also runs validation and exits 1 if any var fails (FR-004).
- [X] T016 [P] [US2] Create `docs/env-vars.md` per [contracts/env-vars-doc.md](./contracts/env-vars-doc.md): 10 Validated entries + 2 Reserved entries (SACP_RATE_LIMIT_PER_MIN and SACP_DEFAULT_TURN_TIMEOUT — listed in debug-export `_CONFIG_KEYS` allowlist but not yet wired in app code). Each Validated entry documents Default / Type / Valid range / Blast radius / Validation rule / Source spec (FR-005, FR-010 first doc).
- [X] T017 [P] [US2] Create `scripts/check_env_vars.py` CI gate: scans src/ for `os.environ.get|environ[...]|getenv("SACP_*")` references, parses `### \`SACP_*\`` headings in docs/env-vars.md, parses `def validate_*` definitions in validators.py, fails CI if a code-referenced var has no doc section OR if a doc section references a `validators.validate_*` function that doesn't exist OR if a doc section is neither Reserved nor has a validator reference.
- [X] T018 [US2] Add `scripts/check_env_vars.py` to `.github/workflows/test.yml` as a pre-test step right after the traceability gate.
- [X] T019 [P] [US2] Add `tests/test_config_validators.py` (placed flat under tests/ matching repo convention) — 12 tests covering: --validate-config-only happy path, missing required var, multiple invalid vars (all reported single-run), bool/url/int/url-list per-validator unit tests, ConfigValidationError aggregates all failures.
- [X] T020 [US2] Add `docs/env-vars.md` authoritative-references entry to Constitution §13 Development & Operations table; bump constitution 0.7.0 → 0.7.1 PATCH per §14.5; update Sync Impact Report block at top of constitution.md.

**Checkpoint**: US2 functional. Invalid env vars now fail-closed at boot; deploy operators can validate config without starting the server.

---

## Phase 5: User Story 3 - FR-to-test traceability across all 11 specs (Priority: P1)

**Goal**: Publish `docs/traceability/fr-to-test.md` mapping every FR across specs 001–011 to ≥1 named test or `untested + Phase-N trigger`. CI gate enforces drift.

**Independent Test**: Reviewer opens the traceability artifact, finds any FR in any spec, sees either a resolvable test path or an explicit `untested + trigger` annotation. CI fails any PR adding a new FR without a traceability entry.

### Implementation for User Story 3

- [ ] T021 [US3] Create `docs/traceability/fr-to-test.md` with one section per spec (001–011); for each FR populate Tests column with discoverable test paths or `untested + <Phase-N trigger>` per [contracts/traceability-artifact.md](./contracts/traceability-artifact.md) (FR-003). Initial population is hand-curated (~10 sub-PRs acceptable). **Strictness rule**: the gate from T022 only checks specs that have a section in this artifact, so each per-spec PR adds its own section and turns the gate on for that spec.
- [X] T022 [P] [US3] Create `scripts/check_traceability.py` CI gate per [contracts/traceability-artifact.md](./contracts/traceability-artifact.md): every FR/SR marker in every spec section in the artifact has a traceability row; every test path resolves; every `untested` row has a non-empty trigger note. Per-spec opt-in via section presence (specs absent from the artifact are skipped — incremental rollout under T021).
- [X] T023 [US3] Add `scripts/check_traceability.py` to `.github/workflows/test.yml` as a pre-test step right after the schema-mirror gate.
- [X] T024 [P] [US3] Add `tests/test_traceability_check.py` (placed flat under `tests/` matching repo convention) — 7 meta-tests: artifact-absent skip; matching spec+artifact pass; missing FR row fails; extra FR row fails; `untested` without trigger fails; nonexistent test path fails; unpopulated spec is skipped (incremental rollout).

**Checkpoint**: US3 functional. Coverage gaps for any FR are queryable in <30 seconds (SC-005).

---

## Phase 6: User Story 4 - Resolve §4.9 secure-by-design override semantics (Priority: P2)

**Goal**: Hold the architectural review session, choose approach (a/b/c), implement the chosen approach, amend 007 §FR-005 + 011 review-gate UI flow + Constitution §4.9, bump Constitution to PATCH.

**Independent Test**: Integration test exercises the facilitator approve-edit-reject path end-to-end on a held draft that re-flags during re-validation; behavior matches the chosen approach.

**Note on scope**: 007 §FR-005 and 011 review-gate UI amendments are explicitly in scope under FR-006 (carveout from FR-017's "per-spec amendments out of scope"). Both ship on this feature branch, not on separate fix/<slug> branches.

### Implementation for User Story 4

- [ ] T025 [US4] Hold §4.9 architectural review session with security-aware reviewer in the loop; consult `docs/AI_attack_surface_analysis_for_SACP_orchestrator.md` §1–13, `docs/red-team-runbook.md` incident catalog, 007 §FR-013 fail-closed contract per [research.md](./research.md) Decision 1 preconditions. Record outcome (chosen approach + rationale) in `docs/adr/0002-secure-by-design-override-semantics.md` (FR-006 acceptance scenario 1).
- [ ] T026 [US4] Modify `src/security/pipeline.py` (or wherever `_validate_and_persist` lives) to call the security pipeline on the facilitator-approve path. Today the approve path bypasses; this is the core §4.9 implementation (FR-006).
- [ ] T027 [US4] If approach (b) chosen: implement override-with-justification path in `src/security/review_gate.py`. On re-pipeline re-flag: write `security_events` row with `event_type='facilitator_override'`, `override_reason=<text>` (≥16 chars validated server-side), `override_actor_id=<facilitator_id>`, `layer='facilitator_override'`, `resolved=true`. Reject submissions where `override_reason` < 16 chars with HTTP 400 per [data-model.md](./data-model.md).
- [ ] T028 [US4] Modify 011 web-ui review-gate UI per chosen approach: textarea for justification on (b); loop indicator on (a); edit-only on (c). Frontend file: `src/web/static/app.jsx` review-gate component.
- [ ] T029 [US4] Amend `specs/007-ai-security-pipeline/spec.md` §FR-005 to be consistent with §4.9 + chosen approach (carveout from FR-017; in-scope under FR-006). Add `## Clarifications` entry citing this PR per Constitution §14.2.
- [ ] T030 [US4] Amend `specs/011-web-ui/spec.md` review-gate flow FR(s) to reflect UI change from T028 (carveout from FR-017; in-scope under FR-006). Add `## Clarifications` entry.
- [ ] T031 [US4] Amend `.specify/memory/constitution.md` §4.9 to drop the "implementation under architectural review" placeholder qualifier; bump to v0.7.1 PATCH per §14.5; update Sync Impact Report block.
- [ ] T032 [P] [US4] Add integration test in `tests/integration/test_secure_by_design.py` covering: held draft → facilitator approve → re-pipeline → re-flag → resolution per chosen approach (acceptance scenarios 2 + 4 per chosen path).
- [ ] T033 [P] [US4] Add 007 testability tests: re-pipeline-on-approve (every approach), override-loop retry-limit (a), override-with-reason persistence (b) — extend `tests/unit/test_security_pipeline.py` or new module.
- [ ] T034 [US4] Update `~/.claude/projects/.../memory/project_secure_by_design_question.md` status from `Scoped to feature 012-audit-fixes` to `Resolved (approach <chosen>) per PR #NNN`.

**Checkpoint**: US4 functional. §4.9 placeholder removed; constitution-vs-spec drift closed. SC-003 satisfied.

---

## Phase 7: User Story 5 - Canonical doc deliverables published (Priority: P2)

**Goal**: Publish 8 net-new canonical docs (env-vars, error-codes, ws-events, retention, state-machines, glossary, roles-permissions, compliance-mapping, operational-runbook) per [research.md](./research.md) Decision 10 ordering.

**Note**: `docs/env-vars.md` (T016) is delivered under US2 since it pairs with the V16 implementation. The remaining 7 docs land under US5.

**Independent Test**: For each doc, every term/code/state/event referenced in any spec.md appears in the corresponding canonical doc; missing entries are CI-failing.

### Implementation for User Story 5

- [ ] T035 [P] [US5] Create `docs/glossary.md` per [contracts/doc-deliverables.md](./contracts/doc-deliverables.md) initial entry list (FR-010, lands first per ordering).
- [ ] T036 [P] [US5] Create `docs/error-codes.md` per [contracts/error-codes-doc.md](./contracts/error-codes-doc.md) (FR-010).
- [ ] T037 [P] [US5] Create `docs/retention.md` per [contracts/doc-deliverables.md](./contracts/doc-deliverables.md): inventory all 15 persistent tables with retention policy / "indefinite + rationale" (FR-010).
- [ ] T038 [US5] Create `docs/state-machines.md` per [contracts/doc-deliverables.md](./contracts/doc-deliverables.md) covering all 12 state machines listed (FR-010). Depends on T035 for terminology cross-refs.
- [ ] T039 [US5] Create `docs/ws-events.md` per [contracts/ws-events-doc.md](./contracts/ws-events-doc.md) covering every event type (FR-010). Depends on T038.
- [ ] T040 [US5] Create `docs/roles-permissions.md` per [contracts/doc-deliverables.md](./contracts/doc-deliverables.md): full role × permission matrix (FR-010). Depends on T038.
- [ ] T041 [US5] Create `docs/compliance-mapping.md` aggregating GDPR / NIST / AI Act mappings per [contracts/doc-deliverables.md](./contracts/doc-deliverables.md) (FR-010). Depends on T037, T039, T040.
- [ ] T042 [US5] Create `docs/operational-runbook.md` (synthesis doc) per [contracts/doc-deliverables.md](./contracts/doc-deliverables.md) (FR-010). Depends on all prior docs in this phase.
- [ ] T043 [P] [US5] Create `scripts/check_doc_deliverables.py` presence-check CI gate per [contracts/doc-deliverables.md](./contracts/doc-deliverables.md): every doc named in FR-010 exists with non-zero size; greps `src/` for `event_type=` literals and HTTP status codes to assert coverage.
- [ ] T044 [US5] Add `scripts/check_doc_deliverables.py` to CI workflow; depends on T043.
- [ ] T045 [P] [US5] Update `.specify/memory/constitution.md` §13 with authoritative-references entries for all 7 new docs from this phase (env-vars.md was added under T020); single Constitution PATCH bump.

**Checkpoint**: US5 functional. SC-002 satisfied (all named doc deliverables published).

---

## Phase 8: User Story 6 - Per-stage instrumentation backing V14 (Priority: P2)

**Goal**: Wire decorator-based per-stage timing capture for turn-loop (003 §FR-030) and security pipeline (007 §FR-020), populating the columns added in T007.

**Independent Test**: Fire a turn end-to-end; assert routing_log has populated `route_ms`, `assemble_ms`, `dispatch_ms`, `persist_ms`; assert security_events rows have populated `layer_duration_ms`.

### Implementation for User Story 6

- [X] T046 [P] [US6] Create `src/orchestrator/timing.py` exposing `with_stage_timing(stage_name)` async decorator + `start_turn()` / `get_timings()` / `record_stage()` / `reset()` helpers, all backed by a `ContextVar[dict[str, int] | None]` accumulator. Survives `asyncio.create_task` boundaries; record_stage is no-op outside a turn context (FR-007 per research.md Decision 7).
- [X] T047 [P] [US6] Add `tests/test_timing_decorator.py` (placed flat under `tests/` matching repo convention) — 6 tests: decorator records duration, records on raise, repeated calls accumulate, no-op outside turn context, ContextVar isolation across `asyncio.create_task`, microbenchmark overhead ≤ 200µs/call (CI-jitter-tolerant; research.md target 50µs).
- [ ] T048 [US6] **Deferred to follow-up**: wiring `@with_stage_timing` into actual stage call sites needs careful refactor of `src/orchestrator/loop.py` (note: file is `loop.py` not `turn_loop.py` from the original plan; stages live as module-level helpers `_check_route`, `_assemble_and_dispatch`, `_dispatch_and_persist`, `_validate_and_persist` rather than as class methods). Also requires adding `start_turn()` call at the top of `execute_turn` and reading `get_timings()` in the persist path to populate the `route_ms` / `assemble_ms` / `dispatch_ms` / `persist_ms` / `advisory_lock_wait_ms` columns added in alembic 008. Land in a focused refactor PR or as part of an ops-amendment cluster touching loop.py.
- [ ] T049 [US6] **Deferred to follow-up**: wiring per-layer timing into `src/security/pipeline.py` and writing `layer_duration_ms` on each `security_events` insert. Same shape as T048; bundle with that PR.
- [ ] T050 [P] [US6] **Deferred**: integration test landing alongside T048+T049; needs real DB to assert columns are populated end-to-end.

**Checkpoint**: US6 functional. SC-008 satisfied (per-stage timings on 100% of production-path turns).

---

## Phase 9: User Story 7 - CI/test infrastructure shared across specs (Priority: P3)

**Goal**: Schema-mirror CI gate, per-test FastAPI app fixture, integration-test CI tier, audit follow-through tracking.

**Independent Test**: Synthetic alembic migration with un-mirrored column → CI fails. Two tests with different middleware configs both pass without cross-contamination. `pytest -m integration` runs only integration tests.

### Implementation for User Story 7

- [X] T051 [P] [US7] Create `scripts/check_schema_mirror.py` per [contracts/schema-mirror-ci.md](./contracts/schema-mirror-ci.md): parse alembic SQL strings + conftest CREATE TABLE blocks into {table: cols} models, diff per-table column sets, exit 1 on drift. No DB dependency. Type-mismatch detection deferred (column-presence drift is the recurring bug class per `feedback_test_schema_mirror.md`). (FR-008)
- [X] T052 [P] [US7] Add `tests/test_schema_mirror.py` (placed flat under `tests/` to match existing convention rather than `tests/unit/` from the original plan) — 4 meta-tests: current repo state passes, synthetic drift exits 1 with column name in stderr, matching synthetic alembic+conftest pass, constraint-only lines (PRIMARY KEY / FOREIGN KEY) not mistaken for columns.
- [X] T053 [US7] Add `scripts/check_schema_mirror.py` to `.github/workflows/test.yml` as a pre-test step; runs before pytest so drift fails the build before any DB-backed test runs.
- [X] T054 [P] [US7] Add `mcp_app` and `web_app` per-test fixtures to `tests/conftest.py` returning a fresh `create_app()` / `create_web_app()` instance per test. Closes the recurring middleware-state-leak bug class (FR-009).
- [X] T055 [P] [US7] Add `tests/test_fastapi_app_isolation.py` (placed flat under `tests/` matching repo convention) — 4 tests: `mcp_app` is FastAPI instance, `app.state` markers don't leak across tests, two apps in same test are distinct objects.
- [ ] T056 [US7] **Deferred**: refactor pass updating ~14 existing test files that create their own `create_app()` inline to use the new `mcp_app` / `web_app` fixtures. Existing inline pattern is already correct (each test calls `create_app()` independently, so isolation holds); the fixture is a QoL/DRY improvement, not a correctness fix. Land incrementally (one test module per follow-up PR) or as part of the 006-testability cluster.
- [X] T057 [P] [US7] Create `AUDIT_FOLLOWTHROUGH.local.md` at repo root with markdown-table tracker per [data-model.md](./data-model.md). Pre-populated with rows for every cross-cutting item in `AUDIT_PLAN.local.md`; status flips as PRs land (FR-011).
- [X] T058 [US7] Add explicit `AUDIT_FOLLOWTHROUGH.local.md` entry to `.gitignore` (the existing `*.local.md` glob is implicit only — explicit entry matches the precedent set by `AUDIT_PLAN.local.md` and `FEEDBACK.local.md`).
- [X] T059 [US7] Split CI workflow `Run tests` step into `Run unit tests (fast tier)` (`pytest -m "not integration"`) and `Run integration tests (slow tier)` (`pytest -m integration`) — sequential within the same job (fast tier fails first if regressions hit; integration tier still runs to surface its own state). True separate-runner-pool tiering deferred to a follow-up that warrants its own CI ergonomics review (FR-015 second half; pairs with T006).

**Checkpoint**: US7 functional. Recurring schema-mirror bug class (memory `feedback_test_schema_mirror.md`) closed; integration tests separated from unit tests.

---

## Phase 10: User Story 8 - Phase-3-readiness process artifacts (Priority: P3)

**Goal**: Establish ADR convention with first retrospective ADR, pattern-list update workflow doc, threat-model freshness review process, spec versioning convention.

**Independent Test**: Each artifact exists per its contract; ADR convention demonstrated by reference example; pattern-list update workflow doc readable and actionable; threat-model review doc names cadence + triggers + ownership; spec versioning convention codified in Constitution.

### Implementation for User Story 8

- [X] T060 [P] [US8] Create `docs/adr/0001-fire-and-forget-summarization.md` retrospective ADR using MADR 4.0 lightweight format. Captures Phase 2's choice of fire-and-forget over synchronous-in-loop or synchronous-with-timeout-fallback for summarization — preserves 003 §FR-021 turn-loop never-halts invariant (FR-013).
- [X] T061 [P] [US8] Create `docs/pattern-list-update-workflow.md` codifying 007 §FR-017's four-step workflow: capture incident → PR within one cycle (corpus + regression test + pattern + runbook update) → verify zero-regression on broader corpus → land within one cycle. Plus ownership and trigger conditions (FR-012).
- [X] T062 [P] [US8] Create `docs/threat-model-review-process.md` per [research.md](./research.md) Decision 9: per-Phase-boundary review cadence + four trigger-based review conditions (new red-team incident category, new participant-side capability, dependency major-version with new attack surface, provider-disclosed regression) + ownership (FR-016).
- [X] T063 [US8] Add `### 14.8 — Spec versioning convention` to `.specify/memory/constitution.md` (placed AFTER §14.7 to preserve sequential numbering): header-block format `**Spec Version**: M.N.P | **Last Amended**: YYYY-MM-DD | **Amended In**: PR #NNN`, MAJOR/MINOR/PATCH semantics, retroactive-only application. Constitution version bumped 0.7.1 → 0.7.2 MINOR per §14.5 (assumes env-vars PR's 0.7.0 → 0.7.1 PATCH merges first; swap at rebase if order flips).
- [X] T064 [P] [US8] Add §13 entries for `docs/pattern-list-update-workflow.md`, `docs/threat-model-review-process.md`, and `docs/adr/` to the Development & Operations table.

**Checkpoint**: US8 functional. Phase-3-readiness conventions established; future contributors have one-place references for ADR / pattern-list update / threat-model review / spec versioning.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Verification that the feature as a whole satisfies its success criteria; closeout artifacts.

- [ ] T065 Walk through [quickstart.md](./quickstart.md) end-to-end on a clean checkout: validate config, look up an FR in traceability, run schema-mirror, exercise §4.9 override path, consult each new doc.
- [ ] T066 Run full test suite `pytest tests/unit/ && pytest -m integration`; assert no regressions vs. main.
- [ ] T067 Update `AUDIT_PLAN.local.md` cross-cutting checkboxes for items delivered via this feature (mark `[x]` for benign+adversarial corpus, FR-to-test traceability, conftest schema-mirror gate, per-test FastAPI app fixture, env-var contract consolidation, pattern-list update workflow, per-stage instrumentation, audit follow-through tracking, §4.9 secure-by-design implementation).
- [ ] T068 Add closeout entries in `AUDIT_FOLLOWTHROUGH.local.md` for each cross-cutting item delivered, including resolution PR + verifying test references.
- [ ] T069 [P] Sanity-check all CI gates green on a synthetic green PR: env_vars, traceability, schema_mirror, doc_deliverables.
- [ ] T070 Update spec status: change `**Status**: Draft` to `**Status**: Implemented` on `specs/012-audit-fixes/spec.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; T001–T005 fully parallel; T006 sequential (modifies `pyproject.toml`).
- **Foundational (Phase 2)**: Depends on Setup. T007 → T008 (sequential — conftest mirrors the migration).
- **User Stories (Phase 3+)**: All depend on Foundational completion.
  - US1, US3, US7 (process), US8 are independent of US4 / US6 (those need T007 schema columns).
  - US2 depends only on Setup (T005 created `src/config/`).
  - US5 (docs) is mostly independent but T039 (ws-events) and T040 (roles-permissions) depend on T038 (state-machines) for cross-refs; T041 (compliance) depends on T037/T039/T040; T042 (operational-runbook) depends on all prior US5 docs.
  - US4 and US6 depend on Foundational (T007).
- **Polish (Phase 11)**: Depends on all desired user stories complete. T067/T068 depend on prior phases for accurate closeout.

### User Story Dependencies

- **US1 (P1)**: No dependencies on other stories. MVP candidate.
- **US2 (P1)**: No dependencies on other stories. T020 (Constitution §13 update) can batch with T045 if landing same-day.
- **US3 (P1)**: No dependencies on other stories. Initial population (T021) can proceed incrementally per spec.
- **US4 (P2)**: Depends on T007 foundational migration. Architectural review session (T025) can be scheduled in parallel with US1/US2/US3 work; review outcome gates T026–T034.
- **US5 (P2)**: Internal ordering (state-machines → ws-events / roles-permissions → compliance → operational-runbook) per research.md Decision 10. No cross-story dependencies.
- **US6 (P2)**: Depends on T007 foundational migration (timing columns).
- **US7 (P3)**: T051–T053 (schema-mirror) ideally lands EARLY because T056 (refactor pass) depends on the new fixture from T054. T057–T058 (audit follow-through file) and T059 (CI tier split) are independent.
- **US8 (P3)**: All tasks independent; no cross-story dependencies.

### Within Each User Story

- US2: T013 + T014 → T015 (validators must exist before run_apps wires them); T017 / T019 [P] with T013/T014; T018 depends on T017.
- US4: T025 (review session) → T026 → T027 (only if (b)); T028 (UI) parallel to T029/T030 (spec amendments) once approach known; T031 (constitution PATCH) lands after spec amendments to avoid drift; T032/T033 (tests) parallel; T034 (memory update) lands after PR # is known.
- US5: see Phase 7 explicit ordering.
- US6: T046 + T047 → T048 / T049; T050 (integration test) after both T048 and T049.
- US7: T051 → T053 (CI integration); T054 → T056 (refactor uses fixture).

### Parallel Opportunities

- All Setup tasks T001–T005 [P] in parallel.
- Across stories: US1 (T009–T012), US2 (T013/T014/T016/T017/T019), US3 (T021/T022/T024) can land simultaneously after Foundational.
- Within US5: T035, T036, T037 fully parallel; T038/T039/T040/T041/T042 sequential per ordering.
- Within US6: T046, T047 [P]; T050 after T048/T049.
- Within US7: T051 / T054 / T057 [P]; T052 / T055 [P] with their respective implementations.
- Within US8: T060, T061, T062, T064 all [P]; T063 sequential (modifies constitution).

---

## Parallel Example: User Story 2

```bash
# Three independent threads in US2:
Task: "Create src/config/validators.py with per-var validate_*"        # T013
Task: "Create docs/env-vars.md per env-vars-doc.md schema"             # T016 [P]
Task: "Create scripts/check_env_vars.py CI gate"                       # T017 [P]

# Then:
Task: "Add validate_all() in src/config/__init__.py"                   # T014 (depends on T013)
Task: "Modify src/run_apps.py + add --validate-config-only"            # T015 (depends on T014)
Task: "Add tests/unit/test_config_validators.py"                       # T019 [P] with T015
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3 — the three P1 stories)

1. Complete Phase 1 Setup
2. Complete Phase 2 Foundational
3. Land US1 (corpus fixtures) — unblocks downstream detector regression work
4. Land US2 (env-var validation) — closes V16 gap
5. Land US3 (FR-to-test traceability) — closes review-cost gap
6. **STOP and VALIDATE**: Three P1 deliverables shipped; pre-Phase-3 readiness has its highest-leverage closes.

### Incremental delivery beyond MVP

7. US4 (§4.9 implementation) — schedule architectural review; gating decision lands ADR + 007/011 amendments + Constitution PATCH
8. US5 (doc deliverables) — land in research.md Decision 10 ordering
9. US6 (per-stage instrumentation) — closes V14 outstanding implementation
10. US7 (CI/test infrastructure) — institutionalizes recurring bug-class fixes
11. US8 (process artifacts) — Phase-3-readiness conventions

### Per-PR strategy

- Setup + Foundational: 1 PR.
- Each user story: 1+ PR. US5 in particular benefits from per-doc PRs (ordering matters; reviewer cost lower).
- US4 architectural-review session (T025) is a meeting, not a PR; T025's deliverable is the ADR PR.
- T029/T030 (007 + 011 spec amendments) land on this feature branch under FR-006 carveout (NOT on separate fix/<slug> branches per FR-017's exception clause).
- Polish-phase PRs (T065–T070) consolidate verification + closeout.

### Phase-3-readiness gating

After US1–US8 close, the spec status flips to Implemented (T070) and AUDIT_PLAN.local.md cross-cutting items show `[x]`. Phase 3 begins on facilitator declaration per Constitution §14.7.

---

## Notes

- [P] tasks = different files, no cross-task dependencies.
- [Story] label maps to spec.md user stories (US1–US8).
- US4's 007 + 011 spec amendments are the documented carveout from FR-017 (in-scope under FR-006); all OTHER per-spec amendments derived from audit findings ship on `fix/<slug>` branches per Constitution §14.7.5 and are NOT in this task list.
- Avoid: vague tasks, same-file conflicts, cross-story coupling that breaks story independence.
- Commit per task or per logical group; `AUDIT_PLAN.local.md` checkboxes track per-finding progress separately from these task IDs.
