# Tasks: Core Data Model

**Input**: Design documents from `/specs/001-core-data-model/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/repository.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependency management, and directory scaffolding

- [X] T001 Create project directory structure per plan.md: `src/`, `src/database/`, `src/models/`, `src/repositories/`, `alembic/`, `tests/`
- [X] T002 Configure pyproject.toml with dependencies: fastapi, asyncpg, alembic, cryptography, bcrypt, pytest, pytest-asyncio, httpx, ruff
- [X] T003 [P] Create `src/config.py` — settings dataclass loading from environment variables (SACP_ENCRYPTION_KEY, POSTGRES_*, POOL_MIN_SIZE, POOL_MAX_SIZE)
- [X] T004 [P] Create `src/models/types.py` — enums for RoutingPreference (8 modes), SpeakerType, SessionStatus, ParticipantStatus, BranchStatus, RoutingAction, ComplexityScore, ModelTier, PromptTier, ModelFamily, CadencePreset, AcceptanceMode, ReviewGateStatus, InterruptStatus, ProposalStatus, VoteChoice
- [X] T005 [P] Create `docker-compose.yml` with PostgreSQL 16 service (port 5432, volume mount, health check)
- [X] T006 [P] Create `.env.example` updates for database connection and encryption key variables

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database connectivity, encryption, migrations — MUST complete before ANY user story

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 Implement `src/database/connection.py` — asyncpg pool lifecycle (create_pool, close_pool) with configurable min/max size and statement/idle timeouts per constitution §6.2
- [X] T008 Implement `src/database/encryption.py` — Fernet encrypt/decrypt helpers wrapping cryptography.fernet; fail-closed if SACP_ENCRYPTION_KEY not set (raise EncryptionKeyMissing)
- [X] T009 [P] Create `src/repositories/base.py` — BaseRepository class holding pool reference and helper methods for prepared statement execution
- [X] T010 Initialize Alembic: create `alembic/alembic.ini` and `alembic/env.py` configured for asyncpg (programmatic runner)
- [X] T011 Create initial migration `alembic/versions/001_initial_schema.py` — all 13 tables with constraints, composite PKs, foreign keys, and indexes per data-model.md
- [X] T012 Create `src/database/roles.sql` — SQL script defining sacp_app role (INSERT+SELECT on log/message tables, full CRUD on mutable tables) and sacp_cleanup role (DELETE for session deletion)
- [X] T013 Create `tests/conftest.py` — pytest fixtures for test database creation, asyncpg pool, migration runner, and per-test transaction rollback isolation

**Checkpoint**: Database connected, schema deployed, encryption working, test harness ready

---

## Phase 3: User Story 1 — Facilitator Creates a Session (Priority: P1) MVP

**Goal**: Create sessions with configuration, auto-bootstrap 'main' branch and facilitator participant

**Independent Test**: Create a session → verify session record, facilitator participant, and 'main' branch all exist with correct defaults

- [X] T014 [P] [US1] Create `src/models/session.py` — Session and Branch frozen dataclasses with `from_record()` factory classmethods
- [X] T015 [P] [US1] Create `src/models/participant.py` — Participant frozen dataclass with `from_record()` factory classmethod (api_key_encrypted remains encrypted in model)
- [X] T016 [US1] Implement `src/repositories/session_repo.py` — create_session (atomic: session + main branch + facilitator participant), get_session, list_sessions; uses prepared statements for get_session
- [X] T017 [US1] Write `tests/test_session_crud.py` — test session creation persists with correct defaults, facilitator linked, main branch created; test get_session retrieval; test referential integrity

**Checkpoint**: Sessions can be created and queried with full atomicity

---

## Phase 4: User Story 2 — Participant Joins and Configuration Persists (Priority: P1)

**Goal**: Add participants with model config, routing prefs, budget, and encrypted API key

**Independent Test**: Add a participant → verify all fields persist, API key is encrypted at rest, budget values exact

- [X] T018 [US2] Implement `src/repositories/participant_repo.py` — add_participant (encrypts API key, hashes auth token), get_participant, update_participant (partial update, re-encrypts key if changed), list_participants
- [X] T019 [US2] Write `tests/test_participant.py` — test participant creation with all config fields; test API key is Fernet-encrypted at rest (not plaintext); test budget values stored exactly; test auth token stored as bcrypt hash only
- [X] T020 [US2] Write `tests/test_encryption.py` — Fernet roundtrip test; fail-closed test when SACP_ENCRYPTION_KEY missing; test key material never appears in repr/str/logs

**Checkpoint**: Participants can join with encrypted credentials and exact config persistence

---

## Phase 5: User Story 3 — Conversation Messages Recorded Immutably (Priority: P1)

**Goal**: Append messages to transcript; enforce immutability; support tree structure

**Independent Test**: Append messages → verify sequential turn numbers, correct speaker attribution, no update/delete possible, parent_turn navigation works

- [X] T021 [P] [US3] Create `src/models/message.py` — Message frozen dataclass with composite identity (turn_number, session_id, branch_id) and `from_record()` factory
- [X] T022 [US3] Implement `src/repositories/message_repo.py` — append_message (auto-assigns turn_number, prepared statement), get_recent (prepared statement), get_range, get_by_speaker, get_summaries; NO update/delete methods
- [X] T023 [US3] Write `tests/test_messages.py` — test append persists with correct turn number and branch; test immutability (UPDATE/DELETE rejected via DB role); test multiple speaker types; test parent_turn tree traversal; test composite PK prevents duplicates

**Checkpoint**: Messages append immutably with tree structure support

---

## Phase 6: User Story 4 — Operational Logs Capture Every Decision (Priority: P2)

**Goal**: Append-only routing, usage, convergence, and admin audit logs

**Independent Test**: Insert log entries → verify persistence; attempt update/delete → verify rejection

- [X] T024 [P] [US4] Create `src/models/logs.py` — RoutingLog, UsageLog, ConvergenceLog, AdminAuditLog frozen dataclasses with `from_record()` factories
- [X] T025 [US4] Implement `src/repositories/log_repo.py` — log_routing (prepared statement), log_usage, log_convergence, log_admin_action; get_routing_history, get_participant_usage, get_participant_cost (budget aggregation), get_convergence_window, get_audit_log; NO update/delete methods
- [X] T026 [US4] Write `tests/test_logs.py` — test each log type inserts correctly; test append-only enforcement (UPDATE/DELETE rejected via DB role); test get_participant_cost aggregation for budget enforcement; test convergence window query

**Checkpoint**: All 4 log types append-only and queryable

---

## Phase 7: User Story 5 — Session Lifecycle Management (Priority: P2)

**Goal**: Pause, resume, archive, and atomically delete sessions

**Independent Test**: Transition session through all states → verify access restrictions and atomic cleanup

- [X] T027 [US5] Extend `src/repositories/session_repo.py` — update_status (validates transition: active↔paused, active/paused→archived, any→deleted; raises InvalidTransition on illegal), delete_session (uses sacp_cleanup role, atomically removes all data except admin_audit_log deletion record)
- [X] T028 [US5] Write `tests/test_lifecycle.py` — test valid transitions (active→paused→active, active→archived); test invalid transitions rejected; test atomic deletion removes messages/participants/logs/invites/proposals but preserves admin_audit_log entry; test archived session is read-only (message append rejected)

**Checkpoint**: Full session lifecycle with atomic deletion

---

## Phase 8: User Story 6 — Human Interjections via Interrupt Queue (Priority: P2)

**Goal**: Priority-ordered human interjection queue with delivery tracking

**Independent Test**: Enqueue interjections with different priorities → verify delivery order (priority DESC, then FIFO)

- [X] T029 [US6] Implement `src/repositories/interrupt_repo.py` — enqueue, get_pending (prepared statement, ordered by priority DESC + created_at ASC), mark_delivered
- [X] T030 [US6] Write `tests/test_interrupt_queue.py` — test enqueue persists with correct priority and pending status; test priority ordering (high before normal); test FIFO within same priority; test mark_delivered updates status and timestamp

**Checkpoint**: Interrupt queue correctly prioritizes and tracks delivery

---

## Phase 9: User Story 7 — Review Gate Draft Staging (Priority: P2)

**Goal**: Stage AI responses for human review with full lifecycle tracking

**Independent Test**: Create draft → test each resolution path (approve, edit, reject, timeout)

- [X] T031 [US7] Implement `src/repositories/review_gate_repo.py` — create_draft, get_pending, resolve (validates resolution status, stores edited_content if 'edited', sets resolved_at)
- [X] T032 [US7] Write `tests/test_review_gate.py` — test draft creation with pending status; test approve path; test edit path (edited_content stored); test reject path; test timeout path; test resolved_at timestamp set

**Checkpoint**: Review gate drafts fully lifecycle-managed

---

## Phase 10: User Story 8 — Invitations and Join Flow (Priority: P3)

**Goal**: Hashed invite tokens with use limits and expiry

**Independent Test**: Create invite → redeem → verify hash storage, use count, expiry enforcement

- [X] T033 [US8] Implement `src/repositories/invite_repo.py` — create_invite (returns Invite + plaintext_token), redeem_invite (hashes token, validates use count and expiry, increments uses, raises InviteExpired/InviteExhausted), list_invites
- [X] T034 [US8] Write `tests/test_invites.py` — test token stored as hash only (plaintext not in DB); test use count increments; test single-use invite rejected on second use; test expired invite rejected; test multi-use invite works up to max_uses

**Checkpoint**: Invitations work with hash-only storage and limit enforcement

---

## Phase 11: User Story 9 — Proposals and Voting (Priority: P3)

**Goal**: Proposals with acceptance modes and one-vote-per-participant

**Independent Test**: Create proposal → cast votes → verify acceptance logic and duplicate prevention

- [X] T035 [US9] Implement `src/repositories/proposal_repo.py` — create_proposal, cast_vote (raises DuplicateVote if already voted), get_votes, resolve_proposal, get_open_proposals
- [X] T036 [US9] Write `tests/test_proposals.py` — test proposal creation with acceptance_mode; test vote recording; test duplicate vote rejected; test unanimous acceptance (all vote accept → status accepted); test proposal expiry

**Checkpoint**: Proposal/voting system enforces acceptance modes and uniqueness

---

## Phase 12: Polish & Cross-Cutting Concerns

**Purpose**: Participant departure, error handling, and validation across all stories

- [X] T037 Implement participant departure in `src/repositories/participant_repo.py` — depart_participant (overwrite api_key_encrypted with random bytes, invalidate auth_token_hash, set status='offline', retain messages)
- [X] T038 [P] Create `src/repositories/__init__.py` — export all repository classes; create `src/models/__init__.py` — export all model classes and types
- [X] T039 [P] Create error types module `src/repositories/errors.py` — InvalidTransition, DuplicateVote, InviteExpired, InviteExhausted, EncryptionKeyMissing, SessionNotActive
- [X] T040 Write `tests/test_departure.py` — test API key overwritten (not nulled) on departure; test auth token invalidated; test status set to offline; test messages retained in transcript
- [X] T041 Validate quickstart.md end-to-end — run all steps from `specs/001-core-data-model/quickstart.md` in a clean environment
- [X] T042 Run full test suite and verify all user story checkpoints pass independently

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational — first MVP slice
- **US2 (Phase 4)**: Depends on Foundational + US1 (needs session to join)
- **US3 (Phase 5)**: Depends on Foundational + US1 + US2 (needs session + participant to send messages)
- **US4 (Phase 6)**: Depends on Foundational — can run parallel to US1-3 if needed
- **US5 (Phase 7)**: Depends on US1 + US3 (needs sessions with data to test lifecycle/deletion)
- **US6 (Phase 8)**: Depends on Foundational + US1 + US2 — can run parallel to US3-5
- **US7 (Phase 9)**: Depends on Foundational + US1 + US2 — can run parallel to US3-6
- **US8 (Phase 10)**: Depends on Foundational + US1 — can run parallel to US2-7
- **US9 (Phase 11)**: Depends on Foundational + US1 + US2 — can run parallel to US3-8
- **Polish (Phase 12)**: Depends on all desired user stories being complete

### Within Each User Story

- Repository implementation before tests (tests validate the repository)
- Models before repositories (repositories return model instances)
- Core operations before edge cases

### Parallel Opportunities

- T003, T004, T005, T006 can all run in parallel (Setup phase)
- T008, T009 can run in parallel (Foundational, different files)
- T014, T015 can run in parallel (US1 models, different files)
- T024 can run parallel with US3 work (US4 models, different file)
- US6, US7, US8, US9 can all run in parallel after Foundational complete
- T038, T039 can run in parallel (Polish, different files)

---

## Parallel Example: User Story 1 (Session Creation)

```bash
# Launch models in parallel:
Task: "Create Session+Branch dataclasses in src/models/session.py"     # T014
Task: "Create Participant dataclass in src/models/participant.py"      # T015

# Then sequentially:
Task: "Implement SessionRepository in src/repositories/session_repo.py"  # T016
Task: "Write session CRUD tests in tests/test_session_crud.py"           # T017
```

---

## Implementation Strategy

### MVP First (User Stories 1-3 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: US1 — Session creation
4. Complete Phase 4: US2 — Participant join
5. Complete Phase 5: US3 — Message append
6. **STOP and VALIDATE**: Test US1-3 independently — can create sessions, add participants, and record immutable messages
7. This is a functional data layer for the core conversation loop

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 + US2 + US3 → Core conversation data (MVP!)
3. US4 → Operational logging and transparency
4. US5 → Session lifecycle management
5. US6 + US7 → Human-AI coordination (interrupt queue + review gate)
6. US8 + US9 → Participation management (invites + proposals)
7. Polish → Departure handling, error types, validation

### Suggested MVP Scope

**US1 + US2 + US3** (Phases 3-5): Sessions, participants, and messages. This delivers a functional data layer that the turn loop and MCP server features can build on.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- 25/5 coding standards enforced by pre-commit — factor functions into helpers proactively
