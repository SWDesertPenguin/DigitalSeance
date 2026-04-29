# Security Requirements Quality Checklist: MCP Server

**Purpose**: Validate the quality, clarity, and completeness of security requirements in the MCP Server spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Feature**: [spec.md](../spec.md)
**Sister checklist**: [requirements.md](requirements.md) (general spec completeness — already passed).
**Cross-feature reference**: 006 is the HTTP entry point. Auth (002), rate limiting (009), output validation (007), debug export (010), and Web UI (011) all attach to its router. Cross-references below check whether 006's wording stays consistent with those sister specs.

Markers used in findings (apply during audit, before resolution):
- `→ ✅` requirement is adequately specified
- `→ ⚠️ partial` spec addresses some aspect but leaves the rest implicit
- `→ ❌ gap` spec silent; code may or may not address it
- `→ 🐛 drift` spec and shipped code disagree
- `→ 📌 accepted` gap is documented in spec already — confirm and re-check

## Requirement Completeness — Transport & Origin

- [ ] CHK001 Is the SSE auth contract specified — token validated BEFORE the SSE stream opens, or on the first event? Cross-ref 002 §FR-001 / §FR-022. [Completeness, Spec §FR-002, cross-ref 002]
- [ ] CHK002 Is the CORS allow-list (Assumptions: "localhost + RFC-1918 LAN ranges") specified at regex granularity, with the specific ranges enumerated and tested? [Completeness, Spec Assumptions, partial]
- [ ] CHK003 Are CSP requirements specified for the MCP API (vs the Web UI's SR-001 of 011)? An API doesn't render HTML, but error pages might — is `Content-Security-Policy: default-src 'none'` set? [Completeness, Gap]
- [ ] CHK004 Are HSTS / X-Content-Type-Options / X-Frame-Options requirements specified for MCP responses (cross-ref 011 SR-002 — does 006 have parallel requirements)? [Completeness, Gap]
- [ ] CHK005 Is the WebSocket origin validation requirement specified (cross-ref 011 SR-004 — but 006 owns the underlying transport)? [Completeness, Gap, cross-ref 011 §SR-004]

## Requirement Completeness — Tool Authorization

- [ ] CHK006 Are requirements specified for the role-check enforcement point — middleware (per-request) or per-endpoint (FR-009 says "by role" without stating where)? [Completeness, Spec §FR-009]
- [ ] CHK007 Are requirements specified for cross-session tool-call rejection (FR-012 "scoped to authenticated session" — at what layer; what's the error shape; cross-ref 002 §FR-022)? [Completeness, Spec §FR-012, cross-ref 002]
- [ ] CHK008 Are requirements specified for tool-call input validation (Pydantic schemas, length caps, content-type enforcement)? [Completeness, Gap]
- [ ] CHK009 Are requirements specified for the case where a tool call references a participant in a different session (handled by §FR-012 scoping, but the error shape isn't specified)? [Completeness, Spec §FR-012, partial]

## Requirement Completeness — Error Surface

- [ ] CHK010 Are requirements specified for error-message content (does FastAPI's default 500 leak stack traces; is there a global exception handler that scrubs)? [Completeness, Gap]
- [ ] CHK011 Are requirements specified for error consistency across tools (uniform 401/403/404/422/429 shape; cross-ref 002 §FR-022 + 009 §FR-002)? [Completeness, cross-ref 002, 009]
- [ ] CHK012 Are requirements specified for error-information leakage (e.g., "session 123 not found" vs "session not accessible" — the former leaks existence)? [Completeness, Gap]

## Requirement Completeness — Tool Surface Coverage

- [ ] CHK013 Are requirements specified for the SSE-vs-tool-call separation — do tool calls flow over the SSE stream or only over HTTP POST? FR-001 + Assumptions clarify HTTP POST alongside SSE; confirm. [Completeness, Spec §FR-001, Assumptions]
- [ ] CHK014 Are requirements specified for the Swagger / OpenAPI surface (is `/docs` exposed in production; if so, is it auth-gated)? [Completeness, Gap]
- [ ] CHK015 Are requirements specified for the `/tools/debug/export` route (cross-ref 010 — facilitator-only is established, but does 006 explicitly require role-gating on this surface)? [Completeness, cross-ref 010 §FR-2]

## Requirement Clarity

- [ ] CHK016 Is "configurable port" (FR-001 default 8750) specified at the env-var level (where is the canonical `SACP_MCP_PORT`)? [Clarity, Spec §FR-001]
- [ ] CHK017 Is "validate bearer tokens via the existing auth service" (FR-002) defined operationally — what error shape on failure (cross-ref 002 §FR-002 / §FR-003 / §FR-017)? [Clarity, Spec §FR-002, cross-ref 002]
- [ ] CHK018 Is "facilitator-only" (FR-009) the same role check used by 010 (`participant.role == "facilitator"`) — single source of truth or ad-hoc per endpoint? [Clarity, Spec §FR-009, cross-ref 010 §FR-2]

## Requirement Consistency

- [ ] CHK019 Does FR-003 (stream turn results to all connected participants) align with 002 §FR-020 (pending-participant access scope)? Pending participants connected via SSE — do they receive AI turn updates or only transcript-visible ones? [Consistency, Spec §FR-003, cross-ref 002 §FR-020]
- [ ] CHK020 Does the CORS default (Assumptions: localhost + LAN) align with 011 §SR-003 (Web UI restricted to own origin only)? Different surfaces but operators may confuse the env vars. [Consistency, Spec Assumptions, cross-ref 011 §SR-003]
- [ ] CHK021 Are auth-failure error shapes consistent across MCP (this spec) and Web UI (011) so reusable error-handlers work? [Consistency, cross-ref 011]

## Acceptance Criteria Quality

- [ ] CHK022 Can SC-002 ("all facilitator tools rejected when called by non-facilitators") be objectively measured per-endpoint (not just at-aggregate)? [Measurability, Spec §SC-002]
- [ ] CHK023 Is SC-005 ("server starts and accepts connections") testable as a startup probe with a specific HTTP response, or is "accepts connections" subjective? [Measurability, Spec §SC-005]
- [ ] CHK024 Are negative-path success criteria specified (zero unauth tool calls succeed, zero cross-session reads succeed, zero stack traces in error responses)? [Acceptance Criteria, Gap]

## Scenario Coverage

- [ ] CHK025 Are recovery requirements defined for SSE connection drop (Edge Cases say "reconnect with same token" — but how does the client know which turns it missed beyond `get_history`)? [Coverage, Recovery Flow, Spec §Edge Cases, partial]
- [ ] CHK026 Are concurrent-tool-call scenarios addressed (the same participant fires two tool calls; rate limit covers it via 009; but does any tool require single-flight semantics)? [Coverage, Gap, cross-ref 009]
- [ ] CHK027 Are server-restart scenarios specified (in-flight SSE streams, in-flight tool calls — what does the client see)? [Coverage, Gap]

## Edge Case Coverage

- [ ] CHK028 Are requirements defined for very large response bodies (a get_history with a high limit or a session with many turns — pagination or hard cap)? [Edge Case, Gap]
- [ ] CHK029 Are requirements defined for slow / hung SSE consumers (the server's per-session asyncio.Queue could grow unbounded if a client stops reading)? [Edge Case, Gap]
- [ ] CHK030 Are requirements defined for HTTP request smuggling / header injection (FastAPI/uvicorn-level concerns — but 006 owns the deployment surface)? [Edge Case, Gap]
- [ ] CHK031 Are requirements defined for the case where a participant's token is rotated mid-SSE-stream (cross-ref 002 §FR-008 — does the existing stream stay alive or does it close)? [Edge Case, Gap, cross-ref 002 §FR-008]

## Non-Functional Requirements

- [ ] CHK032 Is the threat model documented and requirements traced to it (OWASP API1-API10 2023; NIST SP 800-53 SC-7 boundary protection, SC-23 session authenticity, AC-3 access enforcement)? [Traceability, Gap]
- [ ] CHK033 Are observability requirements specified beyond standard FastAPI logging (request IDs, per-tool latency metrics, auth-failure alerts)? [Coverage, Gap]
- [ ] CHK034 Are performance requirements specified for the SSE keepalive cadence (Assumptions mention 30s — but is that a hard contract or descriptive)? [Performance, Spec Assumptions, partial]

## Dependencies & Assumptions

- [ ] CHK035 Is the assumption "rate limiting deferred to a later hardening pass" still current (009 has shipped — this assumption is stale and should be updated to "rate limiting per 009 §FR-006")? [Assumption, Spec Assumptions, 🐛 drift candidate]
- [ ] CHK036 Is the dependency on FastAPI's HTTPBearer (cross-ref 002 §FR-022) covered by a deployment requirement (uvicorn must not be configured to log Authorization headers)? [Dependency, Gap, cross-ref 002 §FR-022]
- [ ] CHK037 Is the assumption "single SSE connection per participant per session" enforced or descriptive? If a malicious client opens 1000 SSE streams, does anything stop them? [Assumption, Spec Assumptions, Gap]

## Ambiguities & Conflicts

- [ ] CHK038 Does FR-011 ("reject all unauthenticated tool calls") align with the existence of any unauthenticated routes (login, invite redemption — those exist somewhere; are they explicitly OUT of `/tools/*` namespace)? [Ambiguity, Spec §FR-011, cross-ref 009 §FR-010]
- [ ] CHK039 Is "scope all tool calls to the participant's authenticated session" (FR-012) interpreted as "session_id from token, ignore session_id from request body" or "match them; reject mismatch"? [Ambiguity, Spec §FR-012]
- [ ] CHK040 Does the SSE endpoint URL `GET /sse/{session_id}` conflict with FR-012's session-scoping (the URL path includes session_id; the auth check reads it from token — must they match)? [Conflict, Spec Clarifications, §FR-012]

## Notes

- Highest-leverage findings to expect: CHK010 (FastAPI default 500 leaks tracebacks; cross-ref 007 §FR-012 should cover but only on root logger), CHK029 (unbounded SSE queue → DoS), CHK032 (no traceability), CHK035 (the Assumptions section says rate limiting is deferred — but 009 is shipped; spec is stale).
- Lower-priority but easy wins: CHK016 (port env var location), CHK034 (keepalive cadence as contract).
- Run audit by reading [src/mcp_server/](../../../src/mcp_server/) including middleware.py, sse.py, tools/, and the FastAPI app construction; cross-reference 002 (auth), 007 (pipeline), 009 (rate limit), 010 (debug export), 011 (Web UI counterpart).
