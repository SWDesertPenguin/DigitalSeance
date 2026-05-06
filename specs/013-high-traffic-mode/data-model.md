# Phase 1 Data Model: High-Traffic Session Mode

## In-memory entities

### `HighTrafficSessionConfig`

Resolved once at session-start; cached on the session object for the session lifetime. Provides constant-time per-turn reads (SC-003). `None` when all three env vars are unset (regression-equivalent Phase 2 behavior, SC-005).

| Field | Type | Source | Notes |
|---|---|---|---|
| `batch_cadence_s` | `int \| None` | `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S` | None disables batching; positive integer in `[1, 300]` enables. |
| `convergence_threshold_override` | `float \| None` | `SACP_CONVERGENCE_THRESHOLD_OVERRIDE` | None falls through to global `SACP_CONVERGENCE_THRESHOLD`. Strict `(0.0, 1.0)`. |
| `observer_downgrade` | `ObserverDowngradeThresholds \| None` | `SACP_OBSERVER_DOWNGRADE_THRESHOLDS` | None disables downgrade evaluator. |

Lifetime: equal to the loop's session iteration. Constructed in `src/orchestrator/loop.py` session-init path; passed by reference into `ConvergenceEngine` and the new observer-downgrade evaluator. No serialization (in-memory only — process restart re-resolves from env).

### `ObserverDowngradeThresholds`

Embedded inside `HighTrafficSessionConfig`. Frozen dataclass.

| Field | Type | Validation | Notes |
|---|---|---|---|
| `participants` | `int` | `[2, 10]` | Threshold to begin evaluation; below 2 is meaningless, above 10 is beyond Phase 3 ceiling. |
| `tpm` | `int` | `[1, 600]` | Turns-per-minute trigger. |
| `restore_window_s` | `int` | `[1, 3600]`, default `120` | Sustained-low-traffic window before restoring a downgraded participant. |

### `BatchEnvelope`

In-memory queue entry. One per `(session_id, recipient_id)` pair. Created on the first batched message after a flush; closed on cadence tick or `cadence + 5s` slack budget, whichever fires first.

| Field | Type | Notes |
|---|---|---|
| `session_id` | `str` | Queue key prefix. |
| `recipient_id` | `str` | Queue key suffix; must reference a human participant. |
| `opened_at` | `datetime` | First message append time. Drives the `cadence + 5s` deadline. |
| `scheduled_close_at` | `datetime` | `opened_at + cadence`. Flush task closes when wall clock crosses this OR cadence + 5s slack. |
| `source_turn_ids` | `list[str]` | Turn IDs in the order received. |
| `messages` | `list[ContextMessage]` | Reuses existing `src/orchestrator/types.py:ContextMessage`. |

No DB persistence — envelope is delivered as a websocket event and dropped.

## DB-persistent audit shapes

### `admin_audit_log` rows (no schema change — see [research.md §1](./research.md))

Three new `action` strings reuse the existing table:

#### `observer_downgrade`
- `session_id` — session where the downgrade fired.
- `facilitator_id` — current session facilitator (orchestrator acts on their behalf).
- `target_id` — downgraded participant's ID.
- `previous_value` — JSON: `{"role": "<original-role>", "model_tier": "<tier>", "consecutive_timeouts": N, "last_seen": "<iso>"}`.
- `new_value` — JSON: `{"role": "observer", "trigger_threshold": "participants" | "tpm", "observed": <value>, "configured": <value>}`.
- `timestamp` — auto.

#### `observer_restore`
- `session_id`, `facilitator_id` — as above.
- `target_id` — participant being restored.
- `previous_value` — JSON: `{"role": "observer", "downgraded_at": "<iso>"}`.
- `new_value` — JSON: `{"role": "<restored-role>", "tpm_observed": <value>, "tpm_threshold": <value>, "sustained_window_s": <restore_window_s>}`.

#### `observer_downgrade_suppressed`
- `session_id`, `facilitator_id` — as above.
- `target_id` — participant who would have been downgraded.
- `previous_value` — JSON: `{"role": "<participant-role>", "model_tier": "<tier>"}`.
- `new_value` — JSON: `{"reason": "last_human_protection", "trigger_threshold": "<which>", "observed": <value>, "configured": <value>}`.

No `restore_at` field for the suppressed variant (suppressed downgrades have nothing to restore).

## Validation rules (per V16)

All three env vars validate at startup; invalid values exit before binding ports.

| Var | Validator | Failure modes |
|---|---|---|
| `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S` | `validate_high_traffic_batch_cadence_s` | non-integer; `< 1`; `> 300`. |
| `SACP_CONVERGENCE_THRESHOLD_OVERRIDE` | `validate_convergence_threshold_override` | non-float; `<= 0.0`; `>= 1.0`. |
| `SACP_OBSERVER_DOWNGRADE_THRESHOLDS` | `validate_observer_downgrade_thresholds` | unparseable; missing required key (`participants` OR `tpm`); unknown key; integer out of range per [research.md §2](./research.md). |

## State transitions

### Participant role under observer-downgrade

```text
            ┌─────────────────┐
            │  active role    │
            │  (initial)      │
            └────────┬────────┘
                     │
                     │  thresholds tripped
                     │  & not last human
                     ▼
            ┌─────────────────┐
            │  observer       │  ── observer_downgrade audit row
            │  (downgraded)   │
            └────────┬────────┘
                     │
                     │  tpm < threshold sustained
                     │  for restore_window_s
                     ▼
            ┌─────────────────┐
            │  active role    │  ── observer_restore audit row
            │  (restored)     │
            └─────────────────┘
```

Suppressed-downgrade short-circuit: when the lowest-priority active candidate is the only remaining human, the role state DOES NOT transition; an `observer_downgrade_suppressed` audit row is written and the evaluator returns without effect.

### `BatchEnvelope` lifecycle

```text
[empty]                           ── flush task wakes, no envelopes for this session → noop
   │
   │  AI message produced for human recipient
   ▼
[open]      opened_at = now, scheduled_close_at = now + cadence
   │
   ├─ another AI message → append to messages, source_turn_ids
   │
   ├─ flush task wakes at scheduled_close_at → close
   │
   └─ wall clock exceeds opened_at + cadence + 5s → close (slack budget tripwire)
   │
   ▼
[delivered]   single websocket event emitted to recipient; queue entry dropped
```

## Persistence boundary

In-memory: `HighTrafficSessionConfig`, `ObserverDowngradeThresholds`, `BatchEnvelope`. No DB writes.

Persistent: `admin_audit_log` rows for the three new event types. No new tables, no migration.

`routing_log` instrumentation (per V14): per-turn `observer_downgrade_eval_ms` stage timing. Re-uses the existing per-stage timing decorator (`@with_stage_timing` from [src/orchestrator/timing.py](../../src/orchestrator/timing.py)).
