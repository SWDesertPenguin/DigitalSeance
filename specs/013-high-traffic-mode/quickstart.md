# Quickstart: High-Traffic Session Mode

Operator workflow for enabling, observing, and disabling the three high-traffic mechanisms. Assumes a running orchestrator deployed per the standard Phase 2 instructions (Compose stack on TrueNAS / k8s / bare-metal Docker).

## Enable batching cadence (mechanism 1)

For consulting sessions with a `review_gate` human:

```bash
# .env or operator config
SACP_HIGH_TRAFFIC_BATCH_CADENCE_S=15
```

Restart the orchestrator. Verify startup validator passes:

```bash
python -m src.run_apps --validate-config-only
# expected: OK
```

In an active session with at least one human participant, drive AI exchanges above the threshold. Confirm in the Web UI that messages arrive in batched envelopes every ~15s (one delivery per recipient per cadence tick).

In `routing_log`, look for `batch_open_ts` / `batch_close_ts` columns:

```sql
SELECT session_id, recipient_id, batch_open_ts, batch_close_ts,
       (batch_close_ts - batch_open_ts) AS hold_duration
FROM routing_log
WHERE batch_close_ts IS NOT NULL
ORDER BY batch_close_ts DESC LIMIT 20;
```

`hold_duration` should stay at or below `cadence + 5s`. Sustained breaches mean the scheduler is under-provisioned — scale up or reduce the cadence.

## Enable per-session convergence override (mechanism 2)

For research co-authorship sessions where global threshold trips too early:

```bash
SACP_CONVERGENCE_THRESHOLD_OVERRIDE=0.85
```

Restart orchestrator. Verify in the convergence engine's per-session log that `_threshold` is `0.85`, not the global default.

Test by driving a session to similarity 0.75 — the engine should NOT declare convergence. Drive to 0.86 — it SHOULD declare convergence and proceed to summarization.

## Enable observer-downgrade (mechanism 3)

For high-participant Phase 3 sessions where context-window pressure threatens session quality:

```bash
SACP_OBSERVER_DOWNGRADE_THRESHOLDS=participants:4,tpm:30,restore_window_s:120
```

Restart orchestrator.

Drive a 5-participant session above 30 turns/minute. Within one turn-prep cycle the lowest-priority active participant should transition to observer:

```sql
SELECT * FROM admin_audit_log
WHERE action IN ('observer_downgrade', 'observer_restore', 'observer_downgrade_suppressed')
ORDER BY timestamp DESC LIMIT 20;
```

When tpm drops below 30 sustained for `restore_window_s` seconds (default 120), the participant is restored.

### Last-human protection

If the lowest-priority candidate is the only human in the session, the downgrade is suppressed:

```sql
SELECT new_value FROM admin_audit_log
WHERE action = 'observer_downgrade_suppressed'
ORDER BY timestamp DESC LIMIT 1;
-- {"reason": "last_human_protection", ...}
```

The session continues without anyone downgrading for that evaluation cycle.

## Disable / rollback

Unset the env var(s) and restart. With all three unset, behavior is identical to Phase 2:
- No batch envelopes emitted (renderer falls back to per-turn).
- Convergence engine reads global `SACP_CONVERGENCE_THRESHOLD` (or its DEFAULT_THRESHOLD constant).
- No `observer_*` rows written.

Verify regression-equivalence by running the SC-005 regression suite:

```bash
pytest tests/test_013_regression_phase2.py -q
```

All 6 curated Phase 2 scenarios pass.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Orchestrator exits at startup with "must be > 0" | Invalid SACP_HIGH_TRAFFIC_BATCH_CADENCE_S value (zero, negative, or > 300) | Set within `[1, 300]` |
| Orchestrator exits with "must be in (0.0, 1.0)" | Invalid SACP_CONVERGENCE_THRESHOLD_OVERRIDE | Set within strict `(0.0, 1.0)` bounds |
| Orchestrator exits with "missing required key" | SACP_OBSERVER_DOWNGRADE_THRESHOLDS missing `participants` or `tpm` | Include both required keys |
| Orchestrator exits with "unknown key" | Typo in SACP_OBSERVER_DOWNGRADE_THRESHOLDS | Check spelling against `participants`, `tpm`, `restore_window_s` |
| Batched envelope never closes | Flush task not running | Check orchestrator logs for the per-session flush task spawn message; if missing, restart orchestrator |
| Downgrade not firing despite tpm above threshold | Last-human protection suppressing | Look for `observer_downgrade_suppressed` audit row |

## Operator authority

These three env vars are operator-deployment surfaces, not facilitator runtime tools. Per Constitution §5, facilitators cannot toggle them mid-session. Reconfiguration requires an orchestrator restart.
