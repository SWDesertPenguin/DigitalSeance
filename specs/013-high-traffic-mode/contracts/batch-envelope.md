# Contract: batch-envelope WebSocket event

Wraps multiple AI-to-human messages into a single delivery on the configured cadence. Hooks into the existing `broadcast_to_session` path in `src/web_ui/events.py`.

## Event shape

WebSocket event additive to the existing message-event taxonomy:

```json
{
  "type": "batch_envelope",
  "session_id": "<session-id>",
  "recipient_id": "<participant-id>",
  "opened_at": "<iso-8601>",
  "closed_at": "<iso-8601>",
  "source_turn_ids": ["<turn-id>", "..."],
  "messages": [
    { "type": "message", "turn_id": "...", "speaker_id": "...", "content": "..." },
    "..."
  ]
}
```

`messages` is a list of the existing per-turn message events in original turn order. The renderer's per-message handler processes each entry as if delivered individually — only the transport is batched.

## Bypass rule

State-change events MUST NOT route through batch envelopes. Explicitly excluded:
- Convergence declarations (`type=convergence`)
- Session-state transitions (`type=session_state_change`)
- Security events (`type=security_event`)
- Routing-mode change events
- Participant-update events (join/leave/role change)
- WebSocket lifecycle events (close-code, ping/pong)

These flow through their existing per-event broadcast paths immediately. A session reaching convergence during a batch window MUST see its convergence event emit out-of-band, in the same tick.

Implementation point: the batch scheduler's enqueue path checks event type and short-circuits when the event is not a `message`. State-change events bypass the queue entirely and call `broadcast_to_session` directly.

## Cadence and slack

- `opened_at` is set on first message append after a flush.
- `scheduled_close_at = opened_at + SACP_HIGH_TRAFFIC_BATCH_CADENCE_S` is the soft close.
- A hard close fires at `opened_at + cadence + 5s` if the scheduled tick is missed (FR-003 / SC-002 budget enforcement).
- A flush of an envelope with zero messages is a no-op (no event emitted; queue entry dropped).

The 5s slack matches V14's per-stage budget envelope. `routing_log` captures `batch_open_ts` and `batch_close_ts` per emitted envelope; sustained P95 `(closed_at - opened_at) > cadence + 5s` indicates scheduler pressure (operator alert).

## Recipient targeting

Envelopes are keyed by `(session_id, recipient_id)`. Only human participants accumulate envelopes — AI participants receive per-turn delivery unchanged (they don't have an "approval queue" failure mode, and batching their context would conflict with the dispatch path).

A session with zero human participants (topology 5 — fully autonomous) sees the batching mechanism as a no-op even when `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S` is set. Spec V12 acknowledges this.

## Disabled state

When `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S` is unset (or `HighTrafficSessionConfig.batch_cadence_s is None`):
- The batch scheduler task is NOT spawned for the session.
- Per-turn AI-to-human messages route via `broadcast_to_session` exactly as in Phase 2.
- No `batch_envelope` events are emitted.
- The Web UI never sees the new event type for this session.

This is the SC-005 regression contract: the `batch_envelope` event is invisible when the env var is unset.
