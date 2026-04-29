# Security Requirements Quality Checklist: Web UI

**Purpose**: Validate the quality, clarity, and completeness of security requirements in the Web UI spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Feature**: [spec.md](../spec.md)
**Sister checklists**: spec already has a dedicated **Security Requirements** subsection (SR-001 through SR-008) — this checklist tests the quality of those plus the broader security surface (FR-006 markdown pipeline, FR-014 close-code handling, US12 pending-state filtering).

Markers used in findings (apply during audit, before resolution):
- `→ ✅` requirement is adequately specified
- `→ ⚠️ partial` spec addresses some aspect but leaves the rest implicit
- `→ ❌ gap` spec silent; code may or may not address it
- `→ 🐛 drift` spec and shipped code disagree
- `→ 📌 accepted` gap is documented in spec already — confirm and re-check

## Requirement Completeness — Headers & CSP

- [ ] CHK001 Is the CSP `script-src` allowlist (SR-001: `'self' 'unsafe-eval' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net`) paired with a SRI-integrity-attribute requirement on every CDN script (mentioned as "task T204" but not codified as a spec requirement)? [Completeness, Spec §SR-001, partial]
- [ ] CHK002 Is the `connect-src` directive (SR-001 includes `<SACP_WEB_UI_MCP_ORIGIN>`) covered by a deployment requirement that operators configure the env var correctly? [Completeness, Spec §SR-001, partial]
- [ ] CHK003 Are CSP report-uri / report-to requirements specified (without them, violations are silent)? [Completeness, Gap]
- [ ] CHK004 Is the precompile-at-build alternative tracked beyond a one-line "future phase" mention (SR-001) — any trigger condition (CDN compromise; CSP audit failure)? [Completeness, Spec §SR-001, partial]
- [ ] CHK005 Are HSTS max-age values pinned (SR-002 lists the header but not the policy: 1 year? 6 months? includeSubDomains?)? [Completeness, Spec §SR-002, partial]
- [ ] CHK006 Are Permissions-Policy directives enumerated (SR-002 mentions the header; the actual deny-list is unspecified — camera, microphone, geolocation, payment etc.)? [Completeness, Spec §SR-002, partial]

## Requirement Completeness — Token & Session

- [ ] CHK007 Is the FR-003 token-handling requirement ("HttpOnly cookie or React ref — never localStorage") specified at storage-mechanism granularity (SameSite, Secure flag, cookie path, lifetime)? [Completeness, Spec §FR-003, partial]
- [ ] CHK008 Are requirements specified for token-rotation invalidation timing (FR-003 says "redirect to AuthGate" — but is there a window between rotation and WS close)? [Completeness, Spec §FR-003, partial]
- [ ] CHK009 Are requirements specified for the Web UI's logout flow (deletes cookie, clears refs, terminates WebSocket — does this exist as a button)? [Completeness, Gap]
- [ ] CHK010 Is the "token-reveal modal" (US11 AC2) specified as one-time-only — what if the user closes without copying? [Completeness, Spec §US11, partial]

## Requirement Completeness — WebSocket Lifecycle

- [ ] CHK011 Is the WebSocket Origin validation (SR-004) specified at exact-match granularity (case-sensitive vs lowercase, scheme + host + port equality)? [Completeness, Spec §SR-004, partial]
- [ ] CHK012 Are WebSocket close-code semantics specified beyond enumeration (FR-014 lists 4401 / 4403 / 4429 / 1006 — but is each documented at user-facing behavior)? [Completeness, Spec §FR-014, partial]
- [ ] CHK013 Are requirements specified for WebSocket-frame size limits (a malicious server could send a 10MB frame to OOM the browser)? [Completeness, Gap]
- [ ] CHK014 Are requirements specified for the case where the WebSocket re-auths after token rotation (FR-003 implies the existing WS closes; what about new WS connections during the gap)? [Completeness, Spec §FR-003, partial]

## Requirement Completeness — Markdown Security Pipeline

- [ ] CHK015 Is the FR-006 invisible-Unicode list (`U+200B..U+200F, U+202A..U+202E, U+2066..U+2069, U+FEFF`) authoritative? Cross-ref 007 §FR-001 sanitization — does the UI re-strip what the server already stripped, or trust the server? [Completeness, Spec §FR-006, cross-ref 007 §FR-001]
- [ ] CHK016 Are requirements specified for additional dangerous schemes beyond `javascript: / data: / vbscript: / file:` (e.g., `chrome-extension:`, `moz-extension:`, `intent:`, custom protocols)? [Completeness, Spec §FR-006, partial]
- [ ] CHK017 Are requirements specified for nested HTML inside markdown (a code block containing literal `<script>` — should render as text per FR-006, but is "raw HTML stripped" the same as "literal HTML rendered as text")? [Completeness, Spec §FR-006, partial]
- [ ] CHK018 Are requirements specified for SVG content (an `<img src=foo.svg>`-style markdown image is neutralized, but inline SVG via a data URI was already forbidden — what about SVG hosted on a same-origin path)? [Completeness, Gap]
- [ ] CHK019 Are markdown-link requirements specified for new-tab opening (`target=_blank` without `rel=noopener noreferrer` is a window-name attack surface)? [Completeness, Gap]

## Requirement Completeness — Pending Filtering

- [ ] CHK020 Is the US12 pending-filtered state_snapshot (AC2: "session name + human participants only — no transcript, no AI roster") authoritative? Same fields cross-ref 002 §FR-020 — is this 011's enforcement of 002's pending-scope? [Completeness, Spec §US12, cross-ref 002 §FR-020]
- [ ] CHK021 Are requirements specified for the pending → participant transition's UI escalation timing (AC3: WS event flips role; what if the WS is briefly disconnected; does the UI re-fetch on reconnect)? [Completeness, Spec §US12, partial]
- [ ] CHK022 Are requirements specified for pending-participant WS event filtering (do they receive `message` events; `convergence_update`; `participant_update` for OTHER participants)? [Completeness, Gap]

## Requirement Clarity

- [ ] CHK023 Is "no `dangerouslySetInnerHTML` on unsanitized content" (SR-005) defined operationally — what counts as "sanitized"; is sanitization the FR-006 markdown pipeline output? [Clarity, Spec §SR-005]
- [ ] CHK024 Is "X-SACP-Request: 1 custom header on all mutations" (SR-006) specified at fetch-call granularity — does the WS connection or SSE need it? [Clarity, Spec §SR-006, partial]
- [ ] CHK025 Is "API keys and system prompts never displayed" (SR-007) specified at field-source level (the server should not send them; if it accidentally did, would the UI defend)? [Clarity, Spec §SR-007]

## Requirement Consistency

- [ ] CHK026 Does FR-006 markdown rendering align with 007 §FR-006 / §FR-007 (image strip, URL flagging) — does the UI re-render attempt anything the server already stripped? [Consistency, Spec §FR-006, cross-ref 007]
- [ ] CHK027 Does SR-003 (CORS own-origin only) align with 006 Assumptions (MCP CORS allows LAN ranges)? Different surfaces; is the boundary clear? [Consistency, Spec §SR-003, cross-ref 006]
- [ ] CHK028 Does FR-014 close-code handling (4401/4403/4429/1006) align with 002 §FR-002 / §FR-003 / §FR-017 / 009 §FR-002 error semantics — are the codes 1:1 with the underlying auth failures? [Consistency, Spec §FR-014, cross-ref 002, 009]
- [ ] CHK029 Does FR-003 (token rotation invalidates UI) align with 002 §FR-008 (rotation invalidates old token) — same SSOT, just propagated? [Consistency, Spec §FR-003, cross-ref 002 §FR-008]

## Acceptance Criteria Quality

- [ ] CHK030 Is SC-004 ("all XSS test vectors neutralized") tied to a specific test corpus (a YAML / JSON fixture of vectors) or only descriptive? [Measurability, Spec §SC-004, Gap]
- [ ] CHK031 Is SC-002 ("AI turns appear within 2 seconds") testable under packet-loss / backpressure conditions, or only on local/LAN? [Measurability, Spec §SC-002, partial]

## Scenario Coverage

- [ ] CHK032 Are recovery requirements defined for the case where the WS receives a malformed message (e.g., invalid JSON, missing required fields) — does the UI crash, ignore, or alert? [Coverage, Recovery Flow, Gap]
- [ ] CHK033 Are requirements specified for the case where the server pushes a `state_snapshot` containing a sensitive field that the server forgot to strip — does the UI defend in depth? [Coverage, Gap, cross-ref SR-007]
- [ ] CHK034 Are requirements specified for the multi-tab case (one tab logged in, another tab opens — both share the cookie; do they conflict on WS connection)? [Coverage, Gap]

## Edge Case Coverage

- [ ] CHK035 Are requirements defined for very large markdown documents (100K char message — DoS-via-render)? [Edge Case, Gap]
- [ ] CHK036 Are requirements defined for adversarial markdown (deeply nested lists, infinite reference loops)? [Edge Case, Gap]
- [ ] CHK037 Are requirements defined for malicious clipboard interactions (copying token from token-reveal modal — does any other origin observe via `navigator.clipboard.readText()`)? [Edge Case, Gap]
- [ ] CHK038 Are requirements defined for the case where the user pastes a token containing whitespace / quotes (US11 AC1 sign-in form — does it normalize / reject)? [Edge Case, Gap]

## Non-Functional Requirements

- [ ] CHK039 Is the threat model documented and requirements traced to it (OWASP ASVS L2 V14 client-side, OWASP CRS XSS catalogue, NIST SP 800-53 SC-7/SC-23/AC-3)? [Traceability, Gap]
- [ ] CHK040 Are subresource-integrity / CDN-failure requirements paired with a fallback (if unpkg.com goes down, the UI is dead — is that accepted residual)? [Coverage, Spec §SR-001, partial]
- [ ] CHK041 Are accessibility requirements (Assumptions: "deferred follow-up") paired with a re-evaluation trigger (when does a11y stop being deferred)? [Assumption, Spec Assumptions, partial]

## Dependencies & Assumptions

- [ ] CHK042 Is the dependency on Babel Standalone for runtime JSX compilation (SR-001 rationale) paired with a re-evaluation trigger (when does the precompile-at-build path become required)? [Dependency, Spec §SR-001, partial]
- [ ] CHK043 Is the Assumption "no build toolchain — CDN-loaded" still aligned with current security posture (every CDN load is a third-party trust)? [Assumption, Spec Assumptions, partial]
- [ ] CHK044 Is the "session creation wizard, invite/onboarding flow simple enough to implement directly" assumption paired with a security review of the onboarding flows once they exist (US11 / US12 ARE the flows; the assumption is partly stale)? [Assumption, Spec Assumptions, partial]

## Ambiguities & Conflicts

- [ ] CHK045 Does SR-007 ("API keys and system prompts never displayed") conflict with US4 §3 (non-facilitator viewing budget cards shows utilization% but not exact dollars)? Different visibility, but is "system prompts" referring to the *participant's own* system prompt (which the participant authored — should they see it)? [Ambiguity, Spec §SR-007, §US4]
- [ ] CHK046 Does FR-006 (markdown rendering with security overrides) duplicate or replace 007 §FR-006/§FR-007 server-side stripping? Is the UI defense-in-depth or the only barrier? [Ambiguity, Spec §FR-006, cross-ref 007]
- [ ] CHK047 Does SR-006 (CSRF custom header) interact correctly with FR-002 (single-file React, CDN-loaded) — can a CSRF attacker include the custom header from a third-party page? Browsers prevent custom headers cross-origin, so safe — confirm the rationale is documented. [Ambiguity, Spec §SR-006, partial]

## Notes

- Highest-leverage findings to expect: CHK001 (SRI not codified — task T204 referenced but not a spec requirement), CHK003 (no CSP reporting → silent violations), CHK013 (no WS frame size limit → OOM), CHK030 (no XSS test corpus), CHK033 (defense-in-depth on server-leaked sensitive fields), CHK039 (no traceability).
- Lower-priority but easy wins: CHK005 (HSTS max-age pin), CHK006 (Permissions-Policy directives), CHK016 (additional dangerous schemes), CHK019 (rel=noopener on links).
- Run audit by reading [src/web_ui/](../../../src/web_ui/) including the FastAPI app, the React component file(s), the WS handler, the markdown override, and the security-headers middleware; cross-reference 002 (auth), 006 (MCP), 007 (server-side strip), 009 (rate-limit close codes), 010 (sensitive-field server-side stripping).
