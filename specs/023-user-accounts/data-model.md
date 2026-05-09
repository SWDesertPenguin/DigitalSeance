# Data Model: User Accounts with Persistent Session History

**Branch**: `023-user-accounts` | **Date**: 2026-05-09 | **Plan**: [plan.md](./plan.md)

Captures entities, schema additions, table relationships, and validation rules derived from [spec.md](./spec.md) and [research.md](./research.md).

---

## Schema additions

One alembic migration (`alembic/versions/013_user_accounts.py`) adds two new tables and zero changes to existing tables. The `tests/conftest.py` raw-DDL mirror MUST be updated alongside the migration (memory: `feedback_test_schema_mirror.md`).

### `accounts`

| Column | Type | Default | Constraints | Source |
|---|---|---|---|---|
| `id` | `uuid` | `gen_random_uuid()` | PRIMARY KEY | FR-001, research.md §2 |
| `email` | `text` | (none) | NOT NULL; partial UNIQUE index `accounts_email_active_uidx` covering `WHERE status IN ('pending_verification', 'active')` | FR-001, research.md §2 |
| `password_hash` | `text` | (none) | NOT NULL (empty string is the post-deletion sentinel); ASCII argon2id-encoded form when non-empty | FR-003, research.md §2 |
| `status` | `text` | `'pending_verification'` | NOT NULL; CHECK `status IN ('pending_verification', 'active', 'deleted')` | FR-001, research.md §2 |
| `created_at` | `timestamptz` | `now()` | NOT NULL | FR-001 |
| `updated_at` | `timestamptz` | `now()` | NOT NULL; trigger updates on row UPDATE | FR-001 |
| `last_login_at` | `timestamptz` | NULL | nullable; populated on each successful login | FR-001 |
| `deleted_at` | `timestamptz` | NULL | nullable; populated when `status` flips to `'deleted'` | FR-012 |
| `email_grace_release_at` | `timestamptz` | NULL | nullable; populated at deletion time = `deleted_at + (SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS × interval '1 day')` | FR-013, research.md §2 |

**Index summary**:
- Primary key on `id`.
- Partial unique index on `(email)` where `status IN ('pending_verification', 'active')` — enforces "no two active or pending accounts share an email" but lets a deleted-account row coexist with a fresh registration on the same email after grace expiry.
- No additional indexes in v1 (the partial unique index doubles as the email-lookup index for login).

### `account_participants`

| Column | Type | Default | Constraints | Source |
|---|---|---|---|---|
| `id` | `uuid` | `gen_random_uuid()` | PRIMARY KEY | FR-002 |
| `account_id` | `uuid` | (none) | NOT NULL; FK → `accounts.id` ON DELETE RESTRICT | FR-002, FR-012 |
| `participant_id` | `text` | (none) | NOT NULL; UNIQUE; FK → `participants.id` ON DELETE CASCADE | FR-002, research.md §9 |
| `created_at` | `timestamptz` | `now()` | NOT NULL | FR-002 |

**Index summary**:
- Primary key on `id`.
- UNIQUE on `participant_id` — enforces FR-002's "a participant belongs to at most one account."
- btree on `account_id` — primary lookup index for `/me/sessions` (research.md §9).

**FK semantics**:
- `accounts.id` is `ON DELETE RESTRICT`: deleting an account row outright would orphan participant ownership; the spec requires zeroing credentials but preserving the row (FR-012). RESTRICT enforces this at the DB layer.
- `participants.id` is `ON DELETE CASCADE`: when a participant row is deleted (e.g., a session is hard-purged per spec 010 retention), the corresponding `account_participants` join row goes with it.

### Cross-column constraints

Application-side (NOT SQL CHECK, due to multi-column-rule subtlety):

- When `accounts.status = 'deleted'`:
  - `email` MUST be empty string (zeroed post-delete) per FR-012.
  - `password_hash` MUST be empty string (zeroed post-delete) per FR-012.
  - `deleted_at` MUST be set.
  - `email_grace_release_at` MUST be set.
- When `accounts.status = 'pending_verification'`:
  - `last_login_at` MUST be NULL (no login until verified).
- When `accounts.status = 'active'`:
  - `email` and `password_hash` MUST be non-empty.
  - `deleted_at` MUST be NULL.

These rules are validated in `src/accounts/service.py` and asserted in `tests/conftest.py` mirror as comments referencing the application-side check.

---

## Entities

### `Account`

The full account row. Mutable via the seven account endpoints (FR-005..FR-012); read-only via internal queries (no read endpoint on the account row directly — `GET /me/sessions` returns the joined session list, not the account row itself).

```python
@dataclass(frozen=True)
class Account:
    id: str  # UUID
    email: str  # lower-cased; empty string when status='deleted'
    password_hash: str  # argon2id encoded; empty string when status='deleted'
    status: Literal['pending_verification', 'active', 'deleted']
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    deleted_at: datetime | None
    email_grace_release_at: datetime | None
```

### `AccountParticipant`

Join row binding an account to a per-session participant. Mutable on participant creation (the participant-creation flow checks if a logged-in account exists on the request and inserts a join row if so; the master-switch-off path skips the insert) and on account deletion (the rows persist but the `accounts.id` FK target is now in `status='deleted'`).

```python
@dataclass(frozen=True)
class AccountParticipant:
    id: str  # UUID
    account_id: str
    participant_id: str
    created_at: datetime
```

### `VerificationCode` (transient)

Single-use 16-character base32 string (Crockford alphabet) with 24h TTL. NOT a durable entity — persisted only in `admin_audit_log` rows (research.md §3). The plaintext code goes to the email transport once; the durable record is the HMAC-SHA256 hash (using `SACP_AUTH_LOOKUP_KEY`) in the audit-log row's payload.

```python
@dataclass(frozen=True)
class VerificationCode:
    plaintext: str  # 16 chars; never persisted
    hash: str  # HMAC-SHA256 hex; persisted in admin_audit_log
    account_id: str
    expires_at: datetime
```

### `ResetCode` (transient)

Same shape as `VerificationCode`; TTL 30 minutes per clarify Q4 instead of 24h. Persisted only in `admin_audit_log`.

### `EmailChangeToken` (transient)

Same shape; TTL 24h; consumed-on-submit. Persisted only in `admin_audit_log` with a payload that includes the `new_email` so consumption can perform the email field update atomically.

### `PasswordHash`

Argon2id-encoded hash string. Format: `$argon2id$v=19$m=<memory>,t=<time>,p=<parallelism>$<salt>$<hash>`. Stored in `accounts.password_hash`. The encoded format includes the parameters used at hash time; `argon2.PasswordHasher.check_needs_rehash(stored)` returns true when the stored params differ from the current `SACP_PASSWORD_ARGON2_*` env vars (research.md §1, §8).

**Re-hash semantics** (SC-007): on every successful login, after `verify()` returns true, `check_needs_rehash()` is consulted; on true, the plaintext (still in scope from the request body) is re-hashed with current parameters and the row is UPDATED.

### `SessionEntry (extended)`

Spec 011's existing `SessionEntry` (in `src/web_ui/session_store.py`) gains an optional `account_id` field. The existing fields (`sid`, `participant_id`, `session_id`, `bearer`, `created_at`) are preserved.

```python
@dataclass(frozen=True)
class SessionEntry:
    sid: str
    participant_id: str | None  # null when account-only state (pre-rebind)
    session_id: str | None  # null when account-only state
    bearer: str | None  # null when account-only state
    created_at: float
    account_id: str | None = None  # NEW — set when account login mints the sid
```

The fields can be in two states (research.md §10):
- **Account-only**: `account_id` set; `participant_id`/`session_id`/`bearer` null. Reachable via account login.
- **Account-and-participant**: all fields set. Reachable via account login + rebind, or via the existing token-paste flow (with `account_id` left null for legacy).

The `SessionStore` gains a reverse index `_by_account: dict[str, set[str]]` mapping `account_id` to its active sids. Maintained on `create()` / `delete()`. Used by FR-011's password-change invalidation (delete every sid except the actor's current one).

### `EmailTransport` (process-scope adapter)

ABC selected at startup via `SACP_EMAIL_TRANSPORT`. v1 ships `NoopEmailTransport` only; the other three enum values raise `NotImplementedError` at startup (research.md §4, §6).

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

`NoopEmailTransport` writes a structured `admin_audit_log` row with `action='account_email_noop_emitted'` (purpose, to-hashed, body-length); body content is NOT included.

### `LoginRateLimiter` (process-scope)

Per-IP sliding-window limiter for `/login` and `/create-account`; separate from spec 019's middleware (FR-015, research.md §5).

```python
class LoginRateLimiter:
    """Sliding-window deque per IP; window=60s; threshold=SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN."""
    _state: dict[str, deque[float]]
    _lock: asyncio.Lock

    async def check(self, ip: str) -> None:
        """Append timestamp; evict old; raise RateLimitExceeded if over threshold."""
```

---

## Cross-spec references

- **Spec 001 (core-data-model)** — schema changes follow §FR-017 forward-only constraint; `accounts` and `account_participants` are new tables; no rewrites or DROPs of existing tables.
- **Spec 002 (participant-auth)** — participant rows remain the per-session security primitive. `account_participants.participant_id` FKs into `participants.id`. Token rotation per spec 002 §FR-007 still happens; the account is an ownership pointer ABOVE the token, not a replacement (FR-016).
- **Spec 007 (ai-security-pipeline) §FR-012** — the ScrubFilter is extended (FR-014) to scrub: argon2id plaintext passwords (incoming request bodies), 16-char base32 codes (verification, reset, email-change), email body content. The scrub patterns land in `src/security/scrubber.py` alongside the existing patterns.
- **Spec 009 (rate-limiting)** — sliding-window algorithm + 429 + Retry-After response shape that this spec's per-IP login limiter follows.
- **Spec 010 (debug-export)** — the export shape consumed by FR-012's account-deletion debug-export. The deletion flow calls the existing internal export function and routes the result through the email transport.
- **Spec 011 (web-ui)** — `SessionStore` is extended (FR-016, research.md §10). Spec 011 amendment lands at `/speckit.tasks` time per the user's reminder (research.md §11). The opaque-sid + signed cookie + H-02 invariants are preserved.
- **Spec 019 (network-rate-limiting)** — separate per-IP limiter at the orchestrator's HTTP boundary. Spec 023's limiter is a tighter, narrower limiter applied at `/login` and `/create-account` only; both apply additively (FR-015, clarify Q10).
- **Spec 024 (facilitator scratch, future)** — pairs with this spec; scratch notes attach to an account row. Spec 024 assumes 023 is implemented and consumes `accounts.id` as the FK target for the scratch-notes table.
- **Constitution V8** — accounts add a Tier-1 secret (password hashes, codes, body content) and a Tier-2 PII (email). Storage and scrub semantics documented in research.md §3 and FR-014.
- **Constitution V11** — one new runtime dependency (`argon2-cffi`); pinned per §6.3. Documented in plan.md and research.md §1.

---

## `admin_audit_log.action` values introduced

This spec introduces 13 new `action` values; payload schemas land in [contracts/audit-log-events.md](./contracts/audit-log-events.md):

- `account_create`
- `account_verification_emitted`
- `account_verification_consumed`
- `account_login`
- `account_login_failed`
- `account_email_change_emitted`
- `account_email_change_old_notified`
- `account_email_change_consumed`
- `account_password_change`
- `account_password_reset_emitted`
- `account_password_reset_consumed`
- `account_delete`
- `account_session_count_threshold_tripped`
- `account_email_noop_emitted` (transport-level; emitted by NoopEmailTransport)
- `account_ownership_transfer` (RESERVED for follow-up amendment per research.md §7; included in v1 contract so future implementation slots in without contract change)

The `routing_log` table is NOT extended by this spec (different from spec 025); all account-related events route through `admin_audit_log` only.
