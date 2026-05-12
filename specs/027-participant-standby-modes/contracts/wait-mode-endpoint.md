# Contract: Participant wait_mode setter endpoint

**Endpoint**: `POST /tools/participant/set_wait_mode`

## Request

```json
{
  "session_id": "string",
  "participant_id": "string",
  "wait_mode": "wait_for_human" | "always"
}
```

The endpoint mirrors the existing participant-settings shape from spec 002 (`POST /tools/facilitator/set_routing_preference` + `POST /tools/facilitator/set_budget`). Authentication is by participant token (the participant's owning human OR the facilitator acting on behalf — same as existing settings endpoints).

## Response

- **200 OK** — `{"wait_mode": "<new_value>"}` on success.
- **400 Bad Request** — `{"error": "invalid_wait_mode", "detail": "..."}` when the value is not in the enum.
- **403 Forbidden** — When the caller is neither the participant's owning human nor the facilitator.
- **404 Not Found** — When the participant id does not exist for the session.

## Side effects

- UPDATE on `participants.wait_mode` for the target row.
- INSERT into `admin_audit_log` with `action='wait_mode_changed'`, `actor_id=<caller>`, `target_id=<participant_id>`, `previous_value=<old_mode>`, `new_value=<new_mode>`.
- `participant_update` WebSocket broadcast carrying the updated `wait_mode` field per spec 011 FR-058 amendment.

## Constraints

- Setting `wait_mode='always'` does NOT clear an existing standby state immediately — it changes future evaluation. The participant exits standby on the next round-robin tick where the evaluator runs and finds the participant in `always` mode (the evaluator skips `always`-mode participants per FR-014).
- The endpoint is participant-side; the facilitator's involvement is permitted but not required.
