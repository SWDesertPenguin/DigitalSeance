# Contract: `facilitator_notes` Table

**Spec**: [../spec.md](../spec.md) §FR-001, §FR-015, §FR-016, §FR-017
**Plan**: [../plan.md](../plan.md) | **Data model**: [../data-model.md](../data-model.md)
**Status**: Phase 1 contract draft

The `facilitator_notes` table is operator-private workspace state. It is NOT part of the canonical transcript (V17) and NOT reachable from the AI context-assembly pipeline (FR-001, enforced by `tests/test_024_architectural.py`).

## DDL

See [data-model.md](../data-model.md#new-table-facilitator_notes) for the canonical DDL.

## FK behavior summary

| FK | ON DELETE | Rationale |
|---|---|---|
| `session_id` -> `sessions(id)` | CASCADE | Hard session deletion (spec 001 §FR-011) wipes notes. Soft archive does NOT cascade. |
| `account_id` -> `accounts(id)` | SET NULL | Account deletion (spec 023 FR-012) degrades notes to session-scoped. |
| `actor_participant_id` -> `participants(id)` | CASCADE | Participant deletion implies a session-scoped lifecycle event. |
| `promoted_message_id` -> `messages(id)` | SET NULL | Defensive: archive-and-recreate flows must not orphan the promote pointer. |

## Indexes

Three partial indexes filter by `deleted_at IS NULL` to keep the hot-path query against an index of currently-live notes only. See the data-model document for DDL.

## Architectural invariants

1. **No context-assembly read.** No code path from `src/orchestrator/`, `src/prompts/`, `src/api_bridge/`, or `src/operations/` may import any symbol from `src.scratch.repository` that exposes `facilitator_notes` rows. Enforced by `tests/test_024_architectural.py`.
2. **Soft-delete is the only DELETE.** Hard DELETE happens only via the parent session''s hard delete cascade OR the operator retention sweep script.
3. **Version is the only OCC token.** `updated_at` is informational; the OCC check is `version` only.
4. **Account FK never points at a deleted account.** ON DELETE SET NULL guarantees this without orchestrator-side defensive code.

## Schema-mirror

Per `feedback_test_schema_mirror`, `tests/conftest.py` MUST carry a parallel DDL block creating `facilitator_notes` with the same shape. The `check_schema_mirror.py` preflight asserts equality.

## Migration

`alembic/versions/019_facilitator_notes.py` adds the table + three indexes. `down_revision = ''018_compression_log''`. Forward-only-safe: dropping `facilitator_notes` on rollback is acceptable because the feature ships behind `SACP_SCRATCH_ENABLED=0`.
