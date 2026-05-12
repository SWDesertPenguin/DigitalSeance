# Data Model: Facilitator Scratch Window

**Branch**: `024-facilitator-scratch` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## New table: `facilitator_notes`

Workspace state for facilitator-authored notes. Not part of the canonical transcript (V17); not part of the AI context-assembly path (FR-001 architectural test).

```sql
CREATE TABLE facilitator_notes (
    id              UUID PRIMARY KEY,
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    account_id      UUID NULL REFERENCES accounts(id) ON DELETE SET NULL,
    actor_participant_id UUID NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ NULL,
    promoted_at     TIMESTAMPTZ NULL,
    promoted_message_id UUID NULL REFERENCES messages(id) ON DELETE SET NULL
);

CREATE INDEX facilitator_notes_session_idx ON facilitator_notes(session_id) WHERE deleted_at IS NULL;
CREATE INDEX facilitator_notes_account_idx ON facilitator_notes(account_id) WHERE account_id IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX facilitator_notes_session_account_idx ON facilitator_notes(session_id, account_id) WHERE deleted_at IS NULL;
```

### Column semantics

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| `id` | UUID | NO | Note primary key. |
| `session_id` | UUID | NO | Owning session. Cascade delete on hard session DELETE (spec 001 §FR-011). |
| `account_id` | UUID | YES | Owning account when scratch is account-scoped (FR-015). NULL when session-scoped. ON DELETE SET NULL so account deletion degrades notes to session-scoped. |
| `actor_participant_id` | UUID | NO | The facilitator participant who authored the note. ON DELETE CASCADE. |
| `content` | TEXT | NO | Markdown-subset note body. Size cap enforced application-side via `SACP_SCRATCH_NOTE_MAX_KB`. |
| `version` | INTEGER | NO | Optimistic concurrency token. Incremented on every UPDATE. Stale UPDATEs return HTTP 409. |
| `created_at` | TIMESTAMPTZ | NO | Note creation timestamp. |
| `updated_at` | TIMESTAMPTZ | NO | Last modification timestamp. |
| `deleted_at` | TIMESTAMPTZ | YES | Soft-delete marker. The row remains for forensic reconstruction + audit-log integrity. |
| `promoted_at` | TIMESTAMPTZ | YES | Set on successful promote-to-transcript (FR-006). |
| `promoted_message_id` | UUID | YES | FK to the resulting `messages` row from the promote. ON DELETE SET NULL. |

### Index rationale

- `facilitator_notes_session_idx` (partial, NOT deleted): supports the typical "list non-deleted notes for the active session" query.
- `facilitator_notes_account_idx` (partial, NOT deleted): supports the account-scoped "survive archive + browse from /me/sessions" path.
- `facilitator_notes_session_account_idx` (composite): supports the scope-detection FR-002 query in one pass.

### Schema-mirror in `tests/conftest.py`

The CI test suite builds schema from `tests/conftest.py` raw DDL (per `feedback_test_schema_mirror`). The migration task MUST add a parallel DDL block in `tests/conftest.py`; the migration test asserts equality.

## Audit-log action registry (spec 029 contract)

Spec 024 introduces five new audit actions. All five MUST be added to `src/orchestrator/audit_labels.py` AND `frontend/audit_labels.js` in the same commit (per the spec 029 contract document and the CI parity gate).

| Action key | Backend label | `scrub_value` | Emit site |
|---|---|---|---|
| `facilitator_note_created` | Facilitator created scratch note | `False` | `ScratchService.create_note` after persistence success. |
| `facilitator_note_updated` | Facilitator updated scratch note | `False` | `ScratchService.update_note` after persistence success. |
| `facilitator_note_deleted` | Facilitator deleted scratch note | `False` | `ScratchService.delete_note` after soft-delete success. |
| `facilitator_promoted_note` | Facilitator promoted note to transcript | `False` | `PromoteHandler.promote` after injection success. |
| `facilitator_note_purged_retention` | Scratch note purged by retention sweep | `False` | `scripts/scratch_retention_sweep.py` per purged note. |

Rationale for `scrub_value=False`: the content is ALREADY ScrubFilter-processed at write time (spec 007 §FR-012). Setting registry-level `scrub_value=True` would double-scrub.

## Spec 029 shared module contracts consumed (FR-014, FR-026)

Per `specs/029-audit-log-viewer/contracts/shared-module-contracts.md`:

- **§1 action-label registry**: spec 024 adds five entries (above); the parity gate enforces backend / frontend agreement.
- **§2 time formatter**: spec 024''s panel renders all timestamps via `format_iso` / `formatIso`. No new time-formatter code in spec 024.
- **§3 `DiffRenderer` React component**: spec 024''s Review Gate sub-panel imports the inline component from `frontend/app.jsx`. No parallel implementation.
- **§4 size thresholds**: spec 024 inherits `MAIN_THREAD_BYTE_THRESHOLD = 50_000` and `WORKER_BYTE_THRESHOLD = 500_000` from `frontend/diff_engine.js`. No redeclaration.

## Read-side projections (no new persistence)

### SummaryArchiveEntry

A rendered list-item over `messages WHERE speaker_type=''summary'' AND session_id=$1 ORDER BY turn_number DESC LIMIT 20 OFFSET $2`. The SPA renders each row as a card showing turn range + first 200 chars of narrative + click-to-expand.

### ReviewGateEntry

A rendered list-item over `admin_audit_log WHERE session_id=$1 AND action IN (''review_gate_approve'',''review_gate_reject'',''review_gate_edit'') ORDER BY timestamp DESC LIMIT 50` plus a LEFT JOIN to `participants` for display names. Click-to-expand routes `previous_value` + `new_value` through spec 029''s `DiffRenderer`.

## State transitions

```text
[ABSENT] -- POST /notes ----> [DRAFT (deleted_at=NULL, promoted_at=NULL)]
[DRAFT]  -- PUT /notes/<id> -> [DRAFT (version+1)]
[DRAFT]  -- POST /promote --> [PROMOTED (promoted_at, promoted_message_id set)]
[DRAFT]  -- DELETE ---------> [SOFT-DELETED (deleted_at set)]
[PROMOTED]-- DELETE --------> [SOFT-DELETED (deleted_at set; promote markers preserved)]
[SOFT-DELETED] -- retention sweep --> [HARD-DELETED]
```

The retention sweep is operator-scheduled (v1 ships the script, NOT an in-process scheduler).

## Architectural test surface (FR-001 / SC-001)

`tests/test_024_architectural.py` provides two enforcement layers per research.md §8:

1. **Import scan** (static): walks `src/orchestrator/`, `src/prompts/`, `src/api_bridge/`, `src/operations/`; asserts no module imports `src.scratch.repository`.
2. **Runtime tracer** (dynamic): pytest fixture monkey-patches `FacilitatorNotesRepository` so every `find_*` / `list_*` call raises `AssertionError`. The fixture activates while the turn loop assembles context for a turn.

Layer 1 catches static developer error; layer 2 catches dynamic-import escapes.
