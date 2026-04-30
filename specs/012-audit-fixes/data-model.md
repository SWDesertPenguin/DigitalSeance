# Phase 1 Data Model: Pre-Phase-3 Audit Cross-Cutting Deliverables

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

This feature is primarily documentation and infrastructure work; schema additions are minimal but real. All changes are additive (no DROP / ALTER existing-column) per Constitution §6 and §14.7.4.

---

## Schema additions (single migration)

**Migration**: `alembic/versions/008_security_events_instrumentation.py`

### `routing_log` — per-stage timing columns

| Column | Type | Nullability | Default | Source |
|---|---|---|---|---|
| `route_ms` | INTEGER | NULL | NULL | 003 §FR-030 |
| `assemble_ms` | INTEGER | NULL | NULL | 003 §FR-030 |
| `dispatch_ms` | INTEGER | NULL | NULL | 003 §FR-030 |
| `persist_ms` | INTEGER | NULL | NULL | 003 §FR-030 |
| `advisory_lock_wait_ms` | INTEGER | NULL | NULL | 003 §FR-032 |

**Validation rules**:

- All five columns are nullable to permit backfill of existing rows during migration without a data-migration step.
- Values MUST be non-negative integers (millisecond counts). Enforced at write time in `src/orchestrator/turn_loop.py`, not as a DB constraint (per Constitution §6 — DB enforces structure; application enforces semantics).
- `route_ms + assemble_ms + dispatch_ms + persist_ms ≤ pipeline_total_ms` (consistency check; not enforced at DB level — verified in tests).

### `security_events` — per-layer timing + override audit

| Column | Type | Nullability | Default | Source |
|---|---|---|---|---|
| `layer_duration_ms` | INTEGER | NULL | NULL | 007 §FR-020 |
| `override_reason` | TEXT | NULL | NULL | §4.9 (b)/(b'-equivalent only) — FR-006 |
| `override_actor_id` | UUID | NULL | NULL | §4.9 (b) — FR-006; references `participants.id` |

**Validation rules**:

- `layer_duration_ms` non-negative; written at the close of every layer call in `src/security/pipeline.py`.
- `override_reason` populated ONLY when `event_type='facilitator_override'`; non-NULL value MUST be ≥ 16 characters (prevents low-friction "ok" / "test" overrides) and ≤ 4000 characters (length cap; enforced in `src/security/review_gate.py`).
- `override_actor_id` non-NULL when `override_reason` is non-NULL; references the facilitator who issued the override. FK to `participants.id` with ON DELETE SET NULL (preserves audit trail when the actor is later removed, per 001 §FR-019 audit-log retention semantics).
- A new event type `event_type='facilitator_override'` joins the existing enumeration (sanitization, credential_detected, jailbreak_detected, pipeline_error, etc.). No DDL change to the column itself (it is a free-form VARCHAR per existing schema); the new value is documented in `docs/error-codes.md` and reflected in the application's event-type literal.

### `tests/conftest.py` raw DDL — mirror update

The same five `routing_log` columns and the three new `security_events` columns are added to `tests/conftest.py`'s raw DDL block. The new schema-mirror CI gate (FR-008) will fail any future PR that updates the alembic migration without updating conftest.

---

## State transitions

### `security_events` — facilitator-override path (FR-006, approach (b))

Existing flow (Phase 2): facilitator reviews held draft → approves → content persists verbatim, bypassing the pipeline.

New flow (after this feature):

```text
held_draft (security_events row, layer='output_validation', resolved=false)
  ↓ facilitator approves
[NEW] re-pipeline runs on the approved content
  ├── re-pipeline PASSES → persist content + UPDATE security_events SET resolved=true, resolution='approve_clean'
  └── re-pipeline RE-FLAGS → choice point (per chosen approach):
      ├── (a) → return to edit-loop; held state survives; UPDATE security_events SET resolution='approve_reflagged_edit_required'
      ├── (b) → require justification textarea; on submit:
      │         INSERT new security_events row (event_type='facilitator_override',
      │           override_reason=<text>, override_actor_id=<facilitator_id>,
      │           layer='facilitator_override', resolved=true)
      │         persist content
      │         UPDATE original security_events SET resolved=true, resolution='approve_overridden'
      └── (c) → reject the approve action; UI returns to edit-loop only
```

Invalid transitions:

- Facilitator cannot override their own previously-approved content within the same draft (the override row is final; further edits start a new draft).
- A non-facilitator participant cannot trigger the override path (V4 — facilitator powers bounded).
- `override_reason` < 16 chars → 400 with documented body shape (per `docs/error-codes.md`).

### `routing_log` — per-stage timing path (FR-007)

Pre-existing flow: `routing_log` row written at end of `persist` stage with the existing columns populated.

New flow: each stage's wrapper decorator (`@with_stage_timing("route")` etc.) writes its duration into a `ContextVar` accumulator; the persist step reads the accumulator and includes the per-stage timings in the same INSERT.

State invariants:

- Decorator overhead ≤ 50µs per call (verified in microbenchmark test under FR-007 acceptance).
- ContextVar isolation across `asyncio.create_task` boundaries (test under FR-007 + 006 §FR-020 acceptance).
- Persist failure does not leave dangling timing state — ContextVar resets at turn boundary regardless of success.

---

## Net-new entities (non-schema)

These are not database entities but feature artifacts that have shape worth defining.

### Audit follow-through record

A row in `AUDIT_FOLLOWTHROUGH.local.md` (markdown table format).

| Field | Type | Description |
|---|---|---|
| `batch` | string | `1` / `2` / `3` / `4` / `5` (matches `AUDIT_PLAN.local.md`) |
| `finding` | string | One-line summary of the audit finding |
| `resolution_pr` | string | `#NNN` or `out-of-scope` or `deferred-phase-3` |
| `verifying_test` | string | `tests/path/to/test.py::test_name` or `none` (with rationale) |
| `status` | enum | `delivered` / `accepted-out-of-scope` / `deferred-to-phase-3` |
| `closed_date` | date | YYYY-MM-DD when the entry was added |

### FR-to-test traceability record

A row in `docs/traceability/fr-to-test.md` (markdown table per spec).

| Field | Type | Description |
|---|---|---|
| `spec` | string | `001-core-data-model` / `002-participant-auth` / etc. |
| `fr` | string | `FR-001` / `FR-002` / etc. |
| `tests` | list of strings | `tests/path/to/test.py::test_name` (one or more) OR `untested` |
| `trigger` | string | When `untested`, the Phase 3 (or other) trigger that justifies non-coverage |

### ADR record

One file per decision under `docs/adr/NNNN-short-title.md`. MADR 4.0 lightweight format:

```markdown
# NNNN. <Title>

**Date**: YYYY-MM-DD
**Status**: proposed / accepted / deprecated / superseded by NNNN

## Context and problem statement

## Considered options

## Decision outcome

### Consequences
```

### Spec version header (FR-014)

Each `specs/NNN/spec.md` gains a header line near the top:

```markdown
**Spec Version**: M.N.P | **Last Amended**: YYYY-MM-DD | **Amended In**: PR #NNN (one-line summary)
```

Applied retroactively only when a spec is next amended (no bulk sweep).

---

## Migration safety notes

- Migration `008` is purely additive; no DROP, no ALTER existing-column type or nullability.
- Forward-only invariant (Constitution §6 + 001 §FR-017) preserved: `downgrade()` body is `pass`.
- Idempotency: the migration uses `op.add_column` which is naturally idempotent under alembic version tracking; rerunning `upgrade head` after a partial failure is safe.
- Restore-from-old-backup compatibility: rows in pre-migration backups have NULL for the new columns, which matches the column nullability and is interpreted as "timing not captured for this row" (acceptable per 003 §FR-030 backfill semantics).
- The conftest mirror update lands in the same PR as the migration to satisfy the new schema-mirror CI gate (FR-008).
