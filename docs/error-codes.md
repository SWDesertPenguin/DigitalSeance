# SACP HTTP & WebSocket Error Code Catalog

Authoritative listing of every status / close code the orchestrator and Web UI emit. Every code that appears in source also appears here; a CI gate enforces this drift class.

Scope: error codes only — successful 2xx codes are not catalogued here.

---

## HTTP error codes

| Status | Endpoint pattern | JSON body shape |
|---|---|---|
| 400 | `/sessions/*`, `/admin/*` (validation errors via `ValueError`) | `{"detail": "<message>"}` |
| 401 | `/sse/*`, `/tools/*`, `/admin/*` (token invalid / expired) | `{"detail": "Invalid or expired token"}` |
| 403 | `/sse/*`, `/tools/*`, `/admin/*` (token wrong session, IP-binding mismatch, facilitator-only path, origin not allowed) | `{"detail": "<reason>"}` |
| 404 | `/sessions/{id}/*`, `/admin/sessions/{id}/*` (session or row not found) | `{"detail": "Session not found"}` |
| 409 | `/tools/admin/detection_events/{event_id}/resurface` (re-surface attempted on archived session per spec 022 FR-008) | `{"detail": {"error": "session_archived", "message": "re-surface requires an active session"}}` |
| 422 | `/admin/sessions/{id}/participants/{pid}` (semantic validation: review-gate timeout out of range, etc.) | `{"detail": "<message>"}` |
| 429 | `/tools/*` (rate limit token-bucket exceeded) | `{"detail": "Rate limit exceeded"}` |
| 500 | any (unhandled exception fallback) | `{"detail": "Internal server error"}` |

### Endpoint coverage notes

- Validation failures from Pydantic / `ValueError` flow through the global exception handler and surface as 400 (with the `ValueError` message) regardless of which router raised them.
- 403 bundles three distinct semantics — token-vs-session mismatch, IP-binding mismatch, and role-gated paths — all sharing a body shape. Disambiguate via the `detail` string.
- 503 (subscriber-cap reached) is reserved but currently unimplemented; it will appear here when the subscriber-cap enforcement lands.

---

## WebSocket close codes

| Code | Meaning |
|---|---|
| 1006 | Abnormal closure / network drop (network-driven, not raised by app) |
| 1011 | Server stopped responding to pings (heartbeat timeout) |
| 4401 | Token absent / invalid / expired / cookie mismatch |
| 4403 | Origin not allowed, IP-binding mismatch, wrong session, participant inactive |
| 4429 | Subscriber cap reached (reserved; not yet enforced) |

### Close-code semantics

- 4401 and 4403 mirror the HTTP 401 / 403 split. Clients that observe a 4401 should re-authenticate before reconnecting; 4403 indicates the session itself rejected the client and reconnecting will not help.
- 1011 carries `reason="no pong"` and only fires from the heartbeat watchdog — server-side application errors close with 4xxx codes instead so clients can disambiguate.

---

## CI gate

A documentation-deliverable check asserts every HTTP status code and WebSocket close code literal that appears in source also appears in this catalog. Adding a new error site without updating this doc will fail CI.
