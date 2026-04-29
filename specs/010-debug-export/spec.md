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
- **FR-7** Config snapshot covers only a fixed `SACP_*` allowlist (`_CONFIG_KEYS` in `src/mcp_server/tools/debug.py`); never includes secrets. A secondary defensive name-pattern guard (`_SECRET_NAME_PATTERN`) drops any allowlisted key whose name ends in `_KEY`, `_SECRET`, `_TOKEN`, `_PASSWORD`, `_CREDENTIAL`, or `_PASSPHRASE` — protection against an operator accidentally adding a sensitive variable to the allowlist.
- **FR-8** Calling the export endpoint MUST be recorded in `admin_audit_log` with `action='debug_export'`, `facilitator_id=<requester>`, `target_id=<session_id>`. The export is a high-leverage facilitator action (it dumps every byte of session state); leaving it unaudited would let an attacker exfiltrate without a forensic trail.
- **FR-9** The strip-list (`_SENSITIVE_FIELDS`) is the canonical source of truth for which serialized participant fields are excluded. New schema columns whose names end in `_encrypted` / `_hash` or equal `bound_ip` MUST be added to the strip-list — a CI guard (`tests/test_mcp_app.py::test_sensitive_fields_cover_obvious_patterns`) fails the build if any obvious-sensitive Participant dataclass field is missing from the set.

## Success Criteria

- **SC-001**: The endpoint returns HTTP 200 with all nine required keys (`session`, `branch_id`, `participants`, `messages`, `interrupts`, `logs`, `config_snapshot`, `exported_at`, `exported_by`) for any session the facilitator is authorized to access.
- **SC-002**: Non-facilitator participants calling the endpoint receive HTTP 403 with a clear `facilitator_only` error code.
- **SC-003**: Sensitive fields (`api_key_encrypted`, `auth_token_hash`, `bound_ip`) are absent from all participant objects in the response. The scrubber removes these keys at serialization time before JSON encoding.
- **SC-004**: Empty collections are returned as `[]` (not `null`) for `messages`, `interrupts`, and each `logs` sub-array when no entries exist. Downstream tools can safely iterate without null-checks.
- **SC-005**: Response latency is <500ms for typical sessions (≤50 participants, ≤500 messages, ≤100 log entries per sub-array) on the single-threaded async event loop. All DB reads are independent SELECT queries with indexed `session_id`; no blocking operations.
- **SC-006**: The config snapshot is never empty and never includes secrets — database URL, encryption key, provider API keys, or any `*_KEY`/`*_SECRET`/`*_TOKEN` values. The allowlist covers only non-sensitive `SACP_*` env vars (e.g., `SACP_CADENCE_PRESET`, `SACP_CONTEXT_MAX_TURNS`, `SACP_CONVERGENCE_THRESHOLD`, `SACP_DEBUG`).
- **SC-007**: The endpoint never mutates session-payload data — no INSERTs, UPDATEs, or DELETEs occur on session / participant / message / log rows as a side-effect. The single allowed write is the FR-8 admin_audit_log row recording the export action itself; this is a forensic record, not a session-payload mutation.
- **SC-008**: The convergence_log embedding bytes (per 004 §FR-016) MUST NOT appear in any export response. Enforced by the column-list-not-`SELECT *` query in `_LOG_QUERIES["convergence"]`. Future-added log tables that include sensitive bytes MUST follow the same pattern.

## Threat model traceability

| FR | Defends against | OWASP API / ASVS | NIST SP 800-53 |
|----|------------------|------------------|----------------|
| FR-1, FR-2, FR-3 (facilitator-only + session-bound) | Cross-session disclosure / privilege escalation | API3 / V4.1 | AC-3, AC-6 |
| FR-4, FR-9, SC-008 (sensitive-field strip + CI guard + embedding strip) | Credential / forensic-byte leakage in exports | API3 / V14.3 | SC-28, SI-15 |
| FR-5, SC-004 (empty-collection contract) | Null-handling crashes in downstream tooling | — | — |
| FR-6, SC-007 (read-only mutation guarantee) | Unintended state change via diagnostic surface | — | SI-7 |
| FR-7, SC-006 (config snapshot allowlist + secret-name pattern) | Operator-secret leakage via env-var dump | API3 / V14.3 | SC-12, AU-9 |
| FR-8 (export-as-action audit) | Untraceable exfiltration via export | API10 / V8.3 | AU-2, AU-3, AU-12 |

Sister cross-references: facilitator role check + session binding mirror 002 §FR-010 + §FR-022; embedding strip is the enforcement point for 004 §FR-016; sanitization of message content (so an exported transcript is already free of credential leaks at the source) is 007 §FR-001 / §FR-008.

## Audit closeout (2026-04-29)

The security-requirements quality audit (`checklists/security.md`) raised 36 findings; resolution split:

**Code changes**:
- CHK036 (export call now writes an `admin_audit_log` row with `action='debug_export'` so exfiltration leaves a forensic trail).
- CHK005 (config snapshot now applies a secondary `_SECRET_NAME_PATTERN` filter that drops any allowlisted key ending in `_KEY` / `_SECRET` / `_TOKEN` / `_PASSWORD` / `_CREDENTIAL` / `_PASSPHRASE` — defense-in-depth against an operator-introduced naming mistake).
- CHK001 (added `tests/test_mcp_app.py::test_sensitive_fields_cover_obvious_patterns` CI guard that fails the build if a `Participant` dataclass field whose name matches the heuristic patterns isn't in `_SENSITIVE_FIELDS`).

**Spec amendments (this commit)**: CHK001 / CHK009 (FR-9 codifies the CI guard), CHK005 / CHK006 (FR-7 codifies the secret-name pattern), CHK013 / CHK015 (FR-1 / SC-001 response shape pinned + `exported_by` defined as participant_id), CHK022 (Edge Case for very-large sessions — `messages` capped at 10K via `get_recent`), CHK029 (Threat-model traceability table), CHK036 (FR-8 audit-log mandate), SC-007 (mutation guarantee tightened — only the FR-8 audit row may write), SC-008 (embedding strip codified as success criterion + cross-ref 004).

**Closed as cross-reference / accepted residual**: CHK002 (sanitization at source — handled by 007 §FR-008 redaction at message persistence; debug export trusts that source), CHK003 (embeddings stripped — confirmed at `_LOG_QUERIES["convergence"]`; codified in SC-008), CHK004 (routing_log "reason" field disclosure — accepted: facilitators have legitimate need to see other participants' breaker / budget state; cross-trust within a session is the threat model), CHK007 (env-var version drift — accepted: snapshot is point-in-time), CHK008 (session-binding enforcement layer — endpoint-level via `_authorize`; spec wording clarified), CHK010 (deleted session export — `get_session` returns None → 404), CHK011 (read-only enforcement at the connection level — accepted residual; transactional read-only mode is Phase 3), CHK012 (load test for export latency — accepted: SC-005 is observational), CHK014 (FastAPI default JSON serialization handles empty collections as `[]`), CHK016 (cross-ref 002 §FR-004 already aligns), CHK017 (cross-ref 006 §FR-009 facilitator role check), CHK018 (cross-ref 001 §FR-007 / §FR-008 immutability), CHK019 (load profile measurement deferred), CHK020 (403 shape uniform via FastAPI HTTPException), CHK021 (negative-path SCs — implicit), CHK023 (concurrent exports — accepted residual; pool isolation handles), CHK024 (write-amplification during export — READ COMMITTED handles partial state), CHK025 (CHK001 fix covers via CI guard), CHK026 (null scalar fields — FastAPI returns them as null in JSON; documented), CHK027 (own row strip — confirmed in `_scrub`), CHK028 (binary content — `_jsonify` coerces bytes to `<N bytes>` placeholder), CHK030 (export observability — FR-8 audit log + FastAPI request log), CHK031 (size warnings in headers — accepted residual; client must handle large bodies), CHK032 (env-var process-source — accepted: `os.environ` at request time is the contract), CHK033 (mutation integration test — implicit via SC-007), CHK034 (allowlist authority — `_CONFIG_KEYS` is the canonical list; FR-7 names it), CHK035 (facilitator-only is the authoritative authz rule).

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): Topologies 1–6 only (orchestrator-driven). The debug export is an orchestrator inspection tool — facilitators query the orchestrator's in-memory state and database via `/tools/debug/export`. Topology 7 (client-side peers) has distributed state; centralized dump semantics do not apply. Phase 2+ will define peer state export conventions.

**Use cases** (per constitution §1): Serves operational troubleshooting for all use cases. Facilitators in technical audits, consulting, and zero-trust scenarios need visibility into routing decisions, convergence state, and cost accounting when diagnosing unexpected behavior without requiring direct database access.
