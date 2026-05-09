# SACP WebSocket Event Catalog

Authoritative listing of every WebSocket event the orchestrator broadcasts. Every event-type literal in source appears here; a CI gate enforces that drift class.

All events share the v1 envelope `{"v": 1, "type": "<name>", ...}`. Schema version is currently 1.

---

## Connection lifecycle

Summary: `connecting → authenticated → streaming` on the happy path; `reconnecting` after network drops; `closed` on any 4xxx / 1011 close.

After each successful connect (and reconnect), the server sends a fresh `state_snapshot` so the client can rehydrate from cold without replaying history.

---

## Event filtering by role

Events are filtered by role on the server. Pending participants see a reduced view; certain events (notably `audit_entry`) are facilitator-only. Client implementers should test their role's actual visibility against a running session — the authoritative filter is enforced server-side.

All `participants[]` arrays drop credential and binding fields before serialization. The exact column list is enforced server-side.

---

## Per-event schemas

### `state_snapshot`

```json
{
  "v": 1,
  "type": "state_snapshot",
  "session": {"id": "<uuid>", "name": "<string>", "status": "active|paused|archived"},
  "me": {"id": "<uuid>", "role": "facilitator|participant|pending", ...},
  "participants": [{"id": "...", "display_name": "...", ...}],
  "messages": [...],
  "pending_drafts": [...],
  "open_proposals": [...],
  "latest_summary": null | {...},
  "convergence_scores": [{"turn_number": N, "similarity_score": F, "divergence_prompted": bool}]
}
```

### `message`

```json
{"v": 1, "type": "message", "message": {<full Message row>}, "turn_number": N}
```

The `message` field carries the persisted-row shape: `turn_number`, `speaker_id`, `speaker_type`, `content`, `token_count`, `cost_usd`, `created_at`, `summary_epoch`.

### `batch_envelope`

```json
{
  "v": 1,
  "type": "batch_envelope",
  "session_id": "<session-id>",
  "recipient_id": "<participant-id>",
  "opened_at": "<iso>",
  "closed_at": "<iso>",
  "source_turn_ids": ["<turn-id>", "..."],
  "messages": [{<full message_event>}, "..."]
}
```

Coalesced AI-to-human delivery — one envelope per `(session_id, recipient_id)` per cadence tick. Each entry in `messages[]` is a complete `message` event with its own envelope; the renderer's existing per-message handler runs once per entry. State-change events (convergence, session-state transitions, participant updates) bypass this envelope and are broadcast directly. Emitted only when high-traffic batching is enabled; absent in standard operation.

### `turn_skipped`

```json
{"v": 1, "type": "turn_skipped", "participant_id": "<uuid>", "reason": "<string>", "turn_number": N}
```

`reason` is one of: `budget_exceeded`, `circuit_open`, `review_gate_pending`, `review_gate_staged`, `no_new_input`, `provider_error`, `empty_response`, `degenerate_output`, `security_pipeline_error`, plus router-emitted `skipped` / `burst_accumulating`.

### `participant_update`

```json
{"v": 1, "type": "participant_update", "participant": {<participant payload>}}
```

Payload drops encrypted fields and adds `spend_daily` / `spend_hourly` aggregates from `usage_log`.

### `participant_removed`

```json
{"v": 1, "type": "participant_removed", "participant_id": "<uuid>"}
```

Emitted when a participant row no longer exists (hard-delete from rejection).

### `convergence_update`

```json
{"v": 1, "type": "convergence_update", "point": {"turn_number": N, "similarity_score": F, "divergence_prompted": bool}}
```

### `review_gate_staged`

```json
{"v": 1, "type": "review_gate_staged", "draft": {<draft row>}}
```

Draft fields: `id`, `participant_id`, `draft_content`, `context_summary`, `created_at`. The secure-by-design implementation reserves an `override_reason` field on this payload.

### `review_gate_resolved`

```json
{"v": 1, "type": "review_gate_resolved", "draft_id": "<uuid>", "resolution": "approved|edited|rejected|timed_out|overridden", "turn_number": N | null}
```

### `summary_created`

```json
{"v": 1, "type": "summary_created", "summary": {<summary row>}}
```

### `session_status_changed`

```json
{"v": 1, "type": "session_status_changed", "status": "active|paused|archived"}
```

### `session_updated`

```json
{"v": 1, "type": "session_updated", "updates": {<partial row>}}
```

Partial-row payload — UI merges into `state.session` rather than replacing.

### `session_concluding`

```json
{
  "v": 1, "type": "session_concluding",
  "trigger_reason": "turns|time|both",
  "trigger_value": {"turns": N, "seconds": N},
  "remaining": {"turns": N|null, "seconds": N|null},
  "trigger_fraction": F,
  "at": "<iso>"
}
```

Emitted on the running → conclude lifecycle transition. Broadcast to every connected session participant. `remaining` carries countdown values for capped dimensions; null on uncapped. Cap values themselves are not in this payload — visibility of the cap is gated separately to the facilitator surface.

### `session_concluded`

```json
{
  "v": 1, "type": "session_concluded",
  "pause_reason": "<string>",
  "summarizer_outcome": "success|failed_closed|skipped",
  "at": "<iso>"
}
```

Emitted on the conclude → paused/stopped lifecycle transition. Broadcast to every connected session participant. `pause_reason` mirrors the corresponding `routing_log.reason`; `summarizer_outcome` reports the outcome of the final summarizer call.

### `loop_status`

```json
{"v": 1, "type": "loop_status", "running": bool}
```

### `error`

```json
{"v": 1, "type": "error", "code": "<string>", "message": "<string>"}
```

Non-fatal server-side warning. `code` examples: `provider_unreachable`, `rate_limited`, `summarization_failed`. Distinct from WS close codes — `error` events keep the connection open.

### `pong`

```json
{"v": 1, "type": "pong"}
```

Response to client `ping`. Heartbeat watchdog closes 1011 if no ping received within `SACP_WS_HEARTBEAT_INTERVAL`.

### `audit_entry`

```json
{
  "v": 1, "type": "audit_entry",
  "entry": {
    "id": N, "facilitator_id": "<uuid>", "action": "<string>",
    "target_id": "<string>", "previous_value": "<string>|null",
    "new_value": "<string>|null", "timestamp": "<iso>"
  }
}
```

**Facilitator-only**. Carries full `previous_value` / `new_value` bodies; non-facilitator clients never see this event type.

### `ai_question_opened`

```json
{
  "v": 1, "type": "ai_question_opened",
  "participant_id": "<uuid>", "turn_number": N,
  "questions": ["<extracted question>", ...],
  "at": "<iso>"
}
```

### `ai_exit_requested`

```json
{
  "v": 1, "type": "ai_exit_requested",
  "participant_id": "<uuid>", "turn_number": N,
  "phrase": "<exact match>", "at": "<iso>"
}
```

Advisory only — facilitator decides whether to honor by flipping the participant's `routing_preference` to `observer`.

### `proposal_created`

```json
{"v": 1, "type": "proposal_created", "proposal": {...}, "tally": {"accept": N, "reject": N, "abstain": N}}
```

### `proposal_voted`

```json
{"v": 1, "type": "proposal_voted", "proposal_id": "<uuid>", "voter_id": "<uuid>", "vote": "accept|reject|abstain", "tally": {...}}
```

### `proposal_resolved`

```json
{"v": 1, "type": "proposal_resolved", "proposal_id": "<uuid>", "status": "accepted|rejected|expired", "tally": {...}}
```

---

## Event ordering guarantees

- **Per-session**: events within a session are totally ordered by their send time on the broadcast channel. Clients should treat the order in which they arrive as authoritative.
- **Cross-session**: not guaranteed. Different sessions share no ordering constraint.
- **Per-type within a session**: not guaranteed (e.g., `participant_update` for participant A may arrive after a `participant_update` for B even if A was modified first). Clients must reconcile via row-level timestamps when necessary.

---

## Event versioning

Today: schema version is implicit at `v: 1`. Breaking changes will bump the envelope `v` and emit both shapes during the migration window; clients refuse to process unknown versions.

---

## CI gate

A documentation-deliverable check asserts every event-type literal that appears in source has a corresponding `### \`<type>\`` section in this file.
