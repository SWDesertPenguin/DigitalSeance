# Security Requirements Quality Checklist: Debug Export

**Purpose**: Validate the quality, clarity, and completeness of security requirements in the Debug Export spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Feature**: [spec.md](../spec.md)
**Sister checklist**: spec is small and security-relevant by design (a single endpoint that dumps "everything about a session"); the parent `requirements.md` is per-fix-branch tracking.

Markers used in findings (apply during audit, before resolution):
- `→ ✅` requirement is adequately specified
- `→ ⚠️ partial` spec addresses some aspect but leaves the rest implicit
- `→ ❌ gap` spec silent; code may or may not address it
- `→ 🐛 drift` spec and shipped code disagree
- `→ 📌 accepted` gap is documented in spec already — confirm and re-check

## Requirement Completeness — Sensitive-Field Stripping

- [x] CHK001 Is the sensitive-field strip-list (FR-4: `api_key_encrypted`, `auth_token_hash`, `bound_ip`) authoritative or descriptive? Is there a single source of truth so adding a new sensitive column requires updating the list? [Completeness, Spec §FR-4, Clarifications]
- [x] CHK002 Are requirements specified for nested sensitive content (e.g., a `messages.content` field that quotes an api_key — covered by 007 §FR-008 redaction at the source, but 010 trusts that source)? [Completeness, Gap, cross-ref 007 §FR-008]
- [x] CHK003 Are requirements specified for the convergence_log embedding bytes (cross-ref 004 §FR-016 "embeddings never exposed externally" — does 010 strip them)? [Completeness, Gap, cross-ref 004 §FR-016]
- [x] CHK004 Are requirements specified for the routing_log "reason" field (could it leak internal state about other participants — pause reasons, breaker counts)? [Completeness, Gap]

## Requirement Completeness — Config Snapshot Allowlist

- [x] CHK005 Is the config-snapshot allowlist (Clarifications: "fixed allowlist of `SACP_*` env vars") authoritative? Where does the canonical list live, and what's the process for adding a new env var? [Completeness, Spec Clarifications, partial]
- [x] CHK006 Are requirements specified for the case where an operator names a sensitive variable with an `SACP_` prefix accidentally (e.g., `SACP_DB_PASSWORD`)? Allow-list-by-name should reject `*_KEY` / `*_SECRET` / `*_TOKEN` regardless of prefix per SC-006 — confirm allowlist's rejection logic. [Completeness, Spec §SC-006, partial]
- [x] CHK007 Are requirements specified for env-var version drift (an export from before a deployment includes `SACP_X`; after deployment, `SACP_X` is removed — does the historical export break)? [Completeness, Gap]

## Requirement Completeness — Scope & Authorization

- [x] CHK008 Is the session-binding requirement (FR-3: `participant.session_id == session_id`) enforced at the endpoint level or middleware level? [Completeness, Spec §FR-3, partial]
- [x] CHK009 Are requirements specified for the case where a facilitator transferred their role mid-session (cross-ref 002 §FR-011) — does the export include their pre-transfer state? [Completeness, Gap, cross-ref 002 §FR-011]
- [x] CHK010 Are requirements specified for export of an archived / deleted session (a deleted session has no rows; what does the export return — 404, empty, error)? [Completeness, Gap]

## Requirement Completeness — Mutation Surface

- [x] CHK011 Is FR-6 (no mutation) enforced beyond code discipline (e.g., a read-only DB transaction explicitly set, or just convention)? [Completeness, Spec §FR-6, partial]
- [x] CHK012 Are requirements specified for the case where the export endpoint is invoked under load (it's a heavy read; does it need its own connection pool or rate-limit budget different from regular tools)? [Completeness, Gap, cross-ref 009]

## Requirement Clarity

- [x] CHK013 Is the response shape pinned (FR-1, SC-001 list 9 keys; is the *order* of keys specified, are extra keys forbidden)? [Clarity, Spec §FR-1, §SC-001]
- [x] CHK014 Is the empty-collection contract (FR-5 / SC-004 `[]` not omitted, not `null`) specified at JSON serialization level — does FastAPI's default behavior comply? [Clarity, Spec §FR-5, §SC-004]
- [x] CHK015 Is "exported_by" (SC-001) defined — facilitator participant_id, display_name, both? [Clarity, Spec §SC-001, Gap]

## Requirement Consistency

- [x] CHK016 Does the sensitive-field strip-list align with what 002 §FR-004 / SC-007 forbid in *log* output (token plaintext, not stored hashes; 010 strips hashes too — strictly tighter)? [Consistency, Spec §FR-4, cross-ref 002 §FR-004]
- [x] CHK017 Does the facilitator-only check (FR-2) align with 006 §FR-009 (facilitator-gated tools) — same role check used? [Consistency, Spec §FR-2, cross-ref 006 §FR-009]
- [x] CHK018 Does the read-only contract (FR-6) align with 001 §FR-007 / FR-008 (immutability through normal application path) — confirm the export path *is* the normal path? [Consistency, Spec §FR-6, cross-ref 001]

## Acceptance Criteria Quality

- [x] CHK019 Is SC-005 ("response latency <500ms for typical sessions") testable with a fixture set (50 participants, 500 messages, 100 log entries each) — and does that fixture exist? [Measurability, Spec §SC-005, Gap]
- [x] CHK020 Is SC-002 ("HTTP 403 with `facilitator_only` error code") consistent with other 403 errors across the API (cross-ref 006 §SC-002 / 002 §FR-017 — same error-code shape)? [Measurability, Spec §SC-002, cross-ref 002, 006]
- [x] CHK021 Are negative-path success criteria specified beyond SC-002 (zero sensitive-field leakage in any export across full corpus; zero mutations on read; zero secret variables in config_snapshot)? [Acceptance Criteria, partial]

## Scenario Coverage

- [x] CHK022 Are large-session export scenarios specified (a session with 100K messages — does the response truncate, paginate, or stream)? [Coverage, Gap]
- [x] CHK023 Are concurrent-export scenarios addressed (two facilitators-of-different-sessions exporting simultaneously — DB connection pool exhaustion)? [Coverage, Gap]
- [x] CHK024 Are export-during-write-amplification scenarios addressed (turn loop is appending while export is reading — read-isolation level)? [Coverage, Gap]

## Edge Case Coverage

- [x] CHK025 Are requirements defined for the case where a sensitive field is added to the schema (cross-ref 001) without updating the strip-list? Is there a CI guard? [Edge Case, Gap, cross-ref 001]
- [x] CHK026 Are requirements defined for the case where the participant data has `null` in non-sensitive fields (FR-5 says collections are `[]`; what about scalar `null` — included or omitted)? [Edge Case, Gap]
- [x] CHK027 Are requirements defined for the case where the calling facilitator's own row is in the participants list (their own `auth_token_hash` is stripped — confirm)? [Edge Case, partial]
- [x] CHK028 Are requirements defined for binary content in `messages.content` (system messages with embedded JSON, summary epoch JSON — are they stringified or returned as objects)? [Edge Case, Gap]

## Non-Functional Requirements

- [x] CHK029 Is the threat model documented and requirements traced to it (OWASP A03:2021 Injection / A04:2021 Insecure Design — confidentiality of cross-session data; NIST SP 800-53 AC-3, SC-12, SI-12)? [Traceability, Gap]
- [x] CHK030 Are observability requirements specified for export usage (logged at what level; alertable on rate; cross-ref 002 §FR-014 admin audit log)? [Coverage, Gap]
- [x] CHK031 Are accessibility requirements specified for the export response (size warnings, format hints in headers)? [Coverage, Gap]

## Dependencies & Assumptions

- [x] CHK032 Is the dependency on `_config_snapshot()` at the server process (Clarifications) covered by a contract — what if the env var is set per-request via a proxy? [Dependency, Spec Clarifications, Gap]
- [x] CHK033 Is the assumption "non-mutating" (FR-6 / SC-007) reinforced by an integration test (run a checkpoint hash before + after export, assert equal)? [Assumption, Gap]

## Ambiguities & Conflicts

- [x] CHK034 Does FR-7 ("never includes secrets") conflict with FR-7's "fixed `SACP_*` allowlist" — the allowlist is the mechanism, but is the *result* (no secrets) verified independently or assumed correct because the allowlist is short? [Ambiguity, Spec §FR-7, partial]
- [x] CHK035 Is "facilitator only" (FR-2) the ONLY authorization check, or do non-facilitator participants get a *partial* export of their own session data? Phase 1 says no — confirm. [Ambiguity, Spec §FR-2]
- [x] CHK036 Does the export include an audit log entry (admin_audit_log) for the export action itself (cross-ref 002 §FR-014 logs facilitator actions; export-as-action — yes or no)? [Ambiguity, Gap, cross-ref 002 §FR-014]

## Notes

- Highest-leverage findings to expect: CHK001 (strip-list authoritativeness — adding a sensitive column should fail CI without strip-list update), CHK003 (embeddings via 004 §FR-016 — high-leakage potential), CHK029 (no traceability), CHK036 (export should be audited).
- Lower-priority but easy wins: CHK013 (response-shape pin), CHK015 (`exported_by` definition), CHK017 (cross-ref 006 facilitator check).
- Run audit by reading [src/mcp_server/tools/debug.py](../../../src/mcp_server/tools/debug.py), the participant scrubber, the config_snapshot allowlist, and the integration tests; cross-reference 001 (schema), 002 (auth), 004 (embeddings), 006 (MCP), 007 (output redaction).
