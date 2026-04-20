# REST Endpoint Inventory (Phase 1 surface consumed by the Web UI)

**Branch**: `011-web-ui`

The Web UI does not define new REST endpoints. Every REST action the UI
performs hits an existing Phase 1 endpoint on port 8750. This file is the
catalog used by `/speckit.tasks` to ensure each FR is backed by a real
endpoint.

All requests carry the Phase 1 bearer token in the `Authorization: Bearer <token>`
header (sourced from the HttpOnly cookie on the UI's side). Mutations additionally
include `X-SACP-Request: 1` for CSRF.

| FR | Method + Path | Purpose | Role |
|---|---|---|---|
| FR-001 | n/a | Port 8751 is the Web UI server; 8750 is MCP API | n/a |
| FR-003 | `POST /login` (NEW on 8751) | Token → cookie exchange | any |
| FR-004 | `WS /ws/{session_id}` (NEW on 8751) | Real-time push | session member |
| FR-006, FR-015 | `POST /tools/participant/inject_message` | Human interjection | participant |
| FR-007 / layout | `GET /tools/participant/status` | Session + self info for sidebar | participant |
| FR-009 | `GET /tools/participant/history?limit=50` | Initial transcript backfill on reconnect edge cases | participant |
| FR-010 | `GET /tools/debug/export` (facilitator) | Budget and convergence aggregate data not on WS | facilitator |
| FR-011 | (derived from WS `convergence_update` + `GET /tools/debug/export`) | Convergence sparkline | participant / facilitator |
| FR-012 | `GET /tools/facilitator/list_drafts` | Seed the review-gate queue on load | facilitator |
| FR-012 | `POST /tools/facilitator/approve_draft` | Approve draft | facilitator |
| FR-012 | `POST /tools/facilitator/reject_draft` | Reject draft | facilitator |
| FR-012 | `POST /tools/facilitator/edit_draft` | Edit + approve draft | facilitator |
| FR-013 | (proposal endpoints — Phase 2c sub-spec if they don't exist) | Create / vote / resolve | any |
| FR-016 | `POST /tools/facilitator/approve_participant` | Approve pending join | facilitator |
| FR-016 | `POST /tools/facilitator/reject_participant` | Reject pending join | facilitator |
| FR-016 | `POST /tools/facilitator/remove_participant` | Remove active participant | facilitator |
| FR-016 | `POST /tools/facilitator/create_invite` | Invite link | facilitator |
| FR-016 | `POST /tools/facilitator/transfer_facilitator` | Transfer role | facilitator |
| FR-016 | `POST /tools/facilitator/set_budget` | Set participant budget | facilitator |
| FR-016 | `POST /tools/facilitator/set_routing_preference` | Change routing mode | facilitator |
| FR-016 | `POST /tools/facilitator/revoke_token` | Force-revoke a token | facilitator |
| FR-016 | `POST /tools/facilitator/add_participant` | Add AI or human participant | facilitator |
| FR-016 | `POST /tools/facilitator/debug_set_timeouts` | Prime circuit-breaker count (testing only; hidden by default) | facilitator |
| FR-017 | `GET /tools/session/export_markdown` | Markdown download | participant |
| FR-017 | `GET /tools/session/export_json` | JSON download | participant |
| FR-018 | `GET /tools/session/summary` | Latest summary | participant |
| FR-019 | `POST /tools/facilitator/set_review_gate_pause_scope` | Toggle pause scope | facilitator |
| FR-020 | (derived from `participant_update` WS event + participant row) | Health indicator | participant |
| session controls | `POST /tools/session/pause` | Pause loop | facilitator |
| session controls | `POST /tools/session/resume` | Resume loop | facilitator |
| session controls | `POST /tools/session/archive` | Archive | facilitator |
| session controls | `POST /tools/session/start_loop` | Start loop | facilitator |
| session controls | `POST /tools/session/stop_loop` | Stop loop | facilitator |
| session creation | `POST /tools/session/create` | Create session (landing page flow) | any |

## Gaps

- **Proposals**: If `/tools/proposal/*` endpoints are not yet exposed (currently
  only the `ProposalRepository` exists), Phase 2c will need a small backend PR
  first. Flag in `tasks.md` as a prerequisite, not a UI task.
- **WebSocket endpoint**: New. Provided by the Web UI app, not the MCP app.
- **Login handshake**: New. Provided by the Web UI app.

## Non-changes

Phase 1 endpoints remain byte-for-byte identical. The Web UI adds consumers,
not contract changes.
