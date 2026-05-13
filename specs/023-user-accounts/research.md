# Research: User Accounts with Persistent Session History

**Branch**: `023-user-accounts` | **Date**: 2026-05-09 | **Plan**: [plan.md](./plan.md)

Resolves the thirteen open decisions queued in [plan.md §"Phase 0 — Outline & Research"](./plan.md). Each section answers one question; each section closes with a Decision / Rationale / Alternatives format.

---

## §1 — Argon2id library choice and pin policy

**Decision**: `argon2-cffi` (PyPI), pinned per Constitution §6.3 to a known-current version. The `Argon2 PasswordHasher` API is wrapped behind `src/accounts/hashing.py` so the rest of the codebase never touches the third-party API directly.

**Rationale**: `argon2-cffi` is the OWASP-recommended Python implementation, MIT-licensed, widely deployed, with a thin C-binding via cffi (already in the dependency tree as a transitive of `cryptography`). The library exposes `PasswordHasher.hash(...)`, `PasswordHasher.verify(...)`, and `PasswordHasher.check_needs_rehash(...)` — the third method is the exact primitive we need for SC-007 transparent re-hash on parameter change. Wrapping in `src/accounts/hashing.py` means a future swap (e.g., to a hypothetical pure-Python argon2 implementation, or to a different library entirely) is an internal-architecture refactor, NOT an FR-021 boundary change.

**Alternatives considered**:
- **`passlib[argon2]`** — broader compat surface (multiple hash schemes via one API) but `passlib` is in maintenance mode (last release 2020 as of late 2024 audit cycle), and pulls argon2-cffi as a transitive anyway. Rejected for the maintenance signal.
- **`hashlib.scrypt`** — stdlib, zero new deps. Rejected because OWASP 2024 explicitly recommends argon2id as the first-choice modern primitive over scrypt; the spec calls argon2id by name (FR-003); deviating would require operator + audit re-justification.
- **Pure-Python argon2 (e.g., `pyargon2`)** — eliminates the cffi binding. Rejected as too new (lower deployment confidence) and slower (CPU-bound hash without C optimization makes the V14 budget harder to hit).

---

## §2 — `accounts` table column shape

**Decision**:
- `id`: `uuid` Postgres type (matches the `participants.id` precedent which uses `text` UUID strings — application-side serialization is identical, but `uuid` typed column is more efficient for the FK from `account_participants`).
- `email`: `text NOT NULL` with a unique index `accounts_email_active_uidx` covering only `status IN ('pending_verification', 'active')` (partial index — deleted accounts release the email after grace; the unique constraint enforces "no two active accounts share an email" without blocking re-registration after grace expiry).
- Email collation: lower-cased application-side at write + read; NO `citext` extension (avoids extension dependency; lower-casing is universal for email addresses; cheaper than maintaining an extension).
- `password_hash`: `text NOT NULL` (argon2id encoded form is ASCII; column allows a NULL post-deletion zeroing, but the empty-string convention is preferred for "credential released" — application-side zeroing replaces the hash with empty string, NOT NULL, so the unique constraint stays clean).
- `status`: `text NOT NULL DEFAULT 'pending_verification'` with a CHECK constraint `status IN ('pending_verification', 'active', 'deleted')`. Same call as spec 025's `length_cap_kind` — CHECK over Postgres enum type for migration agility (Postgres enum types are notoriously hard to extend without pain).
- Timestamps: `created_at`, `updated_at`, `last_login_at`, `deleted_at` all `timestamptz`. `last_login_at` and `deleted_at` are nullable; the others are `NOT NULL DEFAULT now()`.
- `email_grace_release_at`: `timestamptz NULL` — populated at deletion time as `deleted_at + (SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS * interval '1 day')`. The re-registration check on `accounts/create` looks for an existing row with the same email AND `status='deleted'` AND `email_grace_release_at > now()` — if matched, reject; if no match, the email is releasable (or never registered).

**Rationale**: partial unique index on `(email) WHERE status IN ('pending_verification', 'active')` lets a deleted-account row coexist with a fresh registration on the same email after the grace period (FR-013) without dropping the deleted row (FR-012's audit-trail preservation). Lower-casing application-side is the standard cross-database email-handling pattern; `citext` is a Postgres-specific extension that complicates the test fixture's schema-mirror.

**Alternatives considered**:
- **Postgres enum type for `status`** — rejected due to the well-documented pain of `ALTER TYPE ADD VALUE` migrations.
- **`citext` extension for email** — rejected for the schema-mirror complication.
- **NULL on `password_hash` post-deletion** — rejected because the column is `NOT NULL`; either we change to nullable or we use an empty-string sentinel. Empty-string sentinel is simpler.
- **Single-table soft-delete with a separate `deleted_accounts` archive** — rejected; one table with a `status='deleted'` row is simpler and preserves FK integrity for audit log lookups.

---

## §3 — Email + reset code shape and persistence

**Decision**: codes live in `admin_audit_log` only. No durable codes table. Generation, consumption, and TTL enforcement are all application-side; the audit-log row is the durable record.

**Code generation**: 16-character base32 alphabet (Crockford base32 to drop visually ambiguous chars I/L/O/U), generated via `secrets.token_bytes(10)` then base32-encoded and trimmed to 16 chars. ~80 bits of entropy (10 bytes); single-use; TTL enforced by checking the audit-log row's `at` timestamp against `now() - TTL` at consumption time.

**Persistence pattern**:
- Emission: insert `admin_audit_log` row with `action='account_verification_emitted'` (or `'_password_reset_emitted'` etc.), payload contains the code (hash, NOT plaintext) + the target account_id + the TTL deadline.
- Consumption: insert a follow-up `admin_audit_log` row with `action='account_verification_consumed'` referencing the original row's id; the application-side check rejects re-submission if a `_consumed` row already exists for that code-hash.
- Storage: only the code's HMAC-SHA256 hash (using `SACP_AUTH_LOOKUP_KEY` already in tree) appears in the audit log; the plaintext code goes to the email transport and is never persisted. Plaintext-code log emission falls under FR-014 ScrubFilter coverage.

**Rationale**: keeps schema surface minimal (FR-022 already promises "no schema changes beyond the two new tables" in the data model). Audit log is append-only (V9), already centrally scrubbed (V5/FR-014), and already the canonical record of account actions per FR-019. A separate codes table would duplicate the audit-trail role and add a cleanup-on-expiry sweep job. Code-hash storage (vs. plaintext) means an attacker reading the audit log post-breach cannot replay codes — they would need both the audit log and the original email's plaintext.

**Alternatives considered**:
- **Durable `verification_codes` table** — adds schema; needs cleanup sweep; redundant with audit log. Rejected.
- **Redis-backed code store** — would shave a microsecond off the lookup but adds Redis to the deployment graph, contradicting V11 minimal-footprint. Rejected.
- **Plaintext codes in audit log** — rejected on Tier-1 secret handling grounds (V8); hash + lookup-key pattern preserves audit utility without the breach risk.
- **JWT-based codes** — rejected as overkill (the code is single-use, short-lived, and emitted by the orchestrator to itself — JWT's signature-verifying-and-claiming-anything-inside benefit is nil here, while adding a JWT library to the dep graph is concrete cost).

---

## §4 — Email transport ABC and the noop default

**Decision**: minimal ABC in `src/accounts/email_transport.py`:

```python
class EmailTransport(Protocol):
    async def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        purpose: Literal[
            'verification', 'password_reset', 'email_change_new',
            'email_change_old_notify', 'account_delete_export',
        ],
    ) -> None: ...
```

**Noop adapter** (`NoopEmailTransport`) writes a structured `admin_audit_log` row with `action='account_email_noop_emitted'`, payload `{to: <hashed>, subject: <unscrubbed>, purpose: <enum>, body_length: <int>}`. The body itself is NOT logged (it contains the code/link); the body length is logged for forensic sanity-checking. Body content is included in `admin_audit_log` only via the `_emitted` audit row for the code/token (separate, scrubbed-payload row).

**SMTP/SES/SendGrid stubs**: each registered class raises `NotImplementedError` at instantiation time with the message `"SACP_EMAIL_TRANSPORT='{value}' is reserved for a follow-up spec; v1 supports only 'noop'. See specs/023-user-accounts/contracts/email-transport.md."`. The validator catches this at startup so the orchestrator exits before binding ports — operators do not silently fall through to noop after misconfiguring.

**Rationale**: the ABC decision is locked now so the follow-up spec implementing real SMTP / SES / SendGrid has a stable target. The noop adapter's audit-log emission shape is documented in `contracts/email-transport.md` so dev/staging operators can rely on it as the canonical "code retrieval" path. The `purpose` enum lets future transport implementations apply per-purpose templating (e.g., HTML emails for password resets, plain text for export-delete) without per-call type drift.

**Alternatives considered**:
- **Sync `send()` method** — rejected; FastAPI's request handlers are async-native, and SMTP/SES calls will be I/O-bound. Async-from-the-start avoids a future breaking change.
- **Per-purpose method (`send_verification`, `send_reset`, etc.)** — rejected as Liskov-violating; one ABC method with the `purpose` enum lets transport implementations dispatch internally without the ABC growing for every new purpose.
- **Allow noop fallback on smtp/ses/sendgrid configuration error** — rejected; silent fallback is the V15 fail-closed anti-pattern.

---

## §5 — Per-IP login rate limiter sliding-window

**Decision**: in-memory sliding-window deque per IP, separate state container from spec 019's middleware. Window size = 60 seconds (matches the `SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN` semantics — "per minute"). Threshold = `SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN`. Burst behavior: leaky-bucket-style — every request appends a timestamp; on each call, drop timestamps older than 60s; if the remaining count exceeds the threshold, reject 429 + `Retry-After: <seconds_until_oldest_drops>`.

**State container**: process-local `dict[str, collections.deque[float]]` in `src/accounts/rate_limit.py` keyed by `extract_client_ip(request)` (mirrors the existing helper from `src/web_ui/auth.py`). Async-safe via an `asyncio.Lock` per the existing `SessionStore` pattern (low contention; rate-limit checks are short).

**Memory budget**: `SACP_NETWORK_RATELIMIT_MAX_KEYS` already bounds total IP keys (spec 019). Spec 023's limiter is bounded by the same eviction policy applied locally — when the dict grows past `SACP_NETWORK_RATELIMIT_MAX_KEYS / 4` entries (a quarter of the network-layer ceiling — different scope, smaller share), evict the oldest-touched IPs. Documented as a v1-pragmatic ceiling; a future spec can promote this to a dedicated env var.

**Rationale**: separate state per FR-015 + clarify Q10 — the spec-019 limiter targets general HTTP abuse; spec 023's limiter is narrowly credential-stuffing. Independent tunability is intentional defense-in-depth. Sliding-window matches spec 009's algorithm so operator mental model is consistent.

**Alternatives considered**:
- **Shared state with spec 019** — explicitly rejected by clarify Q10. Two limiters, additive composition.
- **Token-bucket** — equivalent expressiveness; sliding-window is what spec 009 uses, so consistency wins.
- **Redis-backed limiter** — rejected per V11 footprint argument.

---

## §6 — Email-transport SMTP/SES/SendGrid follow-up scope

**Decision**: v1 ships the ABC + the `noop` adapter only. The `smtp`, `ses`, and `sendgrid` enum values are reserved (the validator accepts them as syntactically valid; the adapter factory raises `NotImplementedError` at startup). The follow-up spec implementing real transport is provisionally named **"spec 026 email-transport"** — a separate `/speckit.specify` ceremony triggered when the user schedules it. This spec's `contracts/email-transport.md` documents the ABC contract so the follow-up has a clear target.

**Rationale**: locks down v1 scope (one new dependency: `argon2-cffi`; no SMTP / SES / SendGrid client libraries). Operators running with `noop` get the audit-log fallback (clarify Q3) which is operator-recoverable for dev/staging. Production deployments that need real email transport schedule the follow-up spec; until then, the WARN at startup (clarify Q3) catches the obvious misconfiguration.

**Why not implement SMTP in v1**: stdlib `smtplib` is sync-only — wrapping in async via `asyncio.to_thread()` is workable but the connection management (TLS, auth, error handling, retry) is a non-trivial delivery surface. Splitting it out keeps spec 023 implementation focused on the account-model surface; the operator-affecting transport surface lands separately with its own clarification cycle.

**Alternatives considered**:
- **Ship SMTP in v1; defer SES + SendGrid** — adds significant scope to spec 023 implementation (SMTP TLS handling alone is non-trivial). Rejected for scope discipline.
- **Ship all three in v1** — rejected; three new deps (`smtplib` is stdlib but `boto3` and `sendgrid` are not), three new test surfaces, three new failure modes. Not the v1 minimum-viable scope.

---

## §7 — FR-020 (ownership transfer) in-or-defer decision

**Decision: SHIP FR-020 IN V1 (revised at impl-time, was DEFER provisionally).** User direction at scheduling time overrode the provisional defer. v1 ships the ownership-transfer endpoint with a header-keyed deployment-owner authentication shim — the new env var `SACP_DEPLOYMENT_OWNER_KEY` gates the endpoint. Operators set the value at deploy time (validated at startup); callers attach it as `X-Deployment-Owner-Key`. The shim is documented as the v1 admin-auth boundary; a future operator-auth spec can replace it without changing the endpoint shape (the key check moves to a dependency).

**What ships**: `POST /tools/admin/account/transfer_participants` mounted on the same conditional master switch as the rest of the account router; repoints `account_participants.account_id` from source to target; emits `account_ownership_transfer` audit row with actor, source, target, and participant ids; rejects regular-account requests with HTTP 403; rejects requests missing or carrying an incorrect `X-Deployment-Owner-Key` with HTTP 403 (no info leak between cases). The new env var `SACP_DEPLOYMENT_OWNER_KEY` is added to the V16 list (validators + docs/env-vars.md section).

**Rationale for revising**: the v1 schema already supports row-repointing (no migration), the audit row shape is already reserved (`account_ownership_transfer` action), and a header-keyed admin-auth shim is the lightest defensible boundary that doesn't lock the project into a specific operator-auth model later. The shim is intentionally minimal: a single static key, set via env var, never echoed in responses, scrubbed from logs by the existing ScrubFilter token-pattern. Future operator-auth specs (mTLS, OAuth M2M, etc.) can replace the dependency without changing the endpoint contract.

**Alternatives considered**:
- **Defer to a follow-up amendment** (was provisional) — rejected at scheduling; user wants the surface in v1.
- **Filesystem-touch admin path** (e.g., a marker file gated by user/group) — rejected; adds an out-of-process state surface and complicates Docker Compose deployments where the orchestrator runs in a container.
- **mTLS** — viable but heavier than v1 needs; requires CA management on the operator side. Reserve for a future operator-auth spec.

---

## §8 — Argon2id transparent re-hash trigger and rate

**Decision**: on every successful login, after `PasswordHasher.verify()` returns true, call `PasswordHasher.check_needs_rehash(stored_hash)`. If true, immediately re-hash the submitted plaintext with the current parameters and UPDATE `accounts.password_hash`. This happens within the login request handler (synchronously in the response path); the additional argon2id cost is bounded by the same `time_cost` × `memory_cost` budget as the verify itself.

**Latency impact**: a re-hash adds ~one argon2id hash worth of latency to a login that crosses a parameter boundary. Per default parameters (~50ms hash on commodity hardware), the latency floor of an upgrading login is ~100ms (verify + re-hash). Well within SC-002's 500ms P95 budget. For accounts that have already been re-hashed, `check_needs_rehash` returns false and the path is a no-op.

**No batch re-hash sweep**: the spec is intentionally amortized over login frequency. An account that never logs in after a parameter change keeps its old hash forever — that is the spec's accepted behavior (the account is dormant; raising the parameters is a defense-in-depth move for active accounts). A scheduled batch re-hash would require either holding plaintext (impossible) or a new "re-hash on next login" flag table; both are over-engineering.

**Rationale**: matches the OWASP 2024 cheat-sheet's recommendation explicitly. `argon2-cffi` ships `check_needs_rehash` as the canonical primitive for this exact case. Per-login amortization is the standard pattern across the industry (Passlib, Django, Rails — all use the same shape).

**Alternatives considered**:
- **Scheduled batch re-hash** — impossible without plaintext.
- **Force-logout-on-parameter-change with re-hash on next login** — rejected; UX cost (every active session terminated) for a defense-in-depth move that is already amortized by the per-login path.
- **Skip re-hash entirely** — rejected; SC-007 explicitly tests this behavior.

---

## §9 — `/me/sessions` query shape

**Decision**: single SQL query joining `account_participants` × `participants` × `sessions` filtered by `account_id`, ordered by `sessions.last_activity_at DESC`, segmented by status:

```sql
SELECT
  s.id AS session_id,
  s.name,
  s.last_activity_at,
  p.role,
  p.id AS participant_id,
  s.status
FROM account_participants ap
JOIN participants p ON p.id = ap.participant_id
JOIN sessions s ON s.id = p.session_id
WHERE ap.account_id = $1
ORDER BY s.last_activity_at DESC
LIMIT $2 OFFSET $3;
```

The query is run twice per request — once for active states (`s.status IN ('active', 'paused')`) and once for archived (`s.status = 'archived'`). Each segment paginates independently per clarify Q7.

**Indexes**:
- `account_participants(account_id)` — btree, primary lookup for the JOIN.
- `account_participants(participant_id)` — UNIQUE per FR-002, also serves as the lookup index for ownership-transfer FR-020 (deferred but data model supports it).
- `sessions(last_activity_at)` — already exists per spec 011; no new index.
- `sessions(status, last_activity_at DESC)` — composite; exists per spec 001 §FR-017.

**10,000-session warning trip** (FR-008): a count check `SELECT count(*) FROM account_participants WHERE account_id = $1` runs ahead of the segmented queries. If `count > 10_000`, emit a structured WARN log + insert an `admin_audit_log` row with `action='account_session_count_threshold_tripped'`. Cursor pagination is a backlog item; the offset-pagination performance break-even point is in the low five-figures and the warning lands well before performance degrades. The audit row is one-per-trip-per-day (idempotent on `(account_id, day(at))` via application-side dedup).

**Rationale**: indexed JOIN with offset pagination is the standard pattern; no new query shape invented. The 10,000 ceiling matches the user's clarification and prevents silent degradation.

**Alternatives considered**:
- **Cursor-based pagination from v1** — rejected per clarify Q6; offset is fine until 10K, warning trip catches the migration moment.
- **Single query with status segmentation in app code** — slightly cheaper but breaks the per-segment pagination contract from clarify Q7. Rejected.
- **Materialized view for `/me/sessions`** — over-engineering for the v1 scale. Rejected.

---

## §10 — Cookie-flow integration with the existing token-cookie path

**Decision**: account login mints a sid via the existing `SessionStore.create()` — extended to accept an optional `account_id` parameter that populates the new field on `SessionEntry`. The cookie shape is unchanged (signed dict carrying `{sid: <opaque>}`). On `GET /me/sessions`, the account_id from the entry filters the query.

**Rebind to a per-session participant**: when the SPA clicks an active session entry, it calls `POST /me/sessions/{session_id}/rebind` (new endpoint). The orchestrator looks up the participant_id via `account_participants.participant_id WHERE account_id = ? AND session_id = ?`, fetches the bearer from the existing per-session credential store (audit M-08 H-02 path), and updates the existing `SessionEntry` to set its `participant_id`, `session_id`, and `bearer` fields. The sid is preserved (single sid per cookie); the cookie does NOT change.

**Two-state SessionEntry**:
- **Account-only state**: `account_id` set, `participant_id`/`session_id`/`bearer` empty/nil. Reachable via account login.
- **Account-and-participant state**: all four fields set. Reachable via account login + rebind, or via the existing token-paste flow (with `account_id` left nil).

**Account-keyed reverse index** (`SessionStore._by_account: dict[str, set[str]]`): maintained on `create()` and `delete()`. Used by the password-change flow (FR-011) to enumerate all sids for an account_id and delete every sid except the actor's current one.

**Rationale**: preserves the H-02 invariant (single sid per cookie, no payload-readable bearer) while extending the entry to hold the account binding. The reverse index is a small process-local addition with no persistence implication; it lives only as long as the SessionStore process. The two-state shape lets the cookie work for both flows (token-paste and account-login) without a parallel cookie format.

**Alternatives considered**:
- **Two parallel SessionStores (one for tokens, one for accounts)** — rejected per clarify Q9 (extension over parallel store).
- **Account-id in the cookie payload** — rejected; the H-02 fix moved the bearer out of the cookie payload precisely to avoid cookie-jar exfiltration. Re-introducing readable account_id violates the same property.
- **Inline rebind in the `/me/sessions` GET response** — rejected; rebind is a state mutation (writes the bearer into the SessionEntry), it should be a POST.

---

## §11 — Spec 011 amendment trigger and content

**Decision**: amendment lands at `/speckit.tasks` time, NOT at plan time, per the user's reminder file (`reminder_spec_011_amendments_at_impl_time.md`). Plan phase produces the FIXED LIST of spec 011 surfaces this spec's UI work covers; tasks phase commits the amendment alongside the v1 implementation tasks.

**Surfaces (fixed by this research note)**:
1. **Login/logout flow** — replaces the current "paste a token" landing with a "log in or create account" choice. Token-paste remains available behind a "use a token instead" link for the master-switch-off operator deployment.
2. **Account-creation form** — email + password + verification-code submission UI.
3. **Post-login session list** — renders `/me/sessions` response. Active sessions first (live click → rebind via POST → SPA navigates into session), archived sessions second (read-only-transcript click → opens existing archived-session view).
4. **Account-settings panel** — email change, password change, account deletion. No disambiguation modal (no 409 in this spec).
5. **Email-change verification UI** — entry of the verification code emitted to the new email; old email's notification is informational (no UI handling required from the recipient).
6. **Password-change form** — current-password input + new-password input + confirmation. On success, SPA shows a "session refreshed" toast (the actor's sid survives per FR-011).
7. **Account-deletion confirmation** — typed-confirmation modal. On submit, SPA shows the post-deletion landing.

**No surfaces requiring clarify**:
- No 409 disambiguation modal (different from spec 025).
- No facilitator-scoped UI (account is end-user identity).
- No real-time WS event consumption (no new WS events added by spec 023; password-change invalidation surfaces as a 401 on the next SessionStore-gated request, which the SPA already handles per spec 011's existing 401 handler).

**Rationale**: pinning the surface list now removes the late-stage clarify pressure when the user schedules the spec for tasks. The amendment doc itself (the `Session 2026-05-NN (spec 023 user-accounts amendment)` Clarifications entry + new FRs + new SCs) is drafted at tasks time per the reminder.

**Alternatives considered**:
- **Bundle amendment now (matches spec 025's pattern)** — rejected per the user's reminder file. The reminder is explicit: defer the amendment to tasks time.
- **Separate `fix/spec-011-account-flow` PR after tasks** — rejected for the same reason.

---

## §12 — Topology-7 forward note

**Decision**: account-router init in `src/web_ui/account_routes.py` checks `os.environ.get('SACP_TOPOLOGY')`. If equal to `'7'`, the router refuses to mount and emits a startup ERROR naming the cross-spec incompatibility (per spec §V12). Same forward-document pattern as specs 014/020/021/025 — the gate exists; topology-7 deployments don't run accounts.

**Rationale**: spec §V12 explicitly enumerates topology 1–6 applicability. Topology 7 (MCP-to-MCP, Phase 3+) has no orchestrator-side account store. The startup gate makes the incompatibility explicit at deploy time rather than a runtime confusion.

**Alternatives considered**:
- **Silent no-op on topology 7** — rejected; operators deserve the explicit ERROR.
- **Runtime 404 on every account endpoint when topology=7** — duplicates the startup gate; silent runtime 404 is a worse signal than startup error.

---

## §13 — Cross-validator dependency between the email-transport WARN and the master switch

**Decision**: implement as a top-of-startup validator pair: `validate_accounts_enabled()` validates the master switch syntactically; `validate_email_transport()` validates the enum value syntactically. A separate function `emit_accounts_email_transport_warning()` reads BOTH env vars after the validators pass, and emits a startup WARN log entry (NOT a `ValidationFailure`) when `ACCOUNTS_ENABLED=true` AND `EMAIL_TRANSPORT=noop` simultaneously.

**Implementation pattern**:

```python
def validate_accounts_enabled() -> ValidationFailure | None:
    return _validate_bool_enum("SACP_ACCOUNTS_ENABLED")

def validate_email_transport() -> ValidationFailure | None:
    val = os.environ.get("SACP_EMAIL_TRANSPORT", "noop")
    if val not in {"noop", "smtp", "ses", "sendgrid"}:
        return ValidationFailure("SACP_EMAIL_TRANSPORT", f"must be one of: noop, smtp, ses, sendgrid; got {val!r}")
    return None

def emit_accounts_email_transport_warning() -> None:
    """Called from startup banner code AFTER validators pass."""
    accounts = os.environ.get("SACP_ACCOUNTS_ENABLED", "0")
    transport = os.environ.get("SACP_EMAIL_TRANSPORT", "noop")
    if accounts == "1" and transport == "noop":
        logger.warning(
            "SACP_ACCOUNTS_ENABLED=1 with SACP_EMAIL_TRANSPORT=noop: "
            "verification, reset, and notification codes will appear in "
            "admin_audit_log only. Not suitable for production."
        )
```

**Rationale**: keeps WARN-only state out of the `ValidationFailure` path so V16's fail-closed contract isn't tainted (failures abort startup; warnings don't). The split is mechanically simple and matches the existing pattern of separating syntactic validation from semantic cross-checks.

**Alternatives considered**:
- **Fold the WARN into `validate_email_transport()` via a side-effect log** — rejected; mixes the validator's pure-function nature with logging side effects, harder to test.
- **Make the cross-condition a `ValidationFailure`** — rejected per clarify Q3 (operators legitimately use noop in dev).

---

## Summary of Resolutions

| # | Question | Decision |
|---|---|---|
| 1 | Argon2id library | `argon2-cffi`, wrapped behind `src/accounts/hashing.py` |
| 2 | `accounts` columns | UUID id, partial unique email index, CHECK-constrained status, lower-cased application-side, empty-string sentinel for zeroed password |
| 3 | Code persistence | Audit-log only (HMAC-hashed), no durable codes table |
| 4 | Email transport ABC | Async ABC + Noop adapter; smtp/ses/sendgrid raise `NotImplementedError` at startup |
| 5 | Login rate limiter | Sliding-window, separate state from spec 019, additive composition |
| 6 | SMTP/SES/SendGrid | Reserved enum values; v1 ships noop only; follow-up spec lands real transport |
| 7 | FR-020 ownership transfer | DEFER to follow-up amendment (deployment-owner auth surface not in v1 scope) |
| 8 | Argon2id re-hash | Per-login amortized via `check_needs_rehash` |
| 9 | `/me/sessions` query | Single JOIN, segmented by status, offset paginated, 10K warning trip |
| 10 | Cookie integration | Extend `SessionEntry` with optional `account_id`; reverse index for FR-011; rebind via new POST endpoint |
| 11 | Spec 011 amendment | Defer to /speckit.tasks time; surface list locked here |
| 12 | Topology 7 gate | Account-router refuses to mount on topology 7 |
| 13 | Cross-validator WARN | Separate `emit_accounts_email_transport_warning()` function; not a `ValidationFailure` |

All Phase 0 unknowns resolved. Phase 1 design docs (data-model.md, contracts/, quickstart.md) can proceed.
