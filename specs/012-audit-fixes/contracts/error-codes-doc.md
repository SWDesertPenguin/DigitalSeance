# Contract: `docs/error-codes.md`

**Source**: spec FR-010 (error-codes.md)

## Required sections

```markdown
# SACP HTTP & WebSocket Error Code Catalog

## HTTP error codes

| Status | Endpoint pattern | JSON body shape | Source FR |
|---|---|---|---|
| 401 | `/sse/*`, `/tools/*` | `{"detail": "<message>"}` | 002 §FR-NN |
| 403 | `/tools/*`, `/admin/*` | `{"detail": "<message>"}` | 002 / 010 |
| 404 | `/sessions/{id}/*` | `{"detail": "session not found"}` | 006 |
| 409 | `/admin/*` (transfer / approve) | `{"detail": "<conflict>", "current_state": "<state>"}` | 002 §FR-011 |
| 429 | `/tools/*` | `{"detail": "Rate limit exceeded"}` | 009 §SC-004 |
| 500 | any | `{"detail": "Internal server error"}` | 006 §FR-014 |
| 503 | `/sse/*` | `{"detail": "subscriber cap reached"}` | 006 §FR-019 |

## WebSocket close codes

| Code | Meaning | Source FR |
|---|---|---|
| 1006 | Network drop | 011 §FR-014 |
| 4401 | Token invalid / expired | 011 §FR-014 |
| 4403 | Unauthorized origin / pending → role escalation denied | 011 §FR-014 |
| 4429 | Rate limit | 011 §FR-014 |

## Per-event-type error semantics (security_events)

`event_type` enum with documented JSON body shape per type:

- `sanitization`: `{"layer": "sanitize", "pattern_group": "<name>"}`
- `credential_detected`: `{"layer": "exfil", "credential_type": "<type>"}`
- `jailbreak_detected`: `{"layer": "validate", "phrase_match": "<phrase>"}`
- `pipeline_error`: `{"layer": "pipeline_error", "exception_class": "<class>"}`
- `facilitator_override` (NEW per FR-006 (b)): `{"layer": "facilitator_override", "override_reason": "<text>", "override_actor_id": "<uuid>"}`
- `canary_leakage`: `{"layer": "exfil", "canary_id": "<id>"}`
```

## CI gate

A grep-based check (or extension of `check_traceability.py`):

- Find every `HTTPException(status_code=NNN, …)` and `raise HTTPException(...)` call in `src/`.
- Find every `await ws.close(code=NNNN, …)` call.
- Assert every status / close code appears in `docs/error-codes.md`.

## Constitutional reference

Added to Constitution §13 on land.
