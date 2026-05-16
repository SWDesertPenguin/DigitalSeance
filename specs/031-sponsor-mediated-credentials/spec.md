<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Feature Specification: Sponsor-Mediated Credential Sovereignty (Theme A)

**Feature Branch**: `031-sponsor-mediated-credentials`
**Created**: 2026-05-16
**Status**: PROPOSED (scaffold; not yet promoted via `/speckit.plan`)
**Depends-on**: spec 002 (participant-auth  --  sponsor / `invited_by` model), spec 023 (user-accounts  --  identity-persistence layer above the per-session token), spec 028 (capcom-routing-scope  --  visibility partitioning, relevant to the debug.export consent flow), spec 030 (mcp-build  --  MCP dispatcher and `scope_grant._SOVEREIGNTY_EXCLUSIONS` enforcement site)
**Amends**: spec 011 (web-ui) Section FR-016  --  the facilitator admin panel's `set_budget` and `reset_ai_credentials` references narrow to the sponsor-mediated path with the consent flow for facilitator-initiated changes
**Input**: User description: "Theme A from the facilitator-sovereignty endpoint inventory (Stage 2, Proposed Remediation Scope). Establish a hard rule: API keys, budget caps, max_tokens_per_turn, and api_endpoint changes require either (a) caller is the AI's `invited_by` sponsor, or (b) a two-party consent flow (sponsor + facilitator co-sign). The facilitator role retains session-control authority (pause / resume / archive / routing / acceptance mode / cadence / length cap / register slider / review-gate) but loses unilateral wallet authority over sponsored AIs. Wire the existing `_SOVEREIGNTY_EXCLUSIONS` constant from documentation to enforcement in the MCP dispatcher. Add a `credential_change_consents` table, three new audit actions, one new env var for the consent TTL, and a parallel `debug_export_consent_for_sponsor` mechanism for the per-participant wallet/usage fields in `debug.export`."

## Overview

The orchestrator's per-session participant model treats any caller with `role='facilitator'` as authorized to mutate any AI participant's wallet-bearing fields  --  API key (`reset_ai_credentials`), spend caps and per-turn token ceiling (`set_budget`), provider endpoint, and slot lifecycle (`release_ai_slot`). Today's check `_require_facilitator_or_inviter` admits the facilitator branch unconditionally; sponsorship is checked only on the inviter branch. The facilitator-sovereignty endpoint inventory enumerated five HTTP / MCP entry points where this pattern lets a facilitator override an AI's credentials regardless of who invited the AI, plus the dead-code `_SOVEREIGNTY_EXCLUSIONS` dictionary in `src/mcp_protocol/auth/scope_grant.py` that documents the intent but is never read.

Constitution Section 3 names budget autonomy and prompt privacy as sovereignty primitives the facilitator cannot reach. The implementation has drifted: a session-conductor role gained custodian-of-the-wallet authority over every AI in the session. This spec corrects the drift by establishing two paths for credential-bearing mutations on a sponsored AI:

1. **Direct sponsor path.** The AI's `invited_by` participant (the sponsor) mutates the AI's credentials directly. No consent flow; the sponsor IS the human authority for their AI. This is the sovereignty-correct shape that already worked on the inviter branch of the existing check.
2. **Two-party consent path.** A facilitator requests a credential-bearing change via a new endpoint; the request lands as a `credential_change_consents` row with a TTL; the AI's sponsor co-signs from their own UI; the consent row is consumed by a follow-up call that performs the actual mutation; the audit log links the mutation row to the consent row by `consent_id`. The facilitator never holds unilateral wallet authority; the sponsor's co-signature is the gate.

The facilitator role retains every session-control capability it has today  --  pause, resume, archive, routing-preference setting at the session level, acceptance mode, cadence preset, length cap, register slider, review-gate approval/rejection/edit, CAPCOM assignment, summarization triggers. The line drawn is **session control vs. wallet authority**: facilitator may run the session, but may not unilaterally rewrite a sponsored AI's wallet primitives.

The MCP-side enforcement work converts the documented-but-dead `_SOVEREIGNTY_EXCLUSIONS` constant into live policy. The dispatcher's `_check_authorization` reads the constant and refuses the corresponding tool names when invoked under a `scopeRequirement="facilitator"` JWT; the caller must present a `scopeRequirement="sponsor"` JWT (caller matches the AI's `invited_by`) OR an unconsumed `credential_change_consents` row matching the (facilitator, AI, field) tuple.

The debug.export consent flow extends the same pattern. Today's facilitator-only `/tools/debug/export` returns `usage_log` rows and per-participant spend totals for every AI in the session including ones the facilitator did not invite (Theme B in the inventory). Spec 031 reuses the `credential_change_consents` shape with `requested_field='debug_export'` so a facilitator running an `include_sponsored=true` export must collect a fresh consent row from each AI's sponsor before the per-participant wallet/usage fields surface. The aggregate session-level spend (sum across all participants, no per-participant breakdown) remains unconditionally facilitator-readable for cost-control reasons  --  Theme B's Default Behavior fix is scoped here.

This spec is the structural answer to Theme A of the inventory; Themes B (default behavior of `debug.export`), C (`debug_set_timeouts` one-line role guard), D (cross-session enumeration), E (`/tools/session/export_*` visibility filter), F (`/metrics` auth), and G (`provider.test_credentials` consent boundary) are separate work items. Theme B's `debug_export_consent_for_sponsor` mechanism IS in spec 031 scope because it reuses the consent table shape; the rest of Theme B's surgical fixes are Themes-B-and-C work landed on branch `sacp/facilitator-sovereignty-themes-b-c-v1` (commit `61e3b94`).

This spec applies to topologies 1-6 (orchestrator-mediated authorization). Topology 7 (MCP-to-MCP peer) is NOT applicable: there is no central orchestrator to host the consent table or enforce dispatcher-side authorization. Topology 7 deployments will need their own sovereignty model when federation work scopes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sponsor rotates their own AI's API key directly (Priority: P1)

**As a** human participant who invited an AI into the session, **I want** to rotate that AI's API key without any consent dance **so that** I can swap to a different provider account immediately when my current key is depleted or compromised.

**Why this priority**: The sovereignty-correct shape that already works on the inviter branch of `_require_facilitator_or_inviter`. Without it, the consent-flow path has nothing to compare against  --  every sponsor rotation would route through the facilitator surface, inverting the authority model.

**Independent Test**: Spawn a session with facilitator F, sponsor S, AI A (invited_by S). S calls `POST /tools/facilitator/reset_ai_credentials` with A's id and a new key. The mutation succeeds. The audit row has `consent_id=NULL`.

**Acceptance Scenarios**:

1. **Given** sponsor S, AI A (`A.invited_by = S.id`), **When** S calls `reset_ai_credentials` on A, **Then** the mutation MUST succeed AND the audit row MUST persist with `consent_id=NULL`.
2. **Given** sponsor S, AI B (`B.invited_by = different_participant`), **When** S calls `reset_ai_credentials` on B, **Then** the call MUST fail with the sovereignty-violation error AND no audit row MUST persist beyond the failure record.

---

### User Story 2 - Facilitator requests a credential change; sponsor co-signs (Priority: P1)

**As a** facilitator who needs to rotate a sponsored AI's depleted budget cap during an active session, **I want** to initiate a credential-change request the sponsor co-signs **so that** the change persists with a two-party-consent audit trail rather than facilitator-unilateral authority.

**Why this priority**: This is the load-bearing flow that replaces the dropped facilitator-unilateral path. Without it, facilitators have no path to a credential change at all, which strands sessions where the sponsor is async/asleep AND the AI's wallet is the blocker.

**Independent Test**: Facilitator F initiates a `set_budget` consent request against AI A (sponsor S). The request lands as a row in `credential_change_consents` with TTL. S sees the pending request, co-signs. F re-issues the `set_budget` call with the consent_id; the mutation succeeds. The audit row records both the consent_id and the new value.

**Acceptance Scenarios**:

1. **Given** facilitator F, sponsor S, AI A (`A.invited_by = S.id`), **When** F initiates a `credential_change_consent_request` for field `budget_hourly` on A with a new value, **Then** a row MUST persist in `credential_change_consents` with `requested_by_facilitator_id=F.id`, `sponsor_id=S.id`, `ai_participant_id=A.id`, `requested_field='budget_hourly'`, `requested_value_hash=HMAC(new_value)`, `created_at=NOW()`, `expires_at=NOW()+SACP_CONSENT_TTL_SECONDS`, `consumed_at=NULL` AND an `admin_audit_log` row MUST persist with `action='credential_change_consent_requested'`.
2. **Given** an unconsumed consent row, **When** S co-signs via the consent-grant endpoint, **Then** an `admin_audit_log` row MUST persist with `action='credential_change_consent_granted'` AND the row's `consumed_at` MUST remain `NULL` (granted is not consumed; consumption happens at the actual mutation call).
3. **Given** a granted consent row, **When** F calls `set_budget` with the `consent_id` parameter and the value matching the consent's `requested_value_hash`, **Then** the mutation MUST succeed AND the consent row's `consumed_at` MUST update to `NOW()` AND the `set_budget` audit row MUST carry `consent_id` non-null AND the `previous_value` / `new_value` field policy MUST follow the Q2 clarification resolution at implementation time.
4. **Given** a granted consent row, **When** F calls `set_budget` with a value whose hash does NOT match the consent's `requested_value_hash`, **Then** the call MUST fail with the consent-mismatch error AND the consent row MUST remain unconsumed AND no mutation MUST persist.

---

### User Story 3 - MCP dispatcher refuses facilitator scope for sovereignty-excluded tools (Priority: P1)

**As an** MCP client holding a `scopeRequirement="facilitator"` JWT, **I want** the dispatcher to refuse `participant.set_budget` and `provider.test_credentials` on AIs I did not invite **so that** the documented `_SOVEREIGNTY_EXCLUSIONS` boundary is actually enforced.

**Why this priority**: The MCP-side surface is the second sovereignty leak the inventory called out. Today the dispatcher does not consult `_SOVEREIGNTY_EXCLUSIONS` at all; the constant is dead code. Phase 4 (spec 030) shipped the JWT scope grant model expecting this enforcement, and the absence of it is exactly what made the constant aspirational.

**Independent Test**: An MCP client with a facilitator-scope JWT invokes `participant.set_budget` on an AI the facilitator did not invite. The dispatcher refuses with the sovereignty-violation error code. A second client with a sponsor-scope JWT (caller matches the AI's `invited_by`) invokes the same tool with the same params. The dispatch succeeds.

**Acceptance Scenarios**:

1. **Given** a facilitator-scope JWT, AI A (`A.invited_by != caller`), **When** the client calls `tools/call` for `participant.set_budget`, **Then** the dispatcher MUST consult `_SOVEREIGNTY_EXCLUSIONS` AND refuse with the sovereignty-violation JSON-RPC error code AND emit one `security_events` row with `layer='sovereignty_excluded_tool'`.
2. **Given** a sponsor-scope JWT, AI A (`A.invited_by = caller`), **When** the client calls `tools/call` for `participant.set_budget`, **Then** the dispatch MUST succeed AND the mutation MUST persist.
3. **Given** a facilitator-scope JWT with an unconsumed `credential_change_consents` row matching the (caller, A, field) tuple, **When** the client calls `tools/call` for `participant.set_budget` with the `consent_id` parameter, **Then** the dispatcher MUST consult `_SOVEREIGNTY_EXCLUSIONS`, find the matching consent row, AND succeed.
4. **Given** a facilitator-scope JWT, **When** the client calls `tools/call` for `provider.test_credentials` naming an AI the facilitator did not invite, **Then** the dispatcher MUST refuse with the sovereignty-violation error code per the inventory's Theme A scope of `_SOVEREIGNTY_EXCLUSIONS`.

---

### User Story 4 - Consent row expires; facilitator must re-request (Priority: P2)

**As a** facilitator whose consent request sat unanswered past the TTL, **I want** the expired row to be auditable as expired AND the credential-change attempt to fail cleanly **so that** stale consent rows cannot resurrect old requests.

**Why this priority**: Without TTL enforcement, a sponsor's pending row from days ago could be redeemed for a facilitator's unrelated current need. The expiry model is the closing bracket on the two-party flow.

**Independent Test**: Facilitator F initiates a consent request. Sponsor S does not co-sign before `expires_at`. F attempts to redeem the consent. The redemption fails with the consent-expired error. An audit row with `action='credential_change_consent_expired'` persists.

**Acceptance Scenarios**:

1. **Given** an unconsumed consent row with `expires_at < NOW()`, **When** F attempts to redeem it via `set_budget`, **Then** the call MUST fail with the consent-expired error AND no mutation MUST persist AND one `admin_audit_log` row with `action='credential_change_consent_expired'` MUST persist.
2. **Given** an unconsumed consent row with `expires_at < NOW()`, **When** sponsor S attempts to co-sign it, **Then** the co-signature attempt MUST fail with the consent-expired error AND the consent row MUST remain `consumed_at=NULL` AND one `admin_audit_log` row with `action='credential_change_consent_expired'` MUST persist (the expiry-on-grant attempt is distinguishable from the expiry-on-redeem attempt by the `previous_value`/`new_value` audit fields documenting the attempted operation).

---

### User Story 5 - Debug-export with `include_sponsored=true` requires per-sponsor consent (Priority: P2)

**As a** facilitator running a session-wide debug export including per-AI wallet/usage data, **I want** each sponsor to co-sign a `debug_export_consent_for_sponsor` row first **so that** I can run the inclusive export without unilaterally reading every sponsor's AI's spend.

**Why this priority**: This closes Theme B's per-participant wallet/usage leak via the same consent shape as the credential-change flow. Without it, the `debug.export` route remains a per-participant wallet sieve regardless of Theme A's credential-change work.

**Independent Test**: Facilitator F initiates `debug_export_consent_for_sponsor` requests for each sponsored AI in the session. Each sponsor co-signs their AI's row. F calls `GET /tools/debug/export?include_sponsored=true`. The export succeeds AND surfaces the per-participant `usage_log` rows AND spend totals AND budget caps for every AI whose sponsor co-signed. AIs whose sponsors did not co-sign are excluded.

**Acceptance Scenarios**:

1. **Given** an unconsumed `debug_export_consent_for_sponsor` row for AI A AND a consumed row for AI B, **When** F calls `GET /tools/debug/export?include_sponsored=true`, **Then** the response MUST surface per-participant wallet/usage data for B AND MUST exclude that data for A (A's `usage_log` rows + spend totals + budget caps MUST NOT appear) AND one `admin_audit_log` row MUST persist linking the export to the consumed consent row.
2. **Given** no `debug_export_consent_for_sponsor` rows, **When** F calls `GET /tools/debug/export?include_sponsored=false` (or omits the param), **Then** the response MUST return the aggregate session-level spend AND MUST NOT surface per-participant wallet/usage data AND no consent row MUST be required (this is the default behavior Theme B's existing fix narrows to the facilitator's own row AND the rows of AIs the facilitator personally invited).

---

### User Story 6 - HTTP `set_budget` and `reset_ai_credentials` enforce the two-party path (Priority: P1)

**As the** orchestrator's HTTP-layer authorization check, **I want** `_require_facilitator_or_inviter` replaced with `_require_inviter_or_two_party_consent` on the credential-bearing endpoints **so that** the facilitator branch no longer wins unconditionally on sponsored AIs.

**Why this priority**: The behavioral change at the HTTP layer is the parallel of US3 at the MCP layer. Same sovereignty boundary, different surface.

**Independent Test**: Facilitator F calls `POST /tools/facilitator/set_budget` on AI A (sponsor S != F). Without a `consent_id` query param, the call fails with the sovereignty-violation error. With a valid unconsumed `consent_id`, the call succeeds. Inviter S calls the same endpoint on A without any consent_id; the call succeeds (sponsor direct path).

**Acceptance Scenarios**:

1. **Given** facilitator F (`F != A.invited_by`), **When** F calls `set_budget` on A WITHOUT a `consent_id`, **Then** the call MUST fail with the sovereignty-violation error AND no mutation MUST persist.
2. **Given** facilitator F (`F != A.invited_by`) AND a valid unconsumed consent row, **When** F calls `set_budget` on A WITH the matching `consent_id`, **Then** the mutation MUST succeed AND the consent row MUST consume.
3. **Given** sponsor S (`S = A.invited_by`), **When** S calls `set_budget` on A WITHOUT a `consent_id`, **Then** the mutation MUST succeed AND the audit row MUST persist with `consent_id=NULL` (sponsor direct path).
4. **Given** facilitator F (`F != A.invited_by`), **When** F calls `reset_ai_credentials` on A WITHOUT a `consent_id`, **Then** the call MUST fail with the sovereignty-violation error.
5. **Given** facilitator F (`F != A.invited_by`), **When** F calls `release_ai_slot` on A WITHOUT a `consent_id`, **Then** the call MUST fail with the sovereignty-violation error.

---

### User Story 7 - Sponsor UI surfaces pending consent requests (Priority: P3)

**As a** sponsor with a pending consent request awaiting my co-signature, **I want** the UI to show me what the facilitator is asking to change AND the requested value (rendered safely; the hash is what's persisted but the UI may show the operator-tunable plaintext at request time) **so that** I can make an informed co-signature decision.

**Why this priority**: P3 because the structural surface (DB row, audit trail) is the load-bearing primitive; a polished sponsor UI is the second-order ergonomics layer. v1 ships with a minimal UI surfacing the pending count + a per-row review modal; richer notification posture (email, push, in-app toast cadence) lands in a follow-up amendment.

**Independent Test**: Facilitator F initiates a consent request. The sponsor's Web UI shows a pending-requests count in the admin panel. The sponsor clicks through to a row that surfaces the requested field, the requesting facilitator's display name, the consent created_at + expires_at timestamps, and a grant/deny pair of buttons. Granting transitions the row to `consumed_at=NULL` + an audit row.

**Acceptance Scenarios**:

1. **Given** at least one unconsumed consent row where `sponsor_id = current_account`, **When** the sponsor visits the admin panel, **Then** the panel MUST surface a pending-requests count AND clicking the count MUST list the rows with field + facilitator-display-name + timestamps + grant/deny actions.
2. **Given** the sponsor clicks "grant" on a row, **When** the orchestrator processes the grant, **Then** an `admin_audit_log` row with `action='credential_change_consent_granted'` MUST persist AND the panel MUST refresh to remove the row.

---

### Edge Cases

- What happens when a facilitator initiates a consent request, then the facilitator role transfers to a different participant before the consent is co-signed? The consent row's `requested_by_facilitator_id` remains the original facilitator; the new facilitator MUST initiate their own request if they want to redeem the consent. [JUDGMENT  --  consent rows are bound to the actor who initiated them, not to the facilitator role; this prevents stale consent rows from following the role across rotations.]
- What happens when a sponsor leaves the session before the consent request is granted or expired? Per spec 002 `remove_participant` cascade semantics, the AI's sponsorship link is preserved in the audit log AND the consent row remains until expiry; the AI is detached from the session per the existing cascade. The consent row's expiry path handles the gravestone case. [JUDGMENT]
- What happens when an AI's sponsor and `invited_by` diverge mid-session (e.g., the original inviter is removed)? The `invited_by` field is immutable post-creation per spec 002; the consent flow keys on `invited_by`, not on the currently-active sponsor's seat. If `invited_by` is no longer active, the credential-change-by-sponsor path is unavailable for that AI (the only path is the consent flow co-signed by a participant who matches the AI's `invited_by`  --  which, if departed, may never happen). [JUDGMENT  --  this is the sovereignty-correct outcome: a departed sponsor's sovereignty over their AI does not transfer to whoever inherits the facilitator seat. The AI's wallet authority dies with the sponsor's seat departure. If the operator wants a different policy, they raise it as a follow-up amendment.]
- What happens when the `requested_value_hash` is presented at redemption time but the proposed plaintext value has changed between consent-request and consent-redemption (e.g., the facilitator re-typed a different budget on the redemption call)? The hash mismatch fails the call per US2 acceptance scenario 4. The facilitator must initiate a new consent request with the new value.
- What happens when `SACP_CONSENT_TTL_SECONDS` is set below 60 seconds at startup? V16 fail-closed: the validator MUST refuse the value and exit at startup with a clear error naming the offending var and its valid range (60-86400).
- What happens when the consent_id is reused on a second redemption attempt after a successful first redemption? `consumed_at IS NOT NULL` -> the call MUST fail with the consent-already-consumed error AND no mutation MUST persist. Re-use is a single-use violation, not retried with the same consent_id.

## Requirements *(mandatory)*

### Functional Requirements

#### Sovereignty boundary on credential-bearing endpoints

- **FR-001**: The system MUST refuse `POST /tools/facilitator/reset_ai_credentials` from a non-sponsor caller without a valid unconsumed `credential_change_consents` row matching the (caller, target_ai, field='api_key') tuple.
- **FR-002**: The system MUST refuse `POST /tools/facilitator/release_ai_slot` from a non-sponsor caller without a valid unconsumed `credential_change_consents` row matching the (caller, target_ai, field='release') tuple.
- **FR-003**: The system MUST refuse `POST /tools/facilitator/set_budget` from a non-sponsor caller without a valid unconsumed `credential_change_consents` row matching the (caller, target_ai, field={'budget_hourly' | 'budget_daily' | 'max_tokens_per_turn'}) tuple. The system MUST treat each of the three fields as an independent consent unit  --  a consent for `budget_hourly` does NOT grant a `budget_daily` change.
- **FR-004**: The system MUST refuse MCP `participant.update` invocations from a non-sponsor caller on any of the fields `api_endpoint`, `budget_hourly`, `budget_daily`, `max_tokens_per_turn` without a valid unconsumed `credential_change_consents` row.
- **FR-005**: The system MUST refuse MCP `participant.set_budget` invocations from a non-sponsor caller without a valid unconsumed `credential_change_consents` row. This FR is the load-bearing case for converting `_SOVEREIGNTY_EXCLUSIONS` from documentation to enforcement on the MCP path.
- **FR-006**: The system MUST permit any of the endpoints in FR-001..FR-005 from a caller whose participant id matches the target AI's `invited_by` (the sponsor direct path), without requiring any consent row.
- **FR-007**: The system MUST replace the inline `_require_facilitator_or_inviter` check on `reset_ai_credentials`, `release_ai_slot`, and `set_budget` with the new `_require_inviter_or_two_party_consent` semantics at the HTTP layer. The function signature accepts the caller's `Participant` row, the target AI's id, the requested field, and an optional `consent_id`; it returns the resolved consent row (when the consent path is used) or `None` (when the sponsor direct path is used).

#### `credential_change_consents` table and lifecycle

- **FR-008**: The system MUST persist consent requests in a new table `credential_change_consents` with the following columns: `consent_id` (UUID, primary key), `ai_participant_id` (FK to `participants.id`), `sponsor_id` (FK to `participants.id`  --  the AI's `invited_by` at consent-request time), `requested_by_facilitator_id` (FK to `participants.id`), `requested_field` (enum: `api_key`, `budget_hourly`, `budget_daily`, `max_tokens_per_turn`, `api_endpoint`, `release`, `debug_export`), `requested_value_hash` (TEXT  --  HMAC of the proposed new value so audit can correlate without persisting plaintext), `created_at` (TIMESTAMPTZ NOT NULL DEFAULT NOW()), `expires_at` (TIMESTAMPTZ NOT NULL), `consumed_at` (TIMESTAMPTZ NULL). One alembic migration ships the table. The `tests/conftest.py` schema mirror MUST be updated alongside per the `feedback_test_schema_mirror` convention.
- **FR-009**: The system MUST index the `credential_change_consents` table on `(ai_participant_id, expires_at)` to support the sponsor's "pending consent requests" UI query (US7) AND the redemption-time lookup (FR-013).
- **FR-010**: The system MUST compute `requested_value_hash` as `HMAC-SHA256(server_secret, requested_field || ':' || requested_value_canonical)` where `server_secret` is an orchestrator-side key, NOT the per-participant API key, AND `requested_value_canonical` is the canonical string form of the proposed value (booleans as `"true"`/`"false"`, integers as decimal strings, null/release-without-value as the literal string `"release"`). The plaintext value MUST NOT be persisted in the consent row.
- **FR-011**: The system MUST default `consent_id`'s `expires_at` to `created_at + SACP_CONSENT_TTL_SECONDS` at insert time. Callers MUST NOT be able to override the expiry; the env var is the operator's single control surface.
- **FR-012**: The system MUST treat a consent row as redeemable only when ALL of the following hold: `expires_at > NOW()` AND `consumed_at IS NULL` AND `ai_participant_id` matches the redemption call's target AND `requested_field` matches the redemption call's field AND HMAC of the redemption call's proposed value matches `requested_value_hash` AND `requested_by_facilitator_id` matches the redemption-call caller's participant id.
- **FR-013**: The system MUST atomically (a) verify the redemption check in FR-012, (b) set `consumed_at = NOW()` on the consent row, (c) perform the credential-bearing mutation, and (d) write the corresponding audit row, all within a single DB transaction. If any step fails the entire transaction MUST roll back AND no mutation MUST persist.
- **FR-014**: The system MUST refuse a sponsor's co-signature attempt on a consent row whose `expires_at` has passed; the system MUST emit one `admin_audit_log` row with `action='credential_change_consent_expired'` on that refused attempt.
- **FR-015**: The system MUST refuse a redemption attempt on a consent row whose `expires_at` has passed; the system MUST emit one `admin_audit_log` row with `action='credential_change_consent_expired'` on that refused attempt. The expired-on-redeem audit row is structurally distinguishable from the expired-on-grant audit row via the `previous_value`/`new_value` fields documenting the attempted operation.
- **FR-016**: The system MUST NOT delete consent rows automatically. Expired and consumed rows remain in the table for forensic review subject to the project's general retention sweep cadence.

#### Audit log shape

- **FR-017**: The system MUST emit one `admin_audit_log` row with `action='credential_change_consent_requested'` at consent-request time, with the requesting facilitator's participant id in `actor`, the AI's participant id in the target field, and the requested field name embedded in `new_value`. The plaintext requested value MUST NOT be embedded in any audit row.
- **FR-018**: The system MUST emit one `admin_audit_log` row with `action='credential_change_consent_granted'` at sponsor co-signature time, with the sponsor's participant id in `actor` and the consent_id in `new_value` for forensic traceback to the request row.
- **FR-019**: The system MUST emit one `admin_audit_log` row with `action='credential_change_consent_expired'` at each expiry-detection moment per FR-014 and FR-015.
- **FR-020**: The system MUST extend the existing `admin_audit_log` rows emitted by `reset_ai_credentials`, `set_budget`, and `release_ai_slot` (HTTP) AND the MCP `participant.update` / `participant.set_budget` audit rows with a `consent_id` field. The field MUST be non-null when the consent path was used AND MUST be null when the sponsor direct path was used. The existing audit-action names MUST NOT change; the addition is a field, not a new action.

#### MCP dispatcher enforcement

- **FR-021**: The MCP dispatcher's `_check_authorization` path MUST consult `_SOVEREIGNTY_EXCLUSIONS` at every `tools/call` invocation. When the requested tool name is in `_SOVEREIGNTY_EXCLUSIONS` AND the JWT presents `scopeRequirement="facilitator"`, the dispatcher MUST refuse with the sovereignty-violation JSON-RPC error code AND MUST emit one `security_events` row with `layer='sovereignty_excluded_tool'`.
- **FR-022**: The MCP dispatcher MUST permit a tool name in `_SOVEREIGNTY_EXCLUSIONS` when the JWT presents `scopeRequirement="sponsor"` AND the caller's participant id matches the target AI's `invited_by` field at dispatch time. The check MUST be against the DB-current `invited_by` value, NOT against any claim baked into the JWT.
- **FR-023**: The MCP dispatcher MUST permit a tool name in `_SOVEREIGNTY_EXCLUSIONS` when the call carries a `consent_id` parameter resolving to a valid unconsumed `credential_change_consents` row per FR-012. Consumption follows FR-013  --  the dispatcher's call path through the consent table is the same transaction as the underlying participant-mutation call.
- **FR-024**: The `_SOVEREIGNTY_EXCLUSIONS` constant MUST extend beyond its current two entries (`provider.test_credentials`, `participant.set_budget`) to cover `participant.update` (when the call's params include any of `api_endpoint`, `budget_hourly`, `budget_daily`, `max_tokens_per_turn`  --  the dispatcher's consultation MUST be field-aware). The constant's structure MAY ship as a richer mapping than the current `dict[str, str]` if the field-aware check needs it; the schema change is internal-only.
- **FR-025**: The MCP dispatcher MUST log the sovereignty-violation decision path (refusal vs. consent-row-redemption vs. sponsor-direct) in the per-call `routing_log` row so the audit reviewer can trace which path the dispatch followed.

#### Debug-export consent flow

- **FR-026**: The system MUST treat `GET /tools/debug/export?include_sponsored=true` as requiring a fresh unconsumed `credential_change_consents` row per AI in the session whose `usage_log` rows or spend totals are to be included. Each per-AI row's `requested_field` MUST be `debug_export`. Each row's `requested_value_hash` MAY be the HMAC of an empty canonical string (the consent grants a read action, not a value mutation; the hash field is preserved for table-shape uniformity).
- **FR-027**: The system MUST default `GET /tools/debug/export` to `include_sponsored=false` semantics: per-participant `usage_log` rows + spend totals + budget caps for AIs the facilitator did NOT invite MUST NOT appear in the response. Aggregate session-level spend (sum across all participants, no per-participant breakdown) MUST remain unconditionally facilitator-readable.
- **FR-028**: The system MUST emit one `admin_audit_log` row per `debug.export` invocation under the consent path, linking the export call to each consumed `consent_id` it used (multiple consent rows MAY consume in a single export call; each consumption emits its own audit row).
- **FR-029**: The system MUST refuse `GET /tools/debug/export?include_sponsored=true` when ANY sponsored AI in the session lacks an unconsumed `debug_export` consent row. Partial exports with missing-consent AIs silently excluded are NOT permitted in v1  --  the operator must either (a) collect all sponsor consents OR (b) call with `include_sponsored=false`. [JUDGMENT  --  partial silent exclusion is a sovereignty-leak vector via inference; the all-or-nothing posture is the simpler v1 contract.]

#### Configuration

- **FR-030**: The system MUST introduce one new env var `SACP_CONSENT_TTL_SECONDS` per V16 with a validator registered in `src/config/validators.py` AND a section in `docs/env-vars.md` per the project's six-field template. The actual `docs/env-vars.md` edit lands at implementation time per the V16 deliverable gate; the spec body documents the env var's six fields below.

#### Cross-spec FR amendments

- **FR-031**: Spec 011 Section FR-016 (facilitator admin panel  --  pending approvals, session config, invite generation, audit log, backed in part by `POST /tools/facilitator/{transfer_facilitator, set_budget, set_routing_preference}`) MUST be updated to note that `set_budget` calls on AIs the facilitator did not invite now require the consent flow per FR-003. The amendment is a docs change to spec 011's FR-016 narrative; no spec 011 implementation work needs to land at spec 031 ship time beyond the cross-reference note.

### Key Entities

- **CredentialChangeConsent**: a row in the new `credential_change_consents` table representing a single pending or completed two-party authorization for a credential-bearing mutation OR a debug-export inclusion grant. Carries the consent_id, the AI's participant id, the sponsor's participant id at consent-request time, the requesting facilitator's id, the requested field, an HMAC of the proposed value (never plaintext), and the lifecycle timestamps. The row is the load-bearing primitive for the sovereignty-tight wallet authority model.
- **SovereigntyExclusion**: the entry in the dispatcher-consulted `_SOVEREIGNTY_EXCLUSIONS` constant naming a tool the dispatcher MUST NOT grant on a facilitator-scope JWT without sponsor match or a consent row. Today's constant ships two entries; this spec extends the consultation site to read it AND the constant itself to cover the credential-bearing surface of `participant.update`.
- **DebugExportConsent**: a variant of the CredentialChangeConsent shape with `requested_field='debug_export'`. The same table; same lifecycle; the discriminator is the field value. Per-AI granularity  --  one consent row per sponsored AI per export.
- **ConsentMutationLink**: the new `consent_id` field on existing `reset_ai_credentials` / `set_budget` / `release_ai_slot` / `participant.update` / `participant.set_budget` audit rows. Non-null when the two-party path was used; null when the sponsor direct path was used. The link is the audit-reviewer's traceback from the mutation row to the consent row.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A facilitator calling `POST /tools/facilitator/reset_ai_credentials` on an AI they did not invite without a valid `consent_id` parameter MUST receive the sovereignty-violation error code AND no mutation MUST persist. Verified by an integration test parameterized across the three HTTP credential-bearing endpoints (`reset_ai_credentials`, `release_ai_slot`, `set_budget`).
- **SC-002**: A facilitator calling the same endpoints WITH a valid unconsumed `consent_id` matching the AI + field + HMAC tuple MUST succeed AND the mutation MUST persist AND the consent row's `consumed_at` MUST update in the same transaction. Verified by the same integration test parameterized across the three endpoints AND a transaction-rollback assertion.
- **SC-003**: A sponsor calling the same endpoints on an AI they invited WITHOUT a `consent_id` MUST succeed AND the audit row's `consent_id` MUST be null. Verified by the same integration test.
- **SC-004**: An MCP client with a `facilitator`-scope JWT invoking `participant.set_budget`, `participant.update` (with a credential-bearing field), or `provider.test_credentials` on an AI it did not invite without a `consent_id` MUST receive the sovereignty-violation JSON-RPC error code AND one `security_events` row MUST persist with `layer='sovereignty_excluded_tool'`. Verified by a parameterized MCP integration test.
- **SC-005**: An MCP client with a `sponsor`-scope JWT invoking the same tools on an AI it invited MUST succeed AND the audit row's `consent_id` MUST be null. Verified by the same parameterized MCP integration test.
- **SC-006**: A consent row whose `expires_at` has passed MUST cause every co-signature OR redemption attempt against it to fail with the consent-expired error AND emit one `admin_audit_log` row with `action='credential_change_consent_expired'`. Verified by a TTL-clock-frozen integration test.
- **SC-007**: A consent row redeemed once MUST NOT be redeemable a second time. The second attempt MUST fail with the consent-already-consumed error. Verified by an integration test.
- **SC-008**: The `requested_value_hash` field MUST be the HMAC-SHA256 of `requested_field || ':' || requested_value_canonical` per FR-010. Verified by a hash-derivation unit test.
- **SC-009**: `GET /tools/debug/export?include_sponsored=true` MUST refuse the call when any sponsored AI in the session lacks an unconsumed `debug_export` consent row. Verified by an integration test spawning a session with two sponsored AIs, one consent granted and one not, and asserting the all-or-nothing refusal.
- **SC-010**: `GET /tools/debug/export` (without the param OR with `include_sponsored=false`) MUST surface aggregate session-level spend AND MUST NOT surface per-participant `usage_log` / spend / budget caps for non-self-invited AIs. Verified by an integration test asserting the response shape.
- **SC-011**: With `SACP_CONSENT_TTL_SECONDS` set to an invalid value (below 60 OR above 86400 OR non-integer), the orchestrator process MUST exit at startup with a clear error naming the offending var (V15 fail-closed observed in CI). Verified by a startup-validation test.
- **SC-012**: The `tests/conftest.py` schema mirror MUST include the `credential_change_consents` table DDL matching the alembic migration. Verified by the existing schema-mirror parity preflight (`scripts/check_schema_mirror.py` or equivalent  --  exact preflight name resolves at implementation time per the project's `feedback_closeout_preflight_scripts` convention).
- **SC-013**: The MCP dispatcher MUST emit one `routing_log` row per `tools/call` invocation whose target tool appears in `_SOVEREIGNTY_EXCLUSIONS`, naming the decision path (refusal vs. consent-row-redemption vs. sponsor-direct). Verified by an integration test parameterized across the three paths.
- **SC-014**: Spec 011 Section FR-016 MUST carry a cross-reference note pointing to spec 031 for the consent-flow shape of `set_budget` calls on non-self-invited AIs. Verified by a docs-only diff inspection at implementation time.

## Out of Scope

- **Theme C  --  `debug_set_timeouts` role guard.** The one-line fix is a separate change (Themes-B-and-C branch); spec 031 does not pick it up.
- **Theme D  --  cross-session enumeration via MCP `admin.*` / `session.list`.** Separate work item; the consent shape does not apply to enumeration-vs-read; the dispatcher fix is keyed on session-id, not on consent rows.
- **Theme E  --  `/tools/session/export_*` visibility filter.** Separate work item; the question of whether facilitator sees the full unfiltered transcript versus a visibility-partitioned one is surfaced as Clarification Q3 below, but the actual filter implementation is out of spec 031 scope.
- **Theme F  --  `/metrics` auth.** Separate work item; the consent shape does not apply.
- **Theme G  --  `provider.test_credentials` HTTP path consent boundary.** The MCP path's sovereignty exclusion IS in spec 031 scope (per FR-021..FR-024); the HTTP `/tools/provider/list_models` surface (`provider.py:40`) is a separate work item because its surface shape (caller submits an arbitrary API key for validation) differs from the credential-mutation shape and warrants its own spec.
- **Phase 4+ BYOK vault.** The proposal in Open Question Q4 (facilitator-blind credential storage so the encrypted ciphertext's last-4 in audit rows is replaced by a `"rotated"` / `"reset"` literal) is deferred to a follow-up amendment on spec 020 (provider-adapter-abstraction). Spec 031 does NOT change the existing `_key_tail` audit fingerprint shape.
- **Account-owner audit fingerprint** (`X-Deployment-Owner-Key` header -> `_owner_<sha256-first-16>` actor field on `/tools/admin/account/transfer_participants` audit rows). Out of spec 031 scope; spec 023 follow-up.
- **Sponsor notification posture.** Per US7, v1 ships with a minimal in-app pending-requests count + per-row review modal. Email/push/notification cadence richer than that lands in a follow-up amendment if the operator's deployment surfaces the need.
- **Cross-session consent reuse.** Consent rows are session-scoped  --  a sponsor's consent in session A does NOT grant facilitator authority over the same AI's wallet in session B (each session is its own participant record; FK-based scoping is implicit).
- **Topology 7 (MCP-to-MCP peer).** No central orchestrator; the table and dispatcher both presuppose orchestrator-mediated authorization. Topology 7 deployments need their own model.

## Clarifications

### Session 2026-05-16 (RESOLVED  --  operator decisions)

- **Q1: Where does the "facilitator can read" line fall on session-scoped vs. participant-private state?** -> **A: Sovereignty-tight (Option 2).** Quoting the operator's resolution verbatim: "Facilitator reads session metadata, participant roster (display names + provider/model labels), turn ordering, audit log, session-level cost aggregate. Cannot read per-participant spend, usage_log rows, budget caps, max_tokens_per_turn, or api_endpoint without sponsor consent." This is the project's policy for sovereignty-tight read scope going forward AND the boundary spec 031 enforces.
- **Q5: Is `_SOVEREIGNTY_EXCLUSIONS` enforced or documentation?** -> **A: Enforced.** Quoting the operator's resolution verbatim: "`_SOVEREIGNTY_EXCLUSIONS` (in `src/mcp_protocol/auth/scope_grant.py`) becomes live enforcement in the MCP dispatcher's `_check_authorization` path." FR-021..FR-025 implement this decision.

### Session 2026-05-16 (OPEN  --  must decide before `/speckit.plan`)

- **Q2: Should the `set_budget` audit row continue to embed the prior cap in `previous_value`?** [NEEDS CLARIFICATION] The existing `set_budget` audit row at `src/participant_api/tools/facilitator.py:1364` embeds `f"{target.budget_hourly}/{target.budget_daily}/{target.max_tokens_per_turn}"` in `previous_value`. Without the prior cap, forensic reconstruction is harder; with it, anyone reading the audit log via the spec 029 viewer sees historical caps  --  which IS per-participant wallet state the Q1 resolution says facilitator MUST NOT read without consent. The two interpretations:
  - **Stay**: `previous_value` continues to embed the prior cap. Rationale: audit-log readers per spec 029 are already facilitators (the spec 029 viewer is facilitator-scoped); the audit row IS the audit trail; stripping the prior cap reduces forensic value AND introduces an asymmetry where the present cap is visible (FR-020's `new_value` carries it) but the prior cap is not.
  - **Strip**: `previous_value` becomes `"redacted"` or empty; the new cap goes in `new_value` only. Rationale: the audit row is preserved-for-audit, but per Q1, only the AI's sponsor MAY read the cap value at any point in time  --  including historically. The spec 029 viewer's facilitator-readable surface MUST be scrubbed of `previous_value` for `set_budget` rows on AIs the reader did not invite.
  - **Rationale this MUST decide before `/speckit.plan`**: the implementation surface differs materially. Stay requires no migration; strip requires either a new audit-payload-redact-on-read pathway at the spec 029 viewer OR a write-time scrub on the audit row. The plan-phase implementation tasks fork on this answer.
- **Q3: Does Section 4.10 (shared-transcript immutability) imply the facilitator can read the FULL unfiltered transcript via the `/tools/session/export_*` endpoints, or do exports apply the same visibility partition as `/tools/participant/history`?** [NEEDS CLARIFICATION] Theme E in the inventory raised this; today's code splits  --  `/tools/participant/history` filters by spec 028 visibility; `/tools/session/export_*` does not. The answer affects spec 031 in one specific way: if the facilitator can read the full unfiltered transcript via the export endpoints, then the credential-change consent flow does NOT need to extend to a visibility-filter consent (the facilitator's read posture is settled outside spec 031). If the answer is "exports apply the same visibility filter," then a follow-up question arises  --  does spec 031's consent shape need to extend to a `visibility_filter` field type so the facilitator can request a visibility-relaxed export per AI? **The full Theme E fix is out of spec 031 scope per the Out of Scope section.** What spec 031 needs from this clarification is whether the consent shape extends. **Rationale this MUST decide before `/speckit.plan`**: the table schema is fixed at migration time; adding a `visibility_filter` requested_field later is a follow-up migration with a deprecation cycle on the table shape. Better to settle the field enum at v1.

### Downstream considerations (NOT spec 031 scope; referenced for completeness)

- **Q4: BYOK vault for facilitator-blind credentials**  --  deferred to a follow-up amendment on spec 020 (provider-adapter-abstraction). The proposal is to store the AI's encrypted key with no audit-visible identifier so the `_key_tail` fingerprint on `reset_ai_credentials` audit rows is replaced by a `"rotated"` / `"reset"` literal. Spec 031 explicitly does NOT change the existing `_key_tail` shape; the consent flow ships against the current audit-row schema.
- **Q6: Spec 023 deployment-owner-key audit fingerprint**  --  out of spec 031 scope. Spec 023 follow-up.

## Configuration (V16)  --  New Env Var

One new env var is introduced. The validator function in `src/config/validators.py` AND the corresponding section in `docs/env-vars.md` MUST land BEFORE `/speckit.tasks` is run for this spec (V16 deliverable gate). The `docs/env-vars.md` edit is OUT of this scaffold; the spec body documents the six fields below.

### `SACP_CONSENT_TTL_SECONDS`

- **Intended default**: `300` (5 minutes).
- **Intended type**: positive integer.
- **Intended valid range**: `[60, 86400]` seconds (one minute lower bound to prevent racing the human user; 24-hour upper bound to prevent the consent row from sitting indefinitely as a forgotten approval surface).
- **Validation rule**: the validator MUST refuse non-integer values, integers below 60, integers above 86400, AND any non-numeric string. Failure MUST cause the orchestrator process to exit at startup with a clear error naming the offending var AND its valid range.
- **Source spec(s)**: spec 031 FR-011, FR-030. Consumed at consent-row insert time to populate `credential_change_consents.expires_at = NOW() + interval`.
- **Note**: the TTL gates ONLY the sponsor-co-signature window AND the redemption window; the consumed row remains in the table for forensic review after consumption regardless of the TTL setting. The setting MUST NOT be interpreted as a row-retention TTL; row retention follows the project's general retention sweep cadence.

## Cross-References to Existing Specs and Design Docs

- **Spec 002 (participant-auth)**  --  provides the `invited_by` field on `participants` rows that spec 031's FR-006, FR-012, and FR-022 key on. The sponsor-direct path IS the existing inviter-branch shape of `_require_facilitator_or_inviter`; spec 031 preserves the sovereignty-correct half of that check and replaces only the facilitator-unilateral half.
- **Spec 011 (web-ui) Section FR-016**  --  facilitator admin panel surfaces `set_budget` and credential-bearing calls. The cross-reference note added per spec 031 FR-031 is a docs-only change; the panel's actual UI work to surface the consent flow lands at spec 031 implementation time. The Section FR-016 narrative MUST be updated to reference spec 031 for the sponsor-mediated path.
- **Spec 022 (detection-event-history)**  --  the per-instance/cross-instance broadcast mechanism is unrelated to spec 031; the consent flow is per-DB-row and per-call.
- **Spec 023 (user-accounts)**  --  sits ABOVE the per-session participant model. An account may own the participant row whose `invited_by` is the consent-flow gate. Spec 031 is sovereignty-tight by `invited_by`, NOT by `account_id`; the consent check operates at the participant layer, not the account layer. If an account owns multiple participants across sessions, each session's consent flow is independently scoped.
- **Spec 028 (capcom-routing-scope)**  --  visibility partitioning AT the message level; relevant to the debug.export consent flow surface (FR-026..FR-029). The CAPCOM model is orthogonal to the credential-mutation surface  --  a CAPCOM AI's wallet is governed by spec 031 the same as any other sponsored AI.
- **Spec 029 (audit-log-viewer)**  --  consumes the new `credential_change_consent_*` action labels in the action-label registry per the registry's parity-gate model. The audit-label parity preflight MUST be re-run at spec 031 implementation time. Q2's stay-or-strip resolution affects spec 029's `previous_value` rendering for `set_budget` rows.
- **Spec 030 (mcp-build)**  --  provides the MCP dispatcher AND the JWT scope grant model AND the dead-code `_SOVEREIGNTY_EXCLUSIONS` constant spec 031 wires into enforcement. Phase 4 FR-084 sovereignty-boundary specifics were codified inline in spec 030 implementation tasks; spec 031 is the structural enforcement Phase 4 deferred to "sovereignty remediation completing" before declaring Phase 4 complete in spec 030's phase ordering.
- **Local audit reference**  --  the facilitator-sovereignty endpoint inventory's Theme A is the source of the FR set. The inventory's nine STILL-OPEN violations break out as: five HTTP/MCP credential-mutation entries covered by FR-001..FR-005, the `debug.export` per-participant wallet leak covered by FR-026..FR-029, the `_SOVEREIGNTY_EXCLUSIONS` dead-code conversion covered by FR-021..FR-025, and three out-of-scope items (`debug_set_timeouts`, `provider.test_credentials` HTTP path, deferred BYOK vault) noted in Out of Scope.
- **Constitution Section 3**  --  sovereignty primitives (API key isolation, budget autonomy, prompt privacy, exit freedom). Spec 031 is the structural enforcement of budget-autonomy and key-isolation under the facilitator-controlled session model.

## Constitutional Mapping

### Section 4.1  --  Transparency over magic

Every consent-flow decision logs to `admin_audit_log` (FR-017..FR-020) AND `routing_log` (FR-025). The dispatcher's three decision paths (refusal vs. consent-row-redemption vs. sponsor-direct) MUST be loggable AND auditable. No silent skips; expiry detection emits its own audit row at every refusal moment (FR-014, FR-015).

### Section 4.2  --  Human authority over AI autonomy

The sponsor is the human authority of last resort for their AI's wallet. The facilitator's session-control role is preserved; the sponsor's wallet-sovereignty role is preserved; the two-party consent path lets the facilitator request a wallet change through the proper channel rather than overriding it. The interaction model upholds Section 4.2 by ensuring no AI's wallet primitives mutate without an explicit human in the loop matching the AI's sponsorship link.

### Section 4.6  --  Security > Correctness > Readability > Style

Wallet authority is a security boundary, not a convenience surface. The consent-flow path adds two round trips to a facilitator-initiated `set_budget` call where the unilateral path was one round trip; the security gain in FR-006 (sponsor consent IS required for the change to persist) outranks the latency penalty. The hierarchy resolves the trade explicitly in favor of the security primitive.

### Section 4.9  --  Secure by design

Every persistence path through the sovereignty-excluded surface goes through the security pipeline: FR-013 (atomic transaction with consent verify + mutation + audit + row consumption); FR-021..FR-025 (dispatcher consultation of `_SOVEREIGNTY_EXCLUSIONS` BEFORE the call dispatches); FR-007 (HTTP-layer `_require_inviter_or_two_party_consent` replaces `_require_facilitator_or_inviter` on the credential-bearing endpoints). No role  --  including facilitator  --  silently bypasses the consent check.

### Section 4.13  --  No negotiated inter-AI shorthand

The consent flow operates on public structured formats: HMAC-SHA256 with a documented derivation rule (FR-010), explicit field enum on the consent row (FR-008), JSON-RPC envelope on the MCP path (FR-021..FR-025), HTTP JSON body on the participant_api path. No AI-negotiated shorthand; no encoded payloads; the audit log reader can decode every value back to its plaintext meaning from public references. The HMAC of the proposed value is opaque on purpose (the plaintext is participant-private) AND the hash is verified, not interpreted  --  the hash is a correlation surface for audit, not a semantic carrier.

### Section 4.14  --  Evidence-based design

Every factual claim in this spec ties back to either (a) the inventory at `local/FACILITATOR_SOVEREIGNTY_ENDPOINT_INVENTORY.md` (the nine STILL-OPEN violations; the dead-code `_SOVEREIGNTY_EXCLUSIONS` at `src/mcp_protocol/auth/scope_grant.py:67`; the file:line references for each affected endpoint) OR (b) the cited spec (002, 011, 023, 028, 029, 030). Judgments are marked `[JUDGMENT]` in the Edge Cases section AND in the Out of Scope rationale. Open clarifications are marked `[NEEDS CLARIFICATION]` per Q2 and Q3.

## Topology and Use Case Coverage (V12/V13)

### V12  --  Topology Applicability

Spec 031 applies to **topologies 1-6** (orchestrator-mediated authorization). The `credential_change_consents` table and the dispatcher `_SOVEREIGNTY_EXCLUSIONS` consultation both presuppose a central orchestrator hosting the participant model and the JWT scope grant model. **Topology 7 (MCP-to-MCP peer)** is NOT applicable: there is no central orchestrator to host the table or enforce dispatcher-side authorization; each peer's MCP client and server are themselves participants in a federation model that would need its own sovereignty primitive. Topology 7 deployments will need their own consent flow when federation work scopes.

### V13  --  Use Case Coverage

Spec 031 primarily serves V13 use cases Section 1 (Distributed Software Collaboration  --  multi-tool AI workflows where the AI's wallet is the bridge between the operator's account and the orchestrator's session), Section 3 (Consulting Engagement  --  consultant AIs with operator-owned wallets joining client-run sessions where the client's facilitator MUST NOT mutate the consultant's wallet), Section 6 (Decision-Making Under Asymmetric Expertise  --  expert advisory AIs whose sponsorship link is the human-authority-of-last-resort gate), and Section 7 (Zero-Trust Cross-Organization Collaboration  --  the consent-flow primitive is exactly the gate that lets cross-organization collaboration work without unilateral wallet authority granted to any single party).

## Performance Budgets (V14)

- **Consent-request insert** P95 <= 50ms (single-row INSERT to `credential_change_consents` + one audit row).
- **Consent-grant transition** P95 <= 50ms (single-row append to `admin_audit_log`; the consent row itself is not mutated at grant time  --  grant is observable via the audit row).
- **Consent-redemption transaction** P95 <= 100ms (consent row SELECT + consumed_at UPDATE + participant row UPDATE + admin_audit_log INSERT, all in one transaction).
- **MCP dispatcher `_SOVEREIGNTY_EXCLUSIONS` consultation overhead** P95 <= 5ms additive on top of the existing dispatch overhead budget per spec 030 Section FR-039.
- **`debug.export?include_sponsored=true` consent collection check** P95 <= 100ms additive on top of the existing export budget  --  N queries against `credential_change_consents` for N sponsored AIs.

## Assumptions

- The orchestrator's per-session participant model with the `invited_by` field is the sovereignty primitive going forward. Future participant models that decouple sponsorship from session-scoped identity (e.g., a future account-owned-participant model from spec 023's downstream work) MAY require a follow-up amendment to map the `sponsor_id` field; v1 ships against the current per-session shape.
- The `_SOVEREIGNTY_EXCLUSIONS` constant's current location at `src/mcp_protocol/auth/scope_grant.py` is the canonical location post-spec-030 Phase 1. The dispatcher's `_check_authorization` path is the canonical consultation site; the exact line number resolves at implementation time per the spec 030 refactor.
- The HMAC server secret for `requested_value_hash` derivation is sourced from the same key-management surface that handles existing orchestrator-side secrets (e.g., the Fernet key for `api_key_encrypted`); the exact key source resolves at `/speckit.plan` time.
- Spec 029's action-label parity preflight catches drift if spec 031 ships new action labels without registering them in the action-label registry. This is a CI gate at merge time, not a spec-031-side runtime check.
