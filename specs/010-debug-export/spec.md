# Feature Specification: Debug Export

**Feature Branch**: `fix/live-test-feedback` (bundled fix; would be `010-debug-export` as its own feature)
**Created**: 2026-04-15
**Status**: Draft
**Input**: User description: "Add an option to dump everything about a session in one JSON blob for troubleshooting — session + participants + messages + interrupts + logs + config, including nulls/empties."

## Clarifications

### Session 2026-04-15

- Q: Who can call the export endpoint? → A: Facilitator only. Participants get HTTP 403. Enforced by role check against `get_current_participant.role == "facilitator"` and session-id match against the token's session.
- Q: Should sensitive fields be included? → A: No — `api_key_encrypted`, `auth_token_hash`, `bound_ip` are stripped from the participants array. Everything else (including nulls, empty lists, delivered interrupts, cost logs) is included verbatim.
- Q: Where does config come from? → A: A small `_config_snapshot()` captures a fixed allowlist of `SACP_*` env vars from the server process at request time. Secrets (database URL, encryption key, provider keys) are never included.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Single-Call Troubleshooting Dump (Priority: P1)

When something goes wrong in a live session — ordering, empty responses, cost mismatches, stalled loops — the facilitator can call `GET /tools/debug/export?session_id=...` and receive one JSON blob containing everything the server knows about the session. They paste it into a bug report or diff it against a prior export to find regressions. No command-line tooling, no direct DB access, no log scraping.

**Why this priority**: Phase 1 live testing surfaced several bugs that needed cross-cutting context (transcript + interrupt state + routing decisions + config env vars) to diagnose. Re-querying each endpoint individually is slow and error-prone.

**Acceptance Scenarios**:

1. **Given** a facilitator auth token, **When** they GET `/tools/debug/export?session_id=<their-session>`, **Then** the response is 200 with keys: `session`, `branch_id`, `participants`, `messages`, `interrupts`, `logs`, `config_snapshot`, `exported_at`, `exported_by`.
2. **Given** a non-facilitator participant token, **When** they call the same endpoint, **Then** the response is 403.
3. **Given** any participant object in the response, **When** inspecting keys, **Then** `api_key_encrypted`, `auth_token_hash`, and `bound_ip` are absent.
4. **Given** an empty session (no interrupts, no messages), **When** the dump runs, **Then** those arrays are present as `[]` — null-safe for downstream tools.

## Requirements *(mandatory)*

- **FR-1** Endpoint at `GET /tools/debug/export?session_id=<id>`.
- **FR-2** Facilitator-only (`participant.role == "facilitator"`).
- **FR-3** Session-bound (`participant.session_id == session_id` on the token).
- **FR-4** Sensitive participant fields stripped.
- **FR-5** Empty collections returned as `[]`, not omitted.
- **FR-6** No mutation — endpoint is read-only; running the dump never writes to the DB.
- **FR-7** Config snapshot covers only a fixed `SACP_*` allowlist; never includes secrets.
