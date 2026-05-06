# Phase 1 Data Model: Dynamic Mode Assignment

## In-memory entities

### `SessionSignals`

Bounded ring buffer holding the rolling 5-minute observation window for each of the four signal sources. Entries are timestamped instantaneous values.

| Field | Type | Notes |
|---|---|---|
| `turn_rate` | `RingBuffer[SignalEntry]` | Entries: `(timestamp, turns_in_last_minute: int)`. Maintained by the controller from the loop's per-turn callback. |
| `convergence_derivative` | `RingBuffer[SignalEntry]` | Entries: `(timestamp, similarity_value: float \| None)`. Derivative computed on read by the decision cycle (last - first over the buffer's time span). `None` means the engine had no similarity yet for that tick. |
| `queue_depth` | `RingBuffer[SignalEntry]` | Entries: `(timestamp, depth: int)`. Reads from spec-013 batching's per-session queue size. Inactive (no entries appended) when batching is unconfigured. |
| `density_anomaly_count` | `RingBuffer[SignalEntry]` | Entries: `(timestamp, anomaly_count_in_last_minute: int)`. Maintained by counting `convergence_log` rows with `tier='density_anomaly'` produced in the prior minute. |

Buffer sizing: `window_seconds / decision_cycle_interval_seconds = 300 / 5 = 60` entries per source at the initial cap. The buffer is bounded — old entries are evicted on append.

Lifetime: per session; constructed on `dma_controller.start`; dropped on `stop`.

### `ControllerState`

The controller's view of the session. Drives the dwell-floor and recommendation deduplication logic.

| Field | Type | Notes |
|---|---|---|
| `last_emitted_action` | `Literal["NORMAL", "ENGAGE", "DISENGAGE"] \| None` | Action of most recent `mode_recommendation`. Used to dedupe per [research.md §6](./research.md). |
| `last_transition_at` | `datetime \| None` | Timestamp of most recent `mode_transition` (auto-apply only). Drives dwell-floor calculation. |
| `dwell_floor_at` | `datetime \| None` | `last_transition_at + SACP_DMA_DWELL_TIME_S`; the soonest a counter-direction transition can fire. `None` until first transition. |
| `signal_health` | `dict[str, SignalHealthFlag]` | Per-signal-source health: AVAILABLE / UNAVAILABLE / RATE_LIMITED. Drives FR-013 unavailability rate-limit. |
| `unavailability_emitted_in_dwell` | `set[str]` | Signal names that have already emitted `signal_source_unavailable` within the current dwell window. Cleared on next transition or on dwell-floor expiry. |

### `ModeRecommendation`

Per-cycle decision shape. Emitted to `admin_audit_log` when the action differs from `last_emitted_action`.

| Field | Type | Notes |
|---|---|---|
| `session_id` | `str` | |
| `decision_at` | `datetime` | Cycle time. |
| `action` | `Literal["NORMAL", "ENGAGE", "DISENGAGE"]` | Decision outcome. |
| `triggers` | `list[str]` | Names of signal sources that crossed their thresholds (alphabetical; per spec acceptance scenario 3). May contain multiple entries when several signals cross simultaneously. |
| `signal_observations` | `list[SignalObservation]` | One entry per triggering signal: `(signal_name, observed_value, configured_threshold)`. |
| `dwell_floor_at` | `datetime \| None` | The dwell-floor time that would govern auto-apply if it were enabled. Always populated even in advisory mode (informational). |

### `ModeTransition`

Auto-apply variant of recommendation; emitted only when `SACP_AUTO_MODE_ENABLED=true` AND a transition fires.

| Field | Type | Notes |
|---|---|---|
| (all `ModeRecommendation` fields) | | Same shape as recommendation. |
| `engaged_mechanisms` | `list[str]` | Spec-013 mechanisms whose env vars are set AND the controller engaged. |
| `skipped_mechanisms` | `list[str]` | Spec-013 mechanisms whose env vars are NOT set; controller skipped silently. Audit-visible. |

### `ModeTransitionSuppressed`

Emitted when auto-apply would have fired a transition but dwell blocked it.

| Field | Type | Notes |
|---|---|---|
| `session_id` | `str` | |
| `suppressed_at` | `datetime` | When the transition would have fired. |
| `action` | `Literal["ENGAGE", "DISENGAGE"]` | The blocked direction. |
| `reason` | `Literal["dwell_floor_not_reached"]` | Always this in Phase 3 initial; reserved for future reasons. |
| `eligible_at` | `datetime` | `last_transition_at + dwell` — when a transition in this direction would next be eligible. |

## DB-persistent audit shapes

Five new `admin_audit_log` `action` strings — no schema change. Same pattern as spec 013.

### `mode_recommendation`
- `target_id` — session_id (audit row's subject is the session, not a participant).
- `previous_value` — JSON: `{"action": "<previous_action>"}` (or `null` for first emission).
- `new_value` — JSON: `{"action": "<action>", "triggers": [...], "signal_observations": [...], "dwell_floor_at": "<iso-or-null>"}`.

### `mode_transition`
- `target_id` — session_id.
- `previous_value` — JSON: `{"action": "<previous_action>", "engaged_mechanisms": [...]}`.
- `new_value` — JSON: full ModeTransition shape (action, triggers, observations, engaged_mechanisms, skipped_mechanisms, dwell_floor_at).

### `mode_transition_suppressed`
- `target_id` — session_id.
- `previous_value` — JSON: `{"current_action": "<current_action>"}`.
- `new_value` — JSON: `{"would_have_fired": "<action>", "reason": "dwell_floor_not_reached", "eligible_at": "<iso>"}`.

### `decision_cycle_throttled`
- `target_id` — session_id.
- `previous_value` — JSON: `{"cap_per_minute": <int>, "last_cycle_at": "<iso>"}`.
- `new_value` — JSON: `{"reason": "rate_cap_exceeded", "next_eligible_at": "<iso>"}`.
- Rate-limited per FR-013: at most once per dwell window per session.

### `signal_source_unavailable`
- `target_id` — session_id (with the signal name in the new_value).
- `previous_value` — JSON: `{"signal": "<name>", "last_known_state": "<state>"}`.
- `new_value` — JSON: `{"signal": "<name>", "since": "<iso>", "rate_limited_until": "<iso>"}`.
- Rate-limited per FR-013: at most once per dwell window per signal per session.

## Validation rules (per V16)

Six new env vars, all validated at startup; invalid values exit before binding ports.

| Var | Validator | Failure modes |
|---|---|---|
| `SACP_DMA_TURN_RATE_THRESHOLD_TPM` | `validate_dma_turn_rate_threshold_tpm` | non-integer; `< 1`; `> 600`. |
| `SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD` | `validate_dma_convergence_derivative_threshold` | non-float; `<= 0.0`; `> 1.0`. |
| `SACP_DMA_QUEUE_DEPTH_THRESHOLD` | `validate_dma_queue_depth_threshold` | non-integer; `< 1`; `> 1000`. |
| `SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD` | `validate_dma_density_anomaly_rate_threshold` | non-integer; `< 1`; `> 60`. |
| `SACP_DMA_DWELL_TIME_S` | `validate_dma_dwell_time_s` | non-integer; `< 30`; `> 1800`. Required when `SACP_AUTO_MODE_ENABLED=true` (cross-validator dependency per FR-010). |
| `SACP_AUTO_MODE_ENABLED` | `validate_auto_mode_enabled` | not in `{true, false}`. Cross-validator: when `true`, `SACP_DMA_DWELL_TIME_S` must be set. |

## State transitions

### Controller decision-cycle

```text
                ┌──────────────────────────────────────────┐
                │  cycle wakes (token-bucket admit OR drop)│
                └─────────────────┬────────────────────────┘
                                  │
              ┌───────────────────┴───────────────────┐
              │                                       │
       admit  │                                drop   │
              ▼                                       ▼
   ┌─────────────────────┐                    ┌──────────────────────┐
   │ poll signal sources │                    │ rate-limit emit      │
   │ → list of available │                    │ decision_cycle_       │
   │   triggers          │                    │ throttled (FR-013)    │
   └────────┬────────────┘                    └──────────────────────┘
            │
            ▼
   ┌─────────────────────────────────────────────┐
   │ compute action per FR-009 asymmetry rule:    │
   │   ANY trigger over threshold → ENGAGE        │
   │   ALL configured below for dwell → DISENGAGE │
   │   else → NORMAL (continuation of last action)│
   └────────┬────────────────────────────────────┘
            │
            ▼
   ┌──────────────────────┐  action ==
   │ compare to            │  last_emitted_action
   │ last_emitted_action   ├─────────────► no-op
   └────────┬──────────────┘
            │ differs
            ▼
   ┌──────────────────────┐    auto_mode
   │ emit mode_           │   off (advisory)
   │ recommendation        ├─────────────► done
   └────────┬─────────────┘
            │ auto_mode on
            ▼
   ┌──────────────────────┐  dwell_floor
   │ check dwell_floor     │  not reached
   └────────┬─────────────┤─────────────► emit mode_transition_suppressed
            │ reached     │
            ▼
   ┌──────────────────────┐
   │ engage/disengage      │
   │ spec-013 mechanisms; │
   │ emit mode_transition │
   └──────────────────────┘
```

### Signal-source health

```text
[AVAILABLE]  ──── data feed disappears ──→  [UNAVAILABLE]
                                                  │
                                                  │ first occurrence in dwell window
                                                  ▼
                                            emit signal_source_unavailable
                                                  │
                                                  │ rate-limited per dwell window
                                                  ▼
                                            [RATE_LIMITED]
                                                  │
                                                  │ data feed returns
                                                  ▼
                                            [AVAILABLE]
                                                  │
                                                  │ next time it disappears within new dwell
                                                  ▼
                                            emit signal_source_unavailable (resets cycle)
```

## Persistence boundary

In-memory: `SessionSignals`, `ControllerState`. No DB writes from the controller's hot path.

Persistent: five new `admin_audit_log` action strings. No new tables, no migration.

`routing_log` instrumentation (per V14): per-cycle `dma_controller_eval_ms` plus per-signal `dma_signal_<name>_ms`. Reuses the existing `@with_stage_timing` decorator.

## Hooks introduced

- **Spec 004 amendment** (minimal): `ConvergenceEngine.last_similarity` property (read-only). Single-line addition; does not change spec-004 behavior. Per [research.md §2](./research.md).
- **Spec 013 extension** (controller-only mutability path on `HighTrafficSessionConfig`): `engage_mechanism(name)` / `disengage_mechanism(name)` per [research.md §4](./research.md). Default state preserves spec-013 baseline; only the auto-apply path mutates active flags.
