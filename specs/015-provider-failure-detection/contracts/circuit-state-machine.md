# Contract: Circuit Breaker State Machine

**Feature**: Provider Failure Detection and Isolation (spec 015)
**Date**: 2026-05-13

---

## States

| State | Description |
|---|---|
| `closed` | Normal dispatch. Failures are recorded; threshold not yet reached. |
| `open` | Dispatch short-circuited. Waiting for backoff interval to elapse before probe. |
| `half_open` | Backoff interval elapsed. Exactly one probe in flight. Dispatch still skipped. |

All breakers start in `closed` state. Absence of an entry in the process-scope dict implies `closed`.

---

## Transitions

### closed -> open

**Trigger**: `record_failure()` is called and the sliding-window count of failures within `SACP_PROVIDER_FAILURE_WINDOW_S` seconds reaches or equals `SACP_PROVIDER_FAILURE_THRESHOLD`.

**Guard**: both `SACP_PROVIDER_FAILURE_THRESHOLD` and `SACP_PROVIDER_FAILURE_WINDOW_S` are set (breaker active). If either is unset, `record_failure()` is a no-op.

**Actions**:
1. Set `state = "open"`, record `opened_at = now()`.
2. Set `consecutive_open_turns = 0`.
3. Set `probe_schedule_position = 0`.
4. Write `provider_circuit_open_log` row (async, non-blocking).
5. Existing auto-pause path continues to apply via `_record_failure_and_announce` (loop.py) — announcement broadcast.

### open -> half_open

**Trigger**: `is_open()` is called and `SACP_PROVIDER_RECOVERY_PROBE_BACKOFF` is set and the elapsed time since `opened_at` (or since last failed probe) exceeds the interval at `probe_schedule[probe_schedule_position]`.

**Guard**: `SACP_PROVIDER_RECOVERY_PROBE_BACKOFF` is set AND no probe task is currently in flight (`_probe_task is None or _probe_task.done()`).

**Actions**:
1. Set `state = "half_open"`.
2. Launch `asyncio.create_task(_run_probe(...))` — stored as `_probe_task`.
3. Turn dispatch for this participant is still skipped (`is_open()` returns `True` for `half_open`).

### half_open -> closed (probe success)

**Trigger**: the probe task completes with `ValidationResult.ok == True` within `SACP_PROVIDER_PROBE_TIMEOUT_S` seconds.

**Guard**: current state is `half_open`.

**Actions**:
1. Write `provider_circuit_probe_log` row with `probe_outcome="success"`.
2. Set `state = "closed"`, clear `opened_at`, reset `failure_window`, reset `consecutive_open_turns`.
3. Write `provider_circuit_close_log` row with `trigger_reason="probe_success"`.
4. Clear `_probe_task = None`.

### half_open -> open (probe failure)

**Trigger**: the probe task completes with `ValidationResult.ok == False` OR raises an exception OR times out.

**Guard**: current state is `half_open`.

**Actions**:
1. Write `provider_circuit_probe_log` row with `probe_outcome="failure"` or `"timeout"`.
2. Set `state = "open"` (back to waiting).
3. Advance `probe_schedule_position`: if `position < len(schedule) - 1`, increment by 1. If `position == len(schedule) - 1`, stay pinned (cycle-on-last per FR-009). If this is the first probe at the pinned last position (newly cycled), set `schedule_exhausted=True` on the probe log row.
4. Record the new `opened_at` reference time for the next backoff interval (set to now).
5. Clear `_probe_task = None`.

### open/half_open -> closed (api_key_update fast-close, FR-016)

**Trigger**: `update_api_key` MCP tool succeeds for this participant while breaker is open or half_open.

**Guard**: breaker state is `open` or `half_open` for the matching `(session_id, participant_id)` key at any fingerprint (the key changes on rotation; fast-close uses participant_id match only).

**Actions**:
1. Cancel in-flight probe task if any.
2. Set `state = "closed"`, clear `opened_at`, reset `failure_window`, reset `consecutive_open_turns`.
3. Write `provider_circuit_close_log` row with `trigger_reason="api_key_update"`.
4. Write `provider_circuit_probe_log` entries for any cancelled in-flight probe with `probe_outcome="cancelled"`.
5. The circuit key changes (new `api_key_fingerprint`); old key entry is deleted from the process dict.

---

## is_open() semantics

`is_open(session_id, participant_id, provider, api_key_fingerprint)` returns `True` when state is `open` or `half_open`. The dispatch path MUST call `is_open()` before every dispatch. When `True`, the turn is skipped per existing §6.6 fallback policy (FR-004, FR-005).

Side effect: `is_open()` increments `consecutive_open_turns` when returning `True`. When `consecutive_open_turns >= 3`, the existing auto-pause path in `_record_failure_and_announce` fires (FR-005).

---

## Guards when env vars are unset

When `SACP_PROVIDER_FAILURE_THRESHOLD` or `SACP_PROVIDER_FAILURE_WINDOW_S` is unset:
- `record_failure()` is a no-op; returns `False`.
- `is_open()` always returns `False`.
- No `CircuitState` entry is created.
- Behavior is byte-identical to the pre-feature baseline (SC-005).

---

## Per-participant isolation guarantee (FR-010)

The process-scope dict is keyed on the full `(session_id, participant_id, provider, api_key_fingerprint)` tuple. No method on one entry reads or writes any other entry. Two participants sharing the same provider but with different `participant_id` values have independent dict entries and independent state machines. A participant's `api_key_fingerprint` changing (key rotation) creates a new dict entry; the old entry is evicted on fast-close.
