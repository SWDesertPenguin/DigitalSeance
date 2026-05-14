# Quickstart: Provider Failure Detection and Isolation

**Feature**: spec 015 — Bridge-Layer Circuit Breaker
**Date**: 2026-05-13

---

## Enable the circuit breaker

The circuit breaker is inactive by default. All four env vars must be consistent to activate it. Set in your `.env` or `compose.yaml` environment block:

```env
# Minimum activation — threshold + window (both or neither)
SACP_PROVIDER_FAILURE_THRESHOLD=3
SACP_PROVIDER_FAILURE_WINDOW_S=60

# Auto-recovery probe backoff (optional; omit to keep breaker open until restart/key-update)
SACP_PROVIDER_RECOVERY_PROBE_BACKOFF=5,10,30,60

# Probe timeout in seconds (optional; omit to inherit the LiteLLM call timeout)
SACP_PROVIDER_PROBE_TIMEOUT_S=5
```

Restart the orchestrator. At startup the validator will confirm:
- Both threshold and window are set (or both are unset).
- Each backoff entry is an integer in [1, 600].
- Backoff list has 1-10 entries.
- Probe timeout is in [1, 30].

If any value is invalid, the process exits with a message naming the offending variable before binding any port.

---

## Observe breaker state in audit logs

### Which participants are currently open

```sql
SELECT
  o.session_id,
  o.participant_id,
  o.trigger_reason,
  o.failure_count,
  o.opened_at,
  EXTRACT(EPOCH FROM (NOW() - o.opened_at))::int AS open_seconds
FROM provider_circuit_open_log o
LEFT JOIN provider_circuit_close_log c
  ON o.session_id = c.session_id
  AND o.participant_id = c.participant_id
  AND c.closed_at > o.opened_at
WHERE c.id IS NULL
ORDER BY o.opened_at DESC;
```

### Recent probe attempts for a participant

```sql
SELECT probe_at, probe_outcome, probe_latency_ms, schedule_position, schedule_exhausted
FROM provider_circuit_probe_log
WHERE session_id = '<session_id>'
  AND participant_id = '<participant_id>'
ORDER BY probe_at DESC
LIMIT 20;
```

### Recovery events (circuit closed)

```sql
SELECT closed_at, total_open_seconds, probes_attempted, probes_succeeded, trigger_reason
FROM provider_circuit_close_log
WHERE session_id = '<session_id>'
ORDER BY closed_at DESC;
```

---

## Observe breaker state in the metrics surface

The `/metrics` endpoint (per FR-013) exposes per-session circuit breaker state:

```
sacp_circuit_breaker_open_total          # count of currently-open breakers per session
sacp_circuit_breaker_open_since          # per-participant timestamp while open (gauge)
sacp_circuit_breaker_trigger_reason      # breakdown by trigger_reason label
```

Example Prometheus query to find open breakers across all sessions:

```promql
sacp_circuit_breaker_open_total > 0
```

---

## Observe short-circuited turns in the routing log

Every skipped turn due to an open breaker is captured in `routing_log` per spec 003 §FR-030. Filter by `skip_reason = 'circuit_open'`:

```sql
SELECT session_id, participant_id, created_at, skip_reason
FROM routing_log
WHERE skip_reason = 'circuit_open'
ORDER BY created_at DESC
LIMIT 50;
```

---

## Force fast recovery via API key rotation

When you rotate a participant's API key via the `update_api_key` MCP tool and the validation succeeds, the circuit breaker closes immediately (FR-016) without waiting for the next probe tick. The close is recorded with `trigger_reason = 'api_key_update'` in `provider_circuit_close_log`.

---

## Disable / roll back

To deactivate the circuit breaker without code changes:

```env
# Unset all four vars (or remove them from your .env):
# SACP_PROVIDER_FAILURE_THRESHOLD=
# SACP_PROVIDER_FAILURE_WINDOW_S=
# SACP_PROVIDER_RECOVERY_PROBE_BACKOFF=
# SACP_PROVIDER_PROBE_TIMEOUT_S=
```

With all four vars unset, dispatch behavior is byte-identical to the pre-feature baseline (SC-005). No existing audit rows are affected; the new tables remain empty.

---

## What to check when a breaker trips

1. Query `provider_circuit_open_log` for the `trigger_reason` — `auth_error` means the API key may have been revoked; `timeout` or `error_5xx` indicates a provider-side outage; `quality_failure` indicates the model is returning degraded output.
2. Check `provider_circuit_probe_log` to confirm probe attempts are firing on schedule.
3. If the provider has recovered but probes are still failing, inspect probe latency. If probes time out, increase `SACP_PROVIDER_PROBE_TIMEOUT_S`.
4. For immediate recovery on an auth error, rotate the API key via `update_api_key` — this fast-closes the breaker.
