# Contract: Account HTTP Endpoints

**Branch**: `023-user-accounts` | **Source**: spec FR-005..FR-012, FR-016, FR-018 | **Date**: 2026-05-09

Defines the seven account-management endpoints + the session-list endpoint + the rebind endpoint. All endpoints are gated by `SACP_ACCOUNTS_ENABLED` (FR-018) — when `0` (default), every endpoint returns HTTP 404. Authentication, validation, and side-effect contracts are documented per endpoint.

---

## Master-switch gate (applies to all endpoints below)

When `SACP_ACCOUNTS_ENABLED=0` (default), the account router does NOT mount and every endpoint below returns HTTP 404 with body `{"error": "not_found"}` (no information leak about the surface's existence per FR-018).

When `SACP_TOPOLOGY=7`, the account router refuses to mount and emits a startup ERROR (research.md §12). The endpoints return HTTP 404 in this case as well.

---

## `POST /tools/account/create`

**Authentication**: none. Pre-auth per-IP rate limiter applies (FR-015).

### Request body

```json
{
  "email": "alice@example.com",
  "password": "<plaintext>"
}
```

### Validation

| Rule | Error | HTTP code |
|---|---|---|
| `email` is not a syntactically valid email | `email_invalid` | 422 |
| `password` length < 12 chars | `password_too_short` | 422 |
| `password` length > 1024 chars | `password_too_long` | 422 |
| `email` matches an existing `accounts.email` row with `status IN ('pending_verification', 'active')` | (generic; no info leak) `registration_failed` | 409 |
| `email` matches a `status='deleted'` row with `email_grace_release_at > now()` | (generic) `registration_failed` | 409 |
| Per-IP rate limit exceeded | `rate_limit_exceeded` + `Retry-After` | 429 |

### 201 Created response

```json
{
  "account_id": "acct_…",
  "status": "pending_verification",
  "verification_email_sent": true
}
```

### Side effects

- Insert `accounts` row with `status='pending_verification'`, `password_hash` argon2id-encoded.
- Insert `admin_audit_log` row `action='account_create'`.
- Generate 16-char base32 verification code; insert `admin_audit_log` row `action='account_verification_emitted'` with HMAC-hashed code in payload.
- Call `EmailTransport.send(purpose='verification', ...)`.

---

## `POST /tools/account/verify`

**Authentication**: none. Pre-auth per-IP rate limiter applies.

### Request body

```json
{
  "account_id": "acct_…",
  "code": "ABCDEFGH12345678"
}
```

### Validation

| Rule | Error | HTTP code |
|---|---|---|
| `code` length != 16 | `invalid_or_expired_code` | 400 |
| Code does not match a non-consumed `account_verification_emitted` row for this account_id within TTL | `invalid_or_expired_code` | 400 |
| Account `status` is not `'pending_verification'` | `invalid_or_expired_code` | 400 |

### 200 OK response

```json
{
  "account_id": "acct_…",
  "status": "active"
}
```

### Side effects

- UPDATE `accounts.status` to `'active'`, `accounts.updated_at` to `now()`.
- Insert `admin_audit_log` row `action='account_verification_consumed'` referencing the original emit row.

---

## `POST /tools/account/login`

**Authentication**: none. Pre-auth per-IP rate limiter applies (FR-015).

### Request body

```json
{
  "email": "alice@example.com",
  "password": "<plaintext>"
}
```

### Validation

The endpoint MUST always perform an argon2id `verify()` even when the email lookup misses — against a pinned dummy hash — to keep the timing-attack-resistance contract (SC-005, ±5ms).

| Rule | Error | HTTP code |
|---|---|---|
| Per-IP rate limit exceeded | `rate_limit_exceeded` + `Retry-After` | 429 |
| Email not found OR password verify fails OR account `status != 'active'` | `invalid_credentials` (generic — no info leak) | 401 |

### 200 OK response

Minimal body per clarify Q13 (FR-007 two-trip flow); session list NOT inlined.

```json
{
  "account_id": "acct_…",
  "expires_in": 604800
}
```

`Set-Cookie` header sets the existing spec 011 session cookie (signed dict carrying opaque sid). The `SessionEntry` is created with `account_id` populated and `participant_id`/`session_id`/`bearer` null until rebind.

### Side effects

- UPDATE `accounts.last_login_at` to `now()`.
- `SessionStore.create(account_id=...)` mints sid; reverse-index `_by_account` updated.
- `PasswordHasher.check_needs_rehash()` consulted; on true, re-hash with current params and UPDATE `accounts.password_hash` (SC-007 transparent re-hash).
- Insert `admin_audit_log` row `action='account_login'`.
- On failure: insert `admin_audit_log` row `action='account_login_failed'` with the offending IP + timing in payload.

---

## `GET /me/sessions`

**Authentication**: account-cookie (SessionStore lookup; `account_id` MUST be set on the entry).

### Query parameters

- `active_offset` (int, default 0): offset into the active-sessions segment.
- `archived_offset` (int, default 0): offset into the archived-sessions segment.

### 200 OK response

```json
{
  "active_sessions": [
    {
      "session_id": "ses_…",
      "name": "Research synthesis Tuesday",
      "last_activity_at": "2026-05-09T14:22:11Z",
      "role": "participant",
      "participant_id": "par_…",
      "status": "active"
    }
  ],
  "archived_sessions": [...],
  "active_next_offset": 50,
  "archived_next_offset": null
}
```

`*_next_offset` is the offset to pass for the next page or `null` when the segment is exhausted. Pagination is per segment (FR-008, clarify Q7).

### Side effects

- On every call, count `account_participants` for this account_id; if `count > 10_000`, emit a structured WARN log line + insert one `admin_audit_log` row with `action='account_session_count_threshold_tripped'` (idempotent on `(account_id, day(at))` via application-side dedup).
- Read-only otherwise; no mutation.

---

## `POST /me/sessions/{session_id}/rebind`

**Authentication**: account-cookie.

### 200 OK response

```json
{
  "session_id": "ses_…",
  "participant_id": "par_…",
  "rebound": true
}
```

### Validation

| Rule | Error | HTTP code |
|---|---|---|
| `session_id` does not appear in `account_participants` for this account | `not_found` | 404 |
| Account does not own a participant in that session | `not_found` (no info leak) | 404 |

### Side effects

- Look up `participant_id` via `account_participants WHERE account_id=? AND session_id=?` (joined through participants).
- Fetch bearer from per-session credential store.
- UPDATE the existing `SessionEntry` to populate `participant_id`, `session_id`, `bearer`. The sid + cookie are unchanged.
- No `admin_audit_log` row (rebind is participant-credential-binding only; no security-relevant state change beyond the in-memory entry).

---

## `POST /tools/account/email/change`

**Authentication**: account-cookie + active account (FR-010).

### Request body

```json
{
  "new_email": "alice2@example.com"
}
```

### Validation

| Rule | Error | HTTP code |
|---|---|---|
| `new_email` is not a syntactically valid email | `email_invalid` | 422 |
| `new_email` matches an existing active account or grace-window-locked deleted account | (generic) `email_change_failed` | 409 |
| Account `status != 'active'` | `not_authenticated` | 401 |

### 200 OK response

```json
{
  "verification_email_sent": true,
  "old_email_notified": true
}
```

### Side effects (clarify Q11)

- Generate 16-char base32 verification code; insert `admin_audit_log` row `action='account_email_change_emitted'` with HMAC-hashed code + `new_email` in payload.
- Call `EmailTransport.send(to=new_email, purpose='email_change_new', ...)`.
- Simultaneously emit a heads-up notification to the OLD email: insert `admin_audit_log` row `action='account_email_change_old_notified'`; call `EmailTransport.send(to=old_email, purpose='email_change_old_notify', ...)`. No action required from the OLD email recipient.
- The `accounts.email` field does NOT change until the verification code is submitted.

---

## `POST /tools/account/email/verify`

**Authentication**: account-cookie + active account.

### Request body

```json
{
  "code": "ABCDEFGH12345678"
}
```

### 200 OK response

```json
{
  "email_changed": true,
  "new_email": "alice2@example.com"
}
```

### Side effects

- Validate code matches an unconsumed `account_email_change_emitted` row within 24h TTL.
- UPDATE `accounts.email` to the `new_email` from the audit row's payload, `updated_at` to `now()`.
- Insert `admin_audit_log` row `action='account_email_change_consumed'`.

---

## `POST /tools/account/password/change`

**Authentication**: account-cookie + active account.

### Request body

```json
{
  "current_password": "<plaintext>",
  "new_password": "<plaintext>"
}
```

### Validation

| Rule | Error | HTTP code |
|---|---|---|
| `current_password` does not verify against stored hash | `invalid_credentials` (generic) | 401 |
| `new_password` length < 12 | `password_too_short` | 422 |
| `new_password` length > 1024 | `password_too_long` | 422 |

### 200 OK response

```json
{
  "password_changed": true,
  "other_sessions_invalidated": 3
}
```

### Side effects (clarify Q12)

- Argon2id-hash `new_password` with current params; UPDATE `accounts.password_hash`, `updated_at`.
- `SessionStore` reverse-index lookup: enumerate every sid associated with this account_id; delete every sid EXCEPT the actor's current sid (the request's authenticated sid survives).
- Insert `admin_audit_log` row `action='account_password_change'` with `other_sessions_invalidated` count in payload.

---

## `POST /tools/account/delete`

**Authentication**: account-cookie + active account.

### Request body

```json
{
  "current_password": "<plaintext>"
}
```

### Validation

| Rule | Error | HTTP code |
|---|---|---|
| `current_password` does not verify against stored hash | `invalid_credentials` (generic) | 401 |

### 200 OK response

```json
{
  "account_id": "acct_…",
  "status": "deleted",
  "export_email_sent": true,
  "email_grace_release_at": "2026-05-16T14:22:11Z"
}
```

### Side effects (FR-012, FR-013, clarify Q5)

- Generate spec 010 debug-export containing every session the account joined; route through `EmailTransport.send(purpose='account_delete_export', ...)`. Deletion proceeds even if email transport fails (privacy-preserving default per spec edge case).
- UPDATE `accounts`:
  - `email = ''`
  - `password_hash = ''`
  - `status = 'deleted'`
  - `deleted_at = now()`
  - `email_grace_release_at = now() + (SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS × interval '1 day')`
  - `updated_at = now()`
- The account row REMAINS in place (no DELETE) to preserve participant-audit linkage.
- `SessionStore`: invalidate ALL sids for this account_id (no actor-sid carve-out — the actor is deleting themselves).
- Insert `admin_audit_log` row `action='account_delete'`.

---

## Authorization summary

| Endpoint | Master switch | Pre-auth limiter | Account cookie | Active account |
|---|---|---|---|---|
| `POST /tools/account/create` | required | yes | no | n/a |
| `POST /tools/account/verify` | required | yes | no | n/a (flips status to active) |
| `POST /tools/account/login` | required | yes | no | required (status='active' on the row being logged into) |
| `GET /me/sessions` | required | no | required | required |
| `POST /me/sessions/{id}/rebind` | required | no | required | required |
| `POST /tools/account/email/change` | required | no | required | required |
| `POST /tools/account/email/verify` | required | no | required | required |
| `POST /tools/account/password/change` | required | no | required | required |
| `POST /tools/account/delete` | required | no | required | required |

---

## ScrubFilter coverage (FR-014, SC-012)

The following request fields and audit-log payload fields MUST be scrubbed from log content:

- `password`, `current_password`, `new_password` (request body fields)
- `code` (verification, reset, email-change request body fields)
- `email body content` (in noop adapter audit rows; only `body_length` is logged, never the body)

Scrub patterns land in `src/security/scrubber.py` alongside the existing patterns. Spec 007 §FR-012 ScrubFilter is the integration point.

---

## Test obligations

- `test_023_account_create.py`: 201 success, 422 invalid email/password, 409 collision, 429 rate limit.
- `test_023_login_timing.py`: SC-005 ±5ms timing test for non-existent-email vs. wrong-password paths.
- `test_023_login_rate_limit.py`: SC-006 per-IP limiter trips at threshold; 429 + `Retry-After`.
- `test_023_me_sessions.py`: segmentation (active first, archived second), per-segment pagination, cross-account isolation (SC-004), 10K threshold trip.
- `test_023_email_change.py`: notify-old + verify-new flow per clarify Q11; both audit rows emitted.
- `test_023_password_change.py`: SessionStore invalidation per clarify Q12; actor sid survives, others invalidated.
- `test_023_account_delete.py`: debug-export emit, credential zeroing, grace-period reservation, audit row preservation.
- `test_023_master_switch_off.py`: `SACP_ACCOUNTS_ENABLED=0` → 404 on every endpoint above.
