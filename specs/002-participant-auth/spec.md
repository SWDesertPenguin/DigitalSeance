# Feature Specification: Participant Auth & Lifecycle

**Feature Branch**: `002-participant-auth`
**Created**: 2026-04-11
**Status**: Draft
**Input**: User description: "Auth and participant lifecycle — token validation, approval flow, rotation, revocation, facilitator transfer, session binding for SACP Phase 1"

## Clarifications

### Session 2026-04-14

- Q: Pending participant access scope? → A: Facilitator decides per session (configurable: transcript-only, transcript+list, minimal, or full observer)
- Q: Facilitator token expiry recovery path? → A: Dedicated CLI tool (sacp-admin regenerate-token <session-id>) with audit logging

### Session 2026-04-15

- Q: How do we prevent the Swagger default `"string"` literal from being persisted as a real model/provider name? → A: `_AddParticipantBody` rejects blank, whitespace-only, or case-insensitively equal to `"string"` values on `display_name`, `provider`, `model`, `model_tier`, `model_family` at validation time (HTTP 422). The provider dispatcher never sees invalid values, and `Turn -1` failure cycles caused by placeholder-model participants are eliminated.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Token Authentication (Priority: P1)

A participant connects to the orchestrator by presenting a bearer token. The system validates the token against the stored hash, checks that it hasn't expired, and either grants access to the session or rejects the request with a clear error. Invalid, expired, or missing tokens are always rejected — the system never falls through to an unauthenticated state.

**Why this priority**: Nothing else works without authentication. Every subsequent story depends on knowing who the caller is and whether they're authorized.

**Independent Test**: Can be tested by presenting valid, invalid, and expired tokens and verifying the system accepts or rejects each correctly.

**Acceptance Scenarios**:

1. **Given** a participant with a valid, non-expired token, **When** they present the token, **Then** they are authenticated and granted access to their session.
2. **Given** a participant with an expired token, **When** they present the token, **Then** access is denied with a clear "token expired" indication.
3. **Given** an unknown or invalid token, **When** it is presented, **Then** access is denied with a clear "invalid token" indication.
4. **Given** a request with no token, **When** it arrives, **Then** access is denied with a clear "authentication required" indication.
5. **Given** a valid token, **When** it is validated, **Then** the token plaintext never appears in any log output.

---

### User Story 2 - Participant Approval Flow (Priority: P1)

When a new participant redeems an invite and joins a session, they start as "pending" — they can see the conversation transcript but cannot inject messages and their AI is not in the loop. The facilitator reviews and either approves (promoting them to full participant) or rejects (removing them). When auto-approve is enabled on a session, this manual step is skipped.

**Why this priority**: The join flow is how participants enter sessions. Without approval logic, pending participants are stuck and can never participate.

**Independent Test**: Can be tested by creating a pending participant via invite redemption, then approving or rejecting them and verifying role changes, timestamps, and audit log entries.

**Acceptance Scenarios**:

1. **Given** a pending participant, **When** the facilitator approves them, **Then** their role changes to 'participant', their approved_at timestamp is set, and the action is logged to the admin audit log.
2. **Given** a pending participant, **When** the facilitator rejects them, **Then** their record is removed, and the rejection is logged with the reason.
3. **Given** a session with auto-approve enabled, **When** a participant redeems an invite, **Then** they are immediately set to role 'participant' without manual approval.
4. **Given** an approved participant, **When** they connect, **Then** their AI enters the conversation loop and they can inject messages.
5. **Given** a pending participant, **When** they attempt to inject a message, **Then** the injection is rejected.

---

### User Story 3 - Token Rotation (Priority: P2)

A participant can rotate their own token at any time. The system generates a new token, immediately invalidates the old one, and returns the new token plaintext exactly once. The participant must use the new token for all subsequent connections. Token rotation does not require facilitator involvement.

**Why this priority**: Token rotation is a basic security hygiene operation. Participants need it to recover from potential token exposure without involving the facilitator.

**Independent Test**: Can be tested by rotating a participant's token and verifying the old token is rejected, the new token works, and the rotation is logged.

**Acceptance Scenarios**:

1. **Given** an authenticated participant, **When** they rotate their token, **Then** a new token is generated and the plaintext is returned once.
2. **Given** a rotated token, **When** the participant uses the old token, **Then** access is denied.
3. **Given** a rotated token, **When** the participant uses the new token, **Then** they are authenticated normally.
4. **Given** a token rotation, **When** it completes, **Then** the new token expiry is reset to the configured period from the rotation time.

---

### User Story 4 - Token Revocation by Facilitator (Priority: P2)

The facilitator can force-revoke any participant's token. This immediately invalidates the token and disconnects the participant from all active connections. The participant cannot reconnect until they receive a new token. The revocation is logged to the admin audit log.

**Why this priority**: Facilitators need the ability to immediately cut off access when a participant's token is compromised or when they need to enforce session policy.

**Independent Test**: Can be tested by revoking a participant's token and verifying immediate invalidation, disconnection, and audit logging.

**Acceptance Scenarios**:

1. **Given** an active participant, **When** the facilitator revokes their token, **Then** the old token is immediately invalidated.
2. **Given** a revoked token, **When** the participant attempts to connect, **Then** access is denied.
3. **Given** a token revocation, **When** it completes, **Then** the action is logged to the admin audit log with the facilitator ID and target participant ID.
4. **Given** a non-facilitator, **When** they attempt to revoke another participant's token, **Then** the request is rejected.

---

### User Story 5 - Facilitator-Initiated Participant Removal (Priority: P2)

The facilitator can remove a participant from a session. This extends the existing departure logic (which already handles API key overwrite, token invalidation, and status change) by adding facilitator authorization checks, an optional reason, and audit logging. The facilitator must have the facilitator role; non-facilitators are rejected. The participant's messages remain in the transcript per the existing data model guarantees.

**Why this priority**: Essential for session management — the facilitator must be able to remove disruptive or inactive participants. The underlying data operations exist; this story adds the authorization gate and audit trail.

**Independent Test**: Can be tested by attempting removal as both facilitator and non-facilitator, verifying authorization enforcement, audit log entries with reason, and that the existing departure behavior (key overwrite, token invalidation, offline status) is triggered correctly.

**Acceptance Scenarios**:

1. **Given** an active participant, **When** the facilitator removes them with an optional reason, **Then** the existing departure logic executes (key overwritten, token invalidated, status offline) and the action is logged to the admin audit log with the reason.
2. **Given** a removed participant, **When** the transcript is queried, **Then** their messages are still present (guaranteed by existing data model).
3. **Given** a non-facilitator, **When** they attempt to remove another participant, **Then** the request is rejected before any data changes occur.
4. **Given** the facilitator themselves, **When** they attempt to remove themselves, **Then** the request is rejected (facilitator must transfer role first).

---

### User Story 6 - Facilitator Transfer (Priority: P3)

The current facilitator can transfer their role to another active participant. The target participant becomes the facilitator and gains admin tools. The original facilitator becomes a regular participant. Only the current facilitator can initiate a transfer, and only active participants can receive it.

**Why this priority**: Important for long-running sessions but not required for initial operation. Sessions can function with the original facilitator until transfer is needed.

**Independent Test**: Can be tested by transferring the facilitator role and verifying both participants' roles change correctly, the session's facilitator reference updates, and the transfer is logged.

**Acceptance Scenarios**:

1. **Given** the current facilitator, **When** they transfer the role to an active participant, **Then** the target becomes facilitator, the original becomes participant, and the session's facilitator reference updates.
2. **Given** a facilitator transfer, **When** it completes, **Then** the action is logged to the admin audit log with both the old and new facilitator IDs.
3. **Given** an active facilitator, **When** they attempt to transfer to a pending participant, **Then** the transfer is rejected.
4. **Given** a non-facilitator, **When** they attempt to transfer the facilitator role, **Then** the request is rejected.

---

### User Story 7 - Token Expiry Enforcement (Priority: P3)

Tokens have a configurable expiry period (default 30 days from creation or last rotation). The system tracks the expiry timestamp and rejects authentication attempts with expired tokens. Participants with expired tokens must obtain a new token from the facilitator or rotate before expiry.

**Why this priority**: Expiry is a defense-in-depth measure. The system works without it (tokens are manually managed), but expiry limits the window of exposure for compromised tokens.

**Independent Test**: Can be tested by creating tokens with short expiry periods and verifying they are rejected after expiration.

**Acceptance Scenarios**:

1. **Given** a token with a configured expiry, **When** the expiry time passes, **Then** the token is rejected on the next authentication attempt.
2. **Given** a token that has not expired, **When** it is presented, **Then** authentication proceeds normally.
3. **Given** a participant whose token has expired, **When** they attempt to connect, **Then** they receive a clear "token expired" indication distinct from "invalid token".
4. **Given** a token rotation, **When** a new token is generated, **Then** the expiry is reset to the configured period from the rotation time.

---

### User Story 8 - Session Binding via Client IP (Priority: P2)

When a participant authenticates, the system captures their client IP address and binds the authenticated session to that IP. Subsequent requests from the same token but a different IP are rejected. This prevents token theft from being exploitable from a different network location. The binding is reset on token rotation.

**Why this priority**: Defense-in-depth for token security. Without IP binding, a stolen token can be used from anywhere. With it, the attacker must also be on the same network.

**Independent Test**: Can be tested by authenticating from one IP, then attempting to use the same token from a different IP and verifying rejection.

**Acceptance Scenarios**:

1. **Given** a participant authenticates from IP address A, **When** they make subsequent requests from IP A, **Then** the requests are accepted.
2. **Given** a participant authenticated from IP A, **When** a request arrives with the same token from IP B, **Then** the request is rejected with a clear "session binding mismatch" indication.
3. **Given** a participant who has rotated their token, **When** they authenticate with the new token from a different IP, **Then** the binding is reset to the new IP.
4. **Given** a participant behind a known proxy or load balancer, **When** the system reads the client IP, **Then** it uses the forwarded-for header if configured to trust the proxy.

---

### Edge Cases

- What happens when the facilitator's own token expires? They lose access like any other participant. Another participant with a valid token cannot help — a new token must be generated outside the system (direct database access or CLI tool).
- What happens when the only remaining participant is removed? The session becomes empty but remains in its current status (active/paused). No automatic archival.
- What happens when a facilitator transfer targets a participant who has been removed between the request and execution? The transfer is rejected because the target is offline, not active.
- What happens when two concurrent token rotations are requested? One succeeds and the other fails because the old hash no longer matches. The participant retries with the new token.
- What happens when a token is revoked during an active turn? The current turn completes (AI response already in flight), but the next turn skips the revoked participant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST validate bearer tokens against stored hashes before granting access to any session operation.
- **FR-002**: System MUST reject expired tokens with a distinct error distinguishable from invalid tokens.
- **FR-003**: System MUST reject requests with missing or malformed tokens with a clear authentication-required error.
- **FR-004**: System MUST never log token plaintext in any output path including error traces.
- **FR-005**: System MUST support promoting a pending participant to full participant role upon facilitator approval.
- **FR-006**: System MUST support rejecting a pending participant, removing their record and logging the reason.
- **FR-007**: System MUST support session-level auto-approve mode that bypasses manual facilitator approval.
- **FR-008**: System MUST allow participants to rotate their own token, generating a new token and immediately invalidating the old one.
- **FR-009**: System MUST allow facilitators to revoke any participant's token, immediately invalidating it.
- **FR-010**: System MUST restrict facilitator-only operations (approve, reject, remove, revoke, transfer) to participants with the facilitator role.
- **FR-011**: System MUST support facilitator role transfer to another active participant, updating both participants' roles and the session's facilitator reference atomically.
- **FR-012**: System MUST track token expiry timestamps and enforce rejection of expired tokens.
- **FR-013**: System MUST reset token expiry on rotation to the configured period from the rotation time.
- **FR-014**: System MUST log all facilitator actions (approval, rejection, removal, revocation, transfer) to the admin audit log with actor, target, and timestamp.
- **FR-015**: System MUST prevent pending participants from injecting messages or having their AI participate in the conversation loop.
- **FR-016**: System MUST capture the client IP at first authentication and bind subsequent requests to that IP for the token's lifetime.
- **FR-017**: System MUST reject requests where the token is valid but the client IP does not match the bound IP, with a distinct error.
- **FR-018**: System MUST reset the IP binding when a token is rotated, allowing the new token to bind to a new IP.
- **FR-019**: System MUST prevent the facilitator from removing themselves (must transfer role first).
- **FR-020**: Pending participant access scope MUST be configurable per session by the facilitator. The facilitator chooses what pending participants can observe (transcript only, transcript + participant list, full live observer, or minimal pre-join view).

### Key Entities

- **Auth Token**: A bearer credential presented by participants. Stored as an irreversible hash. Has a configurable expiry period. Can be rotated by the participant or revoked by the facilitator.
- **Participant Role**: One of facilitator, participant, or pending. Determines access level. Facilitator is transferable. Pending restricts to read-only transcript access.
- **Admin Audit Log Entry**: Immutable record of facilitator actions — approval, rejection, removal, revocation, transfer — with actor, target, and timestamp.
- **Token Expiry**: A timestamp tracking when a token becomes invalid. Reset on rotation. Default period is 30 days.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Valid tokens authenticate successfully within 1 second under normal load.
- **SC-002**: Invalid or expired tokens are rejected within 1 second with a clear, distinct error for each case.
- **SC-003**: Token rotation completes atomically — no window where both old and new tokens are simultaneously valid.
- **SC-004**: 100% of facilitator actions (approve, reject, remove, revoke, transfer) are recorded in the admin audit log.
- **SC-005**: Pending participants have zero ability to inject messages or trigger AI responses.
- **SC-006**: Facilitator-only operations are rejected 100% of the time when attempted by non-facilitators.
- **SC-007**: Token plaintext never appears in any log output, error trace, or persisted record.

## Assumptions

- Phase 1 uses static bearer tokens with bcrypt hashing. OAuth 2.1 with PKCE replaces this in Phase 3 (constitution §6.6).
- Token expiry defaults to 30 days. This is configurable per deployment, not per participant.
- The data model (participants table, admin_audit_log, invites) already exists from feature 001. This feature adds auth logic, not schema — except for the `token_expires_at` timestamp field which requires a schema migration.
- Active connection tracking and forced disconnection (for revocation/removal) depend on the MCP server layer. This feature defines the auth contract; the MCP server feature implements connection management.
- The facilitator's token is generated at session creation time. If it expires, recovery is handled via a dedicated CLI tool (`sacp-admin regenerate-token <session-id>`) which generates a new token, updates the hash, and emits an admin audit log entry. Direct database operations are discouraged because they bypass the audit trail.
- Token rotation generates a new random token using cryptographically secure random bytes, not a derivation of the old token.
- Bcrypt cost factor 12 (default) is used for all token hashing. This is not configurable in Phase 1.

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): All seven (1–7). Token validation, role enforcement, and IP binding apply uniformly whether the orchestrator dispatches turns (1–6) or peers run client-side (7). Auth boundaries are topology-independent.

**Use cases** (per constitution §1): Foundational — all seven use cases depend on this. Participant sovereignty (token isolation, role separation, facilitator transfer) is a prerequisite for every scenario, especially zero-trust cross-org.
