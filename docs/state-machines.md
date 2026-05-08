# SACP State Machine Catalog

Every implicit state machine in the orchestrator is documented here with its states, valid transitions, invalid transitions (with rejection behavior), and idempotency rules.

---

## 1. Session lifecycle

**States**: `active` (default), `paused`, `archived`, `deleted`

**Transitions**:

| From | To | Trigger | Idempotent |
|---|---|---|---|
| `active` | `paused` | Facilitator pauses | yes |
| `paused` | `active` | Facilitator resumes | yes |
| `active` | `archived` | Facilitator archives (read-only retention) | terminal |
| `paused` | `archived` | Facilitator archives | terminal |
| any | `deleted` | Facilitator deletes session (FK cascade) | terminal |

**Invalid transitions**: `archived` → anything except `deleted` is rejected with HTTP 409. `deleted` is terminal — no row exists to transition.

**Idempotency**: `pause` while paused is a no-op (same status, no audit entry); `resume` while active is a no-op.

---

## 2. Participant lifecycle

**States**: `pending`, `active`, `paused-manual`, `paused-breaker`, `removed`

(`paused-manual` and `paused-breaker` share the same underlying status; the distinction is whether the circuit breaker drove it, tracked via a consecutive-failure counter.)

**Transitions**:

| From | To | Trigger | Idempotent |
|---|---|---|---|
| `pending` | `active` | Facilitator approves OR auto-approve = true | yes |
| `pending` | `removed` | Facilitator rejects (hard-delete) | terminal |
| `active` | `paused-manual` | Facilitator pauses | yes |
| `paused-manual` | `active` | Facilitator resumes | yes |
| `active` | `paused-breaker` | Circuit breaker opens (consecutive failure threshold reached) | yes |
| `paused-breaker` | `active` | Successful turn dispatched OR failure counter reset by facilitator | yes |
| any non-terminal | `removed` | Facilitator removes (hard-delete) | terminal |

**Invalid transitions**: `removed` is terminal (row hard-deleted — audit row survives). Direct `pending` → `paused-*` transitions are rejected; pending must approve before pause is meaningful.

---

## 3. Turn execution

**Stages** (linear, not a state machine in the strict sense — captured here because it's the canonical pipeline that the rest of this catalog references):

```
route → assemble → dispatch → persist → log
```

**Per-stage timing**: each stage records its wall-clock duration into `routing_log.{route_ms, assemble_ms, dispatch_ms, persist_ms}`.

**Failure paths**:

| Stage | Failure | Outcome |
|---|---|---|
| route | Speaker skipped (budget / breaker / observer / no_new_input) | Turn skipped; routing_log entry written |
| assemble | Context build failed (rare — DB error) | Exception propagates; turn loop logs and continues next iteration |
| dispatch | Provider unreachable / timeout | Breaker increments; `provider_error` skip |
| dispatch | Provider returned empty/degenerate | Breaker increments; `empty_response` / `degenerate_output` skip |
| persist | Security pipeline blocked | Re-stage as review-gate draft |
| persist | Security pipeline crashed | Fail-closed `security_pipeline_error` skip; `security_events` row with `layer='pipeline_error'`, `blocked=true` |

**Invariants**:
- The turn loop never halts. Any unhandled exception is logged and the loop proceeds to the next iteration.
- Persist is idempotent at the DB layer — `messages` PRIMARY KEY `(turn_number, session_id, branch_id)` rejects duplicates.

---

## 4. Review-gate draft

**States**: `pending`, `approved`, `edited`, `rejected`, `timed_out`, `overridden` (reserved for the secure-by-design implementation)

**Transitions**:

| From | To | Trigger | Idempotent |
|---|---|---|---|
| (none) | `pending` | Loop staged for review | n/a |
| `pending` | `approved` | Facilitator approves; security pipeline re-runs on the approved content | terminal |
| `pending` | `edited` | Facilitator edits + approves | terminal |
| `pending` | `rejected` | Facilitator rejects | terminal |
| `pending` | `timed_out` | `review_gate_timeout` exceeded | terminal |
| `pending` | `overridden` | Facilitator overrides on re-flag (reserved) | terminal |

**Pause scope**: while a draft is `pending`, the loop pauses dispatch within `review_gate_pause_scope` (`session` or `participant`). Resume is automatic on transition out of `pending`.

**Invalid transitions**: terminal states cannot transition. Approving an already-approved draft is rejected with HTTP 409.

---

## 5. Circuit breaker

**States**: `closed`, `open`

(Stored as a consecutive-failure counter per participant. Below the threshold = closed; at or above = open.)

**Transitions**:

| From | To | Trigger |
|---|---|---|
| `closed` | `closed` | Successful dispatch (resets counter to 0) |
| `closed` | `open` | Consecutive failures exceed the configurable threshold |
| `open` | `closed` | Successful dispatch (rare — open breaker skips dispatch); facilitator manual reset |

**Note**: there is no `half-open` probe state. The breaker reopens on the first success, which means a long-failing participant remains skipped indefinitely until either the facilitator resets the counter or the participant naturally recovers (e.g., on a downstream operator fixing the provider key).

---

## 6. Convergence flag

**States**: `not-converging`, `converging-detected`, `divergence-prompted`, `escalated`

(Computed from rolling-window similarity scores; not stored as an enum column. `convergence_log.divergence_prompted` and `convergence_log.escalated_to_human` flags persist the transition points.)

**Transitions**:

| From | To | Trigger |
|---|---|---|
| `not-converging` | `converging-detected` | Rolling similarity exceeds `SACP_CONVERGENCE_THRESHOLD` |
| `converging-detected` | `divergence-prompted` | Loop enqueues a divergence prompt as facilitator-attributed interrupt |
| `divergence-prompted` | `not-converging` | Subsequent turns drop similarity below threshold |
| `divergence-prompted` | `escalated` | Sustained convergence after divergence prompt fails to break the pattern (manual operator decision; not yet auto-triggered) |

---

## 7. Proposal voting

**States**: `open`, `accepted`, `rejected`, `expired`

**Transitions**:

| From | To | Trigger |
|---|---|---|
| (none) | `open` | Facilitator creates proposal | n/a |
| `open` | `accepted` | Vote tally satisfies `acceptance_mode` (`unanimous` / `majority`) | terminal |
| `open` | `rejected` | Facilitator rejects OR insufficient votes by `expires_at` | terminal |
| `open` | `expired` | `expires_at` passed without resolution | terminal |

**Vote idempotency**: `(proposal_id, participant_id)` is a composite PK on `votes`; re-voting updates the existing row rather than inserting.

---

## 8. Token lifecycle

**States**: `issued`, `active`, `expired`, `revoked`, `rotated`

(State is implicit from the token expiry timestamp, the row's existence, and rotation ceremony.)

**Transitions**:

| From | To | Trigger |
|---|---|---|
| (none) | `issued` | Facilitator issues invite OR auto-rotates | n/a |
| `issued` | `active` | First successful authentication (binds IP) |
| `active` | `expired` | `token_expires_at` passed |
| `active` | `revoked` | Facilitator revokes (`auth_token_hash := NULL`) |
| `active` | `rotated` | Facilitator rotates (old hash NULL'd, new hash issued) |

**Invalid transitions**: `expired` and `revoked` are terminal. Rotation issues a new token rather than transitioning the old one.

---

## 9. Summarization

**States**: `idle`, `triggered`, `in-flight`, `success`, `fallback`, `failure`

**Transitions**:

| From | To | Trigger |
|---|---|---|
| `idle` | `triggered` | Threshold predicate returns true |
| `triggered` | `in-flight` | Background task begins (fire-and-forget — does not block loop) |
| `in-flight` | `success` | Provider returned valid summary |
| `in-flight` | `fallback` | Structured-summary path failed; narrative-only fallback ran |
| `in-flight` | `failure` | Both structured and fallback paths failed; row not written |
| any terminal | `idle` | Next turn boundary (state is per-checkpoint, not per-session) |

**Idempotency**: re-checking the trigger predicate for the same turn is safe; the second call sees `last_summary_turn` updated and returns false. Failed summarization does not retry within the same turn — the next checkpoint boundary tries again. ADR 0001 records the rationale.

---

## 10. WebSocket connection

**States**: `connecting`, `authenticated`, `streaming`, `reconnecting`, `closed`

**Transitions**:

| From | To | Trigger |
|---|---|---|
| (none) | `connecting` | Client opens WS to `/ws/sessions/{id}` | n/a |
| `connecting` | `authenticated` | Cookie validation passes; `me` row resolved |
| `connecting` | `closed` | Auth failure (invalid token or wrong session) | terminal-this-conn |
| `authenticated` | `streaming` | Initial `state_snapshot` sent |
| `streaming` | `reconnecting` | Client-side network drop (close 1006) |
| `reconnecting` | `streaming` | Client reconnects, fresh `state_snapshot` sent |
| `streaming` | `closed` | Server-side close OR client `wsUnsubscribe` | terminal |
| any | `closed` | Heartbeat timeout (close 1011 "no pong") | terminal |

Per-event delivery filters are role-driven.

---

## 11. Rate-limit bucket

**States**: `created`, `active`, `stale`, `evicted`

(In-memory token-bucket per participant and route. State is implicit from last-touched timestamp.)

**Transitions**:

| From | To | Trigger |
|---|---|---|
| (none) | `created` | First request from a new token | n/a |
| `created` / `active` | `active` | Subsequent request within TTL — bucket refilled toward capacity |
| `active` | `stale` | TTL elapsed since last touch |
| `stale` | `evicted` | Periodic sweep removes stale buckets |

**429 emission**: when a bucket is `active` but capacity exhausted, the request is rejected with HTTP 429 and `Retry-After` header.

---

## 12. Invite token

**States**: `created`, `active`, `consumed`, `expired`, `revoked`

**Transitions**:

| From | To | Trigger |
|---|---|---|
| (none) | `created` | Facilitator generates invite | n/a |
| `created` | `active` | First valid use (binds to participant) |
| `active` | `consumed` | `uses >= max_uses` | terminal |
| any non-terminal | `expired` | `expires_at` passed | terminal |
| any non-terminal | `revoked` | Facilitator revokes (row deleted) | terminal |
