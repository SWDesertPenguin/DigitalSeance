# Data Model: AI Participant Standby Modes

**Spec**: `specs/027-participant-standby-modes/spec.md`
**Migration**: `alembic/versions/021_participant_standby_modes.py` (pre-allocated revision slot per parallel-lane coordination memo).

## Schema changes

### `participants` — three new columns + status enum extension

| Column | Type | Default | Notes |
|---|---|---|---|
| `wait_mode` | `TEXT NOT NULL` | `'wait_for_human'` | CHECK constraint `wait_mode IN ('wait_for_human', 'always')`. Set per-participant by the owning human; default applied at INSERT via `SACP_STANDBY_DEFAULT_WAIT_MODE` env var. |
| `standby_cycle_count` | `INTEGER NOT NULL` | `0` | Counts consecutive round-robin ticks where the participant remained in `status='standby'`. Resets to 0 on every standby-exit transition. Backs the FR-017 pivot trigger denominator. |
| `wait_mode_metadata` | `JSONB NOT NULL` | `'{}'::jsonb` | Bounded JSONB. v1 keys: `long_term_observer` (boolean, FR-020 sub-state). Forward-compatible for future opt-in flags without schema churn. |

The `status` column gains one new permitted value `standby` — implemented via dropping + recreating the CHECK constraint to include the new value. Existing rows are unaffected.

### `routing_log` — three new V14 timing columns

| Column | Type | Default | Notes |
|---|---|---|---|
| `standby_eval_ms` | `INTEGER` | `NULL` | Time spent in the standby evaluator for the participant on this tick. Backs SC-003 perf budget. |
| `pivot_inject_ms` | `INTEGER` | `NULL` | Time spent injecting the pivot message (NULL except on the tick where the pivot fired). |
| `standby_transition_ms` | `INTEGER` | `NULL` | Time spent on standby-entry / standby-exit / observer-mark state transition (NULL except on the tick where the transition occurred). |

These are all nullable so pre-feature `routing_log` rows remain valid. The columns are populated by the standby evaluator + pivot injector wrappers in `src/orchestrator/timing.py` (the existing `with_stage_timing` helper extends to the new stage names).

### Partial index

```sql
CREATE INDEX idx_participants_session_standby
ON participants (session_id, status)
WHERE status = 'standby';
```

Backs the per-tick standby-set enumeration. The unconditional `idx_participants_session` (spec 002) already covers the broader case; the partial index keeps the standby-set query at sub-millisecond when most participants are `active`.

## Test conftest mirror

Per `feedback_test_schema_mirror`: `tests/conftest.py:_PARTICIPANTS_TABLE_DDL` raw DDL gains the three new columns. The test database is rebuilt from the conftest, NOT from alembic — mirroring is mandatory.

```sql
-- additions to the existing CREATE TABLE participants block:
wait_mode TEXT NOT NULL DEFAULT 'wait_for_human',
standby_cycle_count INTEGER NOT NULL DEFAULT 0,
wait_mode_metadata TEXT NOT NULL DEFAULT '{}'
```

(JSONB is mirrored as TEXT in the test conftest because SQLite — used as the test substrate fallback — lacks JSONB. The repo writes JSON-encoded strings and reads them with `json.loads`; this is the established pattern for spec 022's metadata-bearing columns.)

## Domain model — Participant dataclass extension

`src/models/participant.py:Participant` gains three new fields (frozen, slots-friendly):

```python
wait_mode: str
standby_cycle_count: int
wait_mode_metadata: dict[str, Any]
```

The `from_record` classmethod's existing splat-construction continues to work because every column maps to a field by name. The `wait_mode_metadata` field is deserialized from the JSONB column to a `dict[str, Any]` at the repository layer (`ParticipantRepository._row_to_participant`).

## Audit-log shape

The five new actions write into the existing `admin_audit_log` table — no schema change. Each row carries:

- `action` — one of `standby_entered`, `standby_exited`, `pivot_injected`, `standby_observer_marked`, `wait_mode_changed`.
- `actor_id` — `'orchestrator'` for the auto-managed transitions (standby_entered / standby_exited / pivot_injected / standby_observer_marked); the facilitator or participant id for `wait_mode_changed`.
- `target_id` — the affected participant's id.
- `previous_value` / `new_value` — populated for `wait_mode_changed` (old/new mode strings); NULL for the auto-managed transitions.
- `metadata` JSONB — carries the triggering reason for standby_entered (`{"reason": "awaiting_human" | "awaiting_gate" | "awaiting_vote" | "filler_stuck"}`); the consecutive-cycle count for pivot_injected (`{"cycles_at_pivot": N}`); empty for the rest.

## WebSocket event shape

Two new event types:

- `participant_standby` — payload `{"participant_id": str, "reason": "awaiting_human" | "awaiting_gate" | "awaiting_vote" | "filler_stuck", "since_turn": int}`.
- `participant_standby_exited` — payload `{"participant_id": str, "cleared_at_turn": int}`.

Both broadcast to session subscribers via the existing `src/web_ui/events.py` channel. No filter changes — both events are facilitator-visible AND participant-visible (a participant seeing their own standby pill rendered in the UI is part of the transparency contract per V5).

## Pivot message shape

INSERT into the existing `messages` table:

```sql
INSERT INTO messages (
  session_id, turn_number, branch_id, speaker_id, speaker_type,
  content, metadata, created_at
) VALUES (
  $session, $next_turn, $branch, 'orchestrator', 'system',
  $pivot_text, '{"kind": "orchestrator_pivot", "rate_cap_remaining": N}'::jsonb, NOW()
);
```

The pivot text is the hardcoded string from `src/prompts/standby_ack_delta.py:PIVOT_TEXT` (pre-validated through the security pipeline at module import). The `rate_cap_remaining` key is informational — operators inspecting the message can see how many pivots remained in the cap envelope.

## Migration ordering

The migration `021_participant_standby_modes.py` chain-links to `018_compression_log.py` (current head as of 2026-05-12). Lane A (spec 024) is pre-allocated `019_*`; lane B (spec 026 ongoing) may use `020_*`. This lane is `021_*`. If lane A or lane B lands first, the down_revision pointer in `021_*` MUST be updated to point at the post-merge head before this PR merges — coordination per `feedback_parallel_merge_sequence_collisions`.
