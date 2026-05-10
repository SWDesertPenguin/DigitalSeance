---

description: "Task list for spec 023 — User Accounts with Persistent Session History"
---

# Tasks: User Accounts with Persistent Session History

**Input**: Design documents from `/specs/023-user-accounts/`
**Prerequisites**: plan.md (loaded), spec.md (4 user stories — US1 P1 create+verify+login, US2 P1 /me/sessions, US3 P2 account settings, US4 P3 ownership transfer DEFERRED per research §7), research.md (13 sections), data-model.md, contracts/account-endpoints.md, contracts/env-vars.md, contracts/email-transport.md, contracts/audit-log-events.md, contracts/codes.md, quickstart.md

**Tests**: INCLUDED. Spec defines 12 Success Criteria (SC-001..SC-012) framed as enforceable contracts; plan.md and research.md cite specific test files for FR coverage. Tests ship alongside implementation per the spec 025 / 029 precedent.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing. Phase 1 covers shared infrastructure (V16 deliverable gate per FR-022, schema migration with conftest mirror per memory `feedback_test_schema_mirror`, the spec 011 amendment forward-ref FRs landing alongside the validators).

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, OR independent functions in the same file with no shared edit point)
- **[Story]**: US1 / US2 / US3 (US4 deferred per research §7; no tasks emitted for it)
- All file paths are absolute or relative to the 023 worktree (`s:\GitHub\DigitalSeance\.claude\worktrees\agent-023\`)

## Path Conventions

- Backend Python: `src/accounts/`, `src/repositories/`, `src/web_ui/`, `src/config/`, `src/models/`
- Frontend (CDN-loaded React JSX, no build toolchain per spec 011 FR-002): `frontend/app.jsx`, `frontend/*.js`
- Tests: `tests/` (pytest) and `tests/frontend/` (Node-runnable per memory `frontend_polish_module_pattern`)
- CI scripts: `scripts/`
- Docs: `docs/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: V16 env-var deliverables (7 validators + 7 docs sections per FR-022), schema migration with conftest mirror, spec 011 amendment forward-ref FRs, baseline validator tests. The V16 gate is non-negotiable per FR-022.

**⚠️ CRITICAL**: No user-story task in Phase 2+ may begin until Phase 1 completes. Spec 023's V16 gate covers seven new env vars (the largest single-spec V16 batch in the project so far).

### V16 deliverable gate (7 validators + 7 doc sections)

- [X] T001 [P] Add `validate_accounts_enabled` to [src/config/validators.py](./../../src/config/validators.py) per [contracts/env-vars.md §SACP_ACCOUNTS_ENABLED](./contracts/env-vars.md): bool-style enum `'0'|'1'`, default `'0'`; out-of-set exits at startup. Reuses the existing `_validate_bool_enum` helper.
- [X] T002 [P] Add `validate_password_argon2_time_cost` to [src/config/validators.py](./../../src/config/validators.py) per [contracts/env-vars.md §SACP_PASSWORD_ARGON2_TIME_COST](./contracts/env-vars.md): empty OR int in `[1, 10]`; out-of-range exits at startup.
- [X] T003 [P] Add `validate_password_argon2_memory_cost_kb` to [src/config/validators.py](./../../src/config/validators.py) per [contracts/env-vars.md §SACP_PASSWORD_ARGON2_MEMORY_COST_KB](./contracts/env-vars.md): empty OR int in `[7168, 1048576]`; out-of-range exits at startup.
- [X] T004 [P] Add `validate_account_session_ttl_hours` to [src/config/validators.py](./../../src/config/validators.py) per [contracts/env-vars.md §SACP_ACCOUNT_SESSION_TTL_HOURS](./contracts/env-vars.md): empty OR int in `[1, 8760]`; out-of-range exits at startup.
- [X] T005 [P] Add `validate_account_rate_limit_per_ip_per_min` to [src/config/validators.py](./../../src/config/validators.py) per [contracts/env-vars.md §SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN](./contracts/env-vars.md): empty OR int in `[1, 1000]`; out-of-range exits at startup.
- [X] T006 [P] Add `validate_email_transport` to [src/config/validators.py](./../../src/config/validators.py) per [contracts/env-vars.md §SACP_EMAIL_TRANSPORT](./contracts/env-vars.md): string enum `noop|smtp|ses|sendgrid`, default `noop`; out-of-set exits at startup. The `smtp/ses/sendgrid` values pass syntactic validation here; the adapter factory raises `NotImplementedError` at startup per research.md §4.
- [X] T007 [P] Add `validate_account_deletion_email_grace_days` to [src/config/validators.py](./../../src/config/validators.py) per [contracts/env-vars.md §SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS](./contracts/env-vars.md): empty OR int in `[0, 365]` (`0` disables grace period entirely); out-of-range exits at startup.
- [X] T008 Append the seven new validators to the `VALIDATORS` tuple at the bottom of [src/config/validators.py](./../../src/config/validators.py) (depends on T001-T007).
- [X] T009 [P] Add `### SACP_ACCOUNTS_ENABLED` section to [docs/env-vars.md](./../../docs/env-vars.md) with the six standard fields per [contracts/env-vars.md](./contracts/env-vars.md).
- [X] T010 [P] Add `### SACP_PASSWORD_ARGON2_TIME_COST` section to [docs/env-vars.md](./../../docs/env-vars.md) with the six standard fields.
- [X] T011 [P] Add `### SACP_PASSWORD_ARGON2_MEMORY_COST_KB` section to [docs/env-vars.md](./../../docs/env-vars.md) with the six standard fields.
- [X] T012 [P] Add `### SACP_ACCOUNT_SESSION_TTL_HOURS` section to [docs/env-vars.md](./../../docs/env-vars.md) with the six standard fields.
- [X] T013 [P] Add `### SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN` section to [docs/env-vars.md](./../../docs/env-vars.md) with the six standard fields.
- [X] T014 [P] Add `### SACP_EMAIL_TRANSPORT` section to [docs/env-vars.md](./../../docs/env-vars.md) with the six standard fields. Note the v1 noop-only behavior + the `NotImplementedError` startup path for the reserved values.
- [X] T015 [P] Add `### SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS` section to [docs/env-vars.md](./../../docs/env-vars.md) with the six standard fields. Note that `0` disables the grace period.
- [X] T016 Run `python scripts/check_env_vars.py` from repo root and confirm V16 CI gate green for the seven new vars (validators + doc sections in lockstep). The gate only flags vars *read in src/* but missing from docs; for spec 023 the consumers land in Phase 2+, so the gate is expected to pass on validator+docs alone.
- [X] T017 [P] Validator unit tests in [tests/test_023_validators.py](./../../tests/test_023_validators.py): each of the seven validators — valid value passes, out-of-range raises `ConfigValidationError` naming the offending var, empty handled per the var's allowed-empty rule. Aggregate test confirms registration in the `VALIDATORS` tuple so `ConfigValidationError` fires at startup on misconfig. Includes the `SACP_EMAIL_TRANSPORT={smtp,ses,sendgrid}` reserved-value-passes-syntactic case (the `NotImplementedError` path lives in Phase 2 when the adapter factory lands).

### Schema migration + conftest mirror (single landing per memory `feedback_test_schema_mirror`)

- [X] T018 Generate alembic migration `015_user_accounts.py` in [alembic/versions/](./../../alembic/versions/) per [data-model.md "Schema additions"](./data-model.md): create `accounts` table (UUID `id`, `email` text, `password_hash` text, `status` text CHECK constrained, `created_at`/`updated_at`/`last_login_at`/`deleted_at`/`email_grace_release_at` timestamptz, partial unique index `accounts_email_active_uidx` on `(email)` WHERE `status IN ('pending_verification', 'active')`); create `account_participants` table (UUID `id`, `account_id` FK→accounts ON DELETE RESTRICT, `participant_id` text UNIQUE FK→participants ON DELETE CASCADE, `created_at`); add btree index on `account_participants(account_id)`. Pre-allocated slot: `revision = '015'`, `down_revision = '014'`. Mirror the same DDL into [tests/conftest.py](./../../tests/conftest.py) raw DDL in the same task per memory `feedback_test_schema_mirror`.
- [X] T019 Run `python scripts/check_schema_mirror.py` and confirm zero drift between alembic 015 and the conftest raw DDL. The schema-mirror gate parses both sources and diffs `{table: set(columns)}`; any drift surfaces as a non-zero exit with the diff on stderr.
- [X] T020 Migration upgrade/downgrade test in [tests/test_023_migration_015.py](./../../tests/test_023_migration_015.py): apply migration 015 to a fresh schema; assert both tables exist with the expected column set, the partial unique index covers only the active/pending statuses, the FK on `account_participants.account_id` is `ON DELETE RESTRICT`, the FK on `account_participants.participant_id` is `ON DELETE CASCADE` and unique. Forward-only per Constitution §6 + 001 §FR-017 — `downgrade()` is a no-op (matches the existing 011/013/014 pattern).

### Spec 011 amendment (lands here per memory `reminder_spec_011_amendments_at_impl_time`)

- [X] T021 Append spec 011 UI FRs FR-030..FR-034 to [specs/011-web-ui/spec.md](./../../specs/011-web-ui/spec.md) per [research.md §11](./research.md): login/logout flow + auth gate, account-creation form + verification UI, post-login session list with active/archived segmentation, account-settings panel (email change with notify-old + verify-new, password change preserving actor's sid, account deletion with export-on-delete confirmation). Match the format of the existing FR-025..FR-029 (spec 029) and FR-021..FR-024 (spec 025) amendments. Add a `### Session 2026-05-09 (spec 023 user-accounts amendment)` Clarifications entry. Add a "Phase 3c — Account UI (ships with spec 023)" subsection under "## Implementation Phases".

**Checkpoint**: V16 gate green; schema migration + conftest mirror landed; spec 011 amendment FRs appended. User-story phases unblocked.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: New top-level package skeletons, argon2-cffi dependency, the email-transport ABC + noop adapter, the password hasher, the codes primitive, the per-IP login rate limiter, the account repository, the SessionStore extension, the topology-7 mount gate, and the master-switch-off canary. All three user stories depend on these.

**⚠️ CRITICAL**: No user-story task in Phase 3+ may begin until Phase 2 completes.

### Dependency landing (research §1)

- [X] T022 Add `argon2-cffi` to [pyproject.toml](./../../pyproject.toml) and refresh the lockfile if applicable. Pin per Constitution §6.3 to a known-current version (research.md §1). The transitive `cffi` is already in the dependency tree via `cryptography`.

### Module skeletons

- [X] T023 [P] Create empty module skeletons under [src/accounts/](./../../src/accounts/): `__init__.py`, `service.py`, `hashing.py`, `codes.py`, `email_transport.py`, `rate_limit.py`. Each contains only a module docstring referencing spec 023.
- [X] T024 [P] Create empty module skeleton [src/repositories/account_repo.py](./../../src/repositories/account_repo.py) (module docstring referencing spec 023).
- [X] T025 [P] Create empty module skeleton [src/models/account.py](./../../src/models/account.py) (module docstring referencing spec 023).

### Argon2id wrapper + transparent re-hash

- [X] T026 [P] Implement `PasswordHasher` wrapper in [src/accounts/hashing.py](./../../src/accounts/hashing.py) per [research.md §1, §8](./research.md): `hash(plaintext) -> str`, `verify(stored_hash, plaintext) -> bool`, `needs_rehash(stored_hash) -> bool`. Reads `SACP_PASSWORD_ARGON2_TIME_COST` and `SACP_PASSWORD_ARGON2_MEMORY_COST_KB` at construction; `parallelism=1` hardcoded per FR-003. OWASP-floor WARN emit on below-floor parameter selection.

### Verification + reset code primitive

- [X] T027 [P] Implement code generation + HMAC hashing in [src/accounts/codes.py](./../../src/accounts/codes.py) per [research.md §3](./research.md) and [contracts/codes.md](./contracts/codes.md): 16-char Crockford base32 via `secrets.token_bytes(10)`; HMAC-SHA256 hash using `SACP_AUTH_LOOKUP_KEY`; `make_verification_code()` (24h TTL), `make_reset_code()` (30min TTL), `make_email_change_code()` (24h TTL); consumed-on-submit lookup against `admin_audit_log` rows.

### Email transport ABC + noop adapter

- [X] T028 [P] Define `EmailTransport` Protocol + `NoopEmailTransport` adapter in [src/accounts/email_transport.py](./../../src/accounts/email_transport.py) per [research.md §4](./research.md) and [contracts/email-transport.md](./contracts/email-transport.md): async `send(to, subject, body, purpose)` method; noop adapter writes a structured `admin_audit_log` row with `action='account_email_noop_emitted'` (purpose, hashed `to`, body length); body content NOT logged.
- [X] T029 Adapter factory in [src/accounts/email_transport.py](./../../src/accounts/email_transport.py): `select_transport()` reads `SACP_EMAIL_TRANSPORT`; returns `NoopEmailTransport()` for `noop`; raises `NotImplementedError` for `smtp/ses/sendgrid` with the documented message pointing at `contracts/email-transport.md`. Mounted at startup so misconfiguration exits before binding ports.

### Per-IP login rate limiter

- [X] T030 [P] Implement `LoginRateLimiter` sliding-window per-IP in [src/accounts/rate_limit.py](./../../src/accounts/rate_limit.py) per [research.md §5](./research.md): `dict[str, deque[float]]` keyed by `extract_client_ip(request)`; window = 60s; threshold = `SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN`; async `check(ip) -> None` raises `RateLimitExceeded` (HTTP 429 + `Retry-After`). Separate state from spec 019's middleware (FR-015 / clarify Q10).

### Account repository

- [X] T031 Implement `accounts` + `account_participants` CRUD in [src/repositories/account_repo.py](./../../src/repositories/account_repo.py) per [data-model.md](./data-model.md): `create_account`, `get_account_by_id`, `get_account_by_email_for_login` (case-insensitive email lookup; returns `None` if not found OR status='deleted'), `update_account_email`, `update_account_password_hash`, `mark_account_deleted` (zero email + password_hash; populate `deleted_at` + `email_grace_release_at`), `update_last_login_at`, `link_participant_to_account`, `list_participants_for_account`.

### SessionStore extension (spec 011 H-02 reuse + FR-011 reverse index)

- [X] T032 Extend [src/web_ui/session_store.py](./../../src/web_ui/session_store.py) `SessionEntry` with optional `account_id: str | None = None` field per [research.md §10](./research.md) and [data-model.md "SessionEntry (extended)"](./data-model.md). Backward-compatible (existing token-paste flow leaves `account_id` as `None`).
- [X] T033 Add `_by_account: dict[str, set[str]]` reverse index to `SessionStore` in [src/web_ui/session_store.py](./../../src/web_ui/session_store.py) per FR-011: maintained on `create()` / `delete()`; `get_sids_for_account(account_id) -> set[str]`; `delete_other_sids_for_account(account_id, except_sid)` for the password-change invalidation semantics (clarify Q12 — the actor's current sid survives).

### Topology-7 mount gate (research §12)

- [X] T034 Topology-7 startup gate in the account router init per [research.md §12](./research.md): when `os.environ.get('SACP_TOPOLOGY') == '7'`, refuse to mount and emit a startup ERROR naming the cross-spec incompatibility (spec V12). Same forward-document pattern as specs 014/020/021/025.

### Master-switch-off canary (FR-018 — lands FIRST after migration)

- [X] T035 Master-switch-off canary in [tests/test_023_master_switch_off.py](./../../tests/test_023_master_switch_off.py) per FR-018 + [plan.md "Notes for /speckit.tasks"](./plan.md): with `SACP_ACCOUNTS_ENABLED=0` (default), assert every account endpoint returns HTTP 404 — `POST /tools/account/{create,verify,login,email/change,email/verify,password/change,delete}` and `GET /me/sessions` and `POST /me/sessions/{session_id}/rebind`. Assert the SPA's existing token-paste landing remains the default surface.

### Cross-validator WARN emit (research §13)

- [X] T036 Add `emit_accounts_email_transport_warning()` in startup banner code per [research.md §13](./research.md) and [contracts/env-vars.md "Cross-validator interaction"](./contracts/env-vars.md): when `SACP_ACCOUNTS_ENABLED=1` AND `SACP_EMAIL_TRANSPORT=noop`, emit a startup WARNING (NOT a `ValidationFailure`) naming the consequence. Test in [tests/test_023_validators.py](./../../tests/test_023_validators.py) Phase 1 file with a new test asserting the WARN log line.

**Checkpoint**: argon2-cffi pinned; account package skeletons in place; password hasher, codes primitive, email-transport ABC + noop adapter, rate limiter, repository, and SessionStore extension all landed; topology-7 gate in place; master-switch-off canary green; cross-validator WARN testable. User-story phases unblocked.

---

## Phase 3: User Story 1 — Account creation, verification, and login (Priority: P1) 🎯 MVP

**Goal**: A new human creates an account with email + password (argon2id-hashed); the orchestrator emits a verification code via the configured email transport (noop default writes to `admin_audit_log`); the user submits the code and the account flips to `active`; they log in with email + password and receive a session cookie. Per-IP login rate limiter enforces FR-015. Timing-attack resistance per SC-005. ScrubFilter coverage per FR-014.

**Independent Test**: Drive an account-creation flow from a fresh DB. Submit email + password to `POST /tools/account/create`; assert the row exists with `status='pending_verification'`, the password is argon2id-hashed (not plaintext), an `account_verification_emitted` audit row appears, and the noop transport logged the code. Submit the verification code to `POST /tools/account/verify`; assert the account flips to `active`. Submit credentials to `POST /tools/account/login`; assert HTTP 200 + session cookie + `account_login` audit row.

### Tests for User Story 1

- [X] T037 [P] [US1] Acceptance scenarios 1-3 (account-creation, code-emission, verification, code-rejection on incorrect/expired) in [tests/test_023_account_create.py](./../../tests/test_023_account_create.py).
- [X] T038 [P] [US1] Acceptance scenarios 4-5 (login success → cookie + audit row; login failure → generic `invalid_credentials` 401, no info leak between non-existent-email and wrong-password) in [tests/test_023_account_login.py](./../../tests/test_023_account_login.py).
- [X] T039 [P] [US1] Acceptance scenario 6 + SC-006 (per-IP login rate limiter trips at threshold; 429 + `Retry-After`; mirrors spec 009 §FR-002 / FR-003 shape) in [tests/test_023_login_rate_limit.py](./../../tests/test_023_login_rate_limit.py).
- [X] T040 [P] [US1] SC-005 timing-attack resistance: login with non-existent email vs. existing email + wrong password produce identical responses (HTTP 401 + identical body + identical timing within ±5ms) in [tests/test_023_login_timing.py](./../../tests/test_023_login_timing.py). Implementation pattern: always run argon2id verify against a pinned dummy hash on the email-miss path so timing is uniform.
- [X] T041 [P] [US1] SC-007 transparent re-hash on parameter change in [tests/test_023_argon2id_rehash.py](./../../tests/test_023_argon2id_rehash.py): seed an account with a low-parameter argon2id hash; bump `SACP_PASSWORD_ARGON2_TIME_COST`; log in; assert the post-login hash uses the new parameters (`PasswordHasher.needs_rehash` returns False after the re-hash) and the `accounts.password_hash` row is updated.
- [X] T042 [P] [US1] SC-012 ScrubFilter coverage in [tests/test_023_scrub_filter.py](./../../tests/test_023_scrub_filter.py): drive create + verify + login + change-password + email-change flows; assert no plaintext password, no plaintext code, and no email body content appears in any log line. Cross-ref spec 007 §FR-012.

### Implementation for User Story 1

- [X] T043 [US1] Implement `Account` + `AccountParticipant` pydantic models in [src/models/account.py](./../../src/models/account.py) per [data-model.md "Entities"](./data-model.md): frozen dataclasses; field annotations match the alembic schema.
- [X] T044 [US1] Implement `service.create_account(email, password)` in [src/accounts/service.py](./../../src/accounts/service.py) per [contracts/account-endpoints.md "POST /tools/account/create"](./contracts/account-endpoints.md): validates email syntax, password length [12, 1024]; checks unique-active-or-pending email; hashes password via `PasswordHasher.hash`; writes `accounts` row with `status='pending_verification'`; emits verification code via the email transport; writes `account_create` + `account_verification_emitted` audit rows.
- [X] T045 [US1] Implement `service.verify_account(account_id, code)` in [src/accounts/service.py](./../../src/accounts/service.py) per [contracts/account-endpoints.md "POST /tools/account/verify"](./contracts/account-endpoints.md): looks up the unconsumed `account_verification_emitted` row by HMAC-hashed code; checks TTL; flips status to `active`; writes `account_verification_consumed` audit row.
- [X] T046 [US1] Implement `service.login(email, password, ip)` in [src/accounts/service.py](./../../src/accounts/service.py) per [contracts/account-endpoints.md "POST /tools/account/login"](./contracts/account-endpoints.md): runs `LoginRateLimiter.check(ip)` first; case-insensitive email lookup; ALWAYS runs `PasswordHasher.verify` (against a pinned dummy hash on email miss for timing-attack resistance per SC-005); on success, mints a SessionStore sid with `account_id` set and updates `last_login_at`; on `needs_rehash`, re-hashes the submitted plaintext and UPDATEs `accounts.password_hash` (SC-007); writes `account_login` (success) or `account_login_failed` (failure) audit row.
- [ ] T047 [US1] Add the seven account-router endpoints in [src/web_ui/account_routes.py](./../../src/web_ui/account_routes.py): `POST /tools/account/{create,verify,login}` for US1 + the four endpoints for US3 (US3 endpoints can be wired as stubs returning 501 in this task; US3 implementation lands in Phase 5). Each endpoint is gated by `SACP_ACCOUNTS_ENABLED` (FR-018) — the router is mounted conditionally; when the master switch is off, callers receive HTTP 404 from the absence of the route.
- [ ] T048 [US1] Mount the account router in [src/web_ui/app.py](./../../src/web_ui/app.py) (or the matching app-init file) conditionally on `SACP_ACCOUNTS_ENABLED=1` AND `SACP_TOPOLOGY != '7'` per FR-018 + research.md §12.
- [X] T049 [US1] Wire the password-change SessionStore invalidation per FR-011 / clarify Q12 in [src/accounts/service.py](./../../src/accounts/service.py): `service.change_password(account_id, current_pw, new_pw, current_sid)` calls `SessionStore.delete_other_sids_for_account(account_id, except_sid=current_sid)` after the hash-update commits. (US1 surfaces this only via the rate-limiter+canary; full US3 path lands in Phase 5.)

**Checkpoint**: US1 fully functional and testable independently. MVP increment: a human creates an account, retrieves the verification code (from email transport or `admin_audit_log` in dev), verifies, logs in, and receives a session cookie. The SPA can resolve the cookie via the existing spec 011 H-02 SessionStore flow.

---

## Phase 4: User Story 2 — Post-login session list (Priority: P1)

**Goal**: An authenticated account calls `GET /me/sessions` and receives `{active_sessions, archived_sessions}` segmented per FR-008. Cross-account isolation per FR-009 / SC-004. Pagination per segment at 50/page; the 10,000-session warning trip per FR-008 emits a structured WARN + an `account_session_count_threshold_tripped` audit row.

**Independent Test**: Create two accounts, A and B. Each joins three sessions in mixed states (active, paused, archived). Log in as A. Call `/me/sessions`; assert exactly A's sessions with `active_sessions` containing the active+paused (both non-archived) and `archived_sessions` containing the archived one. Assert each entry contains session id, name, last-activity-at, role, and participant id. Assert sessions belonging to B do NOT appear in A's response.

### Tests for User Story 2

- [X] T050 [P] [US2] Acceptance scenarios 1-4 (segmented response shape, per-entry fields, cross-account isolation, empty-account empty-arrays not 404) in [tests/test_023_me_sessions.py](./../../tests/test_023_me_sessions.py).
- [X] T051 [P] [US2] Acceptance scenario 5 + offset pagination consolidated into `tests/test_023_me_sessions.py::test_me_sessions_paginates_per_segment`.
- [X] T052 [P] [US2] Acceptance scenarios 6-7 + rebind consolidated into `tests/test_023_me_sessions.py::test_rebind_*`.
- [X] T053 [P] [US2] 10,000-session warning trip per FR-008 in `tests/test_023_me_sessions.py::test_me_sessions_emits_threshold_audit_when_count_exceeds_10k` (idempotent within process).

### Implementation for User Story 2

- [X] T054 [US2] `account_repo.list_sessions_for_account` + `count_sessions_for_account` + `find_binding_for_session` per [research.md §9](./research.md): single JOIN ordered by `sessions.created_at DESC` (v1 last-activity proxy), status segmentation via two calls.
- [X] T055 [US2] `service.list_sessions(account_id, active_offset, archived_offset)`: assembles `{active_sessions, archived_sessions, *next_offset}`; emits FR-008 10K trip with structured WARN + audit row, idempotent per process.
- [X] T056 [US2] `GET /me/sessions` in [src/web_ui/account_routes.py](./../../src/web_ui/account_routes.py): account-cookie auth via `_require_account_session`, `active_offset` / `archived_offset` query params.
- [X] T057 [US2] `POST /me/sessions/{session_id}/rebind` + `SessionStore.rebind_account_session` keep H-02 single-sid invariant.
- [X] T058 [US2] Hook lands at the existing token-paste `/login` endpoint: when an account cookie is present, insert `account_participants` and rebind the existing sid (single-sid invariant). Master-switch-off path leaves the existing flow untouched.

**Checkpoint**: US2 functional. A logged-in account calls `/me/sessions`, sees their sessions segmented by status, paginated, scoped strictly to their own joined sessions. Rebind endpoint resolves to the per-session participant credential without leaking the bearer to the cookie payload.

---

## Phase 5: User Story 3 — Account settings panel: email change, password change, account deletion with export (Priority: P2)

**Goal**: An authenticated user can change email (notify-old + verify-new per clarify Q11), change password (preserves actor's current sid, invalidates all other sids per clarify Q12), or delete the account (export-on-delete, zero credentials, preserve row for audit linkage). The 7-day email grace period (env-tunable via `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`) reserves the email post-delete.

**Independent Test**: Drive an authenticated account through each setting. Email change: assert verification code emitted to NEW email + heads-up to OLD email; email field does NOT change until the code is submitted; OLD email keeps receiving notifications until the change applies. Password change: assert old-password check + new argon2id hash storage + other sids invalidated + actor's current sid survives. Account deletion: assert debug-export emit + email/password_hash zeroing + status flip to `deleted` + `deleted_at` and `email_grace_release_at` populated.

### Tests for User Story 3

- [X] T059 [P] [US3] Email-change notify-old + verify-new flow in [tests/test_023_email_change.py](./../../tests/test_023_email_change.py).
- [X] T060 [P] [US3] Password-change actor-sid-survives + invalid-current-pw + audit row in [tests/test_023_password_change.py](./../../tests/test_023_password_change.py).
- [X] T061 [P] [US3] Account-delete credential-zeroing + grace populated + post-delete login generic in [tests/test_023_account_delete.py](./../../tests/test_023_account_delete.py).
- [X] T062 [P] [US3] Grace-period reservation per `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS` in [tests/test_023_grace_period.py](./../../tests/test_023_grace_period.py).

### Implementation for User Story 3

- [X] T063 [US3] `service.request_email_change` + `service.confirm_email_change` per clarify Q11 (notify-old + verify-new; email column unchanged until verify).
- [X] T064 [US3] `service.change_password` invalidates non-actor sids and writes `account_password_change` audit row per clarify Q12.
- [X] T065 [US3] `service.delete_account` emits debug-export, zeroes credentials, populates `deleted_at` + `email_grace_release_at`, drops all sids via `SessionStore.delete_all_sids_for_account`.
- [X] T066 [US3] Four US3 endpoints in [src/web_ui/account_routes.py](./../../src/web_ui/account_routes.py) replace the Phase 3 501 stubs.
- [X] T067 [US3] ScrubFilter patterns added in [src/security/scrubber.py](./../../src/security/scrubber.py) covering plaintext password / verification-code / reset-code key=value and JSON forms.

### Frontend (spec 011 amendment surfaces — auth gate, login/logout, post-login session list, account-settings panel)

- [X] T068 [US3] Auth-gate region in [frontend/app.jsx](./../../frontend/app.jsx) (`// region: auth-gate`): GuestChoose adds "Log in to your account" and "Create an account" entries; legacy token-paste retained.
- [X] T069 [US3] Login/logout region (`// region: login-logout`): `AccountLoginForm` + `AccountCreateForm` with verification-code submission UI.
- [X] T070 [US3] Post-login session-list region (`// region: post-login-session-list`): `MeSessionList` consuming `/me/sessions` segmented active+archived.
- [X] T071 [US3] Account-settings region (`// region: account-settings`): `AccountSettingsPanel` with email-change / password-change / delete tabs.

**Checkpoint**: US3 functional. Account settings panel works end-to-end. Email change preserves the OLD email until the NEW is verified. Password change invalidates other sessions but keeps the actor logged in. Deletion preserves the row for audit linkage but zeroes the credentials and reserves the email for the grace window.

---

## Phase 6: User Story 4 — Account ownership transfer (Priority: P3) — DEFERRED per research §7

Per [research.md §7](./research.md), FR-020 (account ownership transfer) is DEFERRED to a follow-up amendment. The deployment-owner authentication surface required by US4 does not exist as a coherent operator-facing API today; folding it into spec 023 expands scope beyond the user's stated brief ("deferred to Phase 4 federation if it complicates Phase 3"). The v1 schema (`account_participants` join with FK to `participants`) DOES support row-repointing without further migration, so the deferral is a transport-layer + auth-surface deferral, not a data-model deferral.

**No tasks emitted in this phase.** When the user schedules the follow-up, the new tasks will land:
- A new endpoint `POST /tools/admin/account/transfer_participants` in [src/web_ui/admin_routes.py](./../../src/web_ui/admin_routes.py) (or equivalent admin-surface module).
- A new `account_ownership_transfer` audit-log action (already RESERVED in [contracts/audit-log-events.md](./contracts/audit-log-events.md) per data-model.md).
- A new test file `tests/test_023_ownership_transfer.py` covering acceptance scenarios 1-4 + SC-010 (regular-account 403).

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Quickstart validation, V14 perf-budget verification, security scanning, doc cross-references, cross-spec FR audit.

- [ ] T072 [P] V14 perf-budget regression check per [plan.md "Performance Goals"](./plan.md): instrument login + `/me/sessions` + create with `@with_stage_timing`; assert P95 budgets via a synthetic-load test:
  - SC-002 login P95 ≤ 500ms at default argon2id parameters.
  - SC-003 `/me/sessions` P95 ≤ 200ms for an account with up to 1,000 joined sessions.
  - SC-001 account-creation P95 ≤ 1s end-to-end including hash + email-transport call.
- [ ] T073 [P] Quickstart.md walk-through: operator workflow per [quickstart.md](./quickstart.md) Steps "Operator workflow" through "Disabling / rollback" (enable master switch → set the seven env vars → verify migration applied → drive create + verify + login + email-change + password-change + delete → verify rollback). Run on a deployed orchestrator (Dockge stack) per memory `project_deploy_dockge_truenas`.
- [ ] T074 [P] Cross-spec FR audit:
  - spec 002 §FR-007 token rotation: confirm rotation still happens on the per-session credential; the account binding does NOT short-circuit token rotation per FR-016.
  - spec 002 §FR-016 / spec 001 §FR-019 audit-log carve-out: confirm deletion of an account preserves participant rows + audit entries (FR-012).
  - spec 007 §FR-012 ScrubFilter: confirm patterns in T067 land alongside existing patterns and don't regress prior scrub coverage.
  - spec 010 debug-export: confirm `service.delete_account` calls the existing internal export function rather than reimplementing the export shape.
  - spec 011 H-02 SessionStore invariants: confirm the extension preserves single-sid-per-cookie + no-payload-readable-bearer per research §10.
  - spec 019 per-IP rate limiter: confirm spec 023's limiter (FR-015) operates as a separate state container; both limiters apply additively per clarify Q10.
  - spec 024 facilitator scratch (future): confirm `accounts.id` is the FK target spec 024 will consume; no schema change needed for spec 024's landing.
- [ ] T075 [P] Spec 011 amendment alignment: confirm FR-030..FR-034 (added in T021) cite the right cross-refs into spec 023; confirm the `Phase 3c — Account UI (ships with spec 023)` subsection lists the four frontend regions from T068-T071.
- [ ] T076 Run the security scanners on the branch per CLAUDE.md project guidance: `pre-commit run --all-files` (gitleaks + 2MS + ruff + bandit + standards-lint); manually verify `git push` triggers the pre-push hook (Checkmarx 2MS + KICS) — fix or allowlist findings per the established triage process.
- [ ] T077 [P] Add doc cross-references per [data-model.md "Cross-spec references"](./data-model.md):
  - `docs/error-codes.md` for the new `invalid_credentials` / `rate_limit_exceeded` / `email_invalid` / `password_too_short` etc. error codes (judge disclosure scope per memory `feedback_synthesis_docs_local_first`; if recon-rich, defer the commit).
  - `docs/state-machines.md` for the account state machine (`pending_verification` → `active` → `deleted`).
  - `docs/retention.md` for the email grace period + audit-log carve-out.
  - `docs/ws-events.md` if any new WS events land (research §11 confirms NO new WS events in spec 023).
- [ ] T078 [P] Add a row to the FR-to-test traceability matrix in [docs/traceability/fr-to-test.md](./../../docs/traceability/fr-to-test.md) for every FR-001..FR-022 added by spec 023 (excluding FR-020 deferred per research §7) + spec 011 FR-030..FR-034. Tie each FR to its task ID and test file.
- [ ] T079 Verify CLAUDE.md (worktree-local file created by `update-agent-context.ps1`) has been merged into the main repo CLAUDE.md if appropriate, OR confirm the worktree-local file is intentionally local-only.
- [ ] T080 Status flip: update spec.md `Status:` to `Implemented` only after the user explicitly confirms per memory `feedback_dont_declare_phase_done`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — branch already created from main. V16 gate (T001-T017) + schema (T018-T020) + spec 011 amendment (T021).
- **Foundational (Phase 2)**: Depends on Setup. argon2-cffi pin (T022) + module skeletons (T023-T025) + hashing/codes/transport/rate_limit/repo/SessionStore extension (T026-T033) + topology gate (T034) + master-switch-off canary (T035) + cross-validator WARN emit (T036). Blocks all user stories.
- **User Story 1 (Phase 3, P1)**: Depends on Phase 2 — primary value increment (account-create + verify + login flow).
- **User Story 2 (Phase 4, P1)**: Depends on Phase 2 + US1 (the post-login session list assumes a logged-in account exists from US1; the SessionStore extension is from Phase 2).
- **User Story 3 (Phase 5, P2)**: Depends on US1 (the settings panel assumes the user can log in); US2 is independent (settings panel doesn't require the session list).
- **User Story 4 (Phase 6, P3)**: DEFERRED per research §7. No tasks emitted.
- **Polish (Phase 7)**: Depends on all desired user stories being complete.

### User Story Dependencies (recap)

- **US1 (P1)**: Phase 2 → US1 (no story dependencies). MVP boundary.
- **US2 (P1)**: US1 → US2 (the `/me/sessions` endpoint requires a logged-in cookie from US1).
- **US3 (P2)**: US1 → US3 (settings panel requires logged-in state).
- **US4 (P3)**: DEFERRED.

### Within Each User Story

- Tests written alongside implementation (per project convention; tests included for SC enforcement).
- Models / dataclasses (T043) before services; services before endpoints; endpoints before audit-row emission patterns.
- The master-switch-off canary (T035) lands FIRST after the migration so any "account endpoint accidentally accessible with switch off" leak surfaces early per [plan.md "Notes for /speckit.tasks"](./plan.md). Mirrors spec 025's SC-001 canary and spec 029's master-switch test.
- Argon2id hasher (T026) before any service calling `verify` or `hash`.

### Parallel Opportunities

- All Phase 1 [P] validator tasks (T001-T007) can run in parallel — different functions in `src/config/validators.py` with no shared edit point. T008 (append to `VALIDATORS` tuple) and T016 (CI gate verification) run sequentially after.
- All Phase 1 [P] doc tasks (T009-T015) can run in parallel — different sections in `docs/env-vars.md`.
- Phase 2 module skeletons (T023-T025) [P] all run in parallel.
- Phase 2 implementation tasks across modules (T026-T033) [P] can run in parallel — different files with no shared edit point.
- All [P] test tasks within a user story can run in parallel.
- Phase 3 acceptance test files (T037-T042) [P] all run in parallel.
- Phase 4 test files (T050-T053) [P] all run in parallel.
- Phase 5 test files (T059-T062) [P] all run in parallel.
- Phase 5 frontend regions (T068-T071) edit the same file (`frontend/app.jsx`) but operate on distinct regions (auth-gate, login-logout, post-login-session-list, account-settings) marked with the region-marking comments from T068-T071; coordinate with lane B's register-slider region and lane C's audit-log-panel region.
- Phase 7 [P] polish tasks can run in parallel.

---

## Parallel Example: Phase 1 V16 deliverable gate

```bash
# Seven validator additions in src/config/validators.py (different functions, no shared edit point):
Task: "T001 [P] validate_accounts_enabled"
Task: "T002 [P] validate_password_argon2_time_cost"
Task: "T003 [P] validate_password_argon2_memory_cost_kb"
Task: "T004 [P] validate_account_session_ttl_hours"
Task: "T005 [P] validate_account_rate_limit_per_ip_per_min"
Task: "T006 [P] validate_email_transport"
Task: "T007 [P] validate_account_deletion_email_grace_days"

# Seven docs/env-vars.md sections in parallel:
Task: "T009 [P] SACP_ACCOUNTS_ENABLED section"
Task: "T010 [P] SACP_PASSWORD_ARGON2_TIME_COST section"
Task: "T011 [P] SACP_PASSWORD_ARGON2_MEMORY_COST_KB section"
Task: "T012 [P] SACP_ACCOUNT_SESSION_TTL_HOURS section"
Task: "T013 [P] SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN section"
Task: "T014 [P] SACP_EMAIL_TRANSPORT section"
Task: "T015 [P] SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS section"

# Then T008 (append to VALIDATORS tuple) + T016 (CI gate verification) run sequentially.
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1: Setup (V16 gate + schema + spec 011 amendment).
2. Complete Phase 2: Foundational (argon2-cffi + skeletons + hashing/codes/transport/rate_limit/repo/SessionStore + canary).
3. Complete Phase 3: User Story 1 (create + verify + login).
4. **STOP and VALIDATE**: drive a fresh-DB account creation flow per `quickstart.md`; verify create + verify + login produces the expected audit rows + cookie state.
5. Demo to a test operator; bank the win (accounts surface is opt-in via the master switch; existing token-paste flow remains the default).

### Incremental Delivery

1. Setup + Foundational → Foundation ready (V16 gate green; schema migrated; SessionStore extended).
2. US1 → MVP shipped (humans can create accounts and log in).
3. US2 → post-login session list (the account's primary value lands).
4. US3 → account settings panel (email change, password change, account deletion with export).
5. US4 → DEFERRED per research §7; lands as a follow-up amendment when the deployment-owner authentication surface is designed.
6. Polish → V14 perf verification + quickstart walk-through + scanners + doc cross-refs.

### Parallel Team Strategy

With multiple developers after Phase 2:

- Developer A: US1 (P1 MVP — create + verify + login).
- Developer B: US2 (P1 — `/me/sessions` + rebind; can land in parallel with US1's session-cookie minting once T032 SessionStore extension exists).
- Developer C: Phase 7 polish prep (V14 perf instrumentation T072 — pure test work, can land alongside US1).

US3 is sequential after US1 since it requires a logged-in state to test against. Polish closes out after US1+US2+US3.

---

## Notes

- [P] tasks = different files OR independent functions in the same file with no shared edit point (e.g., seven validator functions in `src/config/validators.py` are P; the `VALIDATORS` tuple append is not).
- [Story] label maps task to specific user story for traceability.
- Each user story is independently completable and testable except for the documented dependencies (US2 + US3 require US1).
- Verify tests fail before implementing (the master-switch-off canary T035 is the foundational example).
- Per memory `feedback_test_schema_mirror`: alembic migration + `tests/conftest.py` raw DDL update MUST land in the same task (T018) — CI builds schema from conftest, not migrations.
- Per memory `reminder_spec_011_amendments_at_impl_time`: spec 011 amendment FRs FR-030..FR-034 land in T021 alongside the V16 gate per the research §11 surface list; do NOT defer.
- Per memory `feedback_no_auto_push`: do not push the branch upstream without explicit confirmation.
- Per memory `feedback_no_local_refs_in_prs`: when authoring the eventual PR body, list only what's IN the PR (do not enumerate held-back files, gitignored drafts, or out-of-scope deferrals like FR-020).
- Per memory `feedback_minimize_ai_footprint`: terse commit prose, no Co-Authored-By trailers, no Generated-with-Claude footers.
- Per memory `feedback_parallel_merge_sequence_collisions`: alembic slot 015 is pre-allocated for spec 023; lanes B / C are working on disjoint regions (register-slider, audit-log-panel) to avoid frontend collision points.
- FR-020 (US4) is DEFERRED per research §7; no tasks emitted in Phase 6. The follow-up amendment will land its own tasks file.
- Total task count: 80 (T001-T080) covering Phase 1 setup, Phase 2 foundational, Phase 3 US1, Phase 4 US2, Phase 5 US3, Phase 7 polish. Phase 6 (US4) is DEFERRED.
