# Feature Specification: Debug Export

**Feature Branch**: `fix/live-test-feedback` (bundled fix; would be `010-debug-export` as its own feature)
**Created**: 2026-04-15
**Status**: Draft
**Input**: User description: "Add an option to dump everything about a session in one JSON blob for troubleshooting — session + participants + messages + interrupts + logs + config, including nulls/empties."

## Clarifications

### Session 2026-05-02 (audit fix/010-compliance — Phase D)

- Q: Is the export response considered PII? → A: Yes, despite being JSON-only. The dump contains every message body, participant display names, routing decisions, cost data, security events. Exporters MUST treat the response file as PII for storage / transmission / retention purposes. SACP does not enforce post-export handling — operator-controlled.

- Q: Can participants self-export their own data via `/tools/debug/export`? → A: No. FR-2 facilitator-only access maps to GDPR controller-only access for the export surface. Participants cannot self-fetch via this endpoint; the endpoint authorizes against the facilitator role, not the requesting participant's data scope. Art. 15 / Art. 20 self-service is deferred to Phase 3.

- Q: How does Phase 1 fulfil Art. 15 SAR / Art. 20 portability today? → A: Operator-mediated. The facilitator (acting as the controller's agent) calls `/tools/debug/export` and manually filters to the requesting participant's content. The boundary between operator debug-export and a future subject-facing Art. 20 endpoint is documented in the Compliance / Privacy section below.

- Q: Is FR-8 audit-log frequency-monitored for exfiltration? → A: No. FR-8 records every export call but doesn't surface the rate. Operators SHOULD configure alerting on `admin_audit_log.action='debug_export'` rate per facilitator. Phase 1 supplies the raw record; rate alerting is operator-controlled.

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

### GDPR article mapping (Phase D fix/010-compliance, 2026-05-02)

Authoritative project-wide GDPR mapping is in `docs/compliance-mapping.md`. The 010-specific FR-to-article mappings are:

| FR / asset | GDPR article | Mapping |
|----|----|----|
| FR-2 (facilitator-only access) | Art. 30, Art. 32(1)(b) | Controller-only access; integrity of processing |
| FR-4, FR-9, SC-008 (sensitive-field + embedding strip) | Art. 5(1)(c), Art. 32(1)(a) | Data minimization + pseudonymisation |
| FR-7, SC-006 (config allowlist + secret-name pattern) | Art. 32(1)(b) | Confidentiality of operator secrets |
| FR-8 (export audit log) | Art. 30, Art. 33 | Records of processing + breach-signal source |
| Operator-mediated Art. 15 fulfilment | Art. 15 | Subject access (manual filtering in Phase 1) |
| Phase 3 self-service trigger | Art. 20 | Portability (deferred) |
| Export response classification | Art. 4(1), Art. 32 | PII classification of operator dump |

## Compliance / Privacy (Phase D fix/010-compliance, 2026-05-02)

This section documents 010's privacy posture around export-as-PII, controller-only access, and Art. 15 / Art. 20 fulfilment. Authoritative project-wide compliance mapping is in `docs/compliance-mapping.md`.

### Export PII classification (Art. 4(1), Art. 32)

The export response is PII despite being JSON-only. The response includes:

- Every message body persisted in the session (Art. 5(1)(c) minimization is at WS broadcast / 011 §SR-011, not at export — operator export sees the raw transcript)
- Participant display names + role + status
- Routing decisions per turn (`provider`, `model`, `complexity`, `domain_match`, `reason`)
- Cost / token counts per turn (`usage_log`)
- Security events (per-layer findings, risk scores, blocked flags)
- Convergence / cadence metadata (without embeddings — SC-008)
- Config snapshot (env-var allowlist; no secrets per FR-7)

Exporters MUST treat the response file as PII for storage, transmission, and retention purposes — disk encryption at rest, secure transport (TLS), retention purge per controller policy. SACP does not enforce post-export handling; that is operator-controlled.

### Access control as controller-only (Art. 30, Art. 32(1)(b))

FR-2 facilitator-only access maps to GDPR **controller-only** access for the export surface. Participants cannot self-export their own data via this endpoint — the endpoint authorizes against the facilitator role, not the requesting participant's data scope. Participant self-service for Art. 15 / Art. 20 is the operator's responsibility (deferred to Phase 3 — see below).

### Subject rights (Art. 15 / Art. 20)

**Art. 15 SAR** — Phase 1 fulfilment is operator-mediated. The facilitator (acting as the controller's agent) calls `/tools/debug/export` and filters the response to a single participant's messages, drafts, proposals, votes. This satisfies the data-subject's right of access, but requires manual filtering — the endpoint dumps the entire session, not a per-participant view. Phase 3 trigger: any deployment serving EU data subjects where SAR volume justifies a self-service endpoint.

**Art. 20 portability** — out of scope for Phase 1 in self-service form. Distinct from the operator debug-export — Art. 20 ships authored content (messages, votes, drafts) to the participant in a "structured, commonly-used, machine-readable" format. Phase 1 fulfilment is the same operator-mediated workflow as Art. 15 (facilitator filters the export), with the operator responsible for delivering the filtered subset to the data subject in JSON. Phase 3 trigger: same as Art. 15.

**Art. 12(3) response window** — 30 days default, extendable to 90 days for complex / multi-system requests. Tracking the request clock is the operator's responsibility (002 Compliance / Privacy section is the authoritative cross-spec note on this).

### Boundary: debug-export vs. Art. 20-export

| Surface | Audience | Access control | Scope | Format |
|----|----|----|----|----|
| `/tools/debug/export` | Operator (controller) | FR-2 facilitator-only | Full session state (transcript, logs, config, security events, routing) | JSON |
| Future Art. 20 endpoint | Data subject | Self-service via subject-bound auth | Participant-authored content only (their messages, votes, drafts) | JSON or CSV — subject's choice per Art. 20(1) |

Phase 1 has no self-service Art. 20 endpoint. Operators fulfil Art. 20 manually by running debug-export and filtering. The boundary is documented so the future endpoint's scope is clear: it is NOT a participant-facing wrapper around debug-export — Art. 20 ships authored content only, not the operator-internal observability surface.

### Data minimization on export (Art. 5(1)(c))

FR-4 + FR-9 + SC-003 + SC-008 enforce data minimization at the field level:

- `_SENSITIVE_FIELDS` strip: `api_key_encrypted`, `auth_token_hash`, `auth_token_lookup`, `bound_ip`
- Convergence-log embedding bytes stripped (SC-008, cross-ref 004 §FR-016)
- Config snapshot allowlist + `_SECRET_NAME_PATTERN` filter (FR-7 + SC-006)

What IS included (for DPIA scope clarity):

- Session metadata (id, status, branch_id, facilitator_id, created_at, ended_at)
- Participant: id, display_name, role, status, model, model_tier, model_family, provider, joined_at, approved_at, departed_at, system_prompt, routing_preference, addressable_names, budget caps, current cost
- Messages: id, branch_id, turn_number, speaker_id, content, complexity, cost_usd, timestamp, metadata flags
- Logs: routing_log (full row + per-stage timings), usage_log, convergence_log (without embeddings), admin_audit_log, security_events
- Config snapshot: allowlisted SACP_* env vars only

This is the DPIA-relevant content scope. The operator's DPIA MUST cover this surface.

### Encryption-at-rest boundary (cross-ref 001 §FR-020)

Per 001 §FR-020, encryption-at-rest is column-level Fernet on `participants.api_key_encrypted` only. Other fields — `display_name`, `system_prompt`, message content — are stored unencrypted at the column level and rely on database-level access control + log scrubbing for confidentiality. The export endpoint is the "decrypted-at-rest" surface for `api_key_encrypted` (the field is stripped via FR-4), but for everything else the export emits the same plaintext that's already in the database. Operators MUST treat the export response with at least the same access controls as the database itself.

### Export frequency monitoring

FR-8 captures every export call in `admin_audit_log` (`action='debug_export'`). The audit log records the call but does NOT surface the rate. High-frequency exports may indicate exfiltration; operators SHOULD configure alerting on `admin_audit_log.action='debug_export'` rate per facilitator (e.g., >10 calls/hour for a single facilitator on a single session is anomalous). Phase 1 supplies the raw record; alerting is operator-controlled. Phase 3 trigger: any production deployment with operator-side anomaly-detection requirements.

### Cross-references

- `docs/compliance-mapping.md` — Art. 15 / Art. 20 / Art. 30 rows authoritative
- 001 §FR-019 — admin_audit_log retention (Art. 17(3)(b) carve-out)
- 001 §FR-020 — encryption-at-rest scope (Phase 1 covers `api_key_encrypted` only)
- 002 §FR-016 — credential overwrite on participant departure
- 002 Compliance / Privacy section — auth-surface privacy posture (Art. 12(3) response window noted there)
- 003 Compliance / Privacy section — Art. 28 processor disclosure (sister)
- 004 §FR-016 — embedding bytes stripped at export
- 007 §FR-012 — log scrubbing for credential patterns
- 007 Compliance / Privacy section — Art. 33 breach signalling

## Audit closeout (2026-04-29)

The security-requirements quality audit (`checklists/security.md`) raised 36 findings; resolution split:

**Code changes**:
- CHK036 (export call now writes an `admin_audit_log` row with `action='debug_export'` so exfiltration leaves a forensic trail).
- CHK005 (config snapshot now applies a secondary `_SECRET_NAME_PATTERN` filter that drops any allowlisted key ending in `_KEY` / `_SECRET` / `_TOKEN` / `_PASSWORD` / `_CREDENTIAL` / `_PASSPHRASE` — defense-in-depth against an operator-introduced naming mistake).
- CHK001 (added `tests/test_mcp_app.py::test_sensitive_fields_cover_obvious_patterns` CI guard that fails the build if a `Participant` dataclass field whose name matches the heuristic patterns isn't in `_SENSITIVE_FIELDS`).

**Spec amendments (this commit)**: CHK001 / CHK009 (FR-9 codifies the CI guard), CHK005 / CHK006 (FR-7 codifies the secret-name pattern), CHK013 / CHK015 (FR-1 / SC-001 response shape pinned + `exported_by` defined as participant_id), CHK022 (Edge Case for very-large sessions — `messages` capped at 10K via `get_recent`), CHK029 (Threat-model traceability table), CHK036 (FR-8 audit-log mandate), SC-007 (mutation guarantee tightened — only the FR-8 audit row may write), SC-008 (embedding strip codified as success criterion + cross-ref 004).

**Closed as cross-reference / accepted residual**: CHK002 (sanitization at source — handled by 007 §FR-008 redaction at message persistence; debug export trusts that source), CHK003 (embeddings stripped — confirmed at `_LOG_QUERIES["convergence"]`; codified in SC-008), CHK004 (routing_log "reason" field disclosure — accepted: facilitators have legitimate need to see other participants' breaker / budget state; cross-trust within a session is the threat model), CHK007 (env-var version drift — accepted: snapshot is point-in-time), CHK008 (session-binding enforcement layer — endpoint-level via `_authorize`; spec wording clarified), CHK010 (deleted session export — `get_session` returns None → 404), CHK011 (read-only enforcement at the connection level — accepted residual; transactional read-only mode is Phase 3), CHK012 (load test for export latency — accepted: SC-005 is observational), CHK014 (FastAPI default JSON serialization handles empty collections as `[]`), CHK016 (cross-ref 002 §FR-004 already aligns), CHK017 (cross-ref 006 §FR-009 facilitator role check), CHK018 (cross-ref 001 §FR-007 / §FR-008 immutability), CHK019 (load profile measurement deferred), CHK020 (403 shape uniform via FastAPI HTTPException), CHK021 (negative-path SCs — implicit), CHK023 (concurrent exports — accepted residual; pool isolation handles), CHK024 (write-amplification during export — READ COMMITTED handles partial state), CHK025 (CHK001 fix covers via CI guard), CHK026 (null scalar fields — FastAPI returns them as null in JSON; documented), CHK027 (own row strip — confirmed in `_scrub`), CHK028 (binary content — `_jsonify` coerces bytes to `<N bytes>` placeholder), CHK030 (export observability — FR-8 audit log + FastAPI request log), CHK031 (size warnings in headers — accepted residual; client must handle large bodies), CHK032 (env-var process-source — accepted: `os.environ` at request time is the contract), CHK033 (mutation integration test — implicit via SC-007), CHK034 (allowlist authority — `_CONFIG_KEYS` is the canonical list; FR-7 names it), CHK035 (facilitator-only is the authoritative authz rule).

## Operator UX notes (Phase F amendment, 2026-05-02)

These items capture diagnostic-readability decisions for the export
output. Sourced from the pre-Phase-3 audit window's UX review.

**Top-level key ordering.** The dump returns a single dict; key order
matters because operators diff exports across deploys with `jq` /
`diff` / `less`. The canonical order is `exported_at`, `exported_by`,
`session`, `branch_id`, `participants`, `messages`, `interrupts`,
`logs`, `spend`, `config_snapshot` — header metadata first, then
session shape, then per-record arrays, then aggregates and config.
Python dicts preserve insertion order; the order is stable as long as
`_build_dump` constructs the return dict literal-by-literal.

**Copy-paste / scan ergonomics.** FastAPI's default `JSONResponse`
emits compact JSON. Operators who paste into bug reports should pipe
through `jq .` or `python -m json.tool` for indentation; the export
endpoint deliberately does NOT pretty-print on the wire to keep
network bytes small. Future enhancement: a `?pretty=1` query param.
Sortable / diffable shape is enforced today by deterministic key
order (above) plus deterministic per-array ordering (`ORDER BY`
clauses on every `_LOG_QUERIES` SQL).

**Large-payload truncation hints.** The `messages` array is hard-
capped at 10,000 rows via `get_recent(session_id, branch_id, 10_000)`;
sessions exceeding that get a silent truncation. Operators with
very-large sessions need to know the cap is in effect — the response
shape does NOT today carry a `truncated: true` flag. Phase 3 follow-
up: emit `messages_truncated_at` when `len(messages) == 10_000` so
downstream tooling can detect the boundary. Until then, operators
treat exports of exactly 10,000 messages as "may be truncated."

**Field-ordering for human scannability.** Within each row, the
underlying dataclass / record column order is preserved by `asdict()`
(dataclasses) or `dict(row)` (asyncpg records). Most-frequently-needed
fields (id, display_name, role, status) appear first by definition
order. Operators who need a different field ordering for ingestion
should handle that in their consumer; the export contract pins
"data-model column order" as the shape.

**Timestamp format.** All timestamps are ISO 8601 with `Z` suffix
(UTC). The `exported_at` field appends an explicit `Z`; per-row
`timestamp` columns coming from PostgreSQL `TIMESTAMP WITHOUT TIME
ZONE` go through `datetime.isoformat()` and lose the `Z` — that's a
known minor inconsistency with documented payload contract:
`exported_at` is canonical-Z, all other timestamps are naive ISO
strings interpreted as UTC. Phase 3: switch all timestamps to
`TIMESTAMPTZ` and emit canonical-Z everywhere. Until then, consumers
treat all 010 timestamps as UTC.

**Null-vs-omitted policy.** Per FR-5, empty collections are returned
as `[]` (never null, never omitted). For scalar fields, FastAPI emits
`null` for `None` Python values (FR-5 doesn't apply to scalars —
those follow JSON semantics). This combination is the supported
contract for downstream tools: iterate over collection fields without
null-checks, `is None` check scalars.

**Binary-content placeholder format.** `_jsonify` coerces any `bytes`
to the string `<{N} bytes>`. The format is fixed; consumers parsing
the export programmatically can detect placeholders via the
`<\d+ bytes>` regex. Today this only fires defensively (the
convergence-log query is a column-list and excludes embedding bytes
by construction); the placeholder is the second line of defense.

**Export-vs-snapshot distinction.** The export is point-in-time, not
a streaming view. There is no caching: every call re-queries every
table. Two consecutive exports of the same session may differ if the
loop is running; operators wanting a frozen snapshot must pause the
session first (cross-ref 003 lifecycle).

**Cross-tool ingestion contract.** Supported tooling: `jq`, `less`,
`diff`, `python -m json.tool`. The export shape is structured JSON
suitable for any of these. The format is NOT optimized for relational
ingestion (e.g., direct CSV conversion); operators wanting tabular
slices should `jq` the relevant subarray.

## Operational notes (Phase F amendment, 2026-05-02)

These items capture operator-facing decisions sourced from the
pre-Phase-3 audit window's operations review.

**Operator workflow.** Standard usage: facilitator hits an issue in
a live session, calls
`GET /tools/debug/export?session_id=<id>` with their bearer token,
captures the JSON, attaches it to a bug report or pastes a `jq`-
filtered slice into a chat thread. Repeat-export cadence is operator-
driven; there is no rate limiter on this endpoint per se but it does
flow through the standard 009 `/tools/*` rate-limit middleware
(60 req/min per facilitator), which is already conservative.

**Admin-audit-log monitoring for export frequency.** Per FR-8 every
export writes a row to `admin_audit_log` with `action='debug_export'`.
Sustained high frequency from a single facilitator is an
exfiltration-risk signal. Suggested alert threshold: > 20 exports per
session per facilitator per hour, or > 5 cross-session exports per
facilitator per hour. Threshold tuning is deployment-dependent —
some operators legitimately diff exports at high cadence during
debugging sweeps.

**Large-session export latency degradation.** SC-005 sets the target
< 500ms for typical sessions (≤50 participants, ≤500 messages,
≤100 log entries / sub-array). Sessions exceeding those caps will
slow the export linearly; operators noticing > 2-second exports
should check session size against the SC-005 caps. The 10K-message
hard cap (`get_recent`) bounds worst case but a session with 10K
messages × 50 participants × all logs may still touch ~5s on
unindexed `session_id` lookups. All log queries use indexed
`session_id`; if query plans drift, ops should verify indexes exist.

**Strip-list update process.** Adding a new sensitive column to the
`participants` table (e.g., a future `mfa_secret`) requires updating
`_SENSITIVE_FIELDS` in `src/mcp_server/tools/debug.py`. The CI guard
at `tests/test_mcp_app.py::test_sensitive_fields_cover_obvious_patterns`
catches columns whose names match the heuristic patterns
(`_encrypted` / `_hash` / `_lookup` / `bound_ip`); columns whose
names don't match the heuristic require manual addition AND a
spec amendment to FR-9 listing the new field.

**Export-content classification.** The export is operator-internal
PII per 010 compliance audit (Batch 2 → 010 compliance). Operators
who receive an export from a facilitator MUST treat it as PII even
though the response is JSON-only. Recipients with no legitimate
need to see participant content (e.g., cross-team support staff)
SHALL NOT receive raw exports — facilitators should `jq` to the
specific subarray relevant to the bug report.

**SAR / Art-15 self-service workflow.** Cross-ref 010 compliance
audit (Batch 2): the debug export is a controller-only operator
tool, NOT a participant-self-service Subject Access Request (SAR)
path. Fulfilling an Art. 15 SAR today requires a facilitator
manually exporting and filtering to the requesting subject's rows.
Phase 3 trigger: any deployment under EU jurisdiction needs either
a participant-self-service portable export (Art. 20) or a documented
manual SAR fulfilment procedure with response-time SLA.

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): Topologies 1–6 only (orchestrator-driven). The debug export is an orchestrator inspection tool — facilitators query the orchestrator's in-memory state and database via `/tools/debug/export`. Topology 7 (client-side peers) has distributed state; centralized dump semantics do not apply. Phase 2+ will define peer state export conventions.

**Use cases** (per constitution §1): Serves operational troubleshooting for all use cases. Facilitators in technical audits, consulting, and zero-trust scenarios need visibility into routing decisions, convergence state, and cost accounting when diagnosing unexpected behavior without requiring direct database access.
