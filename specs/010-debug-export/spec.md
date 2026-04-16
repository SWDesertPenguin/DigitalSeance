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

## Success Criteria

- **SC-001**: The endpoint returns HTTP 200 with all nine required keys (`session`, `branch_id`, `participants`, `messages`, `interrupts`, `logs`, `config_snapshot`, `exported_at`, `exported_by`) for any session the facilitator is authorized to access.
- **SC-002**: Non-facilitator participants calling the endpoint receive HTTP 403 with a clear `facilitator_only` error code.
- **SC-003**: Sensitive fields (`api_key_encrypted`, `auth_token_hash`, `bound_ip`) are absent from all participant objects in the response. The scrubber removes these keys at serialization time before JSON encoding.
- **SC-004**: Empty collections are returned as `[]` (not `null`) for `messages`, `interrupts`, and each `logs` sub-array when no entries exist. Downstream tools can safely iterate without null-checks.
- **SC-005**: Response latency is <500ms for typical sessions (≤50 participants, ≤500 messages, ≤100 log entries per sub-array) on the single-threaded async event loop. All DB reads are independent SELECT queries with indexed `session_id`; no blocking operations.
- **SC-006**: The config snapshot is never empty and never includes secrets — database URL, encryption key, provider API keys, or any `*_KEY`/`*_SECRET`/`*_TOKEN` values. The allowlist covers only non-sensitive `SACP_*` env vars (e.g., `SACP_CADENCE_PRESET`, `SACP_CONTEXT_MAX_TURNS`, `SACP_CONVERGENCE_THRESHOLD`, `SACP_DEBUG`).
- **SC-007**: The endpoint never mutates session data — no INSERTs, UPDATEs, or DELETEs occur as a side-effect. The export is purely read-only.

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): Topologies 1–6 only (orchestrator-driven). The debug export is an orchestrator inspection tool — facilitators query the orchestrator's in-memory state and database via `/tools/debug/export`. Topology 7 (client-side peers) has distributed state; centralized dump semantics do not apply. Phase 2+ will define peer state export conventions.

**Use cases** (per constitution §1): Serves operational troubleshooting for all use cases. Facilitators in technical audits, consulting, and zero-trust scenarios need visibility into routing decisions, convergence state, and cost accounting when diagnosing unexpected behavior without requiring direct database access.
