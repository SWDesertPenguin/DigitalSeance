# Data Model: Session-Length Cap with Auto-Conclude Phase

**Branch**: `025-session-length-cap` | **Date**: 2026-05-07 | **Plan**: [plan.md](./plan.md)

Captures entities, schema additions, FSM extensions, and validation rules derived from [spec.md](./spec.md) and [research.md](./research.md).

---

## Schema additions

One alembic migration (`alembic/versions/NNNN_session_length_cap.py`) adds five nullable columns to `sessions`. All columns default to NULL or `'none'`; existing sessions inherit the no-cap default unchanged (SC-001).

| Column | Type | Default | Constraints | Source |
|---|---|---|---|---|
| `length_cap_kind` | `text` | `'none'` | CHECK in (`'none'`, `'time'`, `'turns'`, `'both'`) | FR-001 |
| `length_cap_seconds` | `bigint` | `NULL` | CHECK (`length_cap_seconds IS NULL OR length_cap_seconds BETWEEN 60 AND 2592000`) | FR-001, FR-020 |
| `length_cap_turns` | `integer` | `NULL` | CHECK (`length_cap_turns IS NULL OR length_cap_turns BETWEEN 1 AND 10000`) | FR-001, FR-020 |
| `conclude_phase_started_at` | `timestamptz` | `NULL` | (no CHECK) | FR-001 |
| `active_seconds_accumulator` | `bigint` | `NULL` | CHECK (`active_seconds_accumulator IS NULL OR active_seconds_accumulator >= 0`) | research.md §1, FR-002 |

Cross-column constraint (enforced application-side, not as SQL CHECK because of Postgres constraint subtlety with multi-column rules):

- When `length_cap_kind = 'time'`, `length_cap_seconds IS NOT NULL` AND `length_cap_turns IS NULL`.
- When `length_cap_kind = 'turns'`, `length_cap_turns IS NOT NULL` AND `length_cap_seconds IS NULL`.
- When `length_cap_kind = 'both'`, both `length_cap_seconds IS NOT NULL` AND `length_cap_turns IS NOT NULL`.
- When `length_cap_kind = 'none'`, both `length_cap_seconds IS NULL` AND `length_cap_turns IS NULL` (FR-022).

These rules are validated in the cap-set endpoint and asserted in `tests/conftest.py` mirror as comments referencing the application-side check.

`tests/conftest.py` raw DDL MUST gain the same five column declarations alongside the migration to avoid the schema-mirror drift documented in memory `feedback_test_schema_mirror.md`.

---

## Entities

### `SessionLengthCap` (per-session columns)

The five columns above represent the full per-session cap state. Mutable via the cap-set endpoint (FR-003); facilitator-only authorization (FR-016). Visible in facilitator session-settings response; absent from non-facilitator `/me` (FR-019).

```python
@dataclass(frozen=True)
class SessionLengthCap:
    kind: Literal['none', 'time', 'turns', 'both']
    seconds: int | None
    turns: int | None
    conclude_phase_started_at: datetime | None
    active_seconds_accumulator: int | None  # in seconds; None until first transition
```

**Validation rules** (per FR-020/FR-021/FR-022):
- `seconds` (when set): integer in `[60, 2_592_000]` (1 minute to 30 days).
- `turns` (when set): integer in `[1, 10_000]`.
- Setting `kind='none'` MUST null both `seconds` and `turns`.
- Both at zero or negative → HTTP 422.

### `LoopState` (existing FSM, extended)

The existing FSM (running, paused, stopped) gains a fourth state: **conclude**. The FSM diagram becomes:

```text
            cap_set ↑   (cap update with no transition)
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
    running ──────────────► conclude ─────────► paused
        │   conclude_phase_      │     auto_pause_on_cap
        │     entered            │
        │                        │ manual_stop_during_conclude
        │                        ▼
        │                     stopped
        │
        │ pause_loop / stop_loop (existing)
        ▼
     paused / stopped
        │
        │ resume_loop (existing)
        ▼
     running
        ↑
        │ conclude_phase_exited (cap extension during conclude)
        │
     conclude
```

**New transition edges** (each emits a `routing_log` row with the labelled `reason`):

| From | To | Trigger | `routing_log.reason` |
|---|---|---|---|
| running | conclude | trigger fraction crossed (FR-005) OR cap-decrease absolute interpretation (FR-026) | `conclude_phase_entered` |
| conclude | running | cap extended such that trigger fraction no longer crossed (FR-013) | `conclude_phase_exited` |
| conclude | paused | last conclude turn produced + summarizer ran (FR-012) | `auto_pause_on_cap` |
| conclude | stopped | facilitator `stop_loop` during conclude phase + summarizer ran (FR-015) | `manual_stop_during_conclude` |
| any | (no transition) | cap-set committed (FR-004) | `cap_set` |

**Existing transitions** (running ↔ paused, running ↔ stopped, paused ↔ running) are unchanged; this spec adds edges, never replaces.

### `ActiveLoopAccumulator` (durable)

Tracks active loop time per session. Persisted as `sessions.active_seconds_accumulator` (research.md §1).

**Update rules**:
- Initialized to `0` on first `start_loop` (loop transition `(none) → running`).
- On every FSM transition that exits the running OR conclude state, increment by `(now() - last_phase_change_at).total_seconds()` and update `last_phase_change_at` (a derivable timestamp; can be the most recent `routing_log` timestamp matching this session's last running/conclude entry, OR a co-located column `last_active_phase_started_at` — pick the cheaper read at implementation time, leans toward co-located column).
- On every transition INTO running OR conclude, set `last_phase_change_at = now()` (no increment yet).
- On pause / stopped exit-out, increment + freeze.

**Restart recovery**: orchestrator startup walks `sessions` rows where `loop_state IN ('running', 'conclude')` (existing fields), assumes the loop was active up to the last `routing_log` timestamp for that session, and increments accordingly. Documented in [quickstart.md §"Restart recovery"](./quickstart.md).

**Cap-check read**: `active_seconds_now = active_seconds_accumulator + (now() - last_phase_change_at) IF current_phase IN ('running', 'conclude') ELSE active_seconds_accumulator`.

### `ConcludeDelta` (Tier 4 prompt fragment)

Hardcoded text in `src/prompts/conclude_delta.py` (research.md §5):

```python
CONCLUDE_DELTA_TEXT = (
    "The session is approaching its conclusion. In your next turn, "
    "please summarize your position so far and offer a final conclusion. "
    "The orchestrator will pause the loop after every active participant "
    "has had a turn to wrap up."
)
```

**Injection rule**: when the loop's current phase is `conclude`, the prompt assembler appends `CONCLUDE_DELTA_TEXT` at Tier 4, after participant `custom_prompt` and after spec 021's register-slider delta (when 021 ships). Implemented via `tier4_extras: list[Tier4Fragment]` in `src/prompts/tiers.py` per research.md §4.

**Removal rule**: when the loop transitions out of `conclude` (back to running via FR-013, or to paused/stopped), the next assembly does NOT include the delta.

### `CapInterpretation` (audit-log discriminator)

When a `cap_set` transition is logged via FR-026's disambiguation flow, `routing_log` carries an additional `interpretation: 'absolute' | 'relative'` field. For cap-set on a fresh session (no decrease), the field is `null` (no disambiguation occurred).

```python
@dataclass(frozen=True)
class CapSetEvent:
    session_id: str
    old_cap: SessionLengthCap
    new_cap: SessionLengthCap
    interpretation: Literal['absolute', 'relative'] | None
    actor_id: str  # the facilitator
    at: datetime
```

Persisted via the existing `routing_log` write path; no new table.

---

## Cross-spec references

- **Spec 001 (core-data-model)** — schema changes to `sessions` follow §FR-017 forward-only constraint; no rewrites.
- **Spec 003 (turn-loop-engine)** — `routing_log.reason` enum gains five new entries (`cap_set`, `conclude_phase_entered`, `conclude_phase_exited`, `auto_pause_on_cap`, `manual_stop_during_conclude`). Cross-ref [contracts/routing-log-reasons.md](./contracts/routing-log-reasons.md).
- **Spec 004 (convergence-cadence)** — adaptive cadence is suspended during conclude phase (FR-010); resumes on conclude-phase exit (FR-014). Cross-ref `src/orchestrator/cadence.py` extension point.
- **Spec 005 (summarization-checkpoints)** — final summarizer reuses the existing pipeline (FR-011); no new summarization logic.
- **Spec 006 (mcp-server)** — cap-set endpoint extends session-settings (research.md §2); facilitator-only authorization mirrors §FR-007.
- **Spec 008 (prompts-security-wiring)** — Tier 4 hook is the conclude delta's attachment point; existing tier isolation, spotlighting, sanitization, output validation continue to apply.
- **Spec 011 (web-ui)** — SPA wiring for cap-config controls + conclude-phase banner + disambiguation modal lands as a separate amendment (research.md §6).
- **Spec 021 (ai-response-shaping)** — register-slider delta composes additively at Tier 4 in the slot ahead of the conclude delta (research.md §4); spec 021's later landing is forward-compatible.
