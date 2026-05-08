# Contract: WebSocket Events

**Branch**: `025-session-length-cap` | **Source**: spec FR-017, FR-018, FR-019 | **Date**: 2026-05-07

Two new WS events broadcast to all session participants on conclude-phase transitions. Both follow the existing `src/web_ui/events.py` envelope shape (cross-ref spec 011 ws-events contract for the envelope schema).

---

## `session_concluding`

**Trigger**: emitted on the running → conclude FSM transition (FR-007). Broadcast to every connected participant in the session.

**Payload**:

```json
{
  "event": "session_concluding",
  "session_id": "ses_…",
  "trigger_reason": "turns" | "time" | "both",
  "trigger_value": {
    "turns": 16,
    "seconds": 1440
  },
  "remaining": {
    "turns": 4,
    "seconds": 360
  },
  "trigger_fraction": 0.80,
  "at": "2026-05-07T18:32:11.482Z"
}
```

**Field semantics**:
- `trigger_reason`: which dimension's trigger fraction was crossed (`'turns'`, `'time'`, or `'both'` if both crossed simultaneously).
- `trigger_value`: the elapsed-counter values at trigger time (NOT the cap values; cap values stay facilitator-only per FR-019).
- `remaining`: counts to 100% on each capped dimension; null on uncapped dimensions. The frontend banner uses these to render "N turns left" / "N minutes left".
- `trigger_fraction`: the configured fraction (defaults to 0.80, configurable per `SACP_CONCLUDE_PHASE_TRIGGER_FRACTION`). Useful for clients computing percentages.
- `at`: orchestrator timestamp at the FSM transition.

**Visibility**: broadcast to ALL session participants (facilitator and non-facilitator alike). Non-facilitators receive `remaining` and `trigger_fraction` but NOT the cap values themselves — preserving FR-019's facilitator-only cap visibility.

**Spec 011 consumer**: renders the banner "Session is concluding — N turns left" / "Session is concluding — N minutes left" at the top of the participant view. Banner persists until `session_concluded` (or `session_concluding` is re-emitted with updated `remaining` after a cap-extension exit-and-re-enter cycle, US3).

---

## `session_concluded`

**Trigger**: emitted on the conclude → paused / stopped FSM transition (FR-012, FR-015). Broadcast to every connected participant.

**Payload**:

```json
{
  "event": "session_concluded",
  "session_id": "ses_…",
  "pause_reason": "auto_pause_on_cap" | "manual_stop_during_conclude",
  "summarizer_outcome": "success" | "failed_closed" | "skipped",
  "at": "2026-05-07T18:38:42.918Z"
}
```

**Field semantics**:
- `pause_reason`: matches the `routing_log.reason` for the transition (`'auto_pause_on_cap'` for FR-012's auto-pause, `'manual_stop_during_conclude'` for FR-015's manual stop).
- `summarizer_outcome`: outcome of the spec 005 final summarizer call: `'success'` (summary persisted), `'failed_closed'` (spec 005 §FR-007 fail-closed; loop still transitioned), `'skipped'` (no active participants produced conclude turns; summarizer ran on whatever transcript exists per spec line 393–395).
- `at`: orchestrator timestamp at the transition.

**Visibility**: broadcast to ALL session participants.

**Spec 011 consumer**: hides the conclude banner; renders a "Session concluded" notice with the `pause_reason` translated to user-facing copy ("The session has paused at its configured length cap." vs. "The session was stopped by the facilitator during the conclusion phase.").

---

## Conclude-phase exit (no new event)

When the loop exits conclude phase via FR-013 (cap extension), NO dedicated WS event is emitted; the `session_concluding` banner state is cleared by the SPA detecting the loop-state field on the next session-status WS message (existing `loop_state_changed` event, payload `{loop_state: 'running'}`). Documented here so spec 011's banner-clearing logic has a clear hook.

If a future revision wants an explicit `session_concluding_cancelled` event, that's an additive change — not introduced in v1.

---

## Test obligations

Per spec.md SC-011:

- `test_025_conclude_phase.py` covers: WS broadcast on `session_concluding` includes `remaining` field with correct values for turns-only / time-only / both caps.
- `test_025_conclude_phase.py` covers: WS broadcast on `session_concluded` carries `pause_reason='auto_pause_on_cap'` after the auto-pause path.
- `test_025_manual_stop.py` covers: WS broadcast on `session_concluded` carries `pause_reason='manual_stop_during_conclude'` after the manual-stop path.
- Multi-client test asserts all connected clients (facilitator + non-facilitator participants) receive both events.
- Cap-value-leak test: assert `session_concluding` payload does NOT include `length_cap_seconds` / `length_cap_turns` fields.
