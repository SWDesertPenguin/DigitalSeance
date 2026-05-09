# Contract: `admin_audit_log` Action Values

**Branch**: `023-user-accounts` | **Source**: spec FR-019, FR-014, edge cases | **Date**: 2026-05-09

Lists the new `admin_audit_log.action` values introduced by this spec, plus payload schemas and ScrubFilter rules. Cross-references spec 001 §FR-019 (audit-log carve-out for deleted accounts) and spec 007 §FR-012 (ScrubFilter integration).

The `routing_log` table is NOT extended by this spec; all account-related events route through `admin_audit_log` only. (Different from spec 025, which adds five `routing_log.reason` values.)

---

## Action values introduced

| Action | Trigger | Actor | Target |
|---|---|---|---|
| `account_create` | `POST /tools/account/create` 201 success | none (pre-auth) | account_id |
| `account_verification_emitted` | verification code generated | none / system | account_id |
| `account_verification_consumed` | verification code accepted | account_id | account_id (self) |
| `account_login` | `POST /tools/account/login` 200 success | account_id | account_id (self) |
| `account_login_failed` | login 401 OR 429 | none / IP-only | account_id (when known) or null |
| `account_email_change_emitted` | email-change request initiated | account_id | account_id (self) |
| `account_email_change_old_notified` | OLD-email heads-up notification sent | account_id | account_id (self) |
| `account_email_change_consumed` | email-change verification code submitted | account_id | account_id (self) |
| `account_password_change` | password change 200 success | account_id | account_id (self) |
| `account_password_reset_emitted` | password-reset request initiated (separate /reset endpoint, future-deferred per Q4) | none (pre-auth) | account_id (when email matches) |
| `account_password_reset_consumed` | password reset 200 success | account_id (post-reset) | account_id |
| `account_delete` | `POST /tools/account/delete` 200 success | account_id | account_id (self) |
| `account_session_count_threshold_tripped` | `/me/sessions` count > 10,000 | account_id | account_id (self) |
| `account_email_noop_emitted` | NoopEmailTransport.send called | none / system | account_id |
| `account_email_send_failed` | EmailTransport.send raised | none / system | account_id |
| `account_ownership_transfer` | RESERVED for follow-up amendment per research.md §7 | (deployment-owner) | source + target account_ids |

All rows use the existing `admin_audit_log` schema (no schema change). Payload extensions are application-side JSON in the existing `payload` column.

---

## Payload schemas

### `account_create`

```json
{
  "account_id": "acct_…",
  "email_hash": "<HMAC-SHA256(email, SACP_AUTH_LOOKUP_KEY)>",
  "client_ip": "203.0.113.42"
}
```

The `email_hash` is included for cross-account-isolation forensic lookup (e.g., "what other audit rows belong to this email's account history?") without storing the plaintext email in the log.

### `account_verification_emitted`

```json
{
  "account_id": "acct_…",
  "code_hash": "<HMAC-SHA256(plaintext_code, SACP_AUTH_LOOKUP_KEY)>",
  "ttl_seconds": 86400,
  "expires_at": "2026-05-10T14:22:11Z"
}
```

The `code_hash` is the durable record; the plaintext code goes to the email transport once and is never persisted.

### `account_verification_consumed`

```json
{
  "account_id": "acct_…",
  "emit_row_id": "<id of the matching account_verification_emitted row>",
  "consumed_at": "2026-05-09T14:25:11Z"
}
```

### `account_login`

```json
{
  "account_id": "acct_…",
  "client_ip": "203.0.113.42",
  "rehash_performed": false
}
```

`rehash_performed` is `true` when the login triggered SC-007 transparent re-hash on parameter change.

### `account_login_failed`

```json
{
  "client_ip": "203.0.113.42",
  "email_hash": "<HMAC-SHA256(submitted_email, SACP_AUTH_LOOKUP_KEY)>",
  "failure_reason": "invalid_credentials" | "rate_limit_exceeded",
  "elapsed_ms": 487
}
```

`failure_reason` is the diagnostic detail kept OUT of the HTTP response (which returns a generic body per SC-005). The `elapsed_ms` field supports timing-leak forensic analysis.

### `account_email_change_emitted`

```json
{
  "account_id": "acct_…",
  "old_email_hash": "<HMAC of old email>",
  "new_email_hash": "<HMAC of new email>",
  "code_hash": "<HMAC of code>",
  "ttl_seconds": 86400,
  "expires_at": "..."
}
```

### `account_email_change_old_notified`

```json
{
  "account_id": "acct_…",
  "old_email_hash": "<HMAC of old email>",
  "new_email_hash": "<HMAC of new email>",
  "notified_at": "..."
}
```

Emitted simultaneously with `account_email_change_emitted` per FR-010 + clarify Q11.

### `account_email_change_consumed`

```json
{
  "account_id": "acct_…",
  "emit_row_id": "<id of the matching account_email_change_emitted row>",
  "old_email_hash": "<HMAC of old email>",
  "new_email_hash": "<HMAC of new email>",
  "consumed_at": "..."
}
```

### `account_password_change`

```json
{
  "account_id": "acct_…",
  "client_ip": "203.0.113.42",
  "other_sessions_invalidated": 3
}
```

`other_sessions_invalidated` counts sids deleted from `SessionStore` excluding the actor's current sid (FR-011 + clarify Q12).

### `account_password_reset_emitted` / `_consumed`

Same shape as the verification pair; TTL 30 minutes instead of 24 hours (clarify Q4).

### `account_delete`

```json
{
  "account_id": "acct_…",
  "client_ip": "203.0.113.42",
  "deleted_at": "...",
  "email_grace_release_at": "...",
  "export_email_outcome": "sent" | "failed"
}
```

The `email_grace_release_at` field captures the grace-period deadline computed at deletion time from `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`.

### `account_session_count_threshold_tripped`

```json
{
  "account_id": "acct_…",
  "session_count": 10042,
  "threshold": 10000
}
```

Idempotent on `(account_id, day(at))` via application-side dedup — at most one row per account per UTC day.

### `account_email_noop_emitted`

```json
{
  "purpose": "verification",
  "to_hashed": "<HMAC of `to`>",
  "subject": "Verify your SACP account",
  "body_length": 412,
  "_dev_plaintext": "ABCDEFGH12345678"
}
```

The `_dev_plaintext` field is present ONLY when the noop adapter is selected (the cross-condition WARN flags this as production-unsafe). The field is scrubbed from any log emission outside the audit-log INSERT path per FR-014.

### `account_email_send_failed`

```json
{
  "purpose": "verification",
  "to_hashed": "<HMAC of `to`>",
  "transport": "noop" | "smtp" | "ses" | "sendgrid",
  "exception_class": "EmailTransportUnavailable",
  "exception_message": "<scrubbed>"
}
```

Caller falls back to admin_audit_log-only recording per the spec edge case.

### `account_ownership_transfer` (RESERVED)

Reserved per research.md §7. Schema TBD by the follow-up amendment; included here so future implementation slots in without contract change. Provisional shape:

```json
{
  "actor_id": "<deployment-owner-id; auth surface TBD by follow-up>",
  "source_account_id": "acct_…",
  "target_account_id": "acct_…",
  "participant_ids": ["par_…", "par_…"],
  "transferred_at": "..."
}
```

---

## ScrubFilter rules (FR-014, SC-012)

The following payload fields are NEVER plaintext in the audit log:

- `password_hash` (only the argon2id encoded form is ever stored, in `accounts.password_hash`; never in audit log).
- Verification / reset / email-change codes (only HMAC hashes appear; the plaintext exists in `_dev_plaintext` ONLY for the noop adapter).
- Email body content (only `body_length` is logged).
- Plaintext emails (only HMAC hashes appear; cross-account-isolation lookups use the hash).

The ScrubFilter (spec 007 §FR-012) integration extends the existing patterns in `src/security/scrubber.py` to cover:

1. Argon2id-encoded password hashes if they appear in any log line outside `accounts.password_hash` storage (defense-in-depth).
2. 16-character base32 codes (Crockford alphabet) — pattern match `[0-9A-HJKMNP-TV-Z]{16}` with allowlist for the audit-log INSERT statement only.
3. Email-address plaintext in any log line outside the noop adapter's `_dev_plaintext` field.

---

## Carve-out: account deletion preserves audit rows

Per spec 001 §FR-019 (Art. 17(3)(b)) and FR-019: deletion of an account does NOT remove or redact `admin_audit_log` rows about that account's actions. The rows persist with their original payloads, including the (already-hashed) email + code references.

The `accounts.id` UUID remains a valid FK target after deletion (the row is preserved; only credential fields are zeroed), so audit rows continue to resolve their `target_id` lookup correctly.

---

## Test obligations

- Each of the 14 new action values has at least one test asserting the row is written with the documented payload shape on the trigger event.
- `test_023_scrub_filter.py` (SC-012) drives login + create + change-password and asserts:
  - No password material appears in any log line.
  - No verification / reset / change codes appear in plaintext outside `_dev_plaintext`.
  - No email plaintext appears outside HMAC hashes.
- `test_023_account_delete.py` asserts audit-row preservation post-delete (the rows about the deleted account remain queryable).
