# Quickstart: AI Participant Standby Modes

**Spec**: `specs/027-participant-standby-modes/spec.md`

This quickstart walks an operator through enabling the standby feature, setting wait modes per participant, and observing the behavior.

## Step 1 — Set the four env vars

In your deployment's `.env`:

```
SACP_STANDBY_DEFAULT_WAIT_MODE=wait_for_human
SACP_STANDBY_FILLER_DETECTION_TURNS=5
SACP_STANDBY_PIVOT_TIMEOUT_SECONDS=600
SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION=1
```

The defaults shown above match production-recommended values. The V16 validator family refuses to bind ports on out-of-range values; operator typos exit at startup with a clear error.

## Step 2 — Apply the migration

```bash
docker compose exec orchestrator alembic upgrade head
```

The migration `021_participant_standby_modes` adds three columns to `participants` and three columns to `routing_log`, plus extends the `participants.status` CHECK constraint to permit the new `standby` value. Pre-existing rows default to `wait_mode='wait_for_human'`, `standby_cycle_count=0`, `wait_mode_metadata='{}'`.

## Step 3 — Verify the participant-side setter endpoint

A participant (or the facilitator on their behalf) sets the wait mode via:

```bash
curl -X POST http://localhost:8750/tools/participant/set_wait_mode \
  -H "Authorization: Bearer $PARTICIPANT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "$SESSION", "participant_id": "$PARTICIPANT", "wait_mode": "always"}'
```

The response carries the new value and an `admin_audit_log` row with `action=wait_mode_changed` is written.

## Step 4 — Observe standby in a live session

Drive a session with two AI participants. AI-A asks the facilitator a question via natural conversation (the spec 004 question detector fires `ai_question_opened`). The facilitator does not reply.

- On the next round-robin tick, the orchestrator's standby evaluator finds the unresolved question event for AI-A and transitions AI-A to `status='standby'`.
- A `participant_standby` WS event broadcasts with `reason='awaiting_human'`.
- The SPA renders a `Standby — awaiting human` pill on AI-A's participant card.
- AI-A is skipped from dispatch; AI-B continues to take turns normally.
- An `admin_audit_log` row records `action='standby_entered'`.

When the facilitator finally replies via `inject_message`, the question event resolves. On the next round-robin tick:

- The standby evaluator clears AI-A's standby flag.
- A `participant_standby_exited` WS event fires.
- AI-A dispatches on its next eligible slot.

## Step 5 — Observe `always` mode

Set AI-A's wait_mode to `always` via Step 3. Drive a session where AI-A asks an unresolved question. On the next round-robin tick:

- AI-A's status remains `active` (the evaluator skips `always`-mode participants).
- The bridge layer's prompt assembler appends the Tier 4 acknowledgment delta to AI-A's prompt.
- AI-A produces a turn that acknowledges the unmet wait, states an assumption, and proceeds.

## Step 6 — Observe the auto-pivot

Leave a `wait_for_human`-mode participant in standby for 5 consecutive round-robin cycles AND past 600 seconds since the gating event opened (the defaults). On the next tick:

- The orchestrator injects a single pivot message into the transcript with `kind='orchestrator_pivot'` metadata.
- The SPA renders the pivot message with distinct banner-style styling.
- An `admin_audit_log` row records `action='pivot_injected'` with `cycles_at_pivot=5` metadata.
- The participant transitions to long-term-observer (`wait_mode_metadata.long_term_observer=true`).
- An `admin_audit_log` row records `action='standby_observer_marked'`.
- The SPA's participant-card renderer swaps the standby pill for the long-term-observer badge.

If a second participant also reaches the pivot threshold later in the same session, the rate cap (default 1) prevents a second pivot — the would-have-pivoted condition logs `routing_log.reason='pivot_skipped_rate_cap'`.

## Step 7 — Observe the long-term-observer exit

When the human finally replies to the long-term-observer participant's gating question, on the next tick:

- The standby evaluator clears the standby flag.
- The `wait_mode_metadata.long_term_observer` flag is cleared.
- The participant returns to `status='active'`.
- The `participant_update` WS event broadcasts with the new state.

Long-term observer is NOT sticky — gate clearance exits the participant cleanly per FR-021.

## Troubleshooting

- **The standby evaluator doesn't fire**: Check `SACP_STANDBY_DEFAULT_WAIT_MODE` is not set to `always` (which opts every new participant out of standby). Check the participant's `wait_mode` column directly via `psql` or the spec 010 debug-export.
- **The pivot never fires**: Verify `SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION` is at least 1 (a value of 0 disables auto-pivot per FR-019). Verify the consecutive cycle count via `SELECT standby_cycle_count FROM participants WHERE id=...`.
- **The standby evaluator is slow**: Inspect `routing_log.standby_eval_ms` for the participant. The V14 budget is P95 < 1ms; sustained values above 5ms indicate a regression and should be reported.
