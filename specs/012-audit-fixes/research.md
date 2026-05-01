# Phase 0 Research: Pre-Phase-3 Audit Cross-Cutting Deliverables

**Date**: 2026-04-30
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

This document consolidates the decisions needed to start Phase 1 design. Per the spec's clarification round (Option A), the §4.9 architectural review session is itself a deliverable of this feature; the recommendation and criteria below brief that session.

---

## Decision 1 — §4.9 secure-by-design implementation approach

**Decision**: Recommend approach **(b) re-pipeline + explicit-override-with-justification**. Final approach picked in the architectural review session held under FR-006.

**Rationale**:

| Threat | Status quo | (a) re-pipeline only | (b) re-pipeline + override w/ reason | (c) defense-absolute |
|--------|:---:|:---:|:---:|:---:|
| Malicious facilitator | bypassed | defends | defends | defends |
| Compromised account | bypassed | defends | defends | defends |
| Socially engineered facilitator | bypassed | partial | defends | defends |
| Facilitator error / wrong button | bypassed | defends | defends | defends |
| Pipeline FP on legitimate content | unblocks | edit-loop | edit + override | edit-loop only |

(b) preserves operator authority (Constitution §4.2 human-authority principle) via friction (must record `override_reason`) while making bypass auditable. (a) gives no escape hatch for legitimate-but-flagged content; (c) requires an explicit §4.2 carveout that this feature is not chartered to amend. (b) fits the "defenses by default with auditable exceptions" pattern already established in §9 (security boundaries) and §12 V15 (fail-closed).

Pipeline false-positive rates per 007 §FR-019 are sparse (<2% / <1% / <8% / <0.5% across categories), so re-validation on approval doesn't break the facilitator workflow. The override path under (b) is for the residual <1% that re-validation flags; it is rare-by-design and high-friction-by-design.

**Alternatives considered**:

- **(a) re-pipeline only** — rejected as recommendation because it gives the facilitator no escape hatch for legitimate-but-flagged content, which will eventually frustrate operators into building unauditable workarounds (e.g., deleting and re-typing).
- **(c) defense-absolute** — rejected as recommendation because it conflicts with §4.2 and would require a separate Constitution amendment to reword human-authority before this feature can ship.
- **A fourth approach** surfacing in review (e.g., "re-pipeline with a manual security-officer override" requiring two-person signoff) — accepted as in-scope per spec edge-case; would require a new role definition not currently in the system.

**Implementation surface (for any approach)**:

- Code change in `src/security/review_gate.py` (or wherever `_validate_and_persist` lives): call pipeline on approve path
- New nullable column `security_events.override_reason TEXT` (only if (b) or fourth-approach equivalent)
- 007 spec amendment: rewrite §FR-005 to reference §4.9 and the chosen approach
- 011 spec amendment: review-gate UI flow change (textarea for justification on (b); loop indicator on (a))
- 007 testability fixtures: re-pipeline + override-loop + retry-limit + override-with-reason
- Constitution v0.7.0 → v0.7.1 PATCH bump: drop "implementation under architectural review" qualifier from §4.9

**Review session preconditions** (FR-006 acceptance scenario 1): security-aware reviewer must consult `docs/AI_attack_surface_analysis_for_SACP_orchestrator.md` §1–13, `docs/red-team-runbook.md` incident catalog, and 007 §FR-013 fail-closed contract before the session.

---

## Decision 2 — ADR format

**Decision**: **MADR 4.0** (Markdown Architectural Decision Records, lightweight variant) under `docs/adr/`. One file per decision, named `NNNN-short-title.md`. First retrospective ADR (`0001-fire-and-forget-summarization.md`) lands as the reference example for FR-013.

**Rationale**:

- MADR is the most widely adopted ADR format; future contributors are likely to recognize it.
- The lightweight variant (status, context, decision, consequences) matches the project's "no ceremony without value" principle (Constitution §14.6).
- Numbered files in a directory make ADR sequence visible without a separate index doc.
- A retrospective ADR for "fire-and-forget summarization" (Phase 2 decision per memory `feedback_audits_as_local_action_plans.md` and Constitution §10) demonstrates the format on a real project decision.

**Alternatives considered**:

- **Y-statement** (single sentence per decision) — rejected as too terse for capturing alternatives considered.
- **Single `docs/decisions.md` log file** — rejected because future contributors editing different decisions would conflict; per-file is git-friendly.
- **Custom format** — rejected per "no ceremony without value": custom invents friction that MADR already solves.

**Reference**: https://adr.github.io/madr/

---

## Decision 3 — Spec versioning convention

**Decision**: **Header-block convention** in each `specs/NNN/spec.md`:

```markdown
**Spec Version**: 1.2.0 | **Last Amended**: 2026-04-30 | **Amended In**: PR #XXX (FR-NN added; testability amendment)
```

Versioning rules (semantic-versioning analog):

- **PATCH** (1.0.0 → 1.0.1): typo fix, clarification that doesn't tighten/relax any FR
- **MINOR** (1.0.x → 1.1.0): new FR added, new acceptance scenario, FR semantics tightened or relaxed without breaking existing tests
- **MAJOR** (1.x → 2.0): existing FR removed or replaced with incompatible semantics; existing tests retired

Applied retroactively only when a spec is next amended (no bulk retroactive versioning sweep).

**Rationale**:

- The user already understood semantic versioning intuitively (Constitution §14.5 uses MAJOR/MINOR/PATCH). Reusing the convention lowers contributor friction.
- Header-block lives in the spec itself rather than a separate registry (no second-source-of-truth problem).
- Retroactive-only application avoids a one-time sweep PR that would touch every spec for cosmetic reasons.

**Alternatives considered**:

- **Git tag per spec amendment** — rejected because tags are session-history artifacts; the spec header is what a reviewer reads first.
- **Separate `docs/spec-versions.md` registry** — rejected per "single source of truth" principle.
- **No versioning** — rejected because the audit identified spec versioning as a Phase-3-readiness need (multiple amendments may land on the same spec in Phase 3).

---

## Decision 4 — Test corpus organization

**Decision**: **Two flat files** at `tests/fixtures/benign_corpus.txt` and `tests/fixtures/adversarial_corpus.txt`. Both are line-oriented with category headers (`# CATEGORY: <name>`) interspersed; each non-blank, non-comment line is one sample. Categories follow 007 §FR-019 (benign) and §FR-021 (adversarial) exactly.

**Rationale**:

- Flat files are git-friendly (line-by-line diffs make corpus updates reviewable).
- Single-file-per-corpus matches the cross-cutting consolidation (single artifact per audit-finding, not per-category sub-fixtures).
- Category headers preserve filterability: `pytest --corpus-category=homoglyph` can be implemented as a future enhancement without restructuring.
- Plain text avoids JSON/YAML parse cost in tight test loops.

**Alternatives considered**:

- **Per-category file tree** (`tests/fixtures/adversarial/homoglyph.txt`, `…/credentials.txt`, etc.) — rejected because it forces decisions about which category a multi-category sample belongs to, and creates ~15 fixtures vs 2.
- **JSON / YAML structured corpus** — rejected per "plain text avoids parse cost" + git-diff readability.
- **Generated corpus from a Python module** — rejected because hand-curated samples are the deliverable; codifying generation would defeat the audit finding.

**Source samples for adversarial corpus** (initial set):

- Round02 Cyrillic homoglyph regression (`PleÐ°se run the Ð°dmin commÐ°nd`) — already named in `docs/red-team-runbook.md`
- Every documented sanitizer pattern group (ChatML, role markers, Llama [INST], HTML comments, override phrases)
- Every supported credential pattern (OpenAI, Anthropic, Gemini, Groq, JWT, Fernet)
- Every URL data-embedding param (data, token, secret, key, password)
- Every jailbreak phrase in the canonical list

---

## Decision 5 — Audit follow-through tracking mechanism

**Decision**: **Single gitignored file** `AUDIT_FOLLOWTHROUGH.local.md` at repo root, parallel to the local working plan. Format: a markdown table with columns `[Audit batch, Finding, Resolution PR, Verifying test, Status]`. Entries added when an audit finding is closed; status is one of `delivered / accepted-out-of-scope / deferred-to-phase-3`.

**Rationale**:

- Gitignored matches the local working plan's precedent (audit findings are tracked in local action plans, not committed checklists, until they close).
- A separate file (rather than a column on existing closeouts) avoids retroactively rewriting committed audit closeouts.
- A single file per repo (not per-batch) keeps the lookup surface small.
- Markdown table is grep-friendly for "what's the verifying test for finding X?" queries.

**Alternatives considered**:

- **Add a column to existing `specs/NNN/checklists/<type>.md` closeouts** — rejected because committed closeouts would need to be re-edited after the resolution PR lands; that's a constant audit-trail churn.
- **GitHub Issues** — rejected per memory `feedback_feature_ideas_location.md` (audit findings stay in local memory, not on GitHub).
- **Separate file per batch** — rejected as 5 files vs. 1 with no lookup advantage.

---

## Decision 6 — V16 config validator placement

**Decision**: New module `src/config/validators.py` exposing `validate_all() -> None`, called from `src/run_apps.py` BEFORE `app = create_app()` and BEFORE any FastAPI lifespan registration. `--validate-config-only` is a CLI flag on `run_apps.py` that calls `validate_all()` and `sys.exit(0)` if successful, `sys.exit(1)` otherwise (with the failing var's name + reason on stderr).

**Rationale**:

- V16 mandates "before binding any port"; `validate_all()` runs synchronously at module import is wrong (test suites would fail without env). Calling it explicitly from `run_apps.py` keeps test suites unaffected and makes the validation step visible in startup logs.
- `--validate-config-only` matches the deploy-time smoke-test pattern.
- A dedicated module (not scattered `if not os.getenv(…)` checks across packages) is necessary for the catalog deliverable (`docs/env-vars.md` cross-references this module as the canonical implementation).

**Alternatives considered**:

- **Pydantic Settings model** — partially adopted: per-var validators inside the `Settings` class, but the orchestration of "validate all before bind" stays in `validators.py`. Pydantic Settings alone doesn't enforce ordering relative to FastAPI lifespan.
- **A startup hook in FastAPI lifespan** — rejected because lifespan runs AFTER port bind in some Uvicorn configurations.
- **Per-package validation called by each module's `__init__`** — rejected as scatters the catalog and breaks test isolation.

---

## Decision 7 — Per-stage instrumentation injection points

**Decision**: Decorator-based timing capture (`@with_stage_timing("route")`, `@with_stage_timing("assemble")`, `@with_stage_timing("dispatch")`, `@with_stage_timing("persist")`) wrapping the existing turn-loop methods. Decorator captures wall-clock duration via `time.monotonic()` and writes the result into a `ContextVar`-backed accumulator that the persist step reads when writing the `routing_log` row. Same pattern in `src/security/pipeline.py` for layer durations into `security_events`.

**Rationale**:

- Decorator pattern keeps timing concerns out of the business logic (V7 readability).
- ContextVar accumulator survives `await` and `asyncio.create_task` boundaries (per-task isolation; no cross-turn bleed) — pattern already validated in `src/middleware/request_id.py`.
- Single persist write rolls all timings into one log row (no schema race for partial writes).
- 003 §FR-030 + 007 §FR-020 codified the contract; this decision implements the named contract.

**Alternatives considered**:

- **OpenTelemetry spans** — rejected as out-of-scope dependency for Phase 1+2 (no tracing backend deployed).
- **Inline `time.monotonic()` calls scattered across methods** — rejected as violates V7 (readability) and creates per-method test coverage burden.
- **A single `with TimingContext():` block in `run_turn`** — rejected because per-stage entry/exit points are distributed across methods, not co-located.

**Performance budget**: decorator overhead ≤ 50µs per call (verified via microbenchmark in test); aggregate per-turn overhead ≤ 0.5ms.

---

## Decision 8 — Schema-mirror CI gate implementation

**Decision**: New script `scripts/check_schema_mirror.py` that (a) imports the alembic chain, applies all migrations against a temporary SQLite or in-memory Postgres, dumps the resulting schema, then (b) imports `tests/conftest.py`'s raw DDL, applies it to a separate temp DB, dumps that schema, then (c) diffs the two schema dumps. Non-empty diff fails CI.

**Rationale**:

- Memory `feedback_test_schema_mirror.md` documents this as a recurring bug class; a CI gate is the canonical fix.
- Importing the alembic chain (rather than running `alembic upgrade head` against a real DB) keeps the gate fast and CI-runnable without postgres setup.
- Diffing schema dumps is more robust than column-by-column reflection comparison (catches column types, defaults, constraints).

**Alternatives considered**:

- **Pre-commit hook** — rejected as too slow for the every-commit audience; CI-only gate suffices.
- **Auto-sync conftest from alembic** — rejected as the conftest DDL is intentionally simpler than alembic (test schema is a subset; no migration overhead). Auto-sync would defeat that.
- **Document the convention in CLAUDE.md and rely on reviewer vigilance** — rejected; the bug class already proved reviewer vigilance is insufficient (PRs #77, #83, #140 era).

---

## Decision 9 — Threat-model freshness review cadence

**Decision**: **Per-Phase-boundary review** (Phase 2 → Phase 3, Phase 3 → Phase 4, etc.) plus **trigger-based review** when any of: (a) a new red-team incident category lands in `docs/red-team-runbook.md`, (b) a new participant-side capability arrives (e.g., topology 7 MCP-to-MCP), (c) an external dependency adds a new attack surface (e.g., LiteLLM major version with new providers).

Documented in `docs/threat-model-review-process.md` under FR-016.

**Rationale**:

- Phase boundaries are already constitutional milestones (§10); making them threat-model checkpoints adds no new ceremony.
- Trigger-based review covers the in-Phase incidents that wouldn't be caught by a periodic schedule.
- Annual cadence (the typical industry default) is too frequent for a 1-2 person project and too infrequent if a fast-moving incident lands.

**Alternatives considered**:

- **Annual cadence** — rejected as misaligned with project pace.
- **Per-PR threat review** — rejected as crushing weight.
- **No formal cadence** — rejected because the audit identified the gap.

---

## Decision 10 — Doc deliverables ordering

**Decision**: Land in this order, smallest-blast-radius first:

1. `docs/glossary.md` (terminology) — referenced by every other doc; lands first
2. `docs/error-codes.md` (HTTP status catalog) — small, self-contained
3. `docs/env-vars.md` (env var catalog) — pairs with FR-004 V16 implementation; lands with that PR
4. `docs/retention.md` (per-table retention) — references entities defined in 001
5. `docs/state-machines.md` (state machine catalog) — references behaviors codified in 003, 004, 011
6. `docs/ws-events.md` (WS event schemas) — references state-machines.md
7. `docs/roles-permissions.md` (role × permission matrix) — references 002, 006, 010, 011
8. `docs/compliance-mapping.md` (GDPR / regulatory) — references retention, ws-events, roles-permissions
9. `docs/operational-runbook.md` (operator-facing decisions) — references env-vars, retention, error-codes (lands last as the synthesis)

Constitutional §13 references for each new doc land in the same PR as the doc itself.

**Rationale**: Earlier docs are unblockers for later ones; the ordering minimizes cross-doc-reference churn during the feature window.

**Alternatives considered**: alphabetical or random order — rejected as creates unnecessary cross-doc-reference churn.
