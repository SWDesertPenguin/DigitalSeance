# Feature Specification: Core Data Model

**Feature Branch**: `001-core-data-model`
**Created**: 2026-04-11
**Status**: Draft
**Input**: User description: "Core data model and database schema — tables for sessions, participants, messages, append-only logs, and migrations foundation for SACP Phase 1"

## Clarifications

### Session 2026-05-02 (audit fix/001-operations — Phase E)

- Q: Does the orchestrator enforce `sslmode=require` for DB connections at startup? → A: No. Phase 1 leaves transport-encryption to the operator's connection string; production deployments MUST set it correctly. Phase 3 trigger: any deployment with regulatory transport-encryption requirements (HIPAA, PCI-DSS).

- Q: When does the FR-022 `sacp_app` least-privilege SQL role land? → A: Phase 3, triggered by any production deployment where database compromise via the orchestrator would cascade beyond the SACP schema. Implementation surface: alembic migration creating `sacp_app` with INSERT/UPDATE/DELETE/SELECT only; deploy-time check that the connection string targets that role.

- Q: When does the `SACP_AUDIT_RETENTION_DAYS` purge enforcer land? → A: Phase 3, alongside the other reserved-env-var purge jobs (see `docs/retention.md` §7). Pre-wire, the effective retention is "never delete" regardless of env-var value; operators with hard-cap retention requirements run an external query (see `docs/operational-runbook.md` §2.5).

- Q: Does `alembic upgrade head` require operator confirmation before applying pending migrations at startup? → A: No. Phase 1 deploys auto-apply pending migrations. Defenses: forward-only constraint (FR-017), schema-mirror CI gate, restore-from-backup as the rollback path. Phase 3 trigger: deployment policy requiring manual approval gates between staging and production migration application.

### Session 2026-04-14

- Q: Audit log retention after session delete? → A: Default indefinite, configurable per deployment
- Q: acceptance_mode="facilitator" semantics? → A: Facilitator decides alone (their vote resolves; others are advisory)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Facilitator Creates a Session (Priority: P1)

A facilitator starts a new collaboration session by providing a name and configuration preferences (cadence, acceptance mode, model tier threshold). The system persists the session and the facilitator's participant record so they can immediately begin inviting others and configuring the environment.

**Why this priority**: Sessions are the root entity — nothing else (participants, messages, logs) can exist without a session. This is the minimum viable data operation.

**Independent Test**: Can be tested by creating a session record and verifying it persists with correct defaults, a linked facilitator participant record, and an auto-created 'main' conversation branch.

**Acceptance Scenarios**:

1. **Given** no sessions exist, **When** a facilitator creates a session with a name and default configuration, **Then** a session record is persisted with status 'active', a participant record with role 'facilitator' is linked, and a 'main' branch record is created.
2. **Given** a session exists, **When** the facilitator retrieves session details, **Then** all configuration fields (cadence, acceptance mode, model tier, auto-archive/delete policies) are returned accurately.
3. **Given** a session is created, **When** any downstream operation references the session, **Then** the session ID resolves correctly via referential integrity.

---

### User Story 2 - Participant Joins and Configuration Persists (Priority: P1)

A participant joins a session with their model choice, routing preference, budget limits, and encrypted API key. Their configuration is stored so the orchestrator can route turns, enforce budgets, and dispatch requests to the correct provider without re-configuration.

**Why this priority**: Participant records are the second foundational entity — the orchestrator cannot route turns or track costs without them.

**Independent Test**: Can be tested by inserting a participant record with all configuration fields (model, routing preference, budget, encrypted API key) and verifying retrieval returns correct values with the API key remaining encrypted at rest.

**Acceptance Scenarios**:

1. **Given** an active session, **When** a participant joins with provider, model, routing preference, and budget limits, **Then** a participant record is persisted with all fields intact and status 'active'.
2. **Given** a participant with an API key, **When** the key is stored, **Then** it is encrypted at rest and never appears in plaintext in any stored record or log output.
3. **Given** a participant with budget_daily set to $5.00, **When** the budget field is read, **Then** it returns 5.00 exactly as stored.

---

### User Story 3 - Conversation Messages Are Recorded Immutably (Priority: P1)

As the conversation progresses, every turn (AI response, human interjection, system message, summarization checkpoint) is appended to the transcript. Messages are never modified or deleted during normal operation. Each message references its session, branch, and speaker so the full conversation tree can be reconstructed.

**Why this priority**: The message transcript is the core product of every session. Immutability is a constitutional guarantee (constitution §7).

**Independent Test**: Can be tested by appending multiple messages with different speaker types and verifying: each persists with correct turn number, branch, and speaker; no message can be updated or deleted through normal operations; tree structure is navigable via parent_turn references.

**Acceptance Scenarios**:

1. **Given** an active session with a 'main' branch, **When** a message is appended, **Then** it is persisted with a sequential turn number, the correct branch, speaker, content, and timestamp.
2. **Given** a persisted message, **When** an attempt is made to modify its content through normal application operations, **Then** the modification is rejected.
3. **Given** messages from multiple speaker types (ai, human, system, summary), **When** the transcript is queried, **Then** all messages are returned in turn order with correct speaker attribution.
4. **Given** a message with parent_turn set, **When** the conversation tree is traversed, **Then** the parent-child relationship resolves correctly for future branching support.

---

### User Story 4 - Operational Logs Capture Every Decision (Priority: P2)

Every routing decision, token usage event, convergence measurement, and facilitator action is logged as it occurs. Logs are append-only — the application cannot modify or delete log entries. This provides full transparency and auditability for all participants.

**Why this priority**: Logs are required for transparency (constitution §4.1), budget enforcement, convergence detection, and facilitator accountability. They support but do not block basic session/message operations.

**Independent Test**: Can be tested by inserting log entries into each log category (routing, usage, convergence, admin audit) and verifying: entries persist correctly, no update or delete operations succeed through the normal application path, and queries return expected results.

**Acceptance Scenarios**:

1. **Given** a turn is routed, **When** the routing decision is logged, **Then** a routing log entry records the intended participant, actual participant, action taken, and reason.
2. **Given** a turn completes, **When** token usage is logged, **Then** input tokens, output tokens, and cost are recorded against the correct participant.
3. **Given** a convergence check runs, **When** results are logged, **Then** the similarity score, divergence prompt status, and escalation status are recorded.
4. **Given** a facilitator takes an administrative action, **When** the action is logged, **Then** the admin audit log records who did what, to whom, with before/after values.
5. **Given** any log entry exists, **When** an attempt is made to update or delete it through normal application operations, **Then** the operation is rejected.

---

### User Story 5 - Session Lifecycle Management (Priority: P2)

A facilitator can pause, resume, archive, and delete sessions. Pausing prevents new turns. Archiving makes a session read-only. Deletion atomically removes all session data (messages, participants, logs) except the admin audit log entry recording the deletion itself.

**Why this priority**: Lifecycle management is essential for operational use but depends on the foundational entities from P1 stories.

**Independent Test**: Can be tested by transitioning a session through each status (active → paused → active → archived → deleted) and verifying data access restrictions and cleanup at each stage.

**Acceptance Scenarios**:

1. **Given** an active session, **When** the facilitator pauses it, **Then** the session status changes to 'paused' and no new messages can be appended.
2. **Given** a paused session, **When** the facilitator resumes it, **Then** the session status returns to 'active' and message appending resumes.
3. **Given** an active or paused session, **When** the facilitator archives it, **Then** the session becomes read-only.
4. **Given** any session, **When** it is deleted, **Then** all associated data (messages, participants, logs, invites, proposals) is atomically removed, except the admin audit log entry recording the deletion.
5. **Given** a session with auto_archive_days set, **When** the inactivity threshold is reached, **Then** the session transitions to 'archived' automatically.

---

### User Story 6 - Human Interjections via Interrupt Queue (Priority: P2)

Human participants can inject priority messages into the conversation at any time. These interjections are queued and delivered on the next turn, taking precedence over AI responses. The queue tracks delivery status so no interjection is lost or silently dropped.

**Why this priority**: Human authority over AI autonomy is a constitutional principle (§4.2). The interrupt queue is the mechanism that enforces it — without it, humans cannot reliably interject during autonomous AI conversation.

**Independent Test**: Can be tested by inserting interjections with different priorities into the queue and verifying: each is persisted with correct priority and 'pending' status, delivery order respects priority then creation time, and status updates to 'delivered' with a timestamp after processing.

**Acceptance Scenarios**:

1. **Given** an active session, **When** a human participant injects a message, **Then** an interrupt queue entry is created with the participant reference, content, priority level, and 'pending' status.
2. **Given** pending interjections exist, **When** the next turn cycle runs, **Then** interjections are delivered before AI turns and their status updates to 'delivered' with a delivery timestamp.
3. **Given** a high-priority interjection (priority=2) and a normal-priority interjection (priority=1), **When** both are pending, **Then** the high-priority interjection is delivered first.
4. **Given** multiple pending interjections with the same priority, **When** they are delivered, **Then** they are delivered in creation order (FIFO within priority).

---

### User Story 7 - Review Gate Draft Staging (Priority: P2)

When a participant uses 'review_gate' routing mode, their AI's response is held in a staging area rather than entering the transcript directly. The participant's human can approve the draft as-is, edit it before approval, or reject it entirely. Drafts that exceed the participant's review timeout auto-resolve. The system tracks the full lifecycle of each draft so no response is silently lost.

**Why this priority**: Review gate is one of the eight routing modes and the primary mechanism for human oversight of AI responses. Without draft staging, review-gated participants have no way to exercise control over what their AI contributes.

**Independent Test**: Can be tested by creating a review gate draft and transitioning it through each resolution path (approve, edit, reject, timeout), verifying status tracking and content persistence at each stage.

**Acceptance Scenarios**:

1. **Given** a review-gated participant's AI generates a response, **When** the response is held, **Then** a draft record is created with the AI's content, a context summary, 'pending' status, and a creation timestamp.
2. **Given** a pending draft, **When** the human approves it, **Then** the draft status changes to 'approved' and the content is eligible to enter the transcript as a message.
3. **Given** a pending draft, **When** the human edits and approves it, **Then** the edited content is stored separately, the draft status changes to 'edited', and the edited version is eligible to enter the transcript.
4. **Given** a pending draft, **When** the human rejects it, **Then** the draft status changes to 'rejected' and nothing enters the transcript.
5. **Given** a pending draft, **When** the participant's review_gate_timeout expires, **Then** the draft status changes to 'timed_out' and auto-resolves per participant configuration.

---

### User Story 8 - Invitations and Join Flow (Priority: P3)

A facilitator generates invite tokens (single-use or multi-use, with optional expiry) so new participants can join. Tokens are stored as hashes — the plaintext is shown once at creation and never stored. Participants who join via invite start as 'pending' until approved (unless auto-approve is enabled).

**Why this priority**: Invitations extend the participant model but are not required for the minimum two-participant MVP where participants can be added directly.

**Independent Test**: Can be tested by creating an invite, using it to add a participant, and verifying: token is stored as hash only, use count increments, expiry is enforced, and the participant starts with the correct role.

**Acceptance Scenarios**:

1. **Given** a facilitator in an active session, **When** they create an invite, **Then** an invite record is stored with the token hash (not plaintext), session reference, use limits, and expiry.
2. **Given** a valid invite token, **When** a participant joins, **Then** the use count increments and a 'pending' participant record is created.
3. **Given** a single-use invite that has been used, **When** another participant attempts to use it, **Then** the invite is rejected.
4. **Given** an expired invite, **When** a participant attempts to use it, **Then** the invite is rejected.

---

### User Story 9 - Proposals and Voting (Priority: P3)

Participants can create proposals for group decisions and cast votes. Each proposal tracks its acceptance mode (inherited from session config), voting deadline, and resolution status. Each participant votes once per proposal.

**Why this priority**: The proposal/voting system supports structured decision-making but is not required for basic conversation flow.

**Independent Test**: Can be tested by creating a proposal, casting votes from multiple participants, and verifying acceptance logic, duplicate vote prevention, and expiry handling.

**Acceptance Scenarios**:

1. **Given** an active session, **When** a participant creates a proposal, **Then** the proposal is recorded with topic, position, acceptance mode, and optional expiry.
2. **Given** an open proposal, **When** a participant votes, **Then** the vote is recorded. A second vote from the same participant is rejected.
3. **Given** a proposal with acceptance_mode 'unanimous', **When** all active participants vote 'accept', **Then** the proposal status changes to 'accepted'.
4. **Given** a proposal with an expiry, **When** the deadline passes without resolution, **Then** the proposal status changes to 'expired'.

---

### Edge Cases

- What happens when a session is deleted while participants are connected? All associated data is atomically removed; connected participants receive disconnection.
- What happens when a participant departs? Their API key is overwritten with `uuid.uuid4().hex` (a deterministic-looking placeholder, not a null), auth token is invalidated, status set to 'offline', but their messages remain in the transcript. The placeholder ensures decrypt attempts fail cleanly rather than returning leftover plaintext.
- What happens when turn numbers collide on the same branch? The composite primary key (turn_number, session_id, branch_id) prevents duplicates — the insert is rejected. The turn-loop engine serializes via PostgreSQL advisory lock on `hashtext(branch_id)` to avoid the collision window (see 003 §Clarifications 2026-04-15).
- What happens when a session has no 'main' branch? Session creation MUST atomically create the 'main' branch to prevent orphaned messages.
- What happens when the encryption key is unavailable at startup? The system MUST fail closed — no API key decryption, no provider dispatch, clear error surfaced via process exit before the FastAPI app binds its port.
- What happens when the encryption key is changed between writes and reads (FR-021)? Decryption raises `cryptography.fernet.InvalidToken`; affected participants must rotate their API key via the participant-self-service flow. Phase 1 does not support transparent re-keying.
- What happens when an audit log row would orphan its session/participant FK (e.g., session deletion)? Per FR-019, the FK constraints are dropped from `admin_audit_log` — the rows persist as denormalized snapshots. A query that joins `admin_audit_log` to `sessions` or `participants` MUST handle missing parents.
- What happens when `turn_number` (INTEGER, ~2.1B max) approaches overflow on a hypothetical multi-million-turn session? Out of scope for Phase 1 — typical sessions are <10K turns. Migrate to BIGINT if the population statistics shift.
- What happens when `domain_tags` (serialized text array per Assumptions) references a domain string that no other participant uses? Accepted — `domain_tags` carries operator-supplied free-form labels by design; FR-009 referential integrity does not extend to denormalized free-form fields.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST persist session records with unique identifiers, name, status, configuration fields (cadence, acceptance mode, model tier, auto-archive/delete policies), and facilitator reference.
- **FR-002**: System MUST atomically create a 'main' branch record whenever a new session is created, ensuring messages always have a valid branch reference.
- **FR-003**: System MUST persist participant records with model configuration, routing preferences, budget limits, domain tags, and status — linked to exactly one session.
- **FR-004**: System MUST store participant API keys encrypted at rest using application-layer encryption. Keys MUST never appear in plaintext in any stored record.
- **FR-005**: System MUST store authentication tokens as irreversible hashes only.
- **FR-006**: System MUST append messages with sequential turn numbering per session-branch, speaker attribution, speaker type classification, token count, cost, and tree-structure references (parent_turn, branch_id).
- **FR-007**: System MUST enforce message immutability — no update or delete operations on message records through the normal application path.
- **FR-008**: System MUST maintain append-only operational logs (routing decisions, token usage, convergence measurements, facilitator actions) that cannot be modified or deleted through the normal application path.
- **FR-009**: System MUST enforce referential integrity between all entities (sessions → participants → messages → logs).
- **FR-010**: System MUST support session lifecycle transitions: active → paused → active, active/paused → archived, any → deleted.
- **FR-011**: System MUST perform atomic session deletion — removing all associated data within a single transactional boundary — no orphaned records remain.
- **FR-012**: System MUST support invite tokens stored as hashes with configurable use limits and expiry.
- **FR-013**: System MUST support proposals with per-session acceptance modes and one-vote-per-participant enforcement. Modes: `unanimous` (all active participants must accept), `majority` (>50% of active participants accept), `facilitator` (the facilitator's vote alone resolves; other votes are advisory only).
- **FR-014**: System MUST support interrupt queue entries with priority levels and delivery tracking.
- **FR-015**: System MUST support review gate draft staging with resolution status tracking (pending, approved, edited, rejected, timed out).
- **FR-016**: System MUST overwrite (not null) API key material when a participant departs, and invalidate their auth token.
- **FR-017**: System MUST support schema evolution through versioned, forward-only migrations.
- **FR-018**: System MUST include tree-structure support (parent_turn, branch_id) in the message data model from the initial release, even though branching UI is deferred to Phase 3.
- **FR-019**: Admin audit log entries MUST be retained indefinitely by default. Retention policy MAY be overridden per deployment via the `SACP_AUDIT_RETENTION_DAYS` env var (default unset = indefinite). To survive session and participant deletion, the `admin_audit_log.session_id` and `admin_audit_log.facilitator_id` columns are denormalized identifiers (NOT NULL TEXT, no foreign-key constraints — see migration 007). The audit log row recording a `delete_session` action MUST itself outlive the deletion transaction.
- **FR-020**: Encryption-at-rest scope (Phase 1) covers ONLY `participants.api_key_encrypted` (Fernet column-level). Other potentially sensitive fields — `system_prompt`, `display_name`, message content — are stored unencrypted at the column level and rely on database-level access control + log scrubbing (007 §FR-012) for confidentiality. Phase 2+ migration to envelope encryption (DEK/KEK) MAY widen this scope; trigger: any deployment that stores material classified higher than "operational metadata".
- **FR-021**: Encryption-key rotation (changing `SACP_ENCRYPTION_KEY`) is NOT supported in Phase 1. Existing ciphertexts cannot be re-keyed. If the operator changes the key, all `participants.api_key_encrypted` rows become undecryptable and the affected participants MUST rotate their stored API keys via the participant-self-service flow (002 §FR-008 token rotation does not affect this — the participant must explicitly re-set their api_key). Phase 2+ envelope encryption introduces per-row key versioning so rotation becomes safe; trigger: first non-test deployment that requires rotation as a security control.
- **FR-022**: Append-only enforcement (FR-007 messages, FR-008 logs) is implemented at the Python repository interface — no `LogRepository` / `MessageRepository` method exists for UPDATE or DELETE on these tables. The `sacp_app` SQL role defined in `roles.sql` grants only INSERT + SELECT on log tables and is intended to enforce append-only at the database layer in a future deployment hardening pass; in Phase 1 the orchestrator connects with a single role that has DELETE permission (used only by `_delete_session_data`). Direct DBA access bypasses both layers; that risk is accepted residual.

### Key Entities

- **Session**: The root entity representing a collaboration conversation. Holds configuration (cadence, thresholds, policies) and links to all other entities. Lifecycle: active → paused → archived → deleted.
- **Participant**: A human or AI collaborator within a session. Holds model configuration, routing preferences, budget limits, encrypted credentials, and status. Self-referential (invited_by).
- **Branch**: A conversation thread within a session. 'main' branch is required; additional branches support Phase 3 forking. Self-referential (parent_branch_id).
- **Message**: An immutable transcript entry. Composite identity (turn_number + session + branch). Four speaker types: ai, human, system, summary. Tree-navigable via parent_turn.
- **Routing Log**: Append-only record of every turn routing decision — who was intended, who responded, why.
- **Usage Log**: Append-only per-turn token count and cost record per participant.
- **Convergence Log**: Append-only similarity measurement per turn with divergence/escalation flags.
- **Admin Audit Log**: Append-only facilitator action record with before/after values.
- **Interrupt Queue**: Priority-ordered human interjection queue with delivery tracking.
- **Review Gate Draft**: Staging area for AI responses awaiting human approval.
- **Invite**: Hashed join token with use limits and expiry.
- **Proposal**: Decision topic with acceptance mode and voting deadline.
- **Vote**: Per-participant vote on a proposal (accept, reject, modify).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 13 core entities can be created, queried, and (where applicable) transitioned through their lifecycle states without data loss or corruption.
- **SC-002**: Message immutability is enforced — no message content is alterable through the application's normal data access path.
- **SC-003**: Append-only log integrity is enforced — no log entries are modifiable or deletable through the application's normal data access path.
- **SC-004**: API keys are encrypted at rest and never appear in plaintext in any persisted record, log output, or error trace.
- **SC-005**: Session deletion atomically removes all associated data within a single transactional boundary — no orphaned records remain.
- **SC-006**: Referential integrity holds across all entity relationships — no orphaned foreign key references exist after any operation.
- **SC-007**: Schema migrations are versioned and reproducible — a fresh environment reaches the current schema state by running migrations in sequence.
- **SC-008**: Composite message identity (turn_number + session + branch) prevents duplicate entries.
- **SC-009**: The data model supports 2 concurrent participants per session with room to scale to 5 in Phase 3 without schema changes.

## Assumptions

- Phase 1 targets two participants per session; the schema accommodates up to five for Phase 3 without structural changes.
- Sub-session tables (sub_sessions, sub_session_participants) are included in the schema for forward compatibility but are not exercised until Phase 3.
- Branching data model (parent_turn, branch_id, branches table) is present from the first migration per constitution §6.9, but branching UI is deferred to Phase 3.
- Application-layer encryption uses Fernet (AES-128-CBC + HMAC-SHA256) with a single key in Phase 1; envelope encryption (DEK/KEK) is a Phase 2 migration.
- The application connects with a dedicated database role that has restricted permissions (INSERT + SELECT only on log tables). A separate elevated role handles session deletion.
- Schema evolution is forward-only — no rollback migrations in production.
- Summarization checkpoint content is stored as structured text within the message content field (speaker_type = 'summary'), not in a separate table.
- Domain tags are stored as serialized arrays in a text field, not as a separate junction table.

## Threat model traceability

| FR | Defends against | OWASP ASVS | NIST SP 800-53 |
|----|-----------------|-----------|----------------|
| FR-001, FR-002, FR-009, FR-010 (entities + lifecycle + RI) | Logical-state corruption | V13.1 | CM-2, SI-7 |
| FR-003, FR-016 (participant config + key overwrite on departure) | Stale credential reuse | V2.1.5 | IA-5(7) |
| FR-004, FR-020 (encryption at rest, scope) | Database-dump credential exposure | V6.1.1, V6.2.1 | SC-28 |
| FR-005 (auth token hashed) | Stored-credential cracking | V2.1.4 | IA-5(2) |
| FR-006, FR-007 (message immutability) | Transcript tampering | V13.4.1 | SI-7, AU-9 |
| FR-008, FR-022 (append-only logs) | Log tampering / forensics evasion | V7.4.2 | AU-9, AU-12 |
| FR-011 (atomic deletion) | Partial-delete data leakage | V13.4.2 | SC-4 |
| FR-012 (invite hashing) | Invite-token bruteforce | V2.1.4 | IA-5(2) |
| FR-014 (interrupt queue) | Drop-priority race | V13.1 | SI-10 |
| FR-015 (review gate staging) | Direct-output bypass of human review | V4.1.1 | AC-3 |
| FR-017 (forward-only migrations) | Schema-rollback corruption | V14.2 | CM-3 |
| FR-019 (audit retention) | Forensics evasion via deletion | V7.4.2 | AU-11, AU-12 |
| FR-021 (no key rotation Phase 1) | (accepted residual: re-key requires participant action) | — | — |

Sister cross-references: token-plaintext scrubbing (FR-004) is enforced by the same root-logger ScrubFilter as 007 §FR-012; auth-token bcrypt parameters (FR-005) are pinned by 002 §FR-A1; encryption-key fail-closed at startup (FR-021 + Edge Cases) is the same path used by 003 §FR-007 dispatch.

## Audit closeout (2026-04-29)

The security-requirements quality audit (`checklists/security.md`) raised 40 findings; resolution split:

**Code changes**: CHK010 (audit log preserved past deletion — migration 007 drops the FK constraints from `admin_audit_log.session_id` and `admin_audit_log.facilitator_id` so rows survive as denormalized snapshots; `_delete_participants_and_session` no longer DELETEs them).

**Spec amendments (this commit)**: CHK001 / CHK002 / CHK028 / CHK029 (FR-021 codifies "key rotation NOT supported in Phase 1"; participants re-set API key on rotation), CHK003 (Edge Case fail-closed via process exit), CHK004 (Edge Case `uuid.uuid4().hex` overwrite), CHK013 (FR-019 `SACP_AUDIT_RETENTION_DAYS` env var), CHK016 (FR-020 encryption-at-rest scope is `api_key_encrypted` only), CHK030 (Edge Case turn_number overflow accepted out-of-scope), CHK032 (Threat-model traceability table), CHK040 (Edge Case domain_tags accepted as denormalized free-form).

**Closed as cross-reference / accepted residual**: CHK005 (backup encryption — operator concern, out of Phase 1 scope), CHK006 / CHK022 (FR-022 codifies interface-level append-only + planned DB-role enforcement), CHK007 (sacp_cleanup role staged for future deployment — FR-022), CHK008 (DBA direct access — accepted residual via FR-022), CHK009 (`summary_epoch` mutability — interface append-only via MessageRepository), CHK011 (concurrent-read isolation — PostgreSQL READ COMMITTED is the default; mid-deletion reads see partial state, accepted), CHK012 (deletion audit-row schema — `(facilitator_id, action='delete_session', target_id=session_id)`, count not recorded in Phase 1), CHK014 (audit log tamper-evidence — accepted residual; cross-row hash chaining is Phase 3 hardening), CHK015 (audit retention vs erasure — operator policy resolves; FR-019 default is indefinite, regulator-driven TTL via `SACP_AUDIT_RETENTION_DAYS`), CHK017 / CHK020 (cross-ref 002 §FR-A1 bcrypt cost factor), CHK018 (atomic = `async with conn.transaction()`), CHK019 (cross-ref 007 §FR-012 ScrubFilter), CHK021 (FR-007 / FR-008 enforced by same interface-level mechanism), CHK023 / CHK033 / CHK034 (no per-event SC for orphan / encryption / cascade duration — implicit in FR-009 / FR-011), CHK024 (no SC for startup fail-closed — accepted; tested via integration on every deploy), CHK025 (partial-cascade failure rolled back by transaction — `async with conn.transaction()` ensures all-or-nothing), CHK026 (concurrent-write races covered by FR-009 RI + advisory lock per 003), CHK027 (forward-only migration partial-apply — alembic offers `downgrade()` for staging; production is forward-only by Assumption), CHK031 (parent_turn-of-deleted-message — Phase 3 branching concern), CHK035 (DB role enforcement test — staged with FR-022), CHK036 (Fernet AES-128-CBC re-eval — when AES-128 is deprecated by NIST, OR every 5 years), CHK037 (summary content as message — accepted: summary IS a message per 005 FR-005), CHK038 (FR-019 vs erasure — operator policy resolves), CHK039 ("normal application path" = anything routed through repositories).

## Operations (Phase E fix/001-operations, 2026-05-02)

This section documents 001's operator-facing architectural decisions and Phase 3 deferrals. Operator playbook (procedures, drills, env-var triage) lives in `docs/operational-runbook.md`; this section covers the contracts and deferral triggers.

### Encryption at transit

Database connections MUST use TLS in production. Connection-string pattern:

- Production: `postgresql://user:pass@host:5432/db?sslmode=require` (or `sslmode=verify-full` if the operator manages the CA chain)
- LAN / dev: `sslmode=disable` is acceptable; documented in deployment readme

The orchestrator does NOT enforce `sslmode=require` at the validator layer in Phase 1 — operators are responsible. Phase 3 trigger: any deployment with regulatory transport-encryption requirements MUST validate `sslmode=require` at startup.

### sacp_app SQL role timeline (FR-022)

FR-022 promises a future hardening pass where the orchestrator binds with a least-privileged Postgres role (`sacp_app`) that lacks DDL / DROP privileges. Phase 1 status:

- Today: orchestrator binds with the operator-supplied connection string; typical operator deployments run as the database owner
- Phase 3 trigger: any production deployment where database compromise via the orchestrator would cascade beyond the SACP schema. Implementation surface: alembic migration creating `sacp_app` role with INSERT/UPDATE/DELETE/SELECT only; deploy-time check that the connection string targets that role

### Audit-log purge enforcer (FR-019, deferred)

`SACP_AUDIT_RETENTION_DAYS` is a reserved env var per FR-019; the purge job itself is deferred to Phase 3 (see `docs/retention.md` §7). Pre-wire, the effective retention is "never delete" regardless of env-var value. Operators that need bounded retention pre-Phase-3 run an external query — see `docs/operational-runbook.md` §2.5.

Phase 3 trigger: any deployment with a hard-cap retention requirement (regulatory or storage-cost driven). Implementation surface: a daily background coroutine that runs `DELETE FROM admin_audit_log WHERE created_at < NOW() - INTERVAL '$SACP_AUDIT_RETENTION_DAYS days'` with a row-deleted counter for retention-monitoring (per `docs/retention.md` §6).

### Deploy-time alembic safety

`alembic upgrade head` runs at orchestrator startup and applies any pending migrations. Phase 1 has no operator approval gate — the deploy applies whatever migrations are pending. This is acceptable because:

1. All migrations are forward-only (FR-017); a destructive migration cannot be rolled back via `alembic downgrade`
2. The schema-mirror CI gate ensures `tests/conftest.py` raw DDL stays in sync with migrations, so a destructive change without test coverage fails CI before deploy
3. Restore-from-backup is the documented rollback path (see `docs/operational-runbook.md` §2)

Phase 3 trigger: any operator deployment policy that requires manual approval gates between staging and production migration application. Implementation surface: a `--print-pending-migrations` CLI flag that emits the planned migrations and exits 0; a separate `alembic upgrade head` invocation applies them after operator review.

### Database operations contracts

Phase 1 contract: single logical Postgres database, single writer. The orchestrator's advisory-lock semantics (003 §FR-022) require the writer to be the same instance handling the turn-loop coroutine. Multi-writer / multi-instance deployment is Phase 3 (cross-ref 003 §FR-027).

Operator-facing topology decisions (connection-pool tuning, DB failover behavior, standby / replica strategy, RTO / RPO) live in `docs/operational-runbook.md` §10.

### Cross-references

- `docs/operational-runbook.md` — operator procedures (§1 deploy, §2 backup/restore, §3 key rotation, §10 DB ops)
- `docs/retention.md` — per-table retention with §FR-019 pattern as canonical
- 001 §FR-017 — forward-only migration constraint
- 001 §FR-019 — admin_audit_log retention pattern + reserved env var
- 001 §FR-020, §FR-021 — encryption-at-rest scope + key-rotation deferral
- 001 §FR-022 — sacp_app SQL role future hardening
- 003 §FR-022, §FR-027 — advisory lock + single-loop-per-session deployment requirement

## Migration safety notes (Phase F amendment, 2026-05-02)

These items capture the operational stance around schema evolution and
reference the FR-017 forward-only invariant. Sourced from the
pre-Phase-3 audit window's migration-safety review.

**Forward-only codification boundary.** FR-017 is enforced from
revision 008 onward. Migrations 001-007 shipped with real `downgrade()`
bodies before FR-017 was codified and are grandfathered. Every
migration with revision >= 008 MUST have a `downgrade()` body that is
exactly `pass` (with a docstring). The CI guard
`tests/test_migration_safety.py::test_fr017_post_codification_migrations_have_pass_downgrade`
fails the build on any violation. Migration 009's downgrade was
re-emptied to `pass` in this branch after slipping past FR-017 review.

**Migration catalog.** The currently-shipped migrations and their risk
classification:

| Revision | File | Risk | Notes |
|---|---|---|---|
| 001 | `001_initial_schema.py` | schema-only | Initial create; grandfathered downgrade. |
| 002 | `002_add_token_expiry.py` | additive | New columns; grandfathered downgrade. |
| 003 | `003_increase_turn_timeout.py` | data-only | Default change; grandfathered downgrade. |
| 004 | `004_convergence_log_composite_pk.py` | structural | PK reshape; grandfathered downgrade. |
| 005 | `005_session_review_gate_pause_scope.py` | additive | New column; grandfathered downgrade. |
| 006 | `006_security_events.py` | additive | New table; grandfathered downgrade. |
| 007 | `007_audit_log_survives_deletion.py` | structural | FK removal; grandfathered downgrade. |
| 008 | `008_security_events_instrumentation.py` | additive | Forward-only `pass` downgrade. |
| 009 | `009_auth_token_lookup_index.py` | additive | Forward-only `pass` downgrade. |

**Migration ordering across alembic + conftest DDL.** Schema changes
land in two places: `alembic/versions/<rev>_*.py` (production migration)
AND `tests/conftest.py` raw DDL (test fixture). Both MUST be updated in
the same commit; the CI gate `scripts/check_schema_mirror.py` (012 US7)
catches drift between the two. The author of a new migration is
responsible for both updates; reviewers verify the DDL match before
merge.

**Migration rollout strategy.** Phase 1 single-instance topology:
migrations run at process startup via the Dockerfile CMD
`alembic upgrade head && python -m src.run_apps`. The `&&` short-circuit
prevents app start on migration failure. Phase 3 multi-instance topology
will require an explicit migration-locking contract (see deferred test
marker `test_migration_locking_under_concurrent_startup_deferred`);
Phase 1 relies on the implicit "exactly one orchestrator process per
session" invariant (003 §FR-027).

**Destructive-migration approval gate.** Migrations 008+ are forward-
only. Any new migration whose `upgrade()` introduces a `DROP TABLE` or
`DROP COLUMN` MUST include an inline approval comment
(`# approved by <reviewer-name>`) above the destructive statement. The
CI guard
`tests/test_migration_safety.py::test_upgrade_destructive_ops_are_documented_at_revision_boundary`
enforces this. Intent: destructive schema changes are operationally
significant and require a human reviewer's explicit sign-off in source.

**Migration-replay / partial-failure / idempotency / restore-from-old-
backup tests.** All four are DB-backed and require a Postgres fixture.
Skipped markers in `tests/test_migration_safety.py` pin the activation
triggers; the cross-spec integration audit (Batch 4) is the natural home
once it ships its Postgres fixture catalog.

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): All seven (1–7). The core data model is topology-agnostic — it persists sessions, participants, and messages equally whether the orchestrator drives turns (1–6) or participants run AI client-side (7 MCP-to-MCP). Schema support for branches and tree structure (parent_turn) is intentionally topology-neutral.

**Use cases** (per constitution §1): Foundational — all seven use cases depend on this (distributed teams, research co-authorship, consulting, open-source, technical audits, asymmetric expertise, zero-trust cross-org). The data model is the substrate for every scenario.
