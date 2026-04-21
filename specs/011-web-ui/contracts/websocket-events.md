# WebSocket Event Contract (v1)

**Branch**: `011-web-ui`
**Endpoint**: `ws://<host>:8751/ws/{session_id}`
**Upgrade auth**: HttpOnly cookie set during `/login`. WS rejected with 4401 if cookie missing/invalid, 4403 if participant is not in the session.

All events are JSON with `{"v": 1, "type": "<event_type>", ...fields}`. Unknown `v` → client ignores + logs warning; unknown `type` → client ignores.

---

## Server → Client

### `state_snapshot`

Sent once immediately after a successful upgrade, and again after any reconnect.

```text
{
  v: 1,
  type: "state_snapshot",
  session: { id, name, status, current_turn, last_summary_turn,
             cadence_preset, review_gate_pause_scope },
  me:      { participant_id, role },
  participants: [ParticipantCard, ...],
  messages:     [Message, ...],           // last 50, ascending by turn_number
  pending_drafts: [ReviewDraft, ...],
  open_proposals: [Proposal, ...],
  latest_summary: SummaryView | null,
  convergence_scores: [ConvergenceDataPoint, ...]   // last 50
}
```

### `message`

Sent after each non-skipped turn is persisted.

```text
{
  v: 1,
  type: "message",
  message: {
    turn_number: int,
    speaker_id: str,
    speaker_type: "human" | "ai" | "summary",
    content: str,
    token_count: int,
    cost_usd: float | null,
    created_at: str,   // ISO-8601
    summary_epoch: int | null,
  },
  turn_number: int,    // duplicated top-level for convenience
}
```

### `turn_skipped`

Sent when the loop skips a turn (budget/circuit/review-gate/no_new_input).

```text
{ v:1, type:"turn_skipped", participant_id: str, reason: str, turn_number: int }
```

### `participant_update`

Sent on any field change for a participant in the session (role, status,
consecutive_timeouts, routing_preference, budget values, etc.). Clients merge
over the existing `ParticipantCard` in state.

```text
{ v:1, type:"participant_update", participant: ParticipantCard }
```

### `convergence_update`

Sent once per turn for which convergence was computed.

```text
{ v:1, type:"convergence_update", point: ConvergenceDataPoint }
```

### `review_gate_staged`

Sent when a new draft is created.

```text
{ v:1, type:"review_gate_staged", draft: ReviewDraft }
```

### `review_gate_resolved`

Sent when a draft is approved/rejected/edited/timed-out.

```text
{ v:1, type:"review_gate_resolved",
  draft_id: str, resolution: "approved"|"rejected"|"edited"|"timeout",
  turn_number: int | null }
```

### `summary_created`

Sent when a new summarization checkpoint lands.

```text
{ v:1, type:"summary_created", summary: SummaryView }
```

### `session_status_changed`

Sent on pause / resume / archive.

```text
{ v:1, type:"session_status_changed", status: "active"|"paused"|"archived" }
```

### `session_updated`

Partial session-row update (rename, config change). UI merges `updates` into its local `state.session`. Added for US11 session rename.

```text
{ v:1, type:"session_updated", updates: { name?: str, ... } }
```

### `loop_status`

Fires when the conversation loop starts or stops. UI uses this to drive a "loop: running / idle" badge in the header so facilitators can tell at a glance whether the AI turn dispatcher is active, separate from individual-user presence.

```text
{ v:1, type:"loop_status", running: bool }
```

### `error`

Sent for non-fatal server-side warnings (rate-limit hit, summarization failure, etc.)
that the UI should surface to the user but not close the connection over.

```text
{ v:1, type:"error", code: str, message: str }
```

### `pong`

Reply to a client `ping`. No payload fields.

### `audit_entry`

Sent after every `log_admin_action` write (T252). Facilitator-only
clients surface it in the admin-panel audit view.

```text
{
  v: 1,
  type: "audit_entry",
  entry: {
    id: int,
    facilitator_id: str,
    action: str,
    target_id: str,
    previous_value: str | null,
    new_value: str | null,
    timestamp: str,
  },
}
```

### `proposal_created`

Sent when a new proposal is opened.

```text
{
  v: 1,
  type: "proposal_created",
  proposal: { id, session_id, topic, position, status, acceptance_mode, ... },
  tally: { accept: int, reject: int, abstain: int },   // seeded at zeros
}
```

### `proposal_voted`

Sent after each vote.

```text
{
  v: 1,
  type: "proposal_voted",
  proposal_id: str,
  voter_id: str,
  vote: "accept" | "reject" | "abstain",
  tally: { accept: int, reject: int, abstain: int },
}
```

### `proposal_resolved`

Sent when a facilitator resolves a proposal.

```text
{
  v: 1,
  type: "proposal_resolved",
  proposal_id: str,
  status: "accepted" | "rejected" | "expired",
  tally: { accept: int, reject: int, abstain: int } | null,
}
```

---

## Client → Server

### `ping`

Sent every 30s to keep the connection alive and prove liveness. Server replies with `pong`.

```text
{ v:1, type:"ping" }
```

### `subscribe`

Optional narrowing. Sends a list of event types the client wants; empty list = default firehose.

```text
{ v:1, type:"subscribe", topics: ["message","participant_update",...] }
```

---

## Close Codes

| Code | Meaning | Client behavior |
|---|---|---|
| 1000 | Normal | Do not reconnect |
| 1006 | Abnormal (network drop) | Exponential backoff reconnect |
| 4401 | Unauthenticated | Do not reconnect; show login prompt |
| 4403 | Not a participant in this session | Do not reconnect; navigate to session picker |
| 4429 | Too many connections from IP | Backoff with jitter, max 3 retries |

## Broadcast Scoping

All events scoped to a single `session_id`. Cross-session leakage is a bug.
The UI server MUST verify the cookie participant is still a session member
before each broadcast (per WebUIConnection.role refresh on connect).
