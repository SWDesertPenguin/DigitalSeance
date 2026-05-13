# Security Checklist: MCP Build

**Purpose**: Validate that the security requirements written into spec 030 are complete, clear, consistent, measurable, and cover the scenarios the build's threat surface implies. This checklist tests the REQUIREMENTS QUALITY — not the implementation. Each item asks whether the spec adequately specifies a security property; it does NOT ask whether the property holds at runtime (runtime verification belongs in tests/, not here).
**Created**: 2026-05-13
**Feature**: [spec.md](../spec.md)
**Status markers used**: [PASS] / [PARTIAL] / [GAP] / [DRIFT] / [ACCEPTED] per `feedback_no_emoji_in_checklists`.

## Authorization & Authentication (Phase 4 OAuth)

- [ ] CHK001 Are the rejected OAuth grant types enumerated explicitly (Implicit, ROPC) AND the reason for rejection captured? [Completeness, Spec §FR-070]
- [ ] CHK002 Is PKCE's `code_challenge_method` constraint specified as `S256`-only with `plain` rejection behavior defined? [Clarity, Spec §FR-071]
- [ ] CHK003 Are all authorize-endpoint query parameters enumerated with their validation rules (required/optional, format, allowed-value constraints)? [Completeness, Spec §FR-072 + contracts/oauth-authorize.md]
- [ ] CHK004 Is the authorization code's TTL specified with a default value AND an env-tunable range? [Clarity, Spec §FR-088 + research.md §3]
- [ ] CHK005 Are token-endpoint grant-type constraints specified with refusal behavior for unsupported grants? [Completeness, Spec §FR-073]
- [ ] CHK006 Is the JWT access token claim set fully enumerated (sub, client_id, scope, auth_time, iat, exp, jti)? [Completeness, Spec §FR-097]
- [ ] CHK007 Is the JWT signing algorithm specified with rationale AND fallback path documented? [Clarity, Spec §FR-088 + research.md §2]
- [ ] CHK008 Are signing-key path semantics specified (single active key vs rotation grace window)? [Coverage, research.md §2]
- [ ] CHK009 Is refresh-token rotation policy specified as strict-rotation-on-every-use with atomic semantics? [Clarity, Spec §FR-079]
- [ ] CHK010 Are refresh-token replay consequences specified (family revocation + security_event row)? [Completeness, Spec §FR-079]
- [ ] CHK011 Is the refresh-token at-rest encryption mechanism specified (Fernet) with lookup-index pattern (SHA-256 hash)? [Clarity, Spec §FR-081 + data-model.md Phase 4]
- [ ] CHK012 Are token family-tracking shapes specified (root token, parent token, family revocation cascade)? [Completeness, data-model.md `oauth_token_families` + `oauth_refresh_tokens`]
- [ ] CHK013 Is the revocation endpoint's RFC 7009 semantic specified for both access and refresh tokens? [Clarity, Spec §FR-074]
- [ ] CHK014 Is the revocation-to-disconnect SLA quantified with a measurable threshold AND env-tunable bound? [Measurability, Spec §FR-092 + FR-094]
- [ ] CHK015 Are per-instance JWT-validation cache TTL semantics specified with an upper bound? [Clarity, Spec §FR-094]

## Scope & Sovereignty

- [ ] CHK016 Is the scope vocabulary fully enumerated (role scopes + tool-category scopes)? [Completeness, Spec §FR-077]
- [ ] CHK017 Are facilitator-scope exclusions enumerated (no BYOK credentials, no non-sponsored budgets, no message-injection on sponsored AI's behalf)? [Completeness, Spec §FR-084]
- [ ] CHK018 Is the sovereignty-remediation work item scope clearly stated as in-spec vs. external? [Clarity, Spec §FR-084 (post-2026-05-13 follow-up amendment)]
- [ ] CHK019 Is sponsor scope's tool list explicitly enumerated AND the message-injection exclusion preserved? [Coverage, Spec §FR-065]
- [ ] CHK020 Are AI-participant accessibility per tool decisions captured via the `aiAccessible` flag with criteria documented? [Clarity, Spec §FR-063 + tasks.md T084]
- [ ] CHK021 Is the AI-participant OAuth exclusion specified at issuance with the structural mechanism (not just at dispatch)? [Clarity, Spec §FR-089]
- [ ] CHK022 Is the scope-narrowing behavior on token request specified (requested ∩ grantable)? [Completeness, Spec §FR-077]

## Client Registration & CIMD Security

- [ ] CHK023 Is the CIMD fetch network timeout specified with a default value? [Clarity, Spec §FR-098]
- [ ] CHK024 Is the CIMD document size bound specified? [Clarity, Spec §FR-098]
- [ ] CHK025 Is the CIMD allowed-hosts allowlist behavior specified for empty-list default? [Coverage, Spec §FR-098]
- [ ] CHK026 Is the client-registration mode default specified with rationale for rejected alternatives? [Clarity, research.md §9]
- [ ] CHK027 Are CIMD adversarial-input rejection requirements specified (oversized, malformed, redirect-chain)? [Edge Case, Spec §FR-076 + Spec §Edge Cases Phase 4]

## Step-Up Authorization & Destructive Actions

- [ ] CHK028 Is the list of destructive actions requiring step-up explicitly enumerated? [Completeness, Spec §FR-086]
- [ ] CHK029 Is the step-up freshness threshold quantified with a default value AND env-tunable range? [Measurability, Spec §FR-086]
- [ ] CHK030 Is the step-up-required error response shape specified (return code, client expectation, retry behavior)? [Clarity, contracts/mcp-tools-call.md]

## MCP Protocol Auth (Phase 2)

- [ ] CHK031 Is the static-bearer-token validation path specified as identical to the participant API's token store? [Consistency, Spec §FR-022]
- [ ] CHK032 Is the `Mcp-Session-Id` cryptographic generation requirement specified with bit-length AND source? [Clarity, Spec §FR-020]
- [ ] CHK033 Are auth-failure error codes preserved with SACP-native code in `data` for forensic continuity? [Completeness, Spec §FR-019]
- [ ] CHK034 Is the MCP-endpoint-disabled posture (404 on `/mcp` while participant_api unaffected) specified? [Coverage, Spec §FR-025]

## Static-Token Migration

- [ ] CHK035 Is the static-token grace duration specified with a default AND counter-start semantics (ship date vs per-participant first-prompted date)? [Clarity, Spec §FR-083 + follow-up clarification]
- [ ] CHK036 Is the migration-prompt response shape specified for first-post-Phase-4 static-token request? [Completeness, Spec §FR-082]
- [ ] CHK037 Is the post-grace static-token rejection behavior specified for the MCP endpoint vs. the participant API? [Consistency, Spec §FR-083]

## Audit & Forensics

- [ ] CHK038 Are the audit-log row shapes specified for each token lifecycle event (issued, refreshed, revoked, replay-attempt)? [Completeness, Spec §FR-085]
- [ ] CHK039 Is the security_event row emission specified for failed flows (PKCE mismatch, AI-subject access, family replay)? [Coverage, Spec §FR-085 + §FR-089]
- [ ] CHK040 Is the transcript-canonicity boundary specified (OAuth events go to admin_audit_log + security_events, NEVER to message transcript)? [Consistency, Spec §FR-096 + Constitution V17]
- [ ] CHK041 Is the token-value scrubbing requirement specified for audit-log rows AND security-event rows? [Clarity, Spec §FR-085]
- [ ] CHK042 Are scope claims in audit-row rendering specified in human-readable form for forensic review? [Clarity, Spec §FR-085 + US16]

## Rate Limiting & DoS Mitigation

- [ ] CHK043 Is the per-IP rate-limit application specified for the authorize endpoint AND token endpoint? [Coverage, Spec §FR-093]
- [ ] CHK044 Is the failed-PKCE-threshold throttle specified with a default value AND temporary-block semantics? [Clarity, Spec §FR-093 + Edge Cases Phase 4]
- [ ] CHK045 Are the MCP rate-limit budgets specified as sharing a per-bearer/per-account bucket with participant_api requests? [Consistency, Spec §FR-028]

## Architectural Security Boundaries

- [ ] CHK046 Is the OAuth-token-validation locality requirement specified as exclusive to `src/mcp_protocol/auth/`? [Clarity, Spec §FR-099]
- [ ] CHK047 Is the architectural test for the auth-validation boundary specified as CI-blocking? [Measurability, Spec §FR-099 + SC-051]
- [ ] CHK048 Is the MCP-tool-to-participant-api parity architectural test specified as CI-blocking? [Measurability, Spec §FR-068 + SC-036]

## Phase 5 Documentation Security

- [ ] CHK049 Is the sample-token redaction policy specified with a prefix pattern AND scanner-allowlist requirement? [Clarity, Spec §FR-121 + research.md §11]
- [ ] CHK050 Are the troubleshooting matrix's 403 root-cause entries specified with sufficient detail (id-vs-token swap as most-likely first cause)? [Completeness, Spec §FR-116]
- [ ] CHK051 Is the masked-display copy-paste block specified for low-trust side-channel verification? [Coverage, Spec §FR-102]
- [ ] CHK052 Are the bearer-token-vs-session-id distinction's security implications specified (token = security primitive, session_id = routing primitive)? [Clarity, Spec §FR-104 + FR-105]
- [ ] CHK053 Is the CSRF/origin posture documented for both pre-Phase-4 and post-Phase-4 states? [Coverage, Spec §FR-115]
- [ ] CHK054 Is the Windows Defender exclusion guidance specified with the exact directory AND a risk note? [Coverage, Spec §FR-111]
- [ ] CHK055 Is the macOS `xattr -d com.apple.quarantine` guidance specified with the exact invocation AND a risk note? [Coverage, Spec §FR-114]

## Cross-Phase Security Invariants

- [ ] CHK056 Is the AI security pipeline (spec 007) bypass-prevention requirement specified at the MCP dispatch boundary? [Consistency, Spec §FR-017 + Cross-References]
- [ ] CHK057 Is the spec 022 cross-instance dispatch's auth-context-preservation requirement specified? [Coverage, Spec §FR-023]
- [ ] CHK058 Is the spec 019 rate limiter's bucket-key consistency specified across MCP and participant_api surfaces? [Consistency, Spec §FR-028]
- [ ] CHK059 Are V15 fail-closed semantics specified for every new Phase 2/3/4 env var? [Completeness, Spec §FR-031 + §FR-069 + §FR-087]
- [ ] CHK060 Is the V16 deliverable gate (validator + docs/env-vars.md) specified as blocking `/speckit.tasks` for the relevant phase? [Clarity, Spec §FR-034 + §FR-069 + §FR-088]

## Ambiguities & Open Questions

- [ ] CHK061 Is the SACP_OAUTH_CIMD_ALLOWED_HOSTS empty-list-equals-all-hosts default's security posture explicitly accepted by the operator? [Ambiguity, Spec §FR-098]
- [ ] CHK062 Is the cross-instance LRU 30s cache TTL adequate against the 5s revocation propagation SLA, or is there a documented gap? [Ambiguity, Spec §FR-092 vs §FR-094]
- [ ] CHK063 Is the "exclusion at issuance vs at dispatch" choice for AI-participant OAuth refusal sufficiently justified against detection-loudness concerns? [Assumption, Spec §FR-089 + follow-up clarification]
- [ ] CHK064 Is the "JWT access + opaque-Fernet refresh" choice's revocation-latency trade-off accepted with documented bounds? [Assumption, research.md §2]
- [ ] CHK065 Is the deployment-side the deployment stack manual-update requirement clearly out-of-PR-scope, not a CI failure? [Clarity, Spec §FR-006]

## Notes

- Items above test whether the SPEC writes the security requirement clearly enough that an implementer cannot reasonably mis-implement it. They do NOT test whether the implementation correctly enforces the requirement (that's tests/test_mcp_oauth_*.py per tasks.md).
- Markers: [Gap] means the spec is silent on the property; [Ambiguity] means the spec mentions it but doesn't pin it; [Conflict] means two spec sections disagree; [Assumption] means the spec accepts a trade-off whose explicit acknowledgment matters.
- Status markers: [PASS] for items already satisfied by the spec text, [PARTIAL] for items partially addressed, [GAP] for items unaddressed, [DRIFT] for items where spec and contracts/data-model disagree, [ACCEPTED] for items the operator has explicitly accepted as residuals.
- Check items off as the spec is amended or accepted: `[x]`.
- Reviewers should add inline status markers like `- [x] CHK001 [PASS] ...` or `- [ ] CHK001 [GAP] reason ...` rather than relying on the bare checkbox.
