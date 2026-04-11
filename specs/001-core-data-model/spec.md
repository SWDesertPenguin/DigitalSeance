# Feature Specification: Core Data Model

**Feature Branch**: `001-core-data-model`
**Created**: 2026-04-11
**Status**: Draft
**Input**: User description: "Core data model and database schema — tables for sessions, participants, messages, append-only logs, and migrations foundation for SACP Phase 1"

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
- What happens when a participant departs? Their API key is overwritten (not nulled), auth token is invalidated, status set to 'offline', but their messages remain in the transcript.
- What happens when turn numbers collide on the same branch? The composite primary key (turn_number, session_id, branch_id) prevents duplicates — the insert is rejected.
- What happens when a session has no 'main' branch? Session creation MUST atomically create the 'main' branch to prevent orphaned messages.
- What happens when the encryption key is unavailable at startup? The system MUST fail closed — no API key decryption, no provider dispatch, clear error surfaced.

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
- **FR-013**: System MUST support proposals with per-session acceptance modes (unanimous, majority, facilitator) and one-vote-per-participant enforcement.
- **FR-014**: System MUST support interrupt queue entries with priority levels and delivery tracking.
- **FR-015**: System MUST support review gate draft staging with resolution status tracking (pending, approved, edited, rejected, timed out).
- **FR-016**: System MUST overwrite (not null) API key material when a participant departs, and invalidate their auth token.
- **FR-017**: System MUST support schema evolution through versioned, forward-only migrations.
- **FR-018**: System MUST include tree-structure support (parent_turn, branch_id) in the message data model from the initial release, even though branching UI is deferred to Phase 3.

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
