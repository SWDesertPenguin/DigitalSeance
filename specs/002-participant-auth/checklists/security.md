# Security Requirements Quality Checklist: Participant Auth & Lifecycle

**Purpose**: Validate the quality, clarity, and completeness of security requirements in the Participant Auth & Lifecycle spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Feature**: [spec.md](../spec.md)
**Sister checklist**: [requirements.md](requirements.md) (general spec completeness — already passed).

Markers used in findings (apply during audit, before resolution):
- `→ ✅` requirement is adequately specified
- `→ ⚠️ partial` spec addresses some aspect but leaves the rest implicit
- `→ ❌ gap` spec silent; code may or may not address it
- `→ 🐛 drift` spec and shipped code disagree
- `→ 📌 accepted` gap is documented in spec (assumptions / edge cases) — not a finding, but worth re-evaluating

## Requirement Completeness — Token Lifecycle

- [x] CHK001 Are token format, length, and entropy source requirements specified (or only the storage hash)? [Completeness, Spec §FR-001, Assumptions]
- [x] CHK002 Are bcrypt cost-factor re-evaluation triggers specified (when does cost=12 become insufficient)? [Completeness, Spec Assumptions, Gap]
- [x] CHK003 Is the password-equivalent strength expected of generated tokens stated (so reviewers can judge whether 30-day expiry is appropriate)? [Completeness, Spec §FR-012, Gap]
- [x] CHK004 Is the behavior on token rotation race (two simultaneous rotation requests by the same participant) defined? [Completeness, Spec Edge Cases]
- [x] CHK005 Are requirements defined for what happens to outstanding tokens when a session is archived / ended? [Completeness, Gap]
- [x] CHK006 Are requirements defined for cross-session token reuse — can the same token authenticate across multiple sessions, or is it always session-bound? [Completeness, Gap]
- [x] CHK007 Is the token-rotation result-handling specified for the case where the new token is generated but the response delivery fails (client never receives plaintext)? [Completeness, Edge Case, Gap]

## Requirement Completeness — IP Binding & Session

- [x] CHK008 Are requirements specified for which header is trusted as client IP (Forwarded, X-Forwarded-For, X-Real-IP), and under what proxy-trust configuration? [Completeness, Spec §FR-016, US8 §4]
- [x] CHK009 Is the IP-binding granularity specified — exact IP, /24 subnet, IPv6 /64 prefix? [Completeness, Spec §FR-016, Gap]
- [x] CHK010 Are requirements defined for IP binding when a participant is behind a CGNAT or load-balancer rotation? [Completeness, Edge Case, Gap]
- [x] CHK011 Is the IP-binding-on-rotation moment defined — does FR-018 reset to the IP of the rotation request itself, or to the next post-rotation request? [Completeness, Spec §FR-018]

## Requirement Completeness — AuthZ & Roles

- [x] CHK012 Is the time-of-check vs time-of-use boundary specified for role checks (is the role checked at request entry, per-operation, or per-side-effect)? [Completeness, Spec §FR-010, Gap]
- [x] CHK013 Is the pending-participant access scope (FR-020) specified at field-level granularity — can pending see other participants' speaker_id, IP, model, system_prompt? [Completeness, Spec §FR-020, Gap]
- [x] CHK014 Are concurrent facilitator-action requirements specified (two facilitators racing — but spec implies one facilitator per session, which §SC needs to confirm)? [Completeness, Gap]
- [x] CHK015 Are requirements specified for WebSocket-channel auth — token in handshake then trusted for connection lifetime, or re-validated per-message? [Completeness, Gap]

## Requirement Completeness — Defense In Depth

- [x] CHK016 Are brute-force / repeated-failed-auth requirements defined (lockout, exponential backoff, alert on N failures)? [Completeness, Gap]
- [x] CHK017 Are anomaly-detection requirements defined for compromise indicators (token used from new IP, unusual hours, simultaneous use)? [Completeness, Gap]
- [x] CHK018 Are CSRF protection requirements specified for token-issuing endpoints (rotate, revoke, transfer)? [Completeness, Gap]
- [x] CHK019 Are session-quarantine / lockdown requirements defined when active compromise is suspected (mass revoke, force re-auth)? [Completeness, Gap]
- [x] CHK020 Are requirements specified for tokens-in-URLs (forbidden? path-only? query-string allowed for downloads?) — current FR wording assumes Authorization header only. [Completeness, Gap]

## Requirement Clarity

- [x] CHK021 Is "1 second under normal load" in SC-001 quantified by load (concurrent participants? requests/sec? hardware)? [Clarity, Spec §SC-001]
- [x] CHK022 Is "clear error" (FR-002, FR-003, FR-017) defined as a structured error code, an HTTP status, an error-message string, or all three? [Clarity, Spec §FR-002, FR-003, FR-017]
- [x] CHK023 Is "configurable expiry" (FR-012) specified as deployment env var, runtime config, or per-session — and where is the canonical knob? [Clarity, Spec §FR-012, Assumptions]
- [x] CHK024 Is "atomic" rotation (SC-003) defined operationally — DB transaction, single SQL statement, optimistic locking? [Clarity, Spec §SC-003]
- [x] CHK025 Is the audit log "actor / target / timestamp" payload (FR-014) specified completely — does it include the action's reason, before/after state, IP? [Clarity, Spec §FR-014]

## Requirement Consistency

- [x] CHK026 Does FR-004 ("token plaintext never logged") align with FR-012 of 007 (log scrubbing for credential patterns)? Are they enforced by the same mechanism (root-logger ScrubFilter) or independent? [Consistency, Spec §FR-004, cross-ref 007 §FR-012]
- [x] CHK027 Does the IP-binding error (FR-017) follow the same shape as the token-expired (FR-002) and token-invalid (FR-003) errors so clients can distinguish them programmatically? [Consistency, Spec §FR-002, FR-003, FR-017]
- [x] CHK028 Are token-rotation, token-revocation, and forced-removal all documented to use the same "token invalidated" mechanism (single source of truth in the auth layer)? [Consistency, Spec §FR-008, FR-009, US5]
- [x] CHK029 Does facilitator-self-removal-prevention (FR-019) align with facilitator-self-transfer-as-recovery — is "transfer first, then leave" the documented escape hatch? [Consistency, Spec §FR-019, US6]

## Acceptance Criteria Quality

- [x] CHK030 Can SC-005 ("zero ability for pending to inject messages or trigger AI responses") be objectively measured with a test fixture, or does it require code review? [Measurability, Spec §SC-005]
- [x] CHK031 Is SC-006 ("100% rejection of non-facilitator privileged ops") testable per-endpoint or only as an aggregate? [Measurability, Spec §SC-006, Gap]
- [x] CHK032 Are rate-limit / latency budgets defined for the auth path (token validation, IP check, role check)? [Acceptance Criteria, Gap]
- [x] CHK033 Is the IP-binding success criterion specified (no SC currently covers IP binding behavior)? [Coverage, Gap]

## Scenario Coverage

- [x] CHK034 Are recovery requirements defined for the case where the bcrypt hashing library degrades (cost factor 12 too slow under load) — graceful degradation or hard failure? [Coverage, Recovery Flow, Gap]
- [x] CHK035 Are concurrent-participant-removal scenarios addressed (two facilitators try to remove the same participant — but spec implies one facilitator only) [Coverage, Gap]
- [x] CHK036 Are repeated-revocation scenarios addressed (revoke an already-revoked token — idempotent or error)? [Coverage, Gap]
- [x] CHK037 Are token-expiry-during-active-turn scenarios addressed (expiry passes mid-turn — does the in-flight turn complete or get cancelled)? [Coverage, Edge Case, Spec §Edge Cases]

## Edge Case Coverage

- [x] CHK038 Are requirements defined for the case where a facilitator's IP changes mid-session (mobile network handoff, VPN flip)? [Edge Case, Gap]
- [x] CHK039 Are requirements defined for tokens issued before a deployment that changes the bcrypt cost factor (forward-compat hash format)? [Edge Case, Gap]
- [x] CHK040 Are requirements defined for malformed Authorization headers (missing Bearer prefix, multiple tokens, base64-decoded plaintext)? [Edge Case, Gap, Spec §FR-003]

## Non-Functional Requirements

- [x] CHK041 Is the threat model documented and requirements traced to it (relate to OWASP ASVS L2 auth controls, NIST SP 800-63B token classes)? [Traceability, Gap]
- [x] CHK042 Are auditability requirements defined for failed auth attempts (does the spec mandate logging "attempt by IP X with token-prefix Y")? [Coverage, Gap]
- [x] CHK043 Are performance regression requirements specified for bcrypt cost re-evaluation (when cost goes from 12 to 14, what's the latency cap)? [Performance, Gap]

## Dependencies & Assumptions

- [x] CHK044 Is the OAuth 2.1+PKCE migration trigger (Phase 3 per constitution §6.6) paired with a concrete signal (calendar deadline, threat-model change, customer requirement)? [Assumption, Spec Assumptions]
- [x] CHK045 Is the dependency on MCP-server connection management (forced disconnect on revocation/removal) covered by an integration contract — what does the auth layer expect, what does MCP guarantee? [Dependency, Spec Assumptions]

## Notes

- Highest-leverage findings to expect: CHK008 (proxy-trust header — spec is vague), CHK013 (pending access at field-level), CHK016 (no brute-force protection), CHK020 (tokens-in-URLs not declared out of scope), CHK041 (no threat-model traceability).
- Lower-priority but easy wins: CHK022 (error-shape uniformity), CHK023 (config-knob location), CHK025 (audit-log payload completeness).
- Run audit by reading [src/auth/](../../../src/auth/), [src/mcp_server/](../../../src/mcp_server/) auth middleware, and the IP-binding / rotation logic; cross-reference with this spec's requirements / assumptions / edge cases.
