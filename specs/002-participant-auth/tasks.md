# Tasks: Participant Auth & Lifecycle

**Input**: Design documents from `/specs/002-participant-auth/`
**Prerequisites**: plan.md, spec.md, research.md, contracts/auth-service.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Schema migration, error types, auth module scaffolding

- [X] T001 Create `src/auth/` directory with `__init__.py`
- [X] T002 Create migration `alembic/versions/002_add_token_expiry.py` — add `token_expires_at` TIMESTAMP and `bound_ip` TEXT columns to participants table (both nullable)
- [X] T003 [P] Add error types to `src/repositories/errors.py` — TokenExpiredError, TokenInvalidError, AuthRequiredError, NotFacilitatorError, IPBindingMismatchError
- [X] T004 [P] Create `src/auth/guards.py` — require_facilitator, require_active, require_pending, require_not_self guard functions

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core auth service with token validation — ALL stories depend on this

**CRITICAL**: No user story work can begin until token validation works

- [X] T005 Implement `src/auth/service.py` — AuthService class with `__init__(pool, encryption_key, token_expiry_days)` and `authenticate(token, client_ip)` method (bcrypt validation, expiry check, IP binding)
- [X] T006 Extend `src/repositories/participant_repo.py` — add `find_by_token_hash(token)` helper that scans participants for matching bcrypt hash
- [X] T007 Extend `src/repositories/participant_repo.py` — add `update_bound_ip(participant_id, ip)` and `update_token_expiry(participant_id, expires_at)` methods
- [X] T008 Update `tests/conftest.py` — add fixtures for AuthService, authenticated participant, session with facilitator and pending participant

**Checkpoint**: Token validation works — valid tokens authenticate, invalid/expired/missing tokens rejected

---

## Phase 3: User Story 1 — Token Authentication (Priority: P1) MVP

**Goal**: Validate bearer tokens against bcrypt hashes with expiry and error distinction

**Independent Test**: Present valid, invalid, expired, and missing tokens → verify correct accept/reject with distinct errors

- [X] T009 [US1] Write `tests/test_auth_service.py` — test valid token authenticates; test invalid token raises TokenInvalidError; test expired token raises TokenExpiredError; test missing token raises AuthRequiredError; test token plaintext never in log output
- [X] T010 [US1] Verify AuthService.authenticate handles all edge cases — concurrent validation, bcrypt timing consistency, empty token string

**Checkpoint**: Authentication layer operational with distinct error types

---

## Phase 4: User Story 2 — Participant Approval Flow (Priority: P1)

**Goal**: Facilitator approves/rejects pending participants; auto-approve mode

**Independent Test**: Create pending participant → approve → verify role change, timestamp, audit log

- [X] T011 [US2] Implement `AuthService.approve_participant(facilitator_id, participant_id)` in `src/auth/service.py` — guard facilitator, guard pending, update role + approved_at, log to admin audit
- [X] T012 [US2] Implement `AuthService.reject_participant(facilitator_id, participant_id, reason)` in `src/auth/service.py` — guard facilitator, guard pending, remove record, log rejection
- [X] T013 [US2] Extend `src/repositories/participant_repo.py` — add `approve(participant_id)` (sets role='participant', approved_at=NOW()) and `delete_participant(participant_id)` methods
- [X] T014 [US2] Write `tests/test_approval.py` — test approve changes role + sets timestamp + audit logged; test reject removes record + audit logged; test auto-approve bypasses manual step; test pending cannot inject messages; test non-facilitator approval rejected

**Checkpoint**: Full approval/rejection flow with audit trail

---

## Phase 5: User Story 3 — Token Rotation (Priority: P2)

**Goal**: Participant self-rotates token; old immediately invalid; expiry resets

**Independent Test**: Rotate → old token fails, new token works, expiry reset

- [X] T015 [US3] Implement `AuthService.rotate_token(participant_id)` in `src/auth/service.py` — generate new token, bcrypt hash, update auth_token_hash + token_expires_at + clear bound_ip, return plaintext
- [X] T016 [US3] Extend `src/repositories/participant_repo.py` — add `update_auth_token(participant_id, new_hash, expires_at)` and `clear_bound_ip(participant_id)` methods
- [X] T017 [US3] Write `tests/test_auth_service.py` (extend) — test rotation returns new token; test old token rejected after rotation; test new token authenticates; test expiry reset; test bound_ip cleared

**Checkpoint**: Token rotation atomic and self-service

---

## Phase 6: User Story 4 — Token Revocation (Priority: P2)

**Goal**: Facilitator force-revokes participant token; audit logged

**Independent Test**: Revoke → token invalid, audit log entry exists

- [X] T018 [US4] Implement `AuthService.revoke_token(facilitator_id, participant_id)` in `src/auth/service.py` — guard facilitator, generate random hash (invalidates), clear bound_ip, log to admin audit
- [X] T019 [US4] Write `tests/test_auth_service.py` (extend) — test revoked token rejected; test audit log records revocation; test non-facilitator revocation rejected

**Checkpoint**: Facilitator can immediately cut off access

---

## Phase 7: User Story 5 — Facilitator-Initiated Removal (Priority: P2)

**Goal**: Facilitator removes participant with auth gate and audit trail

**Independent Test**: Remove as facilitator → departure logic runs + audit logged; remove as non-facilitator → rejected

- [X] T020 [US5] Implement `AuthService.remove_participant(facilitator_id, participant_id, reason)` in `src/auth/service.py` — guard facilitator, guard not self, call existing depart_participant, log to admin audit with reason
- [X] T021 [US5] Write `tests/test_approval.py` (extend) — test removal triggers departure logic; test messages retained; test audit log with reason; test non-facilitator rejected; test self-removal rejected

**Checkpoint**: Authorized removal with full audit trail

---

## Phase 8: User Story 8 — Session IP Binding (Priority: P2)

**Goal**: Bind authenticated session to client IP; reject mismatches

**Independent Test**: Auth from IP A → request from IP B rejected; rotation resets binding

- [X] T022 [US8] Write `tests/test_ip_binding.py` — test first auth binds IP; test same IP accepted; test different IP raises IPBindingMismatchError; test rotation clears binding; test new token binds to new IP

**Checkpoint**: IP binding enforced as defense-in-depth

---

## Phase 9: User Story 6 — Facilitator Transfer (Priority: P3)

**Goal**: Transfer facilitator role atomically; both roles update

**Independent Test**: Transfer → old facilitator becomes participant, new becomes facilitator, session reference updates

- [X] T023 [US6] Implement `AuthService.transfer_facilitator(facilitator_id, target_id)` in `src/auth/service.py` — guard facilitator, guard target active (not pending), update both roles + session.facilitator_id atomically, log to admin audit
- [X] T024 [US6] Extend `src/repositories/participant_repo.py` — add `update_role(participant_id, new_role)` method
- [X] T025 [US6] Extend `src/repositories/session_repo.py` — add `update_facilitator(session_id, new_facilitator_id)` method
- [X] T026 [US6] Write `tests/test_facilitator.py` — test transfer updates both roles; test session facilitator_id updates; test audit log records transfer; test transfer to pending rejected; test non-facilitator transfer rejected

**Checkpoint**: Facilitator role transferable with full audit

---

## Phase 10: User Story 7 — Token Expiry (Priority: P3)

**Goal**: Enforce configurable token expiry; distinct error from invalid

**Independent Test**: Create token with short expiry → wait → authentication rejected with TokenExpiredError

- [X] T027 [US7] Write `tests/test_token_expiry.py` — test expired token raises TokenExpiredError (distinct from TokenInvalidError); test non-expired token authenticates normally; test rotation resets expiry; test configurable expiry period

**Checkpoint**: Expiry enforced with clear error distinction

---

## Phase 11: Polish & Cross-Cutting

**Purpose**: Module exports, integration validation

- [X] T028 [P] Update `src/auth/__init__.py` — export AuthService and guard functions
- [X] T029 [P] Update `src/repositories/errors.py` exports in `src/repositories/__init__.py` — add new error types
- [X] T030 Run full test suite (features 001 + 002) and verify no regressions

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all stories
- **US1 (Phase 3)**: Depends on Foundational (token validation must exist)
- **US2 (Phase 4)**: Depends on Foundational
- **US3 (Phase 5)**: Depends on US1 (needs working auth to test rotation)
- **US4 (Phase 6)**: Depends on US1 (needs working auth to test revocation)
- **US5 (Phase 7)**: Depends on US2 (needs approval flow for participant setup)
- **US8 (Phase 8)**: Depends on US1 (needs working auth to test IP binding)
- **US6 (Phase 9)**: Depends on US2 (needs approved participants to transfer to)
- **US7 (Phase 10)**: Depends on US1 (needs working auth to test expiry)
- **Polish (Phase 11)**: Depends on all stories complete

### Parallel Opportunities

- T003, T004 can run in parallel (Setup, different files)
- US3, US4, US8, US7 can all run in parallel after US1 (independent auth extensions)
- T028, T029 can run in parallel (Polish, different files)

---

## Implementation Strategy

### MVP First (US1 + US2 Only)

1. Setup + Foundational → Auth infrastructure
2. US1 → Token validation works
3. US2 → Approval flow works
4. **STOP and VALIDATE**: Can authenticate and approve participants

### Suggested MVP Scope

**US1 + US2** (Phases 3-4): Token authentication + approval flow. Delivers a working auth layer that the MCP server can build on.

---

## Notes

- This feature extends existing repositories — do NOT create new repository files for participant operations
- AuthService is the only new module — it orchestrates existing repos
- All guard functions raise typed errors, never return booleans
- bcrypt validation is intentionally slow (~200ms) — do not cache or shortcut
- 30 tasks total, compact because much infrastructure exists from feature 001
