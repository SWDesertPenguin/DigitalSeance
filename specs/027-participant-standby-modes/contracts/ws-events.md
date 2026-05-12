# Contract: WebSocket events introduced by spec 027

## `participant_standby`

Emitted when the standby evaluator transitions a participant from `active` to `standby`.

```json
{
  "type": "participant_standby",
  "session_id": "string",
  "participant_id": "string",
  "reason": "awaiting_human" | "awaiting_gate" | "awaiting_vote" | "filler_stuck",
  "since_turn": 42
}
```

Broadcast to all session subscribers (facilitator + participants). No filter — every connected client sees the event.

## `participant_standby_exited`

Emitted when the standby evaluator transitions a participant out of `standby`.

```json
{
  "type": "participant_standby_exited",
  "session_id": "string",
  "participant_id": "string",
  "cleared_at_turn": 47
}
```

Broadcast to all session subscribers.

## `participant_update` (extension)

The existing `participant_update` event from spec 002 §FR-016 gains two new fields in its payload (per spec 011 FR-058 amendment):

```json
{
  "type": "participant_update",
  "participant_id": "string",
  "status": "active" | "pending" | "paused" | "removed" | "circuit_open" | "standby",
  "wait_mode": "wait_for_human" | "always",
  "wait_mode_metadata": {"long_term_observer": false},
  ...existing fields
}
```

The SPA's participant-card renderer consumes the new fields without a polling refetch.

## Pivot message — uses existing `message` event

The pivot message broadcasts via the existing `message` event channel (the standard transcript-append broadcast). The `metadata` field carries the `kind=orchestrator_pivot` discriminator; the SPA's renderer inspects the field for distinct styling.

No new event type for pivots — they ARE messages, just messages with a discriminator.
