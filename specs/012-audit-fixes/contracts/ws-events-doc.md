# Contract: `docs/ws-events.md`

**Source**: spec FR-010 (ws-events.md); WS-event-schema audit

## Required sections

```markdown
# SACP WebSocket Event Catalog

## Connection lifecycle

[State diagram or text: connecting → authenticated → streaming → reconnecting → closed.
Cross-ref docs/state-machines.md.]

## Event filtering by role

| Event type | Pending participant | Active participant | Facilitator |
|---|:---:|:---:|:---:|
| state_snapshot | filtered (see SR-010) | full | full + admin fields |
| message | <visibility> | yes | yes |
| participant_update | <visibility> | yes | yes + role-change details |
| ... | | | |

## Per-event schemas

### `state_snapshot`

**Source**: 011 §FR-005

**Payload**:

```json
{
  "type": "state_snapshot",
  "session": { "id": "<uuid>", "name": "<string>", "state": "active|paused|archived" },
  "participants": [...],
  "transcript": [...],
  "drafts": [...],
  "proposals": [...],
  "summaries": [...],
  "convergence": { ... },
  "budget": { ... }
}
```

**Field-level details**:
- `participants[]` excludes `api_key_encrypted`, `auth_token_hash`, `bound_ip`, `system_prompt` (per 011 §SR-011).
- For pending participants, `participants[]` only contains `session_name + human-participants` (per 011 §SR-010).

### `message`
[shape...]

### `participant_update`
[shape...]

### `convergence_update`
[shape...]

### `routing_mode`
[shape...]

### `review_gate_staged`
[shape; references new override_reason field if §4.9 (b) chosen]

### `loop_status`
[shape...]

### `proposal_*` (created / vote_cast / resolved)
[shape...]

### `summary_generated`
[shape...]

### `interrupt_*` (added / consumed)
[shape...]

## Event ordering guarantees

- Per-session ordering: events within a session are totally ordered by `created_at`.
- Cross-session ordering: not guaranteed.
- Per-type ordering within a session: not guaranteed; UI must reconcile via timestamps.

## Event versioning

Today: implicit (no version field). When breaking change ships, add `version: <int>` to payload root.
```

## Machine-readable schemas (optional Phase 1 stretch)

`specs/011-web-ui/contracts/ws-events/<event-type>.json` JSON Schema files. Stretch goal — not gating this feature's close.

## CI gate

A grep-based check:

- Find every `ws.send_json({"type": "...")` and `broadcast_event(type=...)` call in `src/`.
- Assert every event-type literal appears in `docs/ws-events.md`.

## Constitutional reference

Added to Constitution §13 on land.
