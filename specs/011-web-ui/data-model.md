# Data Model: Phase 2 Web UI

**Branch**: `011-web-ui` | **Date**: 2026-04-20

Phase 2 adds **no new database tables**. All persistence reuses Phase 1 entities. This document describes the **client-side state model** and the **transient server-side structures** needed for WebSocket event delivery.

---

## Server-Side Transient Structures

### `WebUIConnection`

Per-client WebSocket record held in memory by the connection manager.

| Field | Type | Notes |
|---|---|---|
| `participant_id` | str | From cookie auth on upgrade |
| `session_id` | str | Bound at connect; cannot change |
| `role` | Literal["facilitator", "participant", "pending"] | Copied from participant row; gates event filtering |
| `socket` | WebSocket | FastAPI WS instance |
| `connected_at` | datetime | For heartbeat diagnostics |
| `last_pong` | datetime | Updated on each client `pong`; connection dropped if stale > 60s |

Lifecycle: created on successful WS upgrade, removed on disconnect / stale pong / facilitator-initiated token revoke.

### `EventFilter`

Optional client-side subscription narrowing, sent as a `{"type": "subscribe", "topics": [...]}` frame.

| Field | Type | Notes |
|---|---|---|
| `topics` | list[str] | Subset of event types the client wants; empty list = all |

Default (no subscribe frame) = full firehose. Client may re-subscribe at any time.

---

## Client-Side State Model

Single top-level React state object held by `SessionView`. Shape:

```text
SessionState {
  session: {
    id: str
    name: str
    status: "active" | "paused" | "archived"
    current_turn: int
    last_summary_turn: int
    cadence_preset: str
    review_gate_pause_scope: "session" | "participant"
  }
  me: {
    participant_id: str
    role: "facilitator" | "participant" | "pending"
  }
  participants: ParticipantCard[]
  messages: Message[]            // capped at 200 most-recent; scroll-load older via REST
  pending_drafts: ReviewDraft[]  // from state_snapshot + delta events
  open_proposals: Proposal[]
  convergence_scores: ConvergenceDataPoint[]  // last 50 turns
  latest_summary: SummaryView | null
  ws_state: "connecting" | "open" | "reconnecting" | "closed"
  errors: ErrorEntry[]           // inline toast feed
}
```

### `ParticipantCard`

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `display_name` | str | |
| `role` | str | `facilitator` / `participant` / `pending` |
| `provider` | str | `anthropic` / `openai` / `ollama` / `human` / ... |
| `model_family` | str | Shown as a badge |
| `status` | str | `active` / `paused` / `offline` / `pending` |
| `health` | ParticipantHealth | Derived; see below |
| `routing_preference` | str | 8 values from Phase 1 Literal |
| `budget_utilization` | float \| null | 0.0–1.0; null if no budget set |
| `budget_daily_usd` | float \| null | Visible to self + facilitator only; hidden for others |
| `consecutive_timeouts` | int | From participant row |

### `ParticipantHealth` (derived)

State computed client-side from `status` + `consecutive_timeouts` + recent skip entries:

| Derived state | Condition |
|---|---|
| `healthy` | `status == "active"` and `consecutive_timeouts == 0` |
| `warning` | `status == "active"` and `consecutive_timeouts in {1, 2}` |
| `breaker-tripped` | `status == "paused"` and `consecutive_timeouts >= 3` |
| `paused-manual` | `status == "paused"` and `consecutive_timeouts < 3` |
| `offline` | `status == "offline"` |
| `pending` | `status == "pending"` |

### `Message`

| Field | Type | Notes |
|---|---|---|
| `turn_number` | int | Ascending per session |
| `speaker_id` | str | FK to participant |
| `speaker_type` | "human" \| "ai" \| "summary" | Drives badge + render path |
| `content` | str | Markdown; rendered through DOMPurify-hardened marked |
| `token_count` | int | Shown in detail view |
| `cost_usd` | float \| null | Only in facilitator view |
| `created_at` | datetime | Locale-formatted in the UI |

### `ReviewDraft`

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `participant_id` | str | |
| `draft_content` | str | Rendered like a Message but with an "UNAPPROVED" banner |
| `context_summary` | str \| null | |
| `created_at` | datetime | |
| `expires_at` | datetime | For timeout countdown |

### `ConvergenceDataPoint`

| Field | Type | Notes |
|---|---|---|
| `turn_number` | int | |
| `similarity_score` | float | 0.0–1.0 |
| `divergence_prompted` | bool | Marker on sparkline |

### `SummaryView`

| Field | Type | Notes |
|---|---|---|
| `turn_number` | int | The summary's own turn |
| `summary_epoch` | int | Covers turns up to this number |
| `decisions` | Decision[] | |
| `open_questions` | Question[] | |
| `key_positions` | KeyPosition[] | One per participant |
| `narrative` | str | 1–2 paragraphs |

---

## State Transitions

### WebSocket lifecycle

```text
connecting --[upgrade 200]--> open
open --[close 4401 / 4403]--> closed (show login prompt)
open --[close 1006 or ping timeout]--> reconnecting
reconnecting --[upgrade 200]--> open (with fresh state_snapshot)
reconnecting --[5 failures or expired token]--> closed
```

Exponential backoff: 1s, 2s, 4s, 8s, 16s, capped at 30s (matches SC-003).

### Review-gate draft lifecycle (already defined in Phase 1)

```text
pending --[approve / edit]--> resolved → message appended to transcript
pending --[reject]--> resolved (no message)
pending --[timeout expires]--> resolved (no message; auto-rejected)
```

UI reflects the Phase 1 state machine; no new transitions added.

---

## Validation Rules

Rules enforced on the client before REST calls are emitted; the server remains the ground truth:

- Message injection: non-empty, ≤ 10000 characters, Ctrl+Enter to send.
- Budget input: positive float, ≤ 10_000.00 USD.
- Routing preference: one of the 8 Phase 1 Literal values.
- Review-gate edit: non-empty edited_content, otherwise the button is disabled.
- Participant name on add: non-empty, not the literal `"string"` (Swagger placeholder rejection from PR #66).

All validation is defense-in-depth; the Phase 1 Pydantic models reject the same patterns server-side.
