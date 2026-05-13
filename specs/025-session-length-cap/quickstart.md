# Quickstart: Session-Length Cap with Auto-Conclude Phase

**Branch**: `025-session-length-cap` | **Date**: 2026-05-07 | **Plan**: [plan.md](./plan.md)

Operator + facilitator workflows for opting into the session-length cap. Default behavior with no configuration is unchanged from pre-feature: sessions run until manual stop or budget exhaustion. The cap is strictly opt-in (SC-001).

---

## Operator workflow

### Set deployment-wide defaults (optional)

Edit the `.env` file used by the deployment stack at `<deployment-stack-path>/.env` :

```bash
# No deployment-wide cap by default. Set these only if you want every new session to start with a cap.
SACP_LENGTH_CAP_DEFAULT_KIND=none           # one of: none, time, turns, both
SACP_LENGTH_CAP_DEFAULT_SECONDS=            # optional, [60, 2_592_000]
SACP_LENGTH_CAP_DEFAULT_TURNS=              # optional, [1, 10_000]
SACP_CONCLUDE_PHASE_TRIGGER_FRACTION=0.80   # exclusive (0.0, 1.0)
SACP_CONCLUDE_PHASE_PROMPT_TIER=4           # one of {1, 2, 3, 4}
```

Restart the orchestrator stack using the deployment tooling. Verify config validation passes:

```bash
docker compose logs sacp-orchestrator | grep -i "config validation"
# Expected: "Config validation: 5 new SACP_LENGTH_CAP_*/CONCLUDE_PHASE_* validators passed"
```

If any value is out of range, the orchestrator process exits at startup before binding ports (V16 fail-closed). The error message names the offending variable.

### Verify schema migration applied

After the migration lands:

```bash
docker compose exec sacp-orchestrator alembic current
# Expected output ends with: NNNN_session_length_cap (head)

docker compose exec sacp-postgres psql -U sacp -d sacp -c "\d sessions" | grep -E 'length_cap|conclude_phase|active_seconds'
# Expected: 5 rows showing the new columns
```

---

## Facilitator workflow

### Set a cap at session-create

In the session-create modal (spec 011 amendment), pick a preset:

| Preset | Time cap | Turn cap | Use case |
|---|---|---|---|
| Short | 30 minutes | 20 turns | Consulting working session (V13 §3) |
| Medium | 2 hours | 50 turns | Research synthesis push (V13 §2) |
| Long | 8 hours | 200 turns | Technical review and audit (V13 §5) |
| Custom | hand-set | hand-set | any |

The session row is created with the chosen `length_cap_kind`, `length_cap_seconds`, `length_cap_turns`. Loop starts; cap evaluation runs on every dispatch.

### Set or update a cap mid-session

`PATCH /api/sessions/{session_id}/settings` with the cap fields (see [contracts/cap-set-endpoint.md](./contracts/cap-set-endpoint.md)). Example via curl:

```bash
curl -X PATCH "https://sacp.local/api/sessions/ses_abc/settings" \
  -H "Authorization: Bearer $FACILITATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"length_cap_kind": "turns", "length_cap_turns": 50}'
```

200 response confirms the cap was committed.

### Cap-decrease disambiguation flow

If you set a cap below current elapsed (e.g., turn-cap=20 when at turn 30), the endpoint returns 409 with both interpretation options. Spec 011's modal renders the choice; pick `absolute` (immediate conclude) or `relative` (treat as N more turns from here). Re-POST with the explicit `interpretation`:

```bash
curl -X PATCH "https://sacp.local/api/sessions/ses_abc/settings" \
  -H "Authorization: Bearer $FACILITATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"length_cap_turns": 20, "interpretation": "absolute"}'
```

200 response confirms; loop transitions to conclude phase on next dispatch.

### Watch the conclude phase fire

When elapsed crosses the trigger fraction (default 0.80), participants receive the `session_concluding` WS event and see a banner. AIs receive the Tier 4 conclude delta in their next dispatch. After every active AI has produced one conclude turn, the spec 005 summarizer fires once; the loop transitions to paused with the `session_concluded` WS event.

Tail `routing_log` to watch the transitions:

```bash
docker compose exec sacp-postgres psql -U sacp -d sacp -c \
  "SELECT at, reason, payload FROM routing_log WHERE session_id = 'ses_abc' AND reason IN ('cap_set', 'conclude_phase_entered', 'conclude_phase_exited', 'auto_pause_on_cap', 'manual_stop_during_conclude') ORDER BY at;"
```

Expected sequence for a clean cap → conclude → pause flow:
1. `cap_set` (when the cap was first set, if not at session-create)
2. `conclude_phase_entered` (when trigger fraction crossed)
3. `auto_pause_on_cap` (after final summarizer)

For a cap-extension flow (US3), the sequence is:
1. `cap_set` (initial)
2. `conclude_phase_entered`
3. `cap_set` (extension)
4. `conclude_phase_exited`
5. (loop continues; eventually) `conclude_phase_entered` (second time)
6. `auto_pause_on_cap`

For a manual-stop-during-conclude (US4):
1. `cap_set`
2. `conclude_phase_entered`
3. `manual_stop_during_conclude`

---

## Disabling / rollback

### Disable on a single session

```bash
curl -X PATCH "https://sacp.local/api/sessions/ses_abc/settings" \
  -H "Authorization: Bearer $FACILITATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"length_cap_kind": "none"}'
```

This nulls both `length_cap_seconds` and `length_cap_turns` (FR-022) and stops cap evaluation for the session.

### Disable deployment-wide

Set `SACP_LENGTH_CAP_DEFAULT_KIND=none` (and unset `_DEFAULT_SECONDS` / `_DEFAULT_TURNS`) in the `.env`, restart the orchestrator. New sessions will create with no cap; existing sessions are unaffected (cap-set is per-session, not propagated from env after creation).

---

## Restart recovery

If the orchestrator restarts mid-session, the durable `active_seconds_accumulator` column on `sessions` ensures pause-resume semantics survive (research.md §1). On startup, the orchestrator walks `sessions` rows where `loop_state IN ('running', 'conclude')` and resumes the accumulator from the last `routing_log` timestamp for that session.

A session that was in conclude phase at restart will resume in conclude phase: the orchestrator does NOT re-emit `session_concluding` (the SPA reads loop-state on reconnect and renders the banner from existing state). The next dispatch picks up the conclude delta injection.

If you need to verify recovery semantics during deployment:

```bash
# Before restart: capture current state
docker compose exec sacp-postgres psql -U sacp -d sacp -c \
  "SELECT id, loop_state, length_cap_kind, length_cap_seconds, length_cap_turns, active_seconds_accumulator, conclude_phase_started_at FROM sessions WHERE loop_state IN ('running', 'conclude');"

# Restart
docker compose restart sacp-orchestrator

# After restart: confirm same state, accumulator advanced only by orchestrator-active time
# (NOT by the seconds spent during the restart itself)
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Conclude phase fires unexpectedly early | `SACP_CONCLUDE_PHASE_TRIGGER_FRACTION` set too low | Confirm value; default is 0.80. Raise to 0.85 or 0.90 if the wrap-up rounds need less lead time. |
| Conclude delta missing from AI prompts | `SACP_CONCLUDE_PHASE_PROMPT_TIER` set to a tier the participant isn't using | Default is 4; reset and restart. |
| Cap-set returns 409 unexpectedly | Cap value below current elapsed; disambiguation required | Add `"interpretation": "absolute" \| "relative"` to the request body. |
| `active_seconds_accumulator` advances during pause | Bug — file an issue. The accumulator MUST only advance during running/conclude phases per FR-002. | Confirm with multiple `routing_log` snapshots at pause. |
| All five new env-vars present in `.env` but orchestrator exits at startup | One value out of range | Read the startup error message — it names the offending var. Fix and restart. |
| Test `test_025_regression_no_cap.py` fails | Some new code path fired despite `length_cap_kind='none'` | The SC-001 architectural test caught a leak. Find the call site that ignored the kind check. |
