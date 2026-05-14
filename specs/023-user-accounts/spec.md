# Feature Specification: User Accounts with Persistent Session History

**Feature Branch**: `023-user-accounts`
**Created**: 2026-05-07
**Status**: Implemented 2026-05-12 (seven implementation phases shipped via PR #345 + follow-up PR #347; unblocks spec 024 facilitator scratch account-scoped path)
**Input**: User description: "Phase 3+ user accounts. Current participant identity is token-scoped (spec 002); closing the browser tab loses access. This adds a login-based identity layer ABOVE the existing token-based participant model — same tokens still gate per-session participant lifecycle, but accounts persist across browser sessions and remember which active and archived sessions a person joined. Email + password auth with argon2id; OAuth migration coordinated with the Phase 3 OAuth roadmap. Pre-authentication rate limiting per audit follow-through. Single-tenant-per-deployment per spec 011's Phase D privacy stance — accounts see only sessions they joined, no cross-tenant browsing. Applies to topologies 1-6 (orchestrator-mediated identity); incompatible with topology 7 per V12. Primary use cases: research co-authorship (§2), consulting (§3), decision-making under asymmetric expertise (§6)."

## Overview

Spec 002 (participant-auth) defines the **per-session participant**
identity: a participant joins a session by presenting a static
bearer token; the token gates approval, message injection, and
departure. The token model is correct for the per-session
authorization decision, but it has a UX cost — the token is the
*only* identity, so closing the browser tab without saving it
strands the participant. A returning human cannot find their way
back to a session they joined yesterday without operator
mediation (the facilitator regenerates a token per spec 002
clarification). For the V13 use cases that involve asynchronous
return — research co-authorship (§2 weeks-long sessions), consulting
(§3 multi-engagement consultants), expert advisory (§6) — the
token-only model is friction.

This spec defines a **user account** as a persistent identity layer
that sits ABOVE the token model. An account owns the per-session
participant records produced by spec 002. The token remains the
authoritative per-session credential; the account does not
replace it. What the account adds:

1. **Persistent identity.** Email + password (argon2id-hashed)
   creates an account that survives browser tab close, machine
   reboot, and token rotation. A returning human logs in once and
   sees their session list.
2. **Session list.** A new endpoint `GET /me/sessions` returns the
   sessions the account has joined as a participant — active
   sessions first, archived second. Each entry includes session
   id, name, last-activity-at, the participant role within that
   session, and the participant id (so the SPA can re-bind to
   the correct per-session participant credential).
3. **Token rotation made transparent.** Token rotation per spec 002
   §FR-007 still happens (the token is the security primitive),
   but the account holds the rotated token in its server-side
   `SessionStore` (spec 011's H-02 fix already established this
   shape) so the human re-binds without copying the new token
   string by hand.
4. **Account settings.** Email change, password change, account
   deletion with data-export-on-delete. Account deletion preserves
   the participant records the account owns — those rows are
   audit-log artifacts per spec 002 §FR-016 / spec 001 §FR-019 —
   but releases the email/password credentials and unbinds the
   ownership pointer so no future login resolves to the deleted
   account.

The account is **strictly single-tenant** within a deployment, per
spec 011 Phase D clarification ("Phase 1 is explicit single-tenant
— one SACP_* env-var set, one DB, one origin"). An account sees
only sessions it joined as a participant; an account cannot
discover sessions, accounts, or participants belonging to other
tenants. Multi-tenant deployments are Phase 4+ federation scope.

The auth primitive is **argon2id**, NOT bcrypt. Spec 002 uses
bcrypt for static-token hashing — appropriate for that threat
model (token validation runs on every authenticated request and
bcrypt's known cost is acceptable). Account password hashing has
a different threat model: rare invocation (login + change-password
events) versus per-request invocation, and a CPU-DoS surface that
audit findings flagged for spec 002's bcrypt use. Argon2id with
OWASP 2024 parameters (memory ≥ 19 MiB, time cost ≥ 2,
parallelism = 1) is the modern recommendation; the parameters are
operator-tunable via env vars to accommodate hardware variation.

This spec is **Phase 3+ scope** — explicitly NOT a Phase 3
prerequisite. No active Phase 3 work (013, 014, 015–022) depends
on it. It IS a prerequisite for spec 024 (facilitator scratch
notes) per the user's roadmap — scratch notes need a persistent
identity to attach to. Implementation is complete (Status: Implemented
2026-05-12; PRs #345 + #347); the account surface is live.

## Clarifications

### Session 2026-05-14 (/speckit.analyze findings)

- Q: FR-012 says the account-deletion endpoint emits an automated debug-export to the registered email, but tasks.md notes the export payload is a placeholder pending the email-transport implementation. Does the spec accurately reflect the implementation state? → A: Partially. The call site fires correctly and the email-transport call is wired; the full session-row payload content is a placeholder pending the email-transport implementation. FR-012 is partially implemented — the trigger and call site are correct; the payload content finalizes when the transport ships. Added a residuals annotation to FR-012. Finding 23-B1.
- Q: V16 fail-open on `SACP_EMAIL_TRANSPORT`? → A: Fixed. The original design routed startup enforcement through `select_transport()` at the factory layer, but no production call path invoked the factory at startup — so `smtp`/`ses`/`sendgrid` passed V16 syntactically and the process booted without any real transport, deferring the crash to first email send. `validate_email_transport()` in `src/config/validators.py` now rejects `smtp`/`ses`/`sendgrid` directly as "reserved for a follow-up email-transport spec," exiting the process before binding ports. The factory's `EmailTransportNotImplemented` raise is retained as a belt-and-braces guard. Contract doc `contracts/email-transport.md` and `tests/test_023_validators.py` updated; 10/10 tests pass. Finding 23-F1.
- Q: Does this amendment change behavior? → A: 23-B1 is doc-only; 23-F1 is a behavior change — `SACP_EMAIL_TRANSPORT={smtp,ses,sendgrid}` now exits at startup instead of booting and deferring the crash to first email send. Operationally this is the documented intent of the original design; the V16 layer is just doing the work the factory was supposed to do.

### Session 2026-05-09 (Resolved)

All ten initial-draft markers resolved, plus three additional ambiguities surfaced during pre-clarify review. FR text is updated inline below; the original "Initial draft assumptions requiring confirmation" subsection is retained for historical reference.

1. **OAuth migration landing**. The OAuth migration is a separate future spec, NOT spec 014 (`dynamic-mode-assignment`). User input naming "spec 014's auth migration" is interpreted as the Phase 3 OAuth roadmap per Constitution §10. v1 ships email + password; FR-021 keeps the hash-and-credential boundary pluggable for the future OAuth spec. An explanatory cross-ref note is retained in §Cross-References making the misattribution-correction durable.

2. **Email verification mechanism**. Code-entry confirmed: 16-character base32, single-use, 24-hour TTL, as drafted in FR-004. Magic-link, SMS, and no-verification alternatives are all rejected. Magic-link is vulnerable to email-client preview crawlers consuming the single-use token before user click; SMS adds phone-number identity surface and regional-availability friction inconsistent with V13 use cases; no-verification is a credential-stuffing amplifier. Disabling verification entirely is deferred as a possible future env-var enhancement, NOT shipped in v1.

3. **Email transport adapter**. Noop default confirmed for `SACP_EMAIL_TRANSPORT`. When `SACP_ACCOUNTS_ENABLED=true` AND `SACP_EMAIL_TRANSPORT=noop`, the orchestrator MUST emit a startup WARNING naming the consequence (verification codes will appear in `admin_audit_log` only; not suitable for production). The combination MUST NOT fail-closed — operators legitimately run dev/staging with noop transport. The audit-log fallback (edge case "Email transport unavailable") establishes the operator-recoverable pattern.

4. **Password reset flow**. Code-based reset to the registered email confirmed: 16-character base32, single-use, 30-minute TTL (same shape as verification codes, shorter window). Recovery codes printed at signup are deferred to a future enhancement; NOT shipped in v1. Reset attempts MUST count toward the FR-015 per-IP rate limiter. New endpoint pair (request + confirm) and a corresponding FR are planned for `/speckit.plan`-phase work; FR-014 ScrubFilter coverage extends to reset codes.

5. **Account deletion shape**. The drafted shape (zero email + password_hash, retain row with `status='deleted'`, release email after grace, automated debug-export pre-delete via email transport) is confirmed with one tweak: the grace period is env-tunable via a new env var `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`, default 7, valid range `[0, 365]`. The `0` value disables the grace period (immediate email release). FR-013 is updated; the env var is added to the V16 list (§Configuration); SC-009 reads the env var rather than hardcoding 7 days.

6. **Session-list pagination**. Offset-based at 50 per page confirmed (FR-008 stands as drafted). When an account's session count crosses 10,000, a warning MUST be logged at query time and an `admin_audit_log` row recording the migration-threshold trip MUST be emitted. Cursor pagination is a backlog item triggered by that threshold, NOT a v1 deliverable.

7. **Active vs. archived response shape**. Two-segment shape `{active_sessions, archived_sessions}` confirmed (FR-008 stands as drafted). Pagination is per segment, NOT across segments — FR-008 is clarified to make this explicit.

8. **Account ownership transfer (P3)**. The in-or-defer ruling for P3 / FR-020 is pinned to `/speckit.plan` time, NOT pre-deferred at clarify. FR-020 carries an explicit decision-checkpoint note: plan phase decides whether FR-020 ships in v1 implementation or splits into a follow-up amendment. The user's brief ("deferred to Phase 4 federation if it complicates Phase 3") is conditional on plan-phase implementation-surface fit; pre-deferral discards information plan phase produces.

9. **SessionStore extension**. Reuse-and-extend confirmed (NOT a parallel new store). FR-016 stands as drafted. Spec 011's `SessionStore` is extended to map `account_id` to the account's session bindings; the opaque sid remains the cookie payload. This keeps cookie validation single-lookup and invalidation single-point.

10. **Pre-auth rate limiter composition**. Separate limiter, additive composition with spec 019 confirmed. FR-015 stands as drafted. Both limiters apply independently with no shared state; either trips first wins. The narrow per-account limiter targets credential-stuffing; spec 019's broad network-layer limiter targets general HTTP abuse. Independent tunability is intentional defense-in-depth.

11. **Email change — notify-old + verify-new (NEW)**. On email change requests, the OLD email MUST receive a heads-up notification (no action required from the user) at the same time the NEW email receives the verification code. Security-sensitive operations notify both addresses to defend against email-takeover attacks. FR-010 is updated to make this explicit.

12. **Password-change SessionStore invalidation semantics (NEW)**. On a successful password change, the orchestrator MUST invalidate all sids associated with the account_id EXCEPT the actor's current authenticated sid (the session driving the change survives; all others are forced to re-authenticate). FR-011 is updated to specify this precise semantic.

13. **Login response payload shape (NEW)**. Login is a two-trip flow. The login response body is minimal (auth state confirmation + session cookie set in the response headers); the SPA follows up with a separate `GET /me/sessions` call to retrieve the session list. This keeps the login endpoint focused, lets `/me/sessions` keep its own pagination, and avoids inflating login responses with potentially large session arrays. FR-007 is updated to make this explicit.

### Initial draft assumptions requiring confirmation

- **OAuth migration coordination.** User input names "spec 014's
  auth migration" as the OAuth landing point. Spec 014 is
  `dynamic-mode-assignment` (controller layer above 013), not
  an auth-migration spec. Drafted on the assumption the user
  meant the Phase 3 OAuth roadmap in Constitution §10 ("OAuth 2.1
  with PKCE replaces static tokens") — a separate future spec,
  not 014. v1 ships email + password; the OAuth surface is a
  pluggable hash-and-credential boundary so the future OAuth
  spec can add a provider without breaking existing accounts.
  [NEEDS CLARIFICATION: confirm the OAuth migration is a future
  separate spec rather than spec 014.]
- **Email verification mechanism.** Drafted as: signup creates an
  account in `pending_verification` state; the orchestrator emits
  a one-time verification code (cryptographically random,
  16-character base32, single-use, 24-hour TTL) to the email
  address; the user enters the code to activate. NO emailed
  click-link — link-click flows are vulnerable to email-client
  preview crawlers and require an MX integration v1 doesn't
  ship. [NEEDS CLARIFICATION: confirm code-entry flow vs.
  alternatives (SMS, magic-link, no verification at all).]
- **Email-sending mechanism.** Drafted as: the orchestrator
  writes the verification code to `admin_audit_log` AND emits
  via an `SACP_EMAIL_TRANSPORT` adapter (default `noop` —
  development mode, codes appear in logs only). Operators
  configure SMTP / SES / SendGrid via the adapter. [NEEDS
  CLARIFICATION: confirm noop-default vs. requiring an
  email transport at startup; affects deploy ergonomics.]
- **Password reset flow.** Drafted as: forgot-password issues
  a one-time reset code to the registered email (same shape
  as verification code, 30-minute TTL). The reset code permits
  a single password set; subsequent attempts require a new
  reset code. [NEEDS CLARIFICATION: confirm code-based reset
  vs. backup recovery codes printed at signup.]
- **Account deletion preserves participant audit trail.**
  Drafted as: deletion zeroes the email + password hash on the
  account row, retains the row with status `deleted`, releases
  the email for re-registration after a 7-day grace period.
  Participant records the account owned remain — they are
  audit-log artifacts per spec 002 §FR-016. The Art. 17 erasure
  carve-out (spec 002 §FR-016 / spec 001 §FR-019) applies.
  Pre-delete, the account receives an automated debug-export
  (spec 010) containing every session row they joined; the
  export is delivered via the same email transport.
  [NEEDS CLARIFICATION: confirm the 7-day email-grace +
  export-on-delete shape.]
- **Session-list pagination.** Drafted as: offset-based,
  50 per page, ordered by last-activity-at descending.
  Cursor-based pagination is a future enhancement once
  account history grows past the offset-pagination break-even
  point (~10,000 entries per account). [NEEDS CLARIFICATION:
  confirm offset-50 vs. cursor-based.]
- **Active vs archived sessions ordering.** Drafted as: response
  is segmented — `active_sessions: [...]` then `archived_sessions:
  [...]`. The SPA renders these as two ordered groups. Within
  each segment, ordering is last-activity-at descending.
  [NEEDS CLARIFICATION: confirm two-segment shape vs. a single
  flat list with a `status` column.]
- **Account ownership transfer (P3 user story).** User input
  says "deferred to Phase 4 federation if it complicates
  Phase 3." Drafted as: P3 ships only if the implementation
  surface fits within the v1 schema; otherwise it splits into
  a follow-up amendment. The decision lands during
  `/speckit.plan`. [NEEDS CLARIFICATION: confirm P3
  in-scope-or-defer is a `/speckit.plan` decision rather than
  a `/speckit.specify` decision.]
- **`SessionStore` reuse vs. extension.** Spec 011's `SessionStore`
  (the H-02 fix) maps an opaque sid → `(participant_id,
  session_id, bearer)`. Drafted as: this spec extends the same
  store to map `account_id → [SessionEntry]` for post-login
  rebinding, NOT a new store. The opaque sid remains the cookie
  payload; the account is a server-side ownership pointer.
  [NEEDS CLARIFICATION: confirm extension vs. parallel store.]
- **Pre-auth rate limiter composition.** Spec 019 defines
  per-IP network-layer rate limiting that runs BEFORE auth.
  Drafted as: spec 023's account-specific
  `SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN` is a tighter ceiling
  applied at the `/login` endpoint specifically (login attempts
  per IP per minute), composing additively with spec 019's
  general per-IP cap. The two limiters do not share state;
  each enforces its own limit independently. [NEEDS
  CLARIFICATION: confirm separate-limiter composition vs.
  merging into spec 019's middleware.]

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Account creation, email verification, and login (Priority: P1)

A new human navigates to the orchestrator's web UI and is
presented with a "log in" or "create account" choice instead of
the current "paste a token" landing. They click "create account",
enter email + password, submit. The orchestrator hashes the
password with argon2id, creates a `pending_verification` account
row, emits a one-time verification code to the email, and
prompts the user to enter the code. They retrieve the code from
their email, enter it, and the account flips to `active`. They
log in with email + password. The login response sets the
existing spec 011 session cookie (opaque sid) AND records the
account's authenticated state in the `SessionStore`. They are
landed on the post-login session list (US2).

**Why this priority**: P1 because every other story requires an
account to exist. Without account creation, the spec ships zero
value. Email verification is in P1 because un-verified accounts
are an attack vector for credential-stuffing and abuse-pattern
amplification — operators MUST be able to require verification.

**Independent Test**: Drive an account-creation flow from a
fresh DB. Submit email + password to the new endpoint. Assert
an account row is created with `status='pending_verification'`,
the password is stored as an argon2id hash (not plaintext, not
recoverable from the hash), a verification code is recorded in
`admin_audit_log` with `action='account_verification_emitted'`,
and the email transport adapter received the code payload.
Submit the verification code; assert account `status='active'`.
Submit email + password to `/login`; assert HTTP 200, the
existing session cookie is set, `SessionStore` records the
account-authenticated state, and `admin_audit_log` records
`action='account_login'` with actor and timestamp.

**Acceptance Scenarios**:

1. **Given** a fresh deployment with no accounts, **When** a
   user submits email + password to the create-account endpoint,
   **Then** an account row MUST be created with
   `status='pending_verification'`, the password MUST be stored
   as an argon2id hash, AND a one-time verification code MUST
   be emitted via the email transport.
2. **Given** a `pending_verification` account, **When** the
   correct verification code is submitted within the TTL,
   **Then** the account `status` MUST flip to `active`.
3. **Given** a `pending_verification` account, **When** an
   incorrect or expired verification code is submitted,
   **Then** the request MUST be rejected with a clear error
   AND the account MUST remain `pending_verification`.
4. **Given** an `active` account with email + password, **When**
   the user submits matching credentials to `/login`, **Then**
   HTTP 200 MUST be returned, the session cookie MUST be set,
   AND `admin_audit_log` MUST record the login event.
5. **Given** any login attempt with non-matching credentials,
   **When** the request fires, **Then** HTTP 401 MUST be returned
   with a generic `invalid_credentials` error (NO information
   leak distinguishing wrong-email from wrong-password) AND
   the failure MUST be counted toward the per-IP login rate
   limiter.
6. **Given** the per-IP login rate limit is exceeded, **When**
   another login attempt fires from that IP, **Then** HTTP
   429 MUST be returned with `Retry-After` (mirrors spec 009
   §FR-002 / §FR-003 shape).
7. **Given** any account is created or logged in, **When** the
   `admin_audit_log` is inspected, **Then** the event MUST
   appear with no plaintext password, code, or email body
   leaked into the log content (mirrors spec 007 §FR-012
   ScrubFilter).

---

### User Story 2 - Post-login session list with active sessions first, archived sessions second (Priority: P1)

A returning user logs in. The post-login response (or a
follow-up `/me/sessions` GET) returns a structured list of the
sessions they have joined as a participant. Active sessions are
listed first; archived sessions follow. Each entry includes the
session id, the session name, last-activity-at, the user's
participant role within that session, and the participant id
needed to re-bind the SPA to the per-session credential. The
SPA renders this as a menu: clicking an active session takes
the user back into the live UI for that session; clicking an
archived session opens a read-only transcript view.

**Why this priority**: P1 because the session list IS the
account's primary value. Without it, accounts let users log in
to nothing. Active + archived ordering is part of the contract
because the live-vs-historical distinction is the user's first
question.

**Independent Test**: Create an account that has joined three
sessions (one active, one paused, one archived). Log in. Call
`/me/sessions`. Assert the response contains exactly the three
sessions, with the active and paused listed first (both are
non-archived states) and the archived session second. Assert
each entry includes session id, name, last-activity-at, role,
and participant id. Assert sessions belonging to OTHER accounts
do NOT appear in the response.

**Acceptance Scenarios**:

1. **Given** an authenticated account with sessions in mixed
   states, **When** `/me/sessions` is called, **Then** the
   response MUST include `active_sessions: [...]` and
   `archived_sessions: [...]` with the same session IDs that
   the account has participant records for.
2. **Given** the response shape, **When** sessions are
   inspected, **Then** each entry MUST contain at minimum
   session id, name, last-activity-at, the user's role, and
   the participant id.
3. **Given** sessions belonging to a different account,
   **When** the requesting account calls `/me/sessions`,
   **Then** those sessions MUST NOT appear (no cross-account
   leakage).
4. **Given** an account has no sessions, **When**
   `/me/sessions` is called, **Then** the response MUST return
   empty arrays (NOT a 404; an account with no sessions is
   still a valid account).
5. **Given** an account has more than 50 sessions, **When**
   `/me/sessions` is called without pagination params, **Then**
   the first 50 entries MUST be returned with a `next_offset`
   indicator; calling again with the offset MUST return the
   next 50.
6. **Given** a user clicks an active session entry, **When**
   the SPA re-binds, **Then** the SPA MUST resolve to the
   per-session participant credential via the existing
   `SessionStore` flow (no new credential exchange).
7. **Given** a user clicks an archived session entry, **When**
   the SPA opens the read-only view, **Then** the transcript
   MUST render but injection / control actions MUST be
   disabled (mirrors spec 001 archived-session semantics).

---

### User Story 3 - Account settings panel: email change, password change, account deletion with export (Priority: P2)

An authenticated user opens the account-settings panel from
the post-login UI. They can change their email (requires
verification of the new email before the change applies),
change their password (requires re-entering the current
password), or delete the account. Account deletion triggers an
automated debug-export to the registered email containing every
session row the account joined, then zeroes the email and
password hash and marks the account `status='deleted'`. The
account row stays in place to preserve the participant-audit
linkage; only the credential fields are released.

**Why this priority**: P2 because account creation + login (P1)
ships value on its own. Account settings are the maintenance
surface — important but not the critical path for first-use.
Account deletion is the GDPR Art. 20 + Art. 17 fulfillment
surface; the export-on-delete shape lets the user retain a
copy of their participation history before erasure.

**Independent Test**: Drive an authenticated account through
each setting: change email (assert verification emit + flip),
change password (assert old-password check + new-hash storage),
delete account (assert export emit + credential zeroing +
status flip). Assert the account row remains in place after
deletion (no row drop) but is unrecoverable for login.

**Acceptance Scenarios**:

1. **Given** an authenticated account, **When** an email change
   is requested, **Then** a verification code MUST be emitted
   to the NEW email; the email field MUST NOT change until the
   code is submitted; the OLD email continues to receive
   account notifications until the change applies.
2. **Given** an authenticated account, **When** a password
   change is requested with the correct current password,
   **Then** the new password MUST be argon2id-hashed and stored;
   subsequent logins MUST require the new password.
3. **Given** a password change with an incorrect current password,
   **When** the request fires, **Then** HTTP 401 MUST be
   returned AND the new password MUST NOT be stored.
4. **Given** an authenticated account, **When** account deletion
   is requested, **Then** an automated debug-export MUST be
   emitted to the registered email containing every session
   the account joined; the email + password fields MUST be
   zeroed; the account `status` MUST flip to `deleted`.
5. **Given** an account in `status='deleted'`, **When** any
   login attempt fires for the deleted email, **Then** the
   request MUST be rejected with the same generic
   `invalid_credentials` error as a non-existent email (no
   information leak about deletion status).
6. **Given** a deleted account is older than the 7-day email
   grace period, **When** a new account-creation attempt
   uses the same email, **Then** the new account MUST be
   creatable as if the deletion had never happened (no
   stranding of the email).

---

### User Story 4 - Account ownership transfer for organization-managed deployments (Priority: P3)

An organization-managed deployment has a participant whose
sessions belong to one account but who has left the organization;
the deployment owner wants to transfer those sessions to another
account so a successor employee can resume. The owner initiates
a transfer from the orchestrator's admin surface (deployment-
owner-only, NOT account-self-service): both source and target
accounts are confirmed, the participant rows are repointed to
the target account, and an audit-log entry records the transfer.
Tokens issued to the source account remain valid for the
existing per-session participant credential — the transfer
moves ownership only, not the per-session security primitive.

**Why this priority**: P3 because organization-managed
deployments are a subset of v1 deployments (some use cases —
research co-authorship — run with no organizational mediation).
The transfer surface is needed for that subset only; missing it
v1 is an inconvenience for that subset, not a blocker for
others. The user's brief says "deferred to Phase 4 federation
if it complicates Phase 3" — confirming with `/speckit.plan`
whether v1 implementation surface fits.

**Independent Test**: As a deployment owner (operator-side
authentication, NOT a regular account login), call the
ownership-transfer endpoint with source account, target
account, and confirmation. Assert the participant rows
formerly owned by source are now owned by target. Assert
`admin_audit_log` records `action='account_ownership_transfer'`
with actor (deployment owner), source account, target account,
participant id list, and timestamp. Assert the source account
no longer sees those sessions in `/me/sessions`; the target
does.

**Acceptance Scenarios**:

1. **Given** a deployment owner authenticates to the admin
   surface, **When** an ownership-transfer request fires,
   **Then** the participant rows MUST repoint from source to
   target AND `admin_audit_log` MUST record the transfer
   with all required fields.
2. **Given** a regular account attempts the transfer endpoint,
   **When** the request arrives, **Then** HTTP 403 MUST be
   returned (transfer is deployment-owner-only).
3. **Given** a transfer completes, **When** source account's
   `/me/sessions` is queried, **Then** the transferred
   sessions MUST NOT appear; target's response MUST include
   them.
4. **Given** a transfer completes, **When** the per-session
   bearer tokens are inspected, **Then** they MUST remain
   valid for the existing participant credential — transfer
   moves ownership pointer only, not the per-session security
   primitive.

---

### Edge Cases

- **Email collision at signup.** Two users attempt to register
  the same email simultaneously. The first request wins via a
  unique-index constraint on `accounts.email`; the second
  receives a generic "registration failed" error (no
  information leak about email existence).
- **Verification code reuse.** A code submitted once is marked
  consumed; a second submission of the same code rejects.
- **Login attempt against a `pending_verification` account.**
  Login is rejected with the generic `invalid_credentials`
  error — no information leak about verification status.
- **Logged-in user's account is deleted by a deployment owner.**
  Their existing session cookie continues to work for the
  remainder of its TTL (no immediate logout); the next call
  to `/me/sessions` returns empty (no sessions visible) and
  the SPA gracefully shows the post-deletion landing.
- **Logged-in user's password is changed via the settings
  panel.** Their current session cookie remains valid; OTHER
  sessions for that account (e.g., a second browser tab) are
  forcibly logged out (mirrors typical session-invalidation-
  on-password-change UX).
- **Argon2id parameter increase between releases.** The hash
  format includes the parameters used; old hashes verify with
  their stored parameters AND get re-hashed with the new
  parameters on the next successful login (transparent
  re-hash; no user action required).
- **Email transport unavailable when verification code needs
  to send.** The account is created in
  `pending_verification` and the code is recorded in
  `admin_audit_log`; the operator can recover the code from
  the log (development scenario) or retry the send via an
  operator-side endpoint.
- **Account deletion email fails to send.** The deletion
  proceeds (credentials are zeroed); the failed export is
  logged. Operator can re-fetch via spec 010 debug-export
  and email manually if needed. Deletion is not gated on
  email transport availability (privacy-preserving default).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A new `accounts` table MUST be introduced with
  columns: id, email (unique index), password_hash (argon2id
  format), status (enum: `pending_verification`, `active`,
  `deleted`), created_at, updated_at, last_login_at. Schema
  details settled in `/speckit.plan`.
- **FR-002**: A new `account_participants` table MUST link
  accounts to participant records. Columns: account_id,
  participant_id (unique). The unique index on participant_id
  enforces a participant belongs to at most one account.
- **FR-003**: Password hashing MUST use argon2id with
  operator-tunable parameters: time cost
  (`SACP_PASSWORD_ARGON2_TIME_COST`, default 2), memory cost
  in KiB (`SACP_PASSWORD_ARGON2_MEMORY_COST_KB`, default
  19456 = 19 MiB), parallelism (hardcoded 1). Parameters MUST
  meet OWASP 2024 password-storage cheat-sheet minimums; an
  operator who lowers parameters below the minimum gets a
  startup warning.
- **FR-004**: Email verification MUST be required before an
  account transitions from `pending_verification` to `active`.
  The verification mechanism is a one-time 16-character base32
  code, single-use, 24-hour TTL.
- **FR-005**: A new endpoint `POST /tools/account/create` MUST
  accept email + password, create a `pending_verification`
  account, hash the password, and emit a verification code.
- **FR-006**: A new endpoint `POST /tools/account/verify` MUST
  accept the verification code and flip the account to
  `active` if the code matches and is within TTL.
- **FR-007**: A new endpoint `POST /tools/account/login` MUST
  accept email + password and return HTTP 200 with a session
  cookie on success, HTTP 401 with generic
  `invalid_credentials` on failure, HTTP 429 on rate-limit.
  The successful response body is minimal (auth-state
  confirmation only); the session list is NOT inlined into
  the login response. The SPA MUST follow up with a separate
  `GET /me/sessions` call to retrieve the session list
  (two-trip flow). This keeps `/me/sessions` independently
  paginable and avoids inflating login responses with
  potentially large session arrays. (Resolved 2026-05-09.)
- **FR-008**: A new endpoint `GET /me/sessions` MUST return the
  authenticated account's session list segmented as
  `active_sessions` and `archived_sessions`, ordered by
  last-activity-at descending within each segment, paginated
  at 50 entries per page with offset-based navigation.
  Pagination MUST be per segment (an offset/limit pair applies
  within `active_sessions` OR within `archived_sessions`,
  NOT across the combined list). When an account's joined-
  session count exceeds 10,000, a warning MUST be logged at
  query time AND an `admin_audit_log` row MUST be emitted
  recording the cursor-migration threshold trip; cursor
  pagination itself remains a backlog item, NOT a v1
  deliverable. (Resolved 2026-05-09.)
- **FR-009**: `/me/sessions` MUST scope strictly to the
  authenticated account — no session belonging to another
  account MUST appear.
- **FR-010**: A new endpoint `POST /tools/account/email/change`
  MUST emit a verification code to the NEW email AND
  simultaneously emit a heads-up notification to the OLD email
  (no action required from the recipient of the old-email
  notification; informational only). The email field MUST NOT
  update until the verification code is submitted via
  `POST /tools/account/email/verify`. Notifying both
  addresses defends against email-takeover attacks where the
  attacker controls only the new email. (Resolved
  2026-05-09.)
- **FR-011**: A new endpoint `POST /tools/account/password/change`
  MUST require the current password and store the new password
  as an argon2id hash on success. On a successful change, the
  orchestrator MUST invalidate every `SessionStore` sid
  associated with the account_id EXCEPT the actor's current
  authenticated sid (the session driving the change survives;
  all other sessions for that account — additional browser
  tabs, other devices — are forced to re-authenticate). The
  current sid is preserved so the actor is not logged out of
  their own request flow. (Resolved 2026-05-09.)
- **FR-012**: A new endpoint `POST /tools/account/delete` MUST
  emit an automated debug-export (spec 010 format) to the
  registered email containing every session the account
  joined; zero the email + password fields; flip status to
  `deleted`. The account row MUST remain (no DELETE) to
  preserve participant-audit linkage. **[RESIDUAL]** FR-012's
  email payload is currently a placeholder pending the
  email-transport implementation (deferred per 023-F1 V16
  fix-in-progress); the call site fires correctly, the payload
  content is finalized when transport ships.
- **FR-013**: A grace period after account deletion MUST
  reserve the email; new account creation with the same email
  is rejected during the grace window. After the window, the
  email is releasable for re-registration. The grace period
  is governed by `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`
  (default `7`, valid range `[0, 365]`); the value `0`
  disables the grace period entirely (immediate email
  release). (Resolved 2026-05-09.)
- **FR-014**: All account-related endpoints MUST scrub
  password material, verification codes, and reset codes from
  log output (cross-ref spec 007 §FR-012 ScrubFilter).
- **FR-015**: A pre-authentication per-IP rate limiter MUST
  apply to `/tools/account/login` and
  `/tools/account/create`. The limit is governed by
  `SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN` (default 10).
  Limit exceedance returns HTTP 429 with `Retry-After`.
  This limiter is SEPARATE from spec 019's general per-IP
  network-layer rate limiter; both apply additively.
- **FR-016**: The session cookie issued on login MUST follow
  spec 011's existing opaque-sid + server-side `SessionStore`
  shape. The `SessionStore` MUST be extended (not replaced)
  to map `account_id` to the account's set of session
  bindings.
- **FR-017**: Account login MUST issue a session cookie with
  TTL governed by `SACP_ACCOUNT_SESSION_TTL_HOURS` (default
  168 = 7 days). After expiry, re-login is required.
- **FR-018**: The master switch `SACP_ACCOUNTS_ENABLED` MUST
  gate the entire account surface. When `false` (default),
  the account endpoints return HTTP 404 and the SPA falls
  back to the existing token-paste landing.
- **FR-019**: All account-creating, account-modifying, and
  account-deleting actions MUST emit `admin_audit_log`
  rows with actor, target account, action name, and
  timestamp. No password hash, code, or other secret MUST
  appear in the log content.
- **FR-020**: An ownership-transfer endpoint
  (`POST /tools/admin/account/transfer_participants`) MUST
  exist for deployment-owner-authenticated callers only.
  Transfer repoints `account_participants` rows from source
  to target; tokens remain valid (transfer moves ownership
  pointer only, not the per-session credential).
  **Decision checkpoint**: `/speckit.plan` decides whether
  FR-020 ships in the v1 implementation or splits into a
  follow-up amendment. The user's brief defers to Phase 4
  federation if the v1 implementation surface (deployment-
  owner-auth model, participant-row repointing path, admin-
  surface authorization split) does not fit cleanly within
  v1 scope. Pre-deferring at clarify is rejected; plan
  phase produces the implementation surface needed to make
  the in-or-defer call with full information. (Resolved
  2026-05-09.)
- **FR-021**: The OAuth migration surface (a future spec)
  MUST be kept open by hashing-and-credential plug-ability:
  the password-hash column is annotated with the hash format
  (argon2id today; OAuth providers later) so future
  alternatives slot in without schema change.
- **FR-022**: The seven new env vars (`SACP_ACCOUNTS_ENABLED`,
  `SACP_PASSWORD_ARGON2_TIME_COST`,
  `SACP_PASSWORD_ARGON2_MEMORY_COST_KB`,
  `SACP_ACCOUNT_SESSION_TTL_HOURS`,
  `SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN`,
  `SACP_EMAIL_TRANSPORT`,
  `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`) MUST have
  validator functions in `src/config/validators.py` registered
  in the `VALIDATORS` tuple, AND corresponding sections in
  `docs/env-vars.md` with the six standard fields, BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable
  gate). A startup WARNING (NOT a fail-closed exit) MUST be
  emitted when `SACP_ACCOUNTS_ENABLED=true` AND
  `SACP_EMAIL_TRANSPORT=noop` simultaneously, naming the
  consequence (verification, reset, and notification codes
  appear in `admin_audit_log` only; not suitable for
  production). (Resolved 2026-05-09.)

### Key Entities

- **Account** — `accounts` table row. Owns zero or more
  participant records via `account_participants`.
  Single-tenant per deployment.
- **AccountParticipant** — `account_participants` join row
  binding an account to a per-session participant. Unique
  on `participant_id`.
- **VerificationCode** (transient) — single-use 16-char
  base32 string with TTL. Persisted in `admin_audit_log`
  on emission; consumed by submission. Not stored as a
  durable entity.
- **PasswordHash** — argon2id-formatted hash string including
  parameters used at hash time. Format: standard argon2
  encoded form (`$argon2id$v=19$m=...,t=...,p=...$<salt>$<hash>`).
- **SessionStore (extended)** — spec 011's opaque-sid mapping
  is extended to include an `account_id` field for
  authenticated-account state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Account creation, verification, and login flow
  end-to-end MUST complete in under 1s on a development
  hardware baseline (verified by an integration test driving
  the full sequence and asserting wall-clock time).
- **SC-002**: Login P95 ≤ 500ms with the default argon2id
  parameters. Operators tightening parameters (higher time /
  memory cost) accept a higher latency floor; the budget is
  measured at default parameters.
- **SC-003**: `/me/sessions` P95 ≤ 200ms for an account with
  up to 1,000 joined sessions. Verified by a synthetic-load
  test seeding the account with 1,000 participant rows.
- **SC-004**: Cross-account isolation MUST be verified by a
  test where two accounts each join distinct sessions and
  each account's `/me/sessions` returns only their own
  sessions.
- **SC-005**: A login attempt with non-existent email and a
  login attempt with existing email + wrong password MUST
  produce identical responses (HTTP 401 + generic
  `invalid_credentials` body + identical timing within
  ±5ms). Verified by a timing-comparison test.
- **SC-006**: Per-IP login rate limit MUST trip at the
  configured threshold and return HTTP 429 with
  `Retry-After`. Verified by a synthetic-load test that
  drives the limiter past its threshold.
- **SC-007**: Argon2id parameter increase between releases
  MUST trigger transparent re-hash on next login; verified
  by a test that seeds an account with a low-parameter hash
  and asserts the post-login hash uses the new parameters.
- **SC-008**: Account deletion MUST emit a debug-export to
  the registered email AND zero the password hash + email
  fields. Verified by an end-to-end test asserting the
  email transport received the export and the row's
  credential fields are nulls.
- **SC-009**: Email re-registration during the configured
  grace window (governed by
  `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`, default `7`)
  MUST be rejected. Verified by deleting an account,
  attempting re-registration on day 1, asserting rejection;
  advancing test clock past the configured window,
  asserting acceptance. The test reads the env-var value
  rather than hardcoding 7 days.
- **SC-010**: Ownership-transfer attempt by a non-deployment-
  owner MUST return HTTP 403. Verified by a test driving the
  endpoint with a regular-account session.
- **SC-011**: With any of the seven new env vars set to an
  invalid value, the orchestrator process MUST exit at
  startup with a clear error message naming the offending
  var (V16 fail-closed gate observed in CI). The
  `SACP_ACCOUNTS_ENABLED=true` AND
  `SACP_EMAIL_TRANSPORT=noop` cross-condition emits a
  startup WARNING but MUST NOT exit.
- **SC-012**: ScrubFilter coverage MUST be verified for the
  account surface — a test drives login + create + change-
  password and asserts the password material, verification
  codes, and reset codes do NOT appear in any log line.

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** (orchestrator-driven
topologies). The account store is centralized at the
orchestrator; accounts authenticate against the orchestrator's
auth surface; session list is computed at the orchestrator from
the orchestrator's database. All require a single orchestrator
to be the identity authority.

This feature is **NOT applicable to topology 7 (MCP-to-MCP,
Phase 3+)**. In topology 7 each participant's MCP client is the
identity boundary; there is no orchestrator-side account store.
Per V12: any topology-7 deployment MUST recognize that this
spec's account surface does not apply.

### V13 — Use Case Coverage

This feature serves the V13 primary use cases:

- §2 Research Paper Co-authorship
  (`docs/sacp-use-cases.md` §2) — research sessions run
  asynchronously over weeks; a co-author returns days later
  via login rather than reconstructing token state.
- §3 Consulting Engagement
  (`docs/sacp-use-cases.md` §3) — consultants run multiple
  concurrent engagements; the post-login session list
  consolidates their engagement view.
- §6 Decision-Making Under Asymmetric Expertise
  (`docs/sacp-use-cases.md` §6) — experts return repeatedly
  to advisory sessions; persistent identity makes the
  engagement durable.

Other use cases (§1, §4, §5, §7) inherit the feature when
enabled but are not the priority drivers.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts.
This spec contributes four budgets:

- **Login P95**: ≤ 500ms with default argon2id parameters
  (`time_cost=2, memory_kb=19456`). Operators tightening
  parameters accept a higher latency floor; the budget is
  measured at defaults.
- **`/me/sessions` P95**: ≤ 200ms for accounts with up to
  1,000 joined sessions. The query is a single JOIN over
  `account_participants` + `participants` + `sessions`
  filtered by `account_id` (indexed). Pagination at 50/page.
- **Account creation P95**: ≤ 1s end-to-end including
  argon2id hash + email transport adapter call. The hash
  cost dominates; operators tightening parameters accept a
  higher latency floor here too.
- **Per-IP login rate limiter check**: O(1) on the steady-
  state path (matches spec 009 §FR-011's per-check cost
  shape since this limiter follows the same sliding-window
  algorithm).

## Configuration (V16) — New Env Vars

Seven new env vars are introduced (resolved 2026-05-09; was
five at draft, two added by the clarify session: email
transport adapter and deletion-grace tunable). Each MUST have
type, valid range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this
spec (per V16 deliverable gate).

### `SACP_ACCOUNTS_ENABLED`

- **Intended type**: boolean
- **Intended valid range**: `true` | `false`. Default
  `false` (master switch ships off; operators opt in).
- **Fail-closed semantics**: any non-parseable value MUST
  cause startup exit. When `false` the account endpoints
  return HTTP 404 and the SPA falls back to the existing
  token-paste landing.

### `SACP_PASSWORD_ARGON2_TIME_COST`

- **Intended type**: positive integer
- **Intended valid range**: `[1, 10]` per OWASP 2024
  recommendation envelope. Default `2`. Below `1` is
  cryptographically inadequate; above `10` introduces
  unacceptable login latency on commodity hardware.
- **Fail-closed semantics**: outside the range MUST cause
  startup exit. Below the OWASP minimum (`1`) MUST emit a
  startup WARNING; below it AND above the documented
  insecure-floor MUST be rejected outright.

### `SACP_PASSWORD_ARGON2_MEMORY_COST_KB`

- **Intended type**: positive integer (kilobytes)
- **Intended valid range**: `[7168, 1048576]` (7 MiB to
  1 GiB). Default `19456` (19 MiB) per OWASP 2024
  password-storage cheat sheet. Below the floor produces
  a startup error; above the ceiling produces a startup
  warning (memory exhaustion risk on small instances).
- **Fail-closed semantics**: outside the range MUST cause
  startup exit.

### `SACP_ACCOUNT_SESSION_TTL_HOURS`

- **Intended type**: positive integer
- **Intended valid range**: `[1, 8760]` (1 hour to 1 year).
  Default `168` (7 days).
- **Fail-closed semantics**: outside the range MUST cause
  startup exit.

### `SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN`

- **Intended type**: positive integer
- **Intended valid range**: `[1, 1000]` login attempts per
  IP per minute. Default `10`. Below `1` disables the
  limiter (rejected); above `1000` is high enough that the
  limiter is essentially absent.
- **Fail-closed semantics**: outside the range MUST cause
  startup exit. The limiter applies to `/login` and
  `/create-account` endpoints; it composes additively with
  spec 019's general per-IP network-layer rate limiter.

### `SACP_EMAIL_TRANSPORT`

- **Intended type**: string enum
- **Intended valid range**: one of `noop`, `smtp`, `ses`,
  `sendgrid`. Default `noop` (development-friendly; codes
  appear in `admin_audit_log` only). Operators configure a
  real transport for production deployments.
- **Fail-closed semantics**: any non-enumerated value MUST
  cause startup exit. When `SACP_ACCOUNTS_ENABLED=true` AND
  `SACP_EMAIL_TRANSPORT=noop`, the orchestrator MUST emit a
  startup WARNING (NOT an exit) naming the consequence.
  Operators legitimately run dev/staging with noop transport;
  the warning catches the obvious production misconfiguration
  without blocking valid dev flows. (Added 2026-05-09 per
  clarify session.)

### `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`

- **Intended type**: non-negative integer
- **Intended valid range**: `[0, 365]` days. Default `7`.
  The value `0` disables the grace period entirely
  (immediate email release on deletion); the value `365`
  caps the maximum reservation window at one year.
  Operators with stricter or looser retention policies
  tune this knob.
- **Fail-closed semantics**: outside the range MUST cause
  startup exit. (Added 2026-05-09 per clarify session.)

## Cross-References to Existing Specs and Design Docs

- **Spec 002 (participant-auth)** — the per-session bearer
  token model. Spec 023 layers ABOVE 002, NOT replacing it:
  the token still gates per-session participant lifecycle
  (approval, rotation per §FR-007, departure per §FR-016).
  The account binds tokens via `account_participants`. The
  Art. 17 erasure carve-out (002 §FR-016 / 001 §FR-019)
  applies to participant rows owned by deleted accounts.
- **Spec 011 (web-ui)** — login/logout UI, post-login
  session list menu, account-settings panel. The
  `SessionStore` (spec 011 H-02 fix) is extended (FR-016)
  to hold account-authenticated state. A spec 011 amendment
  lands when 023 reaches Status: Implemented.
- **Spec 019 (network-rate-limiting)** — pre-authentication
  per-IP rate limiting at the orchestrator's HTTP boundary.
  Spec 023's `SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN` is a
  separate, tighter limiter applied at `/login` and
  `/create-account`; both apply additively (FR-015).
- **Spec 007 (ai-security-pipeline) §FR-012** — the
  ScrubFilter that scrubs credentials, codes, and tokens
  from log output. Spec 023 extends scrubbing coverage to
  account-related fields (FR-014).
- **Spec 010 (debug-export)** — the export shape used by
  account deletion's data-portability emit (FR-012).
  Re-uses the existing endpoint via internal call rather
  than a new export shape.
- **Spec 001 (core-data-model) §FR-019** — the
  `admin_audit_log` carve-out (Art. 17(3)(b)) applies to
  account-action audit rows: deletion of an account does
  NOT remove the audit-log entries about that account's
  actions.
- **Spec 009 (rate-limiting)** — the sliding-window
  algorithm and 429 + Retry-After response shape that
  spec 023's per-IP login limiter follows.
- **Spec 014 (dynamic-mode-assignment)** — NOT
  spec 014's actual scope; user input's reference to
  "spec 014's auth migration" is interpreted as the
  Phase 3 OAuth roadmap (Constitution §10), a separate
  future spec.
- **Spec 024 (facilitator scratch, future)** — pairs with
  this spec. Scratch notes attach to an account; spec 024
  assumes 023 is implemented.
- **Constitution §10** — Phase 3 deliverables list,
  including "OAuth 2.1 with PKCE replaces static tokens."
  Spec 023 is the email + password v1; OAuth is a future
  follow-up that slots in via FR-021's hash-and-credential
  pluggability.
- **Constitution §14.1** — Feature work workflow. This spec
  scaffolds via `/speckit.specify`; subsequent
  `/speckit.clarify`, `/speckit.plan`, and
  `/speckit.tasks` are deferred.
- **Constitution V12** — topology applicability. Spec 023
  applies to topologies 1-6; incompatible with topology 7.
- **Constitution V13** — primary use cases research
  co-authorship (§2), consulting (§3), decision-making
  under asymmetric expertise (§6).
- **Constitution V14** — per-stage timing budgets. Spec 023
  contributes four budgets (Performance Budgets section).
- **Constitution V16** — env-var validation at startup.
  Spec 023 introduces five new vars (Configuration section).
- **OWASP 2024 Password Storage Cheat Sheet** — argon2id
  parameter floor (memory ≥ 19 MiB, time cost ≥ 2,
  parallelism = 1) that FR-003 enforces.

## Assumptions

- The argon2id parameter defaults (time_cost=2,
  memory_kb=19456) reflect OWASP 2024 password-storage
  cheat-sheet minimums for general web-application
  password hashing. Operators on constrained hardware may
  lower below the recommended floor with a startup warning;
  operators on high-throughput deployments should raise the
  parameters once they have a hardware envelope.
- The OAuth migration is a separate future spec, NOT
  in-scope here. v1 ships email + password; the
  hash-and-credential pluggability (FR-021) keeps the OAuth
  surface achievable without schema change.
- Single-tenant-per-deployment is the v1 boundary, matching
  spec 011 Phase D clarification. Multi-tenant + cross-
  account discovery is Phase 4+ federation scope.
- Email transport is a noop adapter by default (resolved
  2026-05-09; `SACP_EMAIL_TRANSPORT` is now in the V16
  env-var list with valid range `noop|smtp|ses|sendgrid`).
  Operators configure SMTP/SES/SendGrid via the adapter for
  production. A startup WARNING fires when accounts are
  enabled AND transport is noop simultaneously.
- Account deletion preserves the `accounts` row to retain
  the FK target for participant-audit linkage. Only the
  email + password_hash fields are zeroed. Art. 17 erasure
  is fulfilled at the credential layer; the audit-log
  carve-out (Art. 17(3)(b)) keeps the participation record.
- The 7-day email-grace period after deletion is a pragmatic
  default but is operator-tunable in v1 via the new env var
  `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS` (resolved
  2026-05-09). The `0` value disables the grace period
  entirely; the upper bound is `365` days.
- Spec 023 is Phase 3+ scope, NOT a Phase 3 prerequisite.
  Active Phase 3 work (013-022) does not depend on 023. It
  IS a prerequisite for spec 024 facilitator scratch — that
  spec assumes 023 is in place.
- Phase 3 declared 2026-05-05 enables but does not gate
  this spec's status flip; the user's call per
  `feedback_dont_declare_phase_done.md`. This spec stays
  scaffold-only until tasks are scheduled.
- Status remains Draft until clarifications resolve and
  the user accepts the scaffolding.
