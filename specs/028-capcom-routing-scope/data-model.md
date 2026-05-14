# Data Model: CAPCOM-Like Routing Scope

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)
**Phase**: 1 (Design)
**Date**: 2026-05-14

## Schema additions

All additions ship in one alembic revision `024_capcom_routing_scope.py` (the next sequential slot after 023). The `tests/conftest.py` raw-DDL schema mirror updates in lockstep per `feedback_test_schema_mirror`. The two-tier summarizer (FR-018) requires no schema additions — see the Phase 7 note below.

### `messages.kind` (new column)

| field | value |
|---|---|
| type | `TEXT NOT NULL DEFAULT 'utterance'` |
| constraint | `CHECK (kind IN ('utterance', 'capcom_relay', 'capcom_query'))` |
| spec ref | FR-002, FR-012, FR-013 |

Every existing row defaults to `'utterance'`. The CAPCOM AI's dispatch produces `'capcom_relay'` (curated forwarding to the panel) or `'capcom_query'` (question to humans on behalf of the panel). All other AI and human messages remain `'utterance'`.

Application-side enum:

```python
MessageKind = Literal["utterance", "capcom_relay", "capcom_query"]
```

### `messages.visibility` (new column)

| field | value |
|---|---|
| type | `TEXT NOT NULL DEFAULT 'public'` |
| constraint | `CHECK (visibility IN ('public', 'capcom_only'))` |
| spec ref | FR-001, FR-006, FR-014, FR-016 |

`'public'` — every participant's context-assembly includes the row. `'capcom_only'` — only humans and the currently-assigned CAPCOM AI's context-assembly includes the row. The default `'public'` preserves pre-feature behavior; all existing rows migrate as public.

Application-side enum:

```python
MessageVisibility = Literal["public", "capcom_only"]
```

Index supporting the visibility-filter query path:

```sql
CREATE INDEX idx_messages_visibility
ON messages(session_id, visibility, turn_number DESC);
```

### `sessions.capcom_participant_id` (new column)

| field | value |
|---|---|
| type | `TEXT REFERENCES participants(id)` |
| constraint | nullable; `NULL` means no CAPCOM assigned |
| spec ref | FR-003 |

When non-null, this references the active CAPCOM AI for the session. `NULL` is the default state (CAPCOM not assigned) and the post-disable / post-departure state.

### `participants.routing_preference` (new accepted value `'capcom'`)

| field | value |
|---|---|
| existing type | `TEXT DEFAULT 'always'` (no CHECK constraint per `001_initial_schema.py`) |
| change | new value `'capcom'` admitted at the application layer; no DDL change |
| spec ref | FR-004, FR-005 |

The application-layer enum widens:

```python
RoutingPreference = Literal[
    "always", "review_gate", "delegate_low", "domain_gated",
    "burst", "observer", "addressed_only", "human_only",
    "capcom",  # new in spec 028
]
```

### Unique partial index `ux_participants_session_capcom`

```sql
CREATE UNIQUE INDEX ux_participants_session_capcom
ON participants(session_id)
WHERE routing_preference = 'capcom';
```

Enforces single-CAPCOM-per-session at the DB layer per FR-005. The unique index is partial — only rows where `routing_preference='capcom'` are constrained. Rotation transactions update the outgoing CAPCOM's `routing_preference` BEFORE the incoming participant's, so the unique constraint is satisfied at each statement boundary inside the transaction (research.md §14).

### Two-tier summarizer storage (Phase 7, no migration)

Per [research.md §5](./research.md) (revised 2026-05-14 after implementation discovery), spec 005 stores summaries as messages with `speaker_type='summary'` — there is no separate `checkpoint_summaries` table. The two-tier summarizer therefore re-uses the existing `messages.visibility` column:

- Panel summary: `speaker_type='summary'`, `visibility='public'`, covers public source rows.
- CAPCOM summary: `speaker_type='summary'`, `visibility='capcom_only'`, covers public + capcom_only source rows.

The visibility filter (FR-006) routes the matching summary to the participant's context automatically. No additional schema column or unique index is required.

## Invariants

**INV-1 (Single-CAPCOM-per-session)**: At any moment, at most one participant per session has `routing_preference='capcom'`. Enforced by `ux_participants_session_capcom`. Concurrent facilitator assign actions cannot both succeed — the second hits the unique-index violation and the application returns HTTP 409.

**INV-2 (CAPCOM FK integrity)**: `sessions.capcom_participant_id` references a participant whose `routing_preference='capcom'` OR is `NULL`. Application-enforced at write time (the assign/rotate endpoints update both columns transactionally). A defensive DB-level check would be a partial CHECK constraint via a trigger; deferred to v2 unless a drift incident demands it.

**INV-3 (Pre-feature compatibility)**: When `sessions.capcom_participant_id IS NULL`, every message MUST have `visibility='public'`. Application-enforced at the inject_message handler (FR-021). A row with `visibility='capcom_only'` and a NULL `capcom_participant_id` is a defect — the inject handler returns HTTP 409 if the caller attempts it. Pre-existing rows are all `'public'` (default value); post-disable historical rows retain their visibility (FR-011) but no new `capcom_only` rows can be written.

**INV-4 (Panel-cannot-emit-capcom-only)**: When `messages.visibility='capcom_only'`, the speaker MUST be either a human participant OR the participant referenced by `sessions.capcom_participant_id`. Panel AI participants are structurally forbidden from emitting `capcom_only` content (FR-014 / spec.md Clarifications Session 2026-05-14 Q2). Application-enforced at the inject_message handler with HTTP 422 on violation.

**INV-5 (Historical attribution preserved)**: Rotation/disable does NOT rewrite the `speaker_id` of pre-rotation `capcom_only` messages. The audit trail attributes every `capcom_only` row to the CAPCOM-of-record at emission time (FR-010, FR-011).

**INV-6 (Summary-scope consistency)**: For any `(session_id, checkpoint_turn)` pair where summaries are emitted, the summarizer writes at most one `summary` message per visibility scope. Enforced by an application-side existence check before each summary write (no DB unique index needed because the message PK `(turn_number, session_id, branch_id)` already prevents duplicate rows at the turn level — the summarizer reuses distinct turn numbers for panel vs CAPCOM summaries via its existing summary-checkpoint cadence).

## Audit-log action vocabulary

Three new `admin_audit_log.action` values introduced by spec 028:

| action | when | actor | metadata |
|---|---|---|---|
| `capcom_assigned` | facilitator assigns a CAPCOM | facilitator_id | `target_participant_id`, `prior_routing_preference` |
| `capcom_rotated` | facilitator rotates CAPCOM | facilitator_id | `previous_capcom_id`, `new_capcom_id`, `prior_routing_preference_of_new` |
| `capcom_disabled` | facilitator disables CAPCOM mode | facilitator_id | `previous_capcom_id`, `prior_routing_preference` |
| `capcom_departed_no_replacement` | CAPCOM participant removed without rotation | facilitator_id (cascade) | `previous_capcom_id`, `reason='participant_removed'` |

The audit-label registry (spec 029's `src/orchestrator/audit_labels.py`) gains four new entries with human-readable labels and `scrub_value=False` (no sensitive content in these rows). Frontend mirror (`frontend/audit_labels.js`) gains the same four entries.

## Routing-log reason vocabulary

One new `routing_log.reason` value: `message_filtered_capcom_scope:excluded=<N>`. Emitted per-turn when the visibility filter excludes one or more messages from a participant's context. The `excluded=N` suffix carries the exclusion count (zero is not logged — a row is only inserted when at least one message was filtered).

The detection-taxonomy parity script (`scripts/check_detection_taxonomy_parity.py`) gains the new reason value in its allowlist.

## Migration order vs. existing tables

The `024_capcom_routing_scope.py` migration depends on:
- `messages` (created in 001)
- `participants` (created in 001)
- `sessions` (created in 001)
- `checkpoint_summaries` (created by spec 005's migration — verify revision number at task time and set `depends_on` accordingly)
- `admin_audit_log` (created in 001)

No table is dropped or renamed. No row migration logic is needed beyond the column-add operations themselves (every existing row inherits the column DEFAULT).
