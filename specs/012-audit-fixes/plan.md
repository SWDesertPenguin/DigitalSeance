# Implementation Plan: Pre-Phase-3 Audit Cross-Cutting Deliverables

**Branch**: `012-audit-fixes` | **Date**: 2026-04-30 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/012-audit-fixes/spec.md`

## Summary

Pre-Phase-3 audit window surfaced ~635 findings across 5 batches. Per Constitution §14.7.5, per-spec amendments ship on `fix/<slug>` branches. This feature owns the remainder: cross-cutting consolidations (~12), canonical doc deliverables (~9), V14/V16 instrumentation + validation, the §4.9 secure-by-design implementation surface, and Phase-3-readiness process artifacts (~4). Technical approach mixes (a) documentation under `docs/`, (b) test infrastructure additions to `tests/`, (c) targeted code changes in `src/security/` for §4.9 + per-stage instrumentation, (d) a startup config-validator under `src/config/`, and (e) a single alembic migration for `security_events.override_reason` (only if §4.9 lands as approach (b) or beyond).

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm); Markdown for doc deliverables
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest (existing — no new runtime deps)
**Storage**: PostgreSQL 16 (existing). One additive migration adds `security_events.override_reason TEXT NULL` if §4.9 review picks (b); per-stage timing columns on `routing_log` (`route_ms`, `assemble_ms`, `dispatch_ms`, `persist_ms`) and `security_events.layer_duration_ms` are FR-007 deliverables (003 §FR-030 / 007 §FR-020 already codified the contract; columns are net-new here).
**Testing**: pytest (existing) + new `tests/fixtures/{benign,adversarial}_corpus.txt`, new `pytest -m integration` tier, new `tests/conftest.py` per-test FastAPI app fixture, new schema-mirror CI gate (`scripts/check_schema_mirror.py` or equivalent).
**Target Platform**: Linux server (Docker Compose, slim-bookworm container)
**Project Type**: web-service (existing FastAPI orchestrator) + cross-cutting documentation + CI/test infrastructure
**Performance Goals**: V14 budgets per Constitution §12 — no regression on existing per-stage targets (003 §FR-030, 007 §FR-020, 008 §FR-013); the instrumentation itself is the deliverable that makes regressions diagnosable.
**Constraints**: V16 mandates startup config validation BEFORE any port bind; instrumentation MUST not increase per-stage P95 by more than 5%; doc deliverables MUST be referenced from each spec they aggregate; per-spec amendments are explicitly out of scope (Constitution §14.7.5).
**Scale/Scope**: ~12 cross-cutting items, 8 net-new docs, 4 process artifacts, 1 architectural review (§4.9), 1 alembic migration, 1 startup validator module, ~6 instrumentation injection points across `src/orchestrator/` and `src/security/`. Estimated ~25 PRs total spanning the audit window.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle gates

- **V1 Sovereignty preserved.** PASS — feature delivers cross-cutting docs and infrastructure; no change to participant model/key/budget/prompt flows. §4.9 implementation strengthens sovereignty by closing a defense bypass (operator authority no longer overrides defenses).
- **V2 No cross-phase leakage.** PASS — every deliverable is a Phase-2 retroactive close-out or Phase-3 prerequisite; no Phase-3 capability is required.
- **V3 Security hierarchy respected.** PASS — §4.9 implementation is a security improvement; nothing trades readability/style for correctness.
- **V4 Facilitator powers bounded.** PASS — §4.9 implementation CONSTRAINS facilitator authority (under approach (b), override demands recorded justification). No new facilitator capability is introduced.
- **V5 Transparency maintained.** PASS — instrumentation, audit follow-through, env-var docs, override-reason field all increase observability.
- **V6 Graceful degradation.** PASS-WITH-NOTE — V16 startup config validation is intentionally fail-closed at boot (refuse to bind port on invalid config). This is fail-closed-at-startup, not session halt. Once running, the session-level graceful-degradation guarantee is unchanged.
- **V7 Coding standards met.** PASS (defer to per-PR review).
- **V8 Data security enforced.** PASS — `override_reason` is content authored by the facilitator at override time and persisted to `security_events` (existing tier policy). No new data flow.
- **V9 Log integrity preserved.** PASS — per-stage instrumentation appends columns to existing log tables (`routing_log`, `security_events`). Append-only semantics unchanged.
- **V10 AI security pipeline enforced.** PASS — §4.9 implementation strengthens this. The pipeline now runs on the approve path instead of bypassing.
- **V11 Supply chain controls enforced.** PASS — no new runtime dependencies.
- **V12 Topology compatibility verified.** PASS — feature is foundational/cross-cutting per V13; deliverables apply to all 7 topologies. Doc deliverables (`docs/env-vars.md`, `docs/state-machines.md`, etc.) are topology-agnostic by construction. §4.9 implementation applies to topologies 1–6 (Phase 1+2); topology 7 is Phase 3+.
- **V13 Use case coverage acknowledged.** PASS — feature is foundational/cross-cutting (justification per V13 carveout). The audit work serves all 7 use cases by closing pre-Phase-3 gaps that block any of them.
- **V14 Performance budgets specified and instrumented.** PASS — this feature DELIVERS V14 instrumentation (FR-007). The instrumentation work itself is the binding deliverable; future specs inherit the gate.
- **V15 Security pipeline fail-closed.** PASS — §4.9 implementation aligns with V15 (fail-closed extends to defense-when-defense-itself-fails); the override path under (b) preserves the fail-closed property because the override is logged and auditable, not a silent bypass.
- **V16 Configuration validated at startup.** PASS — this feature DELIVERS V16 (FR-004 + FR-005). Implementation MUST validate every `SACP_*` var before binding any port.

### Section §14 (Change Management) gate

The §14.7.5 carveout — "audit work does NOT consume a numbered feature slot" — has a real interpretation tension here. See Complexity Tracking below for the rationalization (cross-cutting consolidations don't run against any one existing spec; they create new artifacts spanning multiple specs).

**Gate verdict**: PASS. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/012-audit-fixes/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 — §4.9 approach decision, ADR format, spec versioning convention, corpus organization
├── data-model.md        # Phase 1 — schema additions (override_reason, per-stage timing columns)
├── quickstart.md        # Phase 1 — how to run gates, consult docs, validate config
├── contracts/
│   ├── env-vars-doc.md          # Shape of docs/env-vars.md
│   ├── error-codes-doc.md       # Shape of docs/error-codes.md
│   ├── ws-events-doc.md         # Shape of docs/ws-events.md
│   ├── retention-doc.md         # Shape of docs/retention.md
│   ├── state-machines-doc.md    # Shape of docs/state-machines.md
│   ├── glossary-doc.md          # Shape of docs/glossary.md
│   ├── compliance-mapping-doc.md# Shape of docs/compliance-mapping.md
│   ├── operational-runbook-doc.md # Shape of docs/operational-runbook.md
│   ├── traceability-artifact.md # Shape of FR-to-test traceability output
│   ├── config-validator-cli.md  # Shape of --validate-config-only CLI contract
│   └── schema-mirror-ci.md      # Shape of conftest schema-mirror CI gate
├── checklists/
│   └── requirements.md  # Already passes
└── tasks.md             # Phase 2 — created by /speckit.tasks (not here)
```

### Source code (repository root)

```text
src/
├── config/                              # NEW — startup validator (FR-004)
│   └── validators.py                    # Per-var validation rules; --validate-config-only entrypoint
├── orchestrator/
│   └── turn_loop.py                     # MODIFIED — per-stage timing capture (003 §FR-030 instrumentation, FR-007)
├── security/
│   ├── pipeline.py                      # MODIFIED — re-pipeline on approve path (FR-006); per-layer duration capture (007 §FR-020, FR-007)
│   └── review_gate.py                   # MODIFIED — override_reason capture if (b) chosen (FR-006)
└── run_apps.py                          # MODIFIED — add --validate-config-only flag (FR-004)

tests/
├── conftest.py                          # MODIFIED — per-test FastAPI app fixture (FR-009)
├── fixtures/                            # NEW directory
│   ├── benign_corpus.txt                # NEW — 007 §FR-019 baseline (FR-001)
│   └── adversarial_corpus.txt           # NEW — 007 §FR-021 categories (FR-002)
├── integration/                         # NEW pytest -m integration tier (FR-015)
└── unit/

scripts/
├── check_schema_mirror.py               # NEW — CI guard for alembic ↔ conftest DDL (FR-008)
└── check_traceability.py                # NEW — CI guard for FR-to-test traceability (FR-003)

docs/                                    # 8 NEW doc deliverables (FR-010)
├── env-vars.md                          # FR-005, FR-010
├── error-codes.md                       # FR-010
├── ws-events.md                          # FR-010
├── retention.md                         # FR-010
├── state-machines.md                    # FR-010
├── glossary.md                          # FR-010
├── compliance-mapping.md                # FR-010
├── operational-runbook.md               # FR-010
├── pattern-list-update-workflow.md      # NEW — FR-012
├── threat-model-review-process.md       # NEW — FR-016
├── adr/                                 # NEW directory — FR-013
│   └── 0001-fire-and-forget-summarization.md  # First retrospective ADR
└── traceability/                        # NEW directory — FR-003
    └── fr-to-test.md                    # Per-spec FR → test mapping

alembic/versions/
└── 008_security_events_instrumentation.py  # NEW migration — adds override_reason (if (b)+ chosen) + layer_duration_ms + routing_log per-stage timing columns

(gitignored audit-followthrough tracker)  # NEW — FR-011 tracking artifact
```

**Structure Decision**: existing single-project layout (`src/`, `tests/`, `docs/`, `alembic/`, `scripts/`) — no restructuring. New directories (`tests/fixtures/`, `tests/integration/`, `docs/adr/`, `docs/traceability/`) sit alongside existing ones. The 8 net-new doc deliverables live at the top of `docs/` next to the existing 13 reference docs (per Constitution §13 authoritative-references entries that will be added on land).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Constitution §14.7.5 says audit work does NOT consume a numbered feature slot, yet this feature is on `012-audit-fixes`. | Cross-cutting consolidations (~12) and net-new doc deliverables (~9) span ≥2 existing specs each; they do not naturally belong to any one spec. The alternative — landing each as a `fix/<slug>` PR against an arbitrarily chosen spec — would scatter the same deliverable across multiple amendment branches, contradicting §14.7.4 ("cross-cutting findings are consolidated into single-PR resolutions"). The numbered slot exists specifically to coordinate the cross-cutting work that §14.7.5's "runs against existing specs" carveout does not cover. | Per-spec `fix/<slug>` PRs for items that legitimately belong to one spec (handled separately, OUT OF SCOPE here per FR-017). For items that span specs, no single-spec home exists, so per-spec branching would force arbitrary attribution. |
| §4.9 architectural review is in scope (FR-006) — not normally a feature deliverable. | The placeholder qualifier in §4.9 is a known constitution-vs-spec drift (`project_secure_by_design_question.md`); resolving it requires a security-aware reviewer in the loop. Pre-deciding outside this feature would split the implementation across two PRs — risking the review concluding then losing momentum before code lands. The user explicitly chose Option A in the spec clarification round to keep both inside this feature window. | Defer the architectural decision to a separate review-only PR, then implement here. Rejected because the user explicitly preferred a single-feature owner per the clarification round (Option A). |

## Phase 0 — Research

See [research.md](./research.md) for:

- §4.9 architectural approach (a/b/c) — recommendation + criteria for review-session decision
- ADR format choice (MADR / Y-statement / project-custom)
- Spec versioning convention (semantic-versioning analog)
- Test corpus organization (single file vs. per-category files)
- Audit follow-through mechanism (column on closeouts vs. separate file)

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md) — Schema additions for `security_events` and `routing_log`; per-test fixture state.
- [contracts/](./contracts/) — One file per external surface (8 doc deliverables + traceability artifact + CLI flag + CI gate).
- [quickstart.md](./quickstart.md) — How to run the new gates, consult the new docs, validate config at deploy time.
