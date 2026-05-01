# Feature Specification: Pre-Phase-3 Audit Cross-Cutting Deliverables

**Feature Branch**: `012-audit-fixes`
**Created**: 2026-04-30
**Status**: Draft
**Input**: User description: "audit fixes"

Phase 2 closed 2026-04-29; the pre-Phase-3 audit window is open. ~37 audits across 5 batches surfaced ~635 actionable findings tracked in `AUDIT_PLAN.local.md` (gitignored). Per Constitution §14.7.5, per-spec amendments derived from audit findings ship as standalone `fix/<slug>` branches and do NOT consume numbered feature slots. **This feature owns only the work that legitimately spans multiple specs and therefore does not fit any one of them**: cross-cutting consolidations (~12), new canonical doc deliverables (~9), CI/test infrastructure shared by multiple specs, and process artifacts (~4) that establish conventions for Phase 3 onward.

## Clarifications

### Session 2026-04-30

- Q: Should the V16 startup validators (US2) refuse-to-bind when a required-secret env var still contains an `.env.example` placeholder string after a copy-paste deploy? → A: Yes. `validate_database_url` and `validate_encryption_key` now reject any value containing `changeme`, `REPLACE_ME_BEFORE_FIRST_RUN`, or `generate-with-python-fernet` (case-insensitive substring match). The `.env.example` and `src/database/roles.sql` defaults use `REPLACE_ME_BEFORE_FIRST_RUN[_*]` as the canonical placeholder. The validator's failure message names the matching placeholder so the operator gets an actionable error ("contains placeholder 'changeme' — replace with a real secret") instead of a misleading downstream auth failure when bcrypt or Fernet rejects the wrong-shaped secret. (Audit finding H-04.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Hand-curated test corpora unblock detector regression coverage (Priority: P1)

A test author working on 007 ai-security-pipeline regression coverage needs hand-curated benign and adversarial corpora spanning every detection category. Today these fixtures don't exist; every audit batch references them as a missing prerequisite that blocks downstream test work.

**Why this priority**: Highest-leverage missing artifact across the entire audit sweep. Referenced by 007 §FR-019 (false-positive targets), 007 §FR-021 (adversarial), and every performance checklist's measurement requirement. Without these fixtures, regression tests for sanitization, credential detection, jailbreak detection, and homoglyph defense cannot be written, and false-positive rate measurement is impossible.

**Independent Test**: A new pytest module imports the corpus fixture files, asserts each is non-empty and contains expected category headers; a follow-up regression test runs the existing 007 sanitizer over the corpora and asserts category-level pass/fail counts.

**Acceptance Scenarios**:

1. **Given** a test author wants to add a homoglyph-injection regression test, **When** they reference `tests/fixtures/adversarial_corpus.txt`, **Then** the file exists, is hand-curated, and contains samples for the homoglyph category named in 007 §FR-021.
2. **Given** the false-positive-rate threshold (007 §FR-019) needs measuring, **When** a test runs the sanitizer over `tests/fixtures/benign_corpus.txt`, **Then** the false-positive rate is computable against the documented benign-content baseline.
3. **Given** a new detection category lands in 007 (e.g., a new credential pattern), **When** the corpus update workflow runs, **Then** both corpora gain corresponding samples within the same PR.

---

### User Story 2 - Every SACP_* env var validated at startup (Priority: P1)

A deploy operator misconfigures `SACP_CONVERGENCE_THRESHOLD=2.0` (out of valid range). Today the application accepts the value and produces undefined behavior; 004 Edge Cases documents this as "operator error; fail-closed semantics not specified" — a real gap. Constitution §12 V16 makes startup validation binding for every `SACP_*` env var.

**Why this priority**: V16 is binding for all current and future specs. Affects every deployed instance. Closing this gap requires a single coordinated effort spanning every spec that introduces an env var; piecemeal per-spec validation work would re-establish the same scattered surface the audit identified.

**Independent Test**: A pytest fixture sets an invalid value for any SACP_* var (or omits a required one), starts the app, asserts the process exits non-zero with a documented error message and no port bind. A separate test invokes `--validate-config-only` and asserts exit code 0 for valid config and non-zero for invalid.

**Acceptance Scenarios**:

1. **Given** any `SACP_*` env var has an out-of-range value, **When** the application boots, **Then** it exits with a clear error before binding any port.
2. **Given** a deploy-time smoke test wants to validate config without starting the app, **When** the operator runs `python -m src.run_apps --validate-config-only`, **Then** the process exits 0 if all vars validate, non-zero otherwise.
3. **Given** a developer is reviewing an env var, **When** they consult `docs/env-vars.md`, **Then** the var appears with default, type, valid range, blast radius, and fail-closed behavior on invalid value.
4. **Given** a future spec introduces a new `SACP_*` env var, **When** the spec is reviewed against V16, **Then** the var has documented validation rules before the spec can be approved.

---

### User Story 3 - FR-to-test traceability across all 11 specs (Priority: P1)

A reviewer triaging coverage gaps for an arbitrary FR across specs 001–011 needs to see, in one place, which test(s) cover it (or that no test covers it). Today this mapping doesn't exist; every audit batch names it as a missing artifact.

**Why this priority**: Single audit-doc artifact that subsumes ~10 per-spec traceability sub-items. Lowers ongoing review cost permanently. Reviewers currently re-derive the mapping every time a coverage question arises.

**Independent Test**: Run a script that parses every `specs/NNN/spec.md` and the test suite, and assert that every FR appears in the traceability artifact with either a named test path or an explicit "untested" tag plus rationale.

**Acceptance Scenarios**:

1. **Given** a reviewer is auditing 003 turn-loop coverage, **When** they consult the traceability artifact, **Then** every 003 FR shows the test path(s) covering it OR an explicit "untested + Phase-3 trigger" tag.
2. **Given** a new FR lands in any spec, **When** the PR adding the FR is reviewed, **Then** CI fails until the traceability artifact has a corresponding entry.

---

### User Story 4 - Resolve §4.9 secure-by-design override semantics (Priority: P2)

Constitution §4.9 currently carries a placeholder qualifier ("under architectural review"); 007 §FR-005 currently encodes the inverse position ("operator authority overrides defenses by design"). This drift is the most prominent known unresolved gap between Constitution and shipped specs.

**Why this priority**: This feature owns both the architectural review and its implementation. The review picks approach (a) re-pipeline-on-approve / (b) re-pipeline + explicit-override-with-justification / (c) defense-absolute (recommended: (b) per `project_secure_by_design_question.md`). Once chosen, the implementation surface is constrained: amend 007 §FR-005, code change in `_validate_and_persist`, possibly add `override_reason` field on `security_events`, possibly change 011 review-gate UI flow, drop placeholder qualifier from §4.9, bump Constitution to PATCH. P2 (not P1) because the review activity gates the implementation, but both stay inside this feature's window.

**Independent Test**: After the chosen approach lands, an integration test exercises the facilitator approve-edit-reject path end-to-end on a held draft that re-flags; assert the documented behavior matches the chosen approach.

**Acceptance Scenarios**:

1. **Given** the architectural review session has been held with a security-aware reviewer in the loop, **When** the review concludes, **Then** an approach (a/b/c) is recorded in the spec amendment for 007 §FR-005 with documented rationale.
2. **Given** the architectural review chooses approach (b), **When** a facilitator approves a held draft that re-flags, **Then** the UI demands a justification, the `security_events` row records `override_reason`, and `admin_audit_log` captures the override.
3. **Given** the architectural review chooses any approach, **When** §4.9 is updated, **Then** the placeholder qualifier is removed and Constitution version bumps to PATCH.
4. **Given** any approach is chosen, **When** 007 §FR-005 is reviewed, **Then** its language is consistent with §4.9 (no inverse-position drift).

---

### User Story 5 - Canonical doc deliverables published (Priority: P2)

A new contributor (or future maintainer, or compliance reviewer) wants a one-place definition for any term, retention policy, error code, role permission, state machine, or WebSocket event schema. Today these are scattered across 11 spec files; the audit identified each as a missing canonical doc.

**Why this priority**: Each doc unblocks future work but no single doc gates today's deploys. As a group, the docs are a Phase 3 prerequisite because Phase 3 design decisions depend on stable definitions.

**Independent Test**: For each doc, run a sanity script: every term/code/state/event referenced in any `specs/NNN/spec.md` must appear in the corresponding canonical doc; missing entries are CI-failing.

**Acceptance Scenarios**:

1. **Given** a reviewer encounters an unfamiliar term in a spec, **When** they consult `docs/glossary.md`, **Then** the term has a one-place definition.
2. **Given** an operator needs to understand retention for any persistent table, **When** they consult `docs/retention.md`, **Then** every table is listed with its policy or an explicit "indefinite + rationale" marker.
3. **Given** a developer is debugging a state-machine transition gap, **When** they consult `docs/state-machines.md`, **Then** each implicit state machine across the system has its states, valid transitions, and invalid-transition rejection behavior documented.
4. **Given** a frontend developer is building a new WebSocket consumer, **When** they consult `docs/ws-events.md`, **Then** every event has its payload schema documented with field types and ordering guarantees.
5. **Given** a compliance reviewer is mapping GDPR articles to controls, **When** they consult `docs/compliance-mapping.md`, **Then** GDPR articles 5/6/15/17/20/28/30/32/33/34/44 each map to specific FRs across specs.
6. **Given** an operator is responding to a 4xx error from the API, **When** they consult `docs/error-codes.md`, **Then** the status code maps to a documented JSON body shape.
7. **Given** a designer is adding a new role, **When** they consult `docs/roles-permissions.md`, **Then** the role × permission matrix shows what each existing role can do.
8. **Given** an on-call operator hits an unfamiliar incident, **When** they consult `docs/operational-runbook.md`, **Then** the relevant playbook is documented or explicitly deferred with trigger.

---

### User Story 6 - Per-stage instrumentation backing V14 (Priority: P2)

Constitution §12 V14 binds future specs to per-stage performance budgets, and PR #163 codified the contracts (003 §FR-030 stage timings into `routing_log`, 007 §FR-020 layer durations into `security_events`, 008 §FR-013 per-stage budget capture). The instrumentation that captures these timings is outstanding.

**Why this priority**: V14 is binding for new specs but not retroactively enforced today. Implementation closes the loop between the codified contract and observable behavior; without it, regressions are diagnosable only at aggregate, not per-stage.

**Independent Test**: Fire a turn end-to-end; assert `routing_log` row contains `route_ms`, `assemble_ms`, `dispatch_ms`, `persist_ms` columns populated with non-null durations; assert `security_events` rows include `layer_duration_ms`.

**Acceptance Scenarios**:

1. **Given** a turn dispatches successfully, **When** `routing_log` is inspected, **Then** per-stage timings are populated per 003 §FR-030.
2. **Given** the security pipeline runs end-to-end, **When** `security_events` rows are inspected, **Then** `layer_duration_ms` is populated per 007 §FR-020.
3. **Given** memoization caches are wired (008 §FR-011/FR-012), **When** the same prompt-tier or sanitized custom_prompt is requested twice, **Then** the second call hits cache (asserted via cache-hit metric).

---

### User Story 7 - CI/test infrastructure shared across specs (Priority: P3)

A test author hits one of several recurring infrastructure gaps: (a) middleware state leaking across tests because tests share a FastAPI app instance, (b) a column added via alembic migration not reflected in `tests/conftest.py` raw DDL only surfacing on CI, (c) integration tests mixed with unit tests in CI runtime making the suite slow, (d) audit findings without follow-through linkage between finding → resolution PR → verifying test.

**Why this priority**: Recurring bug class — alembic migrations not mirrored in `tests/conftest.py` raw DDL surface only on CI, not local; multiplicative cost over time as new tests and migrations land.

**Independent Test**: For each item, a synthetic test asserts the gate works: (a) two tests using different middleware configs both pass without cross-contamination, (b) a synthetic alembic migration adding an unmirrored column fails CI, (c) `pytest -m integration` runs only integration tests, (d) an audit finding can be traced to its resolution PR and verifying test via the tracking artifact.

**Acceptance Scenarios**:

1. **Given** an alembic migration adds a column not reflected in `tests/conftest.py` raw DDL, **When** CI runs, **Then** build fails with a documented error pointing to the drift.
2. **Given** two tests need different FastAPI middleware configurations, **When** both run in the same suite, **Then** neither leaks state into the other.
3. **Given** an operator runs `pytest -m integration`, **When** the suite executes, **Then** only integration tests run (separately from unit tests).
4. **Given** an audit finding is closed by a PR, **When** the follow-through artifact is consulted, **Then** the finding → PR → verifying test linkage is preserved.

---

### User Story 8 - Phase-3-readiness process artifacts (Priority: P3)

A future maintainer needs to understand: how Phase 2 architectural decisions were made (single-instance, fire-and-forget summarization, no token-bucket smoothing, deferred LLM-as-judge, CPU-only inference); how the pattern-list update workflow handles a red-team incident; when to refresh the threat model; how to mark a spec as "amended at version N." These are conventions, not features, but they unblock Phase 3 design.

**Why this priority**: Convention-establishing rather than capability-delivering. Useful but not gating immediate work.

**Independent Test**: Each convention has a sample artifact: an ADR exists for at least one Phase 2 decision; a contributing doc covers the pattern-list update workflow; a memory or doc captures threat-model freshness review cadence; a sample spec amendment uses the new versioning convention.

**Acceptance Scenarios**:

1. **Given** a new contributor wants to understand "why fire-and-forget summarization," **When** they consult the ADR log, **Then** the decision context, alternatives, and rationale are recorded.
2. **Given** a red-team incident produces a new pattern, **When** the contributor consults the pattern-list update workflow doc, **Then** the incident → PR-within-one-cycle → red-team-runbook-entry path is explicit.
3. **Given** a spec is amended substantively, **When** the spec's header is consulted, **Then** the versioning convention shows what version it's at and what changed.

---

### Edge Cases

- An audit finding identified mid-feature turns out to belong to a single spec — it is promoted out of this feature and ships on its own `fix/<slug>` branch per Constitution §14.7.5.
- A Phase-3 trigger condition is hit during this feature window (e.g., a new compliance regulation lands) — the new finding is in scope only if it's cross-cutting; per-spec triggers stay on amendment branches.
- The §4.9 architectural review surfaces a fourth approach not currently named (something other than a/b/c) — the new approach is in scope; the recommended starting point shifts but FR-006's deliverables (decision + implementation + Constitution PATCH) stand.
- The §4.9 architectural review session cannot be scheduled within the feature window because the security-aware reviewer is unavailable — the review escalates to facilitator decision with documented rationale; the chosen approach still ships within this feature.
- The audit window itself runs longer than expected — some doc deliverables (FR-010) may be deferred to Phase 3 explicitly with documented rationale rather than blocking the window from closing.
- A doc deliverable's source is in flux during the feature window (e.g., new state machine introduced) — the doc captures current state with a "next review" trigger.
- A cross-cutting consolidation turns out to be cheaper as per-spec piecemeal work — the cross-cutting framing is dropped and the work moves to per-spec amendment branches with a recorded rationale.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Project MUST publish a hand-curated `tests/fixtures/benign_corpus.txt` covering every detection category named in 007 §FR-019.
- **FR-002**: Project MUST publish a hand-curated `tests/fixtures/adversarial_corpus.txt` covering every detection category named in 007 §FR-021.
- **FR-003**: Project MUST publish a single FR-to-test traceability artifact mapping every FR across all 11 existing specs to ≥1 named test or an explicit "untested + trigger" tag.
- **FR-004**: Project MUST validate every `SACP_*` env var at process startup with documented type, valid range, and fail-closed semantics; invalid values MUST cause the process to exit before binding any port.
- **FR-005**: Project MUST publish `docs/env-vars.md` cataloging every `SACP_*` var with default, type, valid range, blast radius, and validation rule.
- **FR-006**: Project MUST hold the architectural review session for Constitution §4.9, choose among approaches (a) re-pipeline-on-approve / (b) re-pipeline + explicit-override-with-justification / (c) defense-absolute (recommended starting point: (b)), implement the chosen approach (code change in `_validate_and_persist`, possible `override_reason` field on `security_events`, possible 011 review-gate UI flow change), amend 007 §FR-005 to be consistent with §4.9, drop the placeholder qualifier from §4.9, and bump Constitution to PATCH. The architectural review activity is in scope for this feature.
- **FR-007**: Project MUST implement per-stage instrumentation backing 003 §FR-030 (stage timings into `routing_log`), 007 §FR-020 (layer durations into `security_events`), and 008 §FR-013 (per-stage budget capture).
- **FR-008**: Project MUST add a CI guard that fails build when an alembic migration adds a column not reflected in `tests/conftest.py` raw DDL.
- **FR-009**: Project MUST codify a per-test FastAPI app instance fixture in `tests/conftest.py` to prevent middleware state leaks between tests.
- **FR-010**: Project MUST publish each canonical doc deliverable in `docs/`:
  - `docs/glossary.md` (terminology consolidation across specs)
  - `docs/retention.md` (per-table retention policies)
  - `docs/state-machines.md` (state machine catalog)
  - `docs/ws-events.md` (WebSocket event schemas)
  - `docs/error-codes.md` (HTTP status → JSON body shape catalog)
  - `docs/roles-permissions.md` (role × permission matrix)
  - `docs/compliance-mapping.md` (GDPR / regulatory traceability aggregation)
  - `docs/operational-runbook.md` (operator-facing decisions across specs)
- **FR-011**: Project MUST add a lightweight audit-follow-through tracking artifact (column on existing closeouts OR `AUDIT_FOLLOWTHROUGH.local.md`) so audit-finding → resolution-PR → verifying-test linkage is preserved beyond the closing of an individual audit.
- **FR-012**: Project MUST publish a pattern-list update workflow contributing doc covering 007 §FR-017's incident → PR-within-one-cycle → red-team-runbook entry cycle.
- **FR-013**: Project MUST establish an ADR / decision log convention (`docs/adr/` or `docs/decisions.md`) and capture at least one Phase 2 retrospective decision as the reference example.
- **FR-014**: Project MUST establish a spec versioning convention (semantic-versioning analog for spec.md FR-NN amendments) and document it in Constitution §14 or a contributing doc.
- **FR-015**: Project MUST add an `integration` pytest marker and configure CI to run integration tests in a separate tier from unit tests.
- **FR-016**: Project MUST establish a threat-model freshness review process (cadence, trigger conditions, ownership) referenced from Constitution §13 or §14.
- **FR-017**: Per-spec amendments flowing from audit findings (e.g., adding FR-NN to 002, 003, etc.) are explicitly OUT OF SCOPE for this feature; they MUST ship on `fix/<slug>` branches per Constitution §14.7.5.

### Key Entities

- **Cross-cutting consolidation**: An audit finding affecting ≥2 existing specs that does not naturally belong to any one of them. Resolved as a single PR via this feature rather than per-spec piecemeal work.
- **Doc deliverable**: A new file in `docs/` aggregating information currently scattered across multiple spec files. Each is referenced from the spec(s) it aggregates via Constitution §13.
- **Audit follow-through record**: A triple `(audit-finding, resolution-PR, verifying-test)` preserved beyond the closing of an individual audit, so coverage of audit-derived work remains traceable.
- **Per-spec amendment**: Out of scope here per Constitution §14.7.5; handled on `fix/<slug>` branches as standard §14.2 spec amendments.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of named cross-cutting consolidation items in `AUDIT_PLAN.local.md` are either delivered or explicitly accepted-out-of-scope with recorded rationale by feature close.
- **SC-002**: 100% of named doc deliverables (FR-010 list) are published with at least one cross-reference from each spec.md they aggregate.
- **SC-003**: Constitution §4.9 placeholder qualifier is removed and 007 §FR-005 is brought into consistency with §4.9 (closing the most prominent constitution-vs-spec drift).
- **SC-004**: A new spec author can complete V16 env-var validation work for any future spec by referencing `docs/env-vars.md` as the canonical pattern in under 30 minutes.
- **SC-005**: A reviewer can answer "which test covers spec NNN's FR-X?" in under 30 seconds via the FR-to-test traceability artifact, for any spec/FR combination.
- **SC-006**: Phase 3 development is unblocked by facilitator declaration per Constitution §14.7 (no fixed-percentage gate).
- **SC-007**: 100% of new SACP_* env vars introduced in any future spec arrive with documented type/range/fail-closed semantics on first PR (verified by spec-review checklist).
- **SC-008**: Per-stage instrumentation captures non-null `route_ms`, `assemble_ms`, `dispatch_ms`, `persist_ms` (003) and `layer_duration_ms` (007) on 100% of production-path turns.

## Assumptions

- `AUDIT_PLAN.local.md` remains the gitignored source-of-truth tracking document for batch progress; this spec does not replace it but consumes its cross-cutting and doc-deliverable items.
- Per-spec amendments derived from audit findings flow through the standard §14.2 process on `fix/<slug>` branches (per Constitution §14.7.5), NOT through this feature.
- The §4.9 architectural review session is held within this feature window with a security-aware reviewer in the loop; the chosen approach (a/b/c or a documented alternative) and its implementation both ship before feature close.
- Phase 3 begins when the facilitator declares the audit window closed; there is no fixed-percentage completion gate per Constitution §14.7.
- Doc deliverables (FR-010) are written in markdown under `docs/` and referenced from the relevant spec.md files via Constitution §13's authoritative-references entry.
- Contributors update `AUDIT_PLAN.local.md` checkboxes as cross-cutting items land via this feature's PRs.
- The pre-Phase-3 audit window is open and active; this feature runs concurrently with the audits themselves rather than waiting for them all to land first.
- Per-spec testability/compliance/operations/reliability audits may produce findings that are reclassified as cross-cutting mid-window; reclassification is in scope and updates the audit plan accordingly.
- Constitution edits required to support this feature (e.g., bumping the version after FR-006 lands) follow the Sync Impact Report process per §14.5.
