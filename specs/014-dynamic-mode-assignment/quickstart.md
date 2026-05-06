# Quickstart: Dynamic Mode Assignment

Operator workflow for enabling, observing, and tuning the controller. Assumes spec 013 (high-traffic-mode) has reached Status: Implemented and a running orchestrator deployment.

## Step 1 — Enable advisory mode (recommended starting point)

The default Phase 3 configuration is advisory-only. Set one threshold:

```bash
# .env or operator config
SACP_DMA_TURN_RATE_THRESHOLD_TPM=30
# Leave SACP_AUTO_MODE_ENABLED unset — defaults to false (advisory mode).
```

Restart the orchestrator. Verify:

```bash
python -m src.run_apps --validate-config-only
# expected: OK
```

In an active session, drive AI exchanges above 30 tpm for the full observation window (5 minutes). Within ~5 seconds of the window completing, the controller emits a `mode_recommendation` audit event:

```sql
SELECT timestamp, target_id, action, new_value
FROM admin_audit_log
WHERE action = 'mode_recommendation'
ORDER BY timestamp DESC LIMIT 5;
```

The `new_value` column carries the decision payload (action, triggers, signal observations, dwell floor). Spec-013 mechanisms remain in their pre-recommendation state — this is advisory-only.

## Step 2 — Add more signals

Add the convergence-derivative and queue-depth thresholds for richer judgment:

```bash
SACP_DMA_TURN_RATE_THRESHOLD_TPM=30
SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD=0.15
SACP_DMA_QUEUE_DEPTH_THRESHOLD=10
```

Restart. The controller now considers all three signals; ENGAGE recommendations fire when ANY one crosses its threshold (FR-009 asymmetry). DISENGAGE requires ALL configured signals to be below threshold for the dwell window.

## Step 3 — Promote to auto-apply (after advisory observation builds confidence)

Once the operator trusts the controller's signal interpretation across multiple sessions, enable auto-apply:

```bash
SACP_DMA_TURN_RATE_THRESHOLD_TPM=30
SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD=0.15
SACP_DMA_QUEUE_DEPTH_THRESHOLD=10
SACP_DMA_DWELL_TIME_S=120
SACP_AUTO_MODE_ENABLED=true
```

Restart. The orchestrator validates that `SACP_DMA_DWELL_TIME_S` is set when `SACP_AUTO_MODE_ENABLED=true` (FR-010 cross-validator); if the dwell is missing, it exits at startup with a clear error.

In an active session crossing thresholds:
- A `mode_transition` audit event fires (in addition to the `mode_recommendation`).
- The controller engages spec-013 mechanisms whose env vars are set; mechanisms whose env vars are NOT set are listed in `skipped_mechanisms[]` (silent skip per spec 013 each-mechanism-independent contract).
- The dwell floor activates: counter-direction transitions are suppressed for `SACP_DMA_DWELL_TIME_S` seconds.

```sql
SELECT timestamp, action, new_value
FROM admin_audit_log
WHERE action IN ('mode_recommendation', 'mode_transition',
                 'mode_transition_suppressed', 'decision_cycle_throttled',
                 'signal_source_unavailable')
ORDER BY timestamp DESC LIMIT 20;
```

## Step 4 — Tune dwell + thresholds based on observed flap

If the audit log shows frequent `mode_transition_suppressed` events with `reason=dwell_floor_not_reached`, the dwell is doing its job. If you see frequent `mode_transition` events oscillating ENGAGE/DISENGAGE within a short window, lengthen `SACP_DMA_DWELL_TIME_S`.

If you see `decision_cycle_throttled` events more than a few times per hour, the signal-evolution cadence is faster than the controller's cap (12 dpm = one decision every 5s). The cap is a hard CPU-cost ceiling — investigate whether signals are genuinely fluctuating that fast or whether a downstream measurement is jittering.

If you see frequent `signal_source_unavailable` events for one signal, that source's data feed has issues. Per FR-013 these are rate-limited (one per dwell window per signal), so the audit log won't flood, but the underlying problem warrants attention. Mitigation: unset that signal's threshold env var to disable it cleanly while you debug.

## Step 5 — Observe per-signal cost in routing_log

```sql
-- Look for any single signal with disproportionate cost
SELECT stage, COUNT(*), AVG(duration_ms), MAX(duration_ms)
FROM routing_log_stages
WHERE stage LIKE 'dma_signal_%' OR stage = 'dma_controller_eval_ms'
  AND created_at > NOW() - INTERVAL '1 hour'
GROUP BY stage
ORDER BY AVG(duration_ms) DESC;
```

Per V14: total controller cost SHOULD stay under 50ms P95 (SC-003); a regressing signal source can be identified by its `dma_signal_<name>_ms` cost profile (FR-012).

## Step 6 — Disable / rollback

Unset all `SACP_DMA_*` env vars and restart. The controller becomes inactive — no decision cycles run, no audit events emit. Spec-013 mechanisms remain governed by their own env vars (operator-set values still apply unchanged). This satisfies SC-004's regression-equivalence contract.

## Topology-7 forward note

If/when topology 7 ships, set `SACP_TOPOLOGY=7` to cleanly disable this controller without removing `SACP_DMA_*` configuration. The controller's start path checks the topology env var and skips spawning per [research.md §7](./research.md). Topology 7 doesn't exist today — this is forward documentation.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Orchestrator exits with "must be in [1, 600]" | SACP_DMA_TURN_RATE_THRESHOLD_TPM out of range | Set within `[1, 600]` |
| Orchestrator exits with "auto-apply requires SACP_DMA_DWELL_TIME_S" | FR-010 cross-validator | Set the dwell time before enabling auto-apply |
| No recommendations after threshold should be crossed | Window not yet full (5-minute warmup) | Wait one full observation window after restart |
| Recommendations emitted constantly | Threshold too loose for the session's natural traffic | Raise threshold, or add another signal that sharpens the decision |
| Auto-apply oscillating ENGAGE/DISENGAGE | Dwell too short relative to signal evolution | Lengthen `SACP_DMA_DWELL_TIME_S` |
| `signal_source_unavailable` events repeatedly | Underlying signal source's data feed broken | Disable that signal; investigate the source module |

## Operator authority boundary

These env vars are operator-deployment surfaces, not facilitator runtime tools (Constitution §5). Facilitators cannot toggle the controller mid-session. Reconfiguration requires an orchestrator restart.

The controller cannot reconfigure spec-013 mechanism thresholds — it can only toggle whether configured mechanisms engage (FR-016). To change a spec-013 threshold, edit its `SACP_HIGH_TRAFFIC_*` env var and restart.
