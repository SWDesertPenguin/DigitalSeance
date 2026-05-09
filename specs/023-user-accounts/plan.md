# Implementation Plan: User Accounts with Persistent Session History

**Branch**: `023-user-accounts` | **Date**: 2026-05-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/023-user-accounts/spec.md`

## Summary

Phase 3+ persistent-identity layer that sits ABOVE spec 002's per-session bearer tokens. The account is the email + password (argon2id-hashed) record that owns zero or more participant rows via a new `account_participants` join; the existing token model remains the per-session security primitive untouched. Login issues a spec 011 opaque-sid cookie, the existing `SessionStore` is extended with an `account_id` field, and a new `GET /me/sessions` endpoint returns the authenticated account's joined sessions segmented as `{active_sessions, archived_sessions}` with offset pagination at 50/segment. The clarify session resolved 13 ambiguities, including: code-based email verification (16-char base32, 24h TTL) with the noop email transport as the dev default, a `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS` knob (default 7) replacing the hardcoded 7-day window, password-change SessionStore invalidation that survives the actor's current sid, and a notify-old + verify-new flow for email changes. Seven new env vars + V16 validators land before `/speckit.tasks`. The entire account surface is gated by the master switch `SACP_ACCOUNTS_ENABLED` (default `false`).

Technical approach: introduce a new `src/accounts/` package holding the service layer (`accounts/service.py` for create/verify/login/change/delete flows), the password hasher (`accounts/hashing.py` with argon2id wrapper + transparent re-hash on parameter change), the verification + reset code primitive (`accounts/codes.py` — single-use 16-char base32 with TTL), the email transport adapter abstraction (`accounts/email_transport.py` with `noop`, `smtp`, `ses`, `sendgrid` selected at startup), and the per-IP login rate limiter (`accounts/rate_limit.py` — sliding-window mirroring spec 009 + spec 019 patterns). Add `src/repositories/account_repo.py` for `accounts` and `account_participants` table access. Extend `src/web_ui/session_store.py` to add an optional `account_id` field on `SessionEntry`, plus an account-keyed reverse index for the password-change invalidation semantics (FR-011). Add a new FastAPI router `src/web_ui/account_routes.py` exposing the seven account endpoints (`POST /tools/account/create`, `/verify`, `/login`, `/email/change`, `/email/verify`, `/password/change`, `/delete`) plus `GET /me/sessions`. Ship one alembic migration (`013_user_accounts.py`) creating the `accounts` and `account_participants` tables; mirror the schema in `tests/conftest.py` per the established schema-mirror pattern. Spec 011 amendment (login/logout SPA flow, post-login session list, account-settings panel) lands at `/speckit.tasks` time per the forward-ref.

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm)
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest, **argon2-cffi** (new — argon2id reference implementation, MIT-licensed, single transitive dep on cffi which is already in the dependency tree via the cryptography package). No SMTP / SES / SendGrid client library is added in v1; the `smtp`/`ses`/`sendgrid` enum values reserve the surface for follow-up work and the `noop` adapter is the only one wired in v1 (research.md §6).
**Storage**: PostgreSQL 16. One new alembic migration (`alembic/versions/013_user_accounts.py`) adds two tables: `accounts` and `account_participants`. No changes to existing tables; the existing `participants` row is referenced by FK from `account_participants.participant_id` (nullable on the account side — a participant created without an account remains valid, matching the master-switch-off behavior).
**Testing**: pytest with the existing per-test FastAPI fixture (spec 012 US7). DB-gated tests follow the `tests/conftest.py` schema-mirror pattern; the mirror MUST be updated alongside the alembic migration in the same task (memory: `feedback_test_schema_mirror.md`).
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm). Frontend changes ship as a spec 011 amendment, not in this spec's source tree.
**Project Type**: Single project (existing `src/` + `frontend/` + `tests/` layout).
**Performance Goals**:
- Login P95 ≤ 500ms with default argon2id parameters (`time_cost=2, memory_kb=19456`) per SC-002. Argon2id hash dominates; the password verification call is the budget item.
- `/me/sessions` P95 ≤ 200ms for accounts with up to 1,000 joined sessions per SC-003. Single JOIN over `account_participants` × `participants` × `sessions` filtered by `account_id` (indexed); offset pagination at 50/page.
- Account creation P95 ≤ 1s end-to-end including argon2id hash + email transport call per SC-001.
- Per-IP login rate-limit check: O(1) on the steady-state path (sliding-window mirroring spec 009 §FR-011).
**Constraints**:
- Master-switch off behavior MUST be unchanged: `SACP_ACCOUNTS_ENABLED=false` (default) makes every account endpoint return HTTP 404 and the SPA falls back to the existing token-paste landing per FR-018.
- V15 fail-closed: invalid env-var values exit at startup before binding ports (V16). The `SACP_ACCOUNTS_ENABLED=true` AND `SACP_EMAIL_TRANSPORT=noop` cross-condition emits a startup WARNING but MUST NOT exit (operators legitimately run dev/staging with noop transport per clarify Q3).
- Argon2id params are operator-tunable but MUST meet OWASP 2024 floors (memory ≥ 19 MiB, time cost ≥ 2, parallelism = 1) per FR-003. Below-floor values warn at startup; outside the absolute valid range exits.
- Cross-account isolation: `/me/sessions` MUST scope strictly to the authenticated account per FR-009 / SC-004 (no cross-tenant leakage).
- Timing-attack resistance: login responses for non-existent email vs. existing email + wrong password MUST be identical body + identical timing within ±5ms per SC-005. Implementation pattern: always run argon2id verify (against a pinned dummy hash if the email lookup misses) so the failure path consumes the same wall-clock cost.
- ScrubFilter coverage extends to verification codes, reset codes, and password material per FR-014 / SC-012.
- 25/5 coding standards (Constitution §6.10) + 25-line function cap.
- §4.13 [PROVISIONAL] inter-AI shorthand: not engaged — accounts are operator/end-user surface, not AI-to-AI content path.
**Scale/Scope**: Single-tenant per deployment per spec 011 Phase D. Accounts ceiling depends on operator deployment; the synthetic-load test for SC-003 seeds 1,000 participant rows per account. Pagination at 50 entries per segment with a 10,000-session warning trip per FR-008.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | Accounts add an identity layer above spec 002's per-session token. Token rotation per spec 002 §FR-007 still happens; the account does not replace the security primitive (FR-016, account binds tokens via `account_participants`). API-key isolation, model-choice independence, budget autonomy, prompt privacy, and exit freedom are unaffected. |
| **V2 No cross-phase leakage** | PASS | Phase 3+ scaffold per spec line 5. No active Phase 3 work (013, 014, 015–022) depends on this spec; spec 024 (facilitator scratch) is the consumer. No future-phase capability is required. |
| **V3 Security hierarchy** | PASS | Argon2id replaces bcrypt for the new identity surface (different threat model from spec 002's static-token validation per spec line 64–70). The Sec/Operations balance favors security on the account-credential layer (rare invocation, CPU-DoS surface) and operations on the per-request token-validation layer (existing bcrypt). |
| **V4 Facilitator powers bounded** | PASS | Account is end-user identity, not facilitator authority. The single facilitator-adjacent surface — FR-020 ownership transfer — is deployment-owner-authenticated, NOT regular-account-self-service, and its in-scope-or-defer ruling is locked to plan phase per clarify Q8. |
| **V5 Transparency** | PASS | All account-creating, modifying, and deleting actions emit `admin_audit_log` rows per FR-019 (actor, target, action, timestamp). The 10,000-session pagination-threshold trip emits its own audit row per FR-008. No password hash, code, or email body appears in log content per FR-014 + spec 007 §FR-012 ScrubFilter. |
| **V6 Graceful degradation** | PASS | Email transport unavailable falls back to `admin_audit_log` recording the verification code per spec edge case + clarify Q3. Account deletion proceeds even if the export email fails (privacy-preserving default per spec edge case). Argon2id parameter increase between releases triggers transparent re-hash on next login (spec edge case). Master-switch off (default) preserves the pre-feature token-only flow. |
| **V7 Coding standards** | PASS | Service-layer methods stay under 25 lines; the seven endpoints are thin transports calling `accounts.service` helpers. No 5-arg positional violations expected. |
| **V8 Data security** | PASS | New secrets (password hashes, verification codes, reset codes) follow Tier 1 handling: password hashes are argon2id-encoded (one-way), verification + reset codes are persisted only in `admin_audit_log` (consumed-on-submit; no durable code table). Account email is PII (Tier 2) — stored in plaintext in `accounts.email` for login lookup and unique-index enforcement, scrubbed from log content per FR-014. The deletion flow zeroes both email and password_hash on the row. |
| **V9 Log integrity** | PASS | All audit events use existing append-only `admin_audit_log` paths. No new table for codes (consumed-on-submit + persisted in audit log). The carve-out on `admin_audit_log` (spec 001 §FR-019, Art. 17(3)(b)) applies to deleted-account audit rows per spec line 898–901. |
| **V10 AI security pipeline** | PASS | Accounts are user-facing identity; no AI prompt-content path. Tier isolation, spotlighting, sanitization, output validation are unaffected. |
| **V11 Supply chain** | NEEDS NOTE | One new runtime dependency: `argon2-cffi` (MIT, single transitive `cffi` already in tree via `cryptography`). Pinned per Constitution §6.3. The other potential email-transport deps (`smtplib` is stdlib; `boto3` for SES, `sendgrid` for SendGrid) are NOT added in v1; `noop` is the only wired adapter and the enum reserves the surface for a follow-up. Documented in research.md §6. |
| **V12 Topology compatibility** | PASS | Spec §V12 marks the feature applicable to topologies 1–6 (orchestrator-mediated identity); topology 7 (MCP-to-MCP) has no orchestrator-side account store. Same forward-document pattern as specs 014/020/021/025. |
| **V13 Use case coverage** | PASS | Spec §V13 maps to use cases §2 Research Co-authorship, §3 Consulting, §6 Decision-Making Under Asymmetric Expertise — the asynchronous-return cohort. Other use cases inherit when enabled. |
| **V14 Performance budgets** | PASS | Four budgets in spec §"Performance Budgets (V14)" (login P95 ≤ 500ms at default argon2id params, `/me/sessions` P95 ≤ 200ms at 1,000 sessions, account-creation P95 ≤ 1s, per-IP rate-limit check O(1)). Existing `@with_stage_timing` instrumentation pattern reused. |
| **V15 Fail-closed** | PASS | Invalid env vars exit at startup (V16). Argon2id verify failure → generic `invalid_credentials` 401 (no exception leak to the response). Email transport unavailable → `admin_audit_log` fallback + verification continues to work in dev (operator-recoverable; not a fail-closed event). The cross-condition `SACP_ACCOUNTS_ENABLED=true` + `SACP_EMAIL_TRANSPORT=noop` emits WARN, NOT exit, per clarify Q3 (operators legitimately use noop in dev). |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Seven new env vars require validators in `src/config/validators.py` (registered in the `VALIDATORS` tuple) plus `docs/env-vars.md` sections with the six standard fields BEFORE `/speckit.tasks` (FR-022 — V16 deliverable gate). Cross-validator interaction: `SACP_ACCOUNTS_ENABLED=true` AND `SACP_EMAIL_TRANSPORT=noop` emits a startup WARN. Below-OWASP-floor argon2id parameters emit a startup WARN; outside the absolute valid range exits. Contract in [contracts/env-vars.md](./contracts/env-vars.md). |
| **V17 Transcript canonicity** | PASS | Accounts do not touch the canonical transcript. The account binds participant rows via `account_participants`; participant records produced by spec 002 remain the per-session identity attached to messages. No transcript mutation, compression, or rewrite. |
| **V18 Derived artifacts traceable** | PASS | The account-deletion debug-export reuses spec 010's existing export shape (FR-012); no new derivation-metadata requirement. The export is a derived artifact, but its derivation metadata is owned by spec 010, not this spec. |
| **V19 Evidence and judgment markers** | PASS | Spec uses `[NEEDS CLARIFICATION]` markers (resolved 2026-05-09) per §4.14; no unsourced factual claims. The OWASP 2024 password-storage cheat-sheet citation (memory ≥ 19 MiB, time cost ≥ 2, parallelism = 1) is sourced. |

One conditional row (V11 NEEDS NOTE) — addressed in research.md §6. No violations requiring Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/023-user-accounts/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (account endpoints, env-vars,
│                        #                  email-transport, audit-log
│                        #                  rows, codes)
├── spec.md              # Feature spec (Status: Clarified 2026-05-09)
└── tasks.md             # Phase 2 output (/speckit.tasks command — NOT created here)
```

### Source Code (repository root)

```text
src/
├── accounts/                           # NEW — service layer for the account surface
│   ├── __init__.py
│   ├── service.py                      # create / verify / login / email-change / password-change / delete
│   ├── hashing.py                      # argon2id wrapper; transparent re-hash on parameter change
│   ├── codes.py                        # 16-char base32 single-use codes (verification + reset); TTL helpers
│   ├── email_transport.py              # transport ABC + noop adapter; smtp/ses/sendgrid stubs raise NotImplementedError
│   ├── rate_limit.py                   # per-IP login limiter (sliding window, separate from spec 019)
│   └── ownership_transfer.py           # FR-020 implementation surface — populated only if Phase 0 §7 lands "in v1"
├── repositories/
│   └── account_repo.py                 # NEW — accounts + account_participants CRUD
├── web_ui/
│   ├── account_routes.py               # NEW — 7 account endpoints + GET /me/sessions
│   ├── auth.py                         # extend to recognise account-cookie state alongside token-cookie state
│   └── session_store.py                # extend SessionEntry with optional account_id; add account-keyed reverse index for FR-011 invalidation
├── config/
│   └── validators.py                   # add 7 validators (SACP_ACCOUNTS_ENABLED + 6 supporting vars)
└── models/
    └── account.py                      # NEW — Account + AccountParticipant pydantic models

alembic/versions/
└── 013_user_accounts.py                # NEW — adds accounts + account_participants tables

tests/
├── conftest.py                         # mirror new accounts + account_participants tables in raw DDL (memory: feedback_test_schema_mirror)
├── test_023_account_create.py          # NEW — US1 P1 — create + verify + login flow
├── test_023_login_timing.py            # NEW — US1 P1 — SC-005 timing-attack-resistance test (±5ms)
├── test_023_login_rate_limit.py        # NEW — US1 P1 — SC-006 per-IP login rate-limiter
├── test_023_me_sessions.py             # NEW — US2 P1 — /me/sessions segmentation + pagination + cross-account isolation
├── test_023_email_change.py            # NEW — US3 P2 — notify-old + verify-new flow per clarify Q11
├── test_023_password_change.py         # NEW — US3 P2 — SessionStore invalidation per clarify Q12 (preserve actor's sid)
├── test_023_account_delete.py          # NEW — US3 P2 — debug-export emit + credential zeroing + grace period
├── test_023_argon2id_rehash.py         # NEW — SC-007 transparent re-hash on parameter change
├── test_023_validators.py              # NEW — 7 env-var validators + cross-condition WARN
├── test_023_scrub_filter.py            # NEW — SC-012 ScrubFilter coverage for codes + passwords
├── test_023_master_switch_off.py       # NEW — FR-018 SACP_ACCOUNTS_ENABLED=false → 404 on every account endpoint
└── test_023_ownership_transfer.py      # NEW — US4 P3 — ONLY land if research.md §7 puts FR-020 in v1; otherwise the file is created in the follow-up amendment

docs/
└── env-vars.md                         # add 7 new sections (V16 gate; FR-022)
```

**Structure Decision**: Single Python service (Option 1) consistent with the existing repo layout. New top-level package `src/accounts/` houses the service-layer logic (hashing, codes, email transport, rate limiter) so the surface is discoverable and unit-testable in isolation. The seven account HTTP endpoints land in a new router file `src/web_ui/account_routes.py` that mounts behind the existing `auth.py` flow when `SACP_ACCOUNTS_ENABLED=true`; the master-switch-off path returns 404 from a no-op router so the SPA's existing token-paste landing remains the default. The `SessionStore` extension is additive (a new optional `account_id` field on `SessionEntry` plus an account-keyed reverse index for FR-011 password-change invalidation) — no replacement, single-lookup cookie validation preserved per clarify Q9. The alembic migration adds two new tables and is mirrored in `tests/conftest.py` raw DDL in the same task.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(No violations. V11 NEEDS NOTE is addressed in research.md §6 — single new dependency `argon2-cffi`, MIT-licensed, transitive `cffi` already in tree via `cryptography`. Pinned per Constitution §6.3.)

## Phase 0 — Outline & Research

Open decisions queued for `research.md`:

1. **Argon2id library choice and pin policy.** `argon2-cffi` (MIT, transitive `cffi` already in tree) vs. `passlib[argon2]` (broader, more-deps abstraction layer) vs. building on `hashlib.scrypt` instead. Decision criteria: minimal supply-chain footprint, OWASP 2024 parameter compliance, transparent re-hash semantics, pinning compatibility with Constitution §6.3.
2. **`accounts` table column shape.** FR-001 fixes the column set (id, email, password_hash, status enum, created_at, updated_at, last_login_at). Research locks: `id` UUID vs. opaque-string format (matching `participants.id` precedent), `email` collation (case-insensitive lookup via `citext` extension or application-side lower-casing), `status` enum representation (Postgres enum type vs. CHECK-constrained text — same call as spec 025's `length_cap_kind`), unique-index shape (covers email but not password_hash).
3. **Email + reset code shape and persistence.** FR-004 fixes the verification mechanism (16-char base32, single-use, 24h TTL); clarify Q4 fixes the reset variant (same shape, 30-min TTL). Research designs: persistence pattern (no durable codes table — codes live only in `admin_audit_log` rows; consumption marks the row as superseded by a `code_consumed` follow-up event) vs. a transient `verification_codes` table. Decision criterion: V8 simplicity + audit-trail integrity. Tentative: audit-log-only, mirrors the existing token-issuance pattern.
4. **Email transport ABC and the noop default.** Clarify Q3 confirmed noop default + WARN on the cross-condition. Research designs the ABC: minimal interface (`async send(to: str, subject: str, body: str) -> None`); noop adapter writes a structured row to `admin_audit_log` and returns. The `smtp` / `ses` / `sendgrid` enum values reserve the surface for follow-up; the v1 implementation raises `NotImplementedError` on selection (with a clear startup error pointing at the follow-up spec) so operators don't silently fall through to noop after misconfiguring.
5. **Per-IP login rate limiter sliding-window.** FR-015 + clarify Q10 fix the additive-with-spec-019 composition (separate limiter, no shared state). Research locks the sliding-window primitive: in-memory deque per IP keyed off `extract_client_ip` (mirrors spec 019's `src/middleware/network_rate_limit.py`); window size = 60 seconds; burst behavior matches spec 009 §FR-002. Decision criterion: same shape as spec 019 for operator predictability; separate state container per FR-015.
6. **Email-transport SMTP/SES/SendGrid follow-up scope.** Clarify Q3 confirms noop is the v1 default; the other three enum values exist for future work. Research declares: v1 ships only the `noop` adapter + a clear `NotImplementedError` path for the other three values; the smtp/ses/sendgrid wiring is a follow-up spec (provisional name "spec 023.1" or "spec 026 email-transport"). Documented in `contracts/email-transport.md` so the future implementation has a contract to land into.
7. **FR-020 (ownership transfer) in-or-defer decision.** Clarify Q8 pinned the in-or-defer call to plan phase. Research evaluates the v1 implementation surface: deployment-owner authentication path (does the operator surface authentication exist today, or does it have to be invented for this spec?), `account_participants` row-repointing query shape, admin audit row schema, the regular-account 403 contract. **Provisional decision: DEFER to a follow-up amendment.** The deployment-owner authentication surface does not exist as a coherent operator-facing API today — building it for one ownership-transfer endpoint expands scope beyond the user's stated brief ("deferred to Phase 4 federation if it complicates Phase 3"). The v1 schema (`account_participants` join with FK to `participants`) DOES support row-repointing without further migration, so the deferral is a transport-layer + auth-surface deferral, not a data-model deferral. Research records the rationale; tasks.md drops US4 from v1 scope; spec 024 (facilitator scratch) is unaffected since it does not consume FR-020.
8. **Argon2id transparent re-hash trigger and rate.** Spec edge case + SC-007 require re-hash on parameter change. Research designs: on every successful login, the verifier checks the stored hash's encoded parameters against current env-var parameters; mismatch triggers a re-hash + UPDATE on `accounts.password_hash`. Rate-impact: amortized over login frequency; no batch migration. Decision criterion: simplicity over throughput optimization (no scheduled re-hash sweep).
9. **`/me/sessions` query shape.** FR-008 + SC-003 fix the contract. Research locks the SQL: a single JOIN over `account_participants` × `participants` × `sessions` filtered by `account_id`, ordered by `sessions.last_activity_at DESC`, segmented by `sessions.status` (active states first, archived second). Index design: `account_participants(account_id)` btree (primary lookup), `sessions(last_activity_at)` btree (ordering), `account_participants.participant_id` UNIQUE (FR-002 enforcement). The 10,000-session warning + audit-row trip implements as a count check on every call (cheap; backed by `account_participants` count by `account_id`).
10. **Cookie-flow integration with the existing token-cookie path.** Spec 011's H-02 `SessionStore` issues opaque sids on token-paste login. Research designs: the new account-login path mints the same opaque sid + the existing cookie shape, but with `SessionEntry.account_id` set; the existing `auth.py` flow that reads the cookie continues to work unchanged (the bearer + participant binding is null in the account-only case). When the user clicks an active session entry from `/me/sessions`, the SPA calls a new "rebind" endpoint that adds the per-session bearer to the existing account-bound `SessionEntry` (preserving the H-02 opaque-sid invariant — single sid per cookie, no payload-readable bearer).
11. **Spec 011 amendment trigger and content.** Per the user's reminder file `reminder_spec_011_amendments_at_impl_time.md`, the spec 011 amendment for this spec lands at `/speckit.tasks` time, NOT at plan time. Research declares: plan phase produces the list of UI surfaces (login/logout flow, post-login session list with active/archived segmentation, account-settings panel for email/password/delete, disambiguation modal? — none required for spec 023, no 409 disambiguation flow); tasks phase commits the spec 011 amendment alongside the v1 implementation tasks. Documented here so the amendment scope is fixed before drafting time.
12. **Topology-7 forward note.** Spec §V12 marks topology 7 incompatible. Research drafts the controller-side gate: account-router init checks `SACP_TOPOLOGY` env var and refuses to mount when it equals `7` (with a clear startup error naming the cross-spec incompatibility). Same forward-document pattern as specs 014/020/021/025.
13. **Cross-validator dependency between the email-transport WARN and the master switch.** Clarify Q3 fixed the WARN-not-EXIT semantic. Research designs the cross-check as a top-of-startup validator pair: `validate_accounts_enabled()` runs first and validates the master switch; `validate_email_transport()` runs second and validates the enum value; a third validator `validate_accounts_email_transport_combination()` reads both vars and emits the WARN (NOT a `ValidationFailure`) when both conditions hit. Decision criterion: keep WARN-only state out of the `ValidationFailure` path so the V16 fail-closed contract isn't tainted.

Output: [research.md](./research.md) with one decision section per open question.

## Phase 1 — Design & Contracts

**Prerequisites:** `research.md` complete.

1. **Data model** ([data-model.md](./data-model.md)) extracts entities from spec:
   - `Account` — `accounts` table row. Columns: `id` (UUID), `email` (unique, lower-cased), `password_hash` (argon2id encoded), `status` (`'pending_verification'` | `'active'` | `'deleted'`), `created_at`, `updated_at`, `last_login_at`, `deleted_at` (nullable; for grace-period reservation), `email_grace_release_at` (nullable; computed at deletion time from `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`).
   - `AccountParticipant` — `account_participants` table row. Columns: `id` (UUID), `account_id` (FK → accounts.id), `participant_id` (FK → participants.id, UNIQUE per FR-002), `created_at`. Index: `(account_id)` for the `/me/sessions` lookup.
   - `VerificationCode` (transient) — 16-char base32 string with TTL. Persisted only in `admin_audit_log` rows with `action='account_verification_emitted'` / `'account_verification_consumed'`. Not a durable entity.
   - `ResetCode` (transient) — same shape as VerificationCode; TTL 30 min instead of 24h. Persisted in `admin_audit_log` with action `'account_password_reset_emitted'` / `'account_password_reset_consumed'`.
   - `EmailChangeToken` (transient) — same shape; TTL 24h; consumed-on-submit. Persisted in `admin_audit_log` with action `'account_email_change_emitted'` / `'account_email_change_consumed'`.
   - `PasswordHash` — argon2id-encoded hash string including parameters used at hash time. Format: `$argon2id$v=19$m=...,t=...,p=...$<salt>$<hash>`. Cross-spec re-hash semantics documented (SC-007).
   - `SessionStoreEntry (extended)` — spec 011's `SessionEntry` gains an optional `account_id: str | None` field (nullable; `None` for the existing token-paste flow, set for the account-login flow). Account-keyed reverse index `_by_account: dict[str, set[str]]` mapping `account_id` to its set of sids (FR-011 invalidation).
   - `EmailTransport` (process-scope adapter) — ABC selected at startup via `SACP_EMAIL_TRANSPORT`. v1 ships `NoopEmailTransport` only; `smtp` / `ses` / `sendgrid` selections raise `NotImplementedError` at startup with a clear pointer at the follow-up spec (research.md §6).
   - `LoginRateLimiter` (process-scope) — separate sliding-window per-IP limiter for `/login` and `/create-account` endpoints; not shared with spec 019's middleware (FR-015).

2. **Contracts** ([contracts/](./contracts/)) — Phase 1 outputs five contract docs:
   - `contracts/account-endpoints.md` — HTTP shapes for the seven endpoints + `GET /me/sessions`. Request/response bodies, validation rules, success/error codes, side effects (audit-log emit, SessionStore mutation, email-transport call). Authorization: account-cookie (FR-016 via SessionStore extension) for the authenticated endpoints; pre-auth limiter (FR-015) for `/create` and `/login`; master-switch (FR-018) gates all eight.
   - `contracts/env-vars.md` — seven new vars × six standard fields. Cross-validator note for the `SACP_ACCOUNTS_ENABLED` + `SACP_EMAIL_TRANSPORT=noop` WARN path.
   - `contracts/email-transport.md` — `EmailTransport` ABC method signature, the noop adapter behavior (writes structured `admin_audit_log` row), the smtp/ses/sendgrid follow-up reservation contract.
   - `contracts/audit-log-events.md` — list of `admin_audit_log.action` values introduced by this spec (account_create, account_verification_emitted, account_verification_consumed, account_login, account_login_failed, account_email_change_emitted, account_email_change_old_notified, account_email_change_consumed, account_password_change, account_password_reset_emitted, account_password_reset_consumed, account_delete, account_session_count_threshold_tripped). Payload schemas and ScrubFilter rules.
   - `contracts/codes.md` — 16-char base32 generation (cryptographically random via `secrets.token_hex` adapted to base32 alphabet), single-use semantics, TTL enforcement, the consumed-on-submit pattern, ScrubFilter coverage.

3. **Quickstart** ([quickstart.md](./quickstart.md)) — operator + facilitator + end-user workflows:
   - Operator: enable accounts (`SACP_ACCOUNTS_ENABLED=true`), set the six supporting vars, restart, verify config-validation passes.
   - Operator: run the alembic migration, verify the two new tables.
   - Operator: switch from `SACP_EMAIL_TRANSPORT=noop` to a real transport (forward-pointer to follow-up spec; v1 stays on noop).
   - End-user: create account → verify code (read from `admin_audit_log` in dev) → login → see session list.
   - End-user: change email (notify-old + verify-new) → change password (other sessions invalidated, current sid survives) → delete account (export emit + credential zeroing).
   - How to read `admin_audit_log` for account events.
   - Disabling/rollback: `SACP_ACCOUNTS_ENABLED=false` + restart; existing accounts retained but inaccessible.

4. **Agent context update**: run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType claude` to merge spec 023's tech surface into `CLAUDE.md`.

5. **Re-evaluate Constitution Check** post-design — confirm V11 (one new runtime dep), V14 (4 budgets), V16 (7 env vars), V8 (PII handling) surfaces are still accurate after `data-model.md` and `contracts/` lock the schema and endpoint shape.

**Output**: data-model.md, contracts/*.md, quickstart.md, updated CLAUDE.md.

## Notes for `/speckit.tasks`

- **V16 deliverable gate (FR-022)**: tasks MUST gate validator + doc work BEFORE any code-path work. Seven new env vars (`SACP_ACCOUNTS_ENABLED`, `SACP_PASSWORD_ARGON2_TIME_COST`, `SACP_PASSWORD_ARGON2_MEMORY_COST_KB`, `SACP_ACCOUNT_SESSION_TTL_HOURS`, `SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN`, `SACP_EMAIL_TRANSPORT`, `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`) need validator functions in `src/config/validators.py` registered in the `VALIDATORS` tuple, plus full sections in `docs/env-vars.md` with the six standard fields each.
- **Cross-validator WARN path**: `SACP_ACCOUNTS_ENABLED=true` + `SACP_EMAIL_TRANSPORT=noop` emits a startup WARNING (NOT a fail-closed exit) per clarify Q3. The validator pattern is documented in research.md §13; tasks should land the warning emit alongside the validators in the same task so the cross-condition is testable from the start.
- **Schema-mirror discipline**: the alembic migration (`013_user_accounts.py`) and the `tests/conftest.py` raw-DDL mirror MUST land in the same task per memory `feedback_test_schema_mirror.md` — CI builds schema from conftest, not migrations.
- **Master-switch-off canary first**: `test_023_master_switch_off.py` (FR-018) lands FIRST after the migration so any "account endpoint accidentally accessible with the switch off" leak surfaces before the rest of the surface grows. Mirrors spec 025's SC-001 canary pattern.
- **Timing-attack-resistance test (SC-005)**: `test_023_login_timing.py` measures the wall-clock cost of login-with-non-existent-email vs. login-with-wrong-password, asserts ±5ms. Implementation must always run argon2id verify against a pinned dummy hash on the email-miss path.
- **FR-020 deferral (clarify Q8 + research §7)**: provisional decision is to DEFER ownership transfer to a follow-up amendment. If research.md §7 lands the in-v1 ruling instead, `test_023_ownership_transfer.py` and `src/accounts/ownership_transfer.py` join the task list; if deferred (the provisional ruling), they do NOT, and tasks.md cross-references the deferral with the rationale.
- **Spec 011 amendment lands at /speckit.tasks time** (per user's reminder `reminder_spec_011_amendments_at_impl_time.md`). The amendment scope is fixed in research.md §11: login/logout SPA flow, post-login session list with active/archived segmentation, account-settings panel (email change, password change, delete), no disambiguation modal (no 409 in this spec). Tasks should include the amendment as a single task that follows the contract-locking work but precedes the SPA-bundle implementation tasks.
- **Argon2id library pin (research §1)**: `argon2-cffi` is the chosen library. Tasks should add the dep to `pyproject.toml` + lockfile in the same task as the validator landing so the supply-chain footprint is reviewable in one place.
- **No `routing_log` changes**: this spec is purely `admin_audit_log`-side; no `routing_log.reason` enum extensions needed (different from spec 025 which added five). Documented for clarity.
- **Topology-7 forward note**: account-router init checks `SACP_TOPOLOGY` and skips mount when topology 7 is active. Same forward-document pattern as specs 014/020/021/025 — tasks land the gate; no topology-7-specific behavior implemented.
- **Email-transport follow-up reservation (research §6)**: smtp/ses/sendgrid wiring is a follow-up spec. Tasks land the ABC + noop adapter only; the three reserved enum values raise `NotImplementedError` at startup. Documented in `contracts/email-transport.md` so the follow-up has a contract to land into.
- **Phase 3+ scoping**: spec 023 is Phase 3+ scaffolding. Active Phase 3 work (013–022) does not depend on it; spec 024 (facilitator scratch) is the prerequisite consumer. Tasks should not block on or wait for Phase 3 closure — the implementation gate is the user scheduling per Constitution §14.1.
