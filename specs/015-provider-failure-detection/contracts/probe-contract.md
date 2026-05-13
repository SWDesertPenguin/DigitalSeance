# Contract: Recovery Probe

**Feature**: Provider Failure Detection and Isolation (spec 015)
**Date**: 2026-05-13

---

## What a probe call is

A probe is a call to `adapter.validate_credentials(api_key, model)` on the process-scope `ProviderAdapter` singleton (from `src/api_bridge/adapter.py`). This is the same call made by the `update_api_key` MCP tool during key validation (spec §7.1). It is a lightweight credential check, not a full dispatch.

The probe call is wrapped with `asyncio.wait_for(..., timeout=SACP_PROVIDER_PROBE_TIMEOUT_S)` when that var is set; when unset, it inherits the LiteLLM adapter's configured call timeout.

The probe is launched as `asyncio.create_task` from within the breaker at the `open -> half_open` transition. It runs concurrently with other participant turns; it MUST NOT block the turn loop.

---

## Inputs to the probe call

| Field | Source |
|---|---|
| `api_key` | Decrypt `participant.api_key_encrypted` using the session's `encryption_key` from `_TurnContext`. |
| `model` | `participant.model` |

These are read from the `CircuitState`'s stored participant reference at the time the probe task fires.

---

## Result classification

| Outcome | Condition | Probe log `probe_outcome` | Breaker transition |
|---|---|---|---|
| Success | `ValidationResult.ok == True` | `"success"` | `half_open -> closed` |
| Failure | `ValidationResult.ok == False` | `"failure"` | `half_open -> open` |
| Exception | any exception raised by `validate_credentials` | `"failure"` | `half_open -> open` |
| Timeout | `asyncio.TimeoutError` from `wait_for` | `"timeout"` | `half_open -> open` |

All non-success outcomes keep the breaker in (or return it to) `open` state. This is conservative: when in doubt, keep the circuit open and wait for the next backoff interval.

---

## Probe does not enter the transcript

A probe call is not a dispatch call. Specifically:
- No entry is written to the `messages` table.
- No entry is written to the `routing_log` table.
- No WS event is broadcast for the probe itself.
- The probe result is captured only in `provider_circuit_probe_log`.

FR-007 is satisfied by choosing `validate_credentials()` as the probe mechanism.

---

## Probe frequency guarantee (FR-006)

The `half_open` state enforces "at most one probe per backoff tick":
- A probe task is created only when `state == "open"` AND the backoff interval has elapsed AND `_probe_task is None or _probe_task.done()`.
- While `_probe_task` is running (`state == "half_open"`), no new probe task is created regardless of how many dispatch calls `is_open()` handles.
- When the probe completes (any outcome), `_probe_task` is cleared and the state machine transitions before any new probe can be scheduled.

---

## Backoff schedule consumed by probe scheduling

The probe is triggered from within `is_open()` at the moment the backoff interval for `probe_schedule[probe_schedule_position]` has elapsed since the last `opened_at` reference time. The reference time is:
- Set to `opened_at` when the breaker first trips.
- Reset to `now()` after each failed probe (the next interval starts counting from the failure, not from the original open).

This means the backoff schedule is a delay-between-probes schedule, not an absolute-time schedule relative to the original trip time.
