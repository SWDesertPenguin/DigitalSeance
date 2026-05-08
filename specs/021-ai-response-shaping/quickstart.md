# Quickstart: AI Response Shaping

Operator workflow for enabling, observing, and tuning the two response-shaping dimensions. Assumes Phase 3 has been declared and a running orchestrator deployment.

## Step 1 — Enable the master switch (filler scorer + retry pipeline)

The default Phase 3 configuration ships with shaping disabled. Set the master switch:

```bash
# .env or operator config
SACP_RESPONSE_SHAPING_ENABLED=true
# Leave SACP_FILLER_THRESHOLD unset — per-family defaults from BehavioralProfile apply.
# Leave SACP_REGISTER_DEFAULT unset — defaults to 2 (Conversational).
```

Restart the orchestrator. Verify:

```bash
python -m src.run_apps --validate-config-only
# expected: OK
```

In an active session, drive a turn whose draft is hedge-heavy, restatement-heavy, or carries multiple closing patterns. The filler scorer evaluates every dispatched draft; if the aggregate exceeds the per-family threshold (anthropic/openai default `0.60`; gemini/groq/ollama/vllm default `0.55`), a tightened-Tier-4-delta retry fires. Up to two retries; the first below-threshold retry's output is persisted.

Inspect the routing log:

```sql
SELECT created_at, participant_id, filler_score, shaping_reason,
       shaping_score_ms, shaping_retry_dispatch_ms
FROM routing_log
WHERE filler_score IS NOT NULL
ORDER BY created_at DESC LIMIT 20;
```

The `shaping_reason` column carries `null` when no retry fired, `'filler_retry'` when a below-threshold retry was accepted, `'filler_retry_exhausted'` when both retries also exceeded threshold, or `'shaping_pipeline_error'` on the fail-closed path.

## Step 2 — Tune the threshold based on observed retry firing

If retries fire too often (fast-burning the compound retry budget on legitimately structured turns), raise the threshold uniformly:

```bash
SACP_FILLER_THRESHOLD=0.65
```

When set, this env var overrides every family's default uniformly. Restart.

If retries rarely fire on drafts that operators perceive as filler-heavy, lower the threshold:

```bash
SACP_FILLER_THRESHOLD=0.50
```

Per-family thresholds (the `BehavioralProfile` dict's `default_threshold` field per family) apply when the env var is unset. Operators who need a per-family tightening file a Constitution §14.2 amendment with the override; per-family env vars are out of scope until session experience justifies the operator-tunable surface (per spec assumption).

Diagnostic query — score distribution per family:

```sql
SELECT
    p.provider_family,
    COUNT(*) AS dispatches,
    AVG(rl.filler_score) AS mean_score,
    PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY rl.filler_score) AS p50,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY rl.filler_score) AS p95,
    SUM(CASE WHEN rl.shaping_reason = 'filler_retry'
             THEN 1 ELSE 0 END)::float / COUNT(*) AS retry_rate
FROM routing_log rl
JOIN participants p ON rl.participant_id = p.id
WHERE rl.filler_score IS NOT NULL
  AND rl.created_at > NOW() - INTERVAL '24 hours'
GROUP BY p.provider_family
ORDER BY mean_score DESC;
```

Use the `retry_rate` column to assess whether the threshold is biting too aggressively (rate > 0.30 likely too low) or too leniently (rate < 0.05 likely too high) per family.

## Step 3 — Set the session-level register slider

The slider is independent of the master switch — it always emits its preset's Tier 4 delta into the prompt assembler regardless of `SACP_RESPONSE_SHAPING_ENABLED`. Slider deltas are a prompt-composition concern, not a shaping concern.

The slider is a facilitator runtime tool (set via the orchestrator-controls UI when spec 011 ships, or via the facilitator API directly until then). Five positions:

| Slider | Preset | Delta |
|---|---|---|
| 1 | Direct | "Reply briefly and directly. No preamble, no restatement, no closing." |
| 2 | Conversational | "Reply in a conversational register. Brief preamble acceptable; avoid academic register." |
| 3 | Balanced | (no delta — tier text alone) |
| 4 | Technical | "Use precise technical register. Cite sources for non-obvious claims." |
| 5 | Academic | "Use formal academic register. Structured argumentation with explicit citations expected." |

After each change, query `/me` for any participant in the session — the response includes the new `register_slider`, `register_preset`, and `register_source='session'`:

```bash
curl -s -H "Authorization: Bearer $TOKEN" "$ORCH/me/$PARTICIPANT_ID" | jq '{register_slider, register_preset, register_source}'
# {
#   "register_slider": 1,
#   "register_preset": "direct",
#   "register_source": "session"
# }
```

Audit-log query:

```sql
SELECT timestamp, target_id, previous_value, new_value, facilitator_id
FROM admin_audit_log
WHERE action = 'session_register_changed'
ORDER BY timestamp DESC LIMIT 10;
```

## Step 4 — Set a per-participant override

For mixed-register sessions (the V13 §2 research-co-authorship case), the facilitator can override a single participant's register without affecting others. The override is audit-logged on every set/clear; cascade-deletes on participant or session removal are NOT audit-logged separately (the parent event is sufficient).

After setting an override, verify isolation:

```bash
# Override-targeted participant
curl -s "$ORCH/me/$P_OVERRIDE_ID" | jq '{register_slider, register_source}'
# { "register_slider": 5, "register_source": "participant_override" }

# Same-session non-overridden participant
curl -s "$ORCH/me/$P_OTHER_ID" | jq '{register_slider, register_source}'
# { "register_slider": 4, "register_source": "session" }
```

Audit-log query for override events:

```sql
SELECT timestamp, action, target_id, new_value, facilitator_id
FROM admin_audit_log
WHERE action IN ('participant_register_override_set',
                 'participant_register_override_cleared')
ORDER BY timestamp DESC LIMIT 20;
```

## Step 5 — Observe per-stage shaping cost

```sql
-- Look for shaping cost regressions
SELECT
    AVG(shaping_score_ms)         AS mean_score_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY shaping_score_ms) AS p95_score_ms,
    AVG(shaping_retry_dispatch_ms) AS mean_retry_dispatch_ms,
    COUNT(*) FILTER (WHERE shaping_retry_dispatch_ms IS NOT NULL) AS retries_fired
FROM routing_log
WHERE shaping_score_ms IS NOT NULL
  AND created_at > NOW() - INTERVAL '1 hour';
```

Per V14 budget 1: `p95_score_ms` SHOULD stay under 50ms. A regressing scorer (e.g., a future `_HEDGE_TOKENS` list expansion that explodes regex cost) shows up here first.

## Step 6 — Disable / rollback

Unset the master switch and restart:

```bash
SACP_RESPONSE_SHAPING_ENABLED=false
```

The filler scorer + retry pipeline becomes inactive — no scoring runs, no retries fire, no `routing_log` shaping columns populate. Pre-feature acceptance tests pass byte-identically (SC-002 regression contract).

The register slider remains active independent of the master switch. To disable the slider (return to tier-text-only assembly), the facilitator sets the slider to `3` (Balanced — no delta), or operators unset the participants' overrides and remove the `session_register` rows.

## Topology-7 forward note

If/when topology 7 (MCP-to-MCP) ships, set `SACP_TOPOLOGY=7` to cleanly disable the shaping pipeline AND the register-preset emitter without removing `SACP_RESPONSE_SHAPING_ENABLED` configuration. Per [research.md §10](./research.md): the shaping pipeline init checks the topology env var and skips spawning. Topology 7 doesn't exist today — this is forward documentation.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Orchestrator exits with "must be in [0.0, 1.0]" | `SACP_FILLER_THRESHOLD` out of range | Set within `[0.0, 1.0]` |
| Orchestrator exits with "must be in [1, 5]" | `SACP_REGISTER_DEFAULT` out of range | Set within `[1, 5]` |
| Orchestrator exits with "must be 'true' or 'false'" | `SACP_RESPONSE_SHAPING_ENABLED` not parseable | Set to `true` or `false` (case-insensitive) or `1`/`0` |
| `shaping_reason='filler_retry_exhausted'` on every turn | Threshold too tight; or model genuinely insensitive to the tightened delta | Raise threshold; investigate model-specific tendencies via the per-family score-distribution query in Step 2 |
| `shaping_reason='shaping_pipeline_error'` repeatedly | Sentence-transformers gone, regex bug, or embedding decode failure | Inspect orchestrator logs for the warning trail; the session continues — no loop gating |
| `/me` doesn't reflect a slider change | Resolver query pointing at wrong session row | Confirm the participant's `session_id` matches the session whose slider was set |
| Override survived participant remove | Cascade not firing | Investigate FK constraint on `participant_register_override.participant_id` — must be `ON DELETE CASCADE` |
| Retries firing at the per-stage timing budget ceiling | Shaping retry dispatch dominates per-turn cost | Raise threshold to fire fewer retries OR investigate provider-side latency; per FR-006 each retry consumes one compound-retry slot |

## Operator authority boundary

The three new env vars (`SACP_FILLER_THRESHOLD`, `SACP_REGISTER_DEFAULT`, `SACP_RESPONSE_SHAPING_ENABLED`) are operator-deployment surfaces, not facilitator runtime tools (Constitution §5). Facilitators cannot toggle the master switch mid-session. Reconfiguration requires an orchestrator restart.

The session register slider AND per-participant override ARE facilitator runtime tools — both are settable mid-session and audit-logged on every change.

The shaping pipeline cannot reconfigure spec 008's prompt assembler beyond emitting a Tier 4 delta and a shaping-retry delta. To change the existing tier text, edit `src/prompts/tiers.py` and follow the spec 008 amendment process.
