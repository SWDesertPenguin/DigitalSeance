# Quickstart: User Accounts with Persistent Session History

**Branch**: `023-user-accounts` | **Date**: 2026-05-09 | **Plan**: [plan.md](./plan.md)

Operator + end-user workflows for opting into the user-accounts surface. Default behavior with no configuration is unchanged from pre-feature: the SPA renders the existing token-paste landing and accounts are entirely absent. The accounts surface is strictly opt-in via the master switch `SACP_ACCOUNTS_ENABLED` (FR-018).

---

## Operator workflow

### Enable the accounts surface (opt-in)

Edit the `.env` file used by the Dockge stack at `/mnt/.ix-apps/app_mounts/dockge/stacks/sacp/.env` (per project memory `project_deploy_dockge_truenas.md`):

```bash
# Master switch — turns the entire account surface on.
SACP_ACCOUNTS_ENABLED=1                            # default 0; set to 1 to enable.

# Argon2id parameters — OWASP 2024 cheat-sheet defaults.
SACP_PASSWORD_ARGON2_TIME_COST=2                   # range [1, 10]; default 2.
SACP_PASSWORD_ARGON2_MEMORY_COST_KB=19456          # range [7168, 1048576]; default 19456 (19 MiB).

# Account session cookie TTL.
SACP_ACCOUNT_SESSION_TTL_HOURS=168                 # range [1, 8760]; default 168 (7 days).

# Per-IP login rate limiter (separate from spec 019's limiter; additive composition).
SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN=10          # range [1, 1000]; default 10.

# Email transport. v1 ships only "noop"; smtp/ses/sendgrid are reserved for a follow-up spec.
SACP_EMAIL_TRANSPORT=noop                          # one of: noop, smtp, ses, sendgrid; default noop.

# Account-deletion email grace period.
SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS=7           # range [0, 365]; default 7. 0 = immediate release.
```

Restart the orchestrator stack from Dockge. Verify config validation passes:

```bash
docker compose logs sacp-orchestrator | grep -i "config validation"
# Expected: "Config validation: 7 new SACP_ACCOUNT*/PASSWORD_ARGON2_*/EMAIL_TRANSPORT validators passed"
```

If any value is out of range, the orchestrator process exits at startup before binding ports (V16 fail-closed). The error message names the offending variable.

### Cross-condition WARN (development environments)

If `SACP_ACCOUNTS_ENABLED=1` AND `SACP_EMAIL_TRANSPORT=noop`, the orchestrator emits a startup WARNING (NOT a fail-closed exit) per FR-022:

```bash
docker compose logs sacp-orchestrator | grep -i "WARN"
# Expected line:
# WARN: SACP_ACCOUNTS_ENABLED=1 with SACP_EMAIL_TRANSPORT=noop:
#       verification, reset, and notification codes will appear in
#       admin_audit_log only. Not suitable for production.
```

This combination is legitimate for dev/staging — codes appear in `admin_audit_log` rows that operators can read. The warning catches the obvious production misconfiguration without blocking the dev flow.

### Verify schema migration applied

After the alembic migration lands:

```bash
docker compose exec sacp-orchestrator alembic current
# Expected output ends with: 013_user_accounts (head)

docker compose exec sacp-postgres psql -U sacp -d sacp -c "\dt accounts account_participants"
# Expected: 2 rows (accounts and account_participants tables)

docker compose exec sacp-postgres psql -U sacp -d sacp -c "\d accounts"
# Expected: 9 columns (id, email, password_hash, status, created_at, updated_at,
# last_login_at, deleted_at, email_grace_release_at) plus the partial unique index.
```

### Switch from noop to a real email transport

`smtp`, `ses`, and `sendgrid` are RESERVED enum values; v1 raises `NotImplementedError` at startup if any of them is selected. Setting (e.g.) `SACP_EMAIL_TRANSPORT=smtp` produces a startup ERROR:

```bash
docker compose logs sacp-orchestrator | grep -i "SACP_EMAIL_TRANSPORT"
# Expected:
# ERROR: SACP_EMAIL_TRANSPORT='smtp' is reserved for a follow-up spec;
# v1 supports only 'noop'. See specs/023-user-accounts/contracts/email-transport.md.
```

Real SMTP / SES / SendGrid wiring lands in a follow-up spec (provisional name "spec 026 email-transport"). Until then, the noop adapter is the only operational transport; production deployments needing real email should defer enabling accounts until the follow-up ships.

---

## End-user workflow

### Create an account

The SPA's landing page (with `SACP_ACCOUNTS_ENABLED=1`) presents a "log in" or "create account" choice. Click "create account":

```bash
curl -X POST "https://sacp.local/tools/account/create" \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "correct-horse-battery-staple"}'
```

Successful response (HTTP 201):

```json
{
  "account_id": "acct_…",
  "status": "pending_verification",
  "verification_email_sent": true
}
```

The orchestrator emits a verification code via the configured email transport. With `SACP_EMAIL_TRANSPORT=noop` (dev), the code lands in `admin_audit_log`:

```bash
docker compose exec sacp-postgres psql -U sacp -d sacp -c \
  "SELECT at, action, payload FROM admin_audit_log WHERE action='account_verification_emitted' ORDER BY at DESC LIMIT 1;"
```

The payload carries the **HMAC hash** of the code (NOT the plaintext); the plaintext appears in the `account_email_noop_emitted` row alongside it (via the noop transport). Read both rows together to retrieve the code. Production transports will emit the plaintext to the user's inbox directly.

### Verify the account

```bash
curl -X POST "https://sacp.local/tools/account/verify" \
  -H "Content-Type: application/json" \
  -d '{"account_id": "acct_…", "code": "ABCDEFGH12345678"}'
```

Successful response (HTTP 200):

```json
{
  "account_id": "acct_…",
  "status": "active"
}
```

Failed response (HTTP 400) for an incorrect or expired code:

```json
{"error": "invalid_or_expired_code"}
```

### Log in

```bash
curl -X POST "https://sacp.local/tools/account/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "correct-horse-battery-staple"}' \
  -c cookies.txt
```

Successful response (HTTP 200) — minimal body, session cookie set in the response headers (FR-007 two-trip flow):

```json
{
  "account_id": "acct_…",
  "expires_in": 604800
}
```

Failed response (HTTP 401) — generic body for non-existent email OR wrong password:

```json
{"error": "invalid_credentials"}
```

The non-existent-email and existing-email-wrong-password paths return identical bodies + identical timing within ±5ms (SC-005, timing-attack resistance).

Rate-limited response (HTTP 429) when the per-IP limiter trips:

```json
{"error": "rate_limit_exceeded"}
```

`Retry-After` header set per FR-015.

### List your sessions

After login (with the cookie from `login`):

```bash
curl "https://sacp.local/me/sessions" -b cookies.txt
```

Successful response (HTTP 200):

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
  "archived_sessions": [
    {
      "session_id": "ses_…",
      "name": "Q1 strategy review",
      "last_activity_at": "2026-04-12T09:15:33Z",
      "role": "facilitator",
      "participant_id": "par_…",
      "status": "archived"
    }
  ],
  "active_next_offset": null,
  "archived_next_offset": null
}
```

Pagination per segment (offset, 50/page):

```bash
curl "https://sacp.local/me/sessions?active_offset=50&archived_offset=0" -b cookies.txt
```

When the account's joined-session count exceeds 10,000, a structured WARN log + an `admin_audit_log` row with `action='account_session_count_threshold_tripped'` are emitted.

### Rebind to an active session

Click an active session entry; the SPA calls:

```bash
curl -X POST "https://sacp.local/me/sessions/ses_…/rebind" -b cookies.txt
```

The orchestrator looks up the participant_id via `account_participants WHERE account_id = ? AND session_id = ?`, fetches the bearer from the per-session credential store, and updates the existing `SessionEntry` to set `participant_id`, `session_id`, and `bearer`. The sid + cookie are preserved.

### Change your email

```bash
curl -X POST "https://sacp.local/tools/account/email/change" \
  -H "Content-Type: application/json" \
  -d '{"new_email": "alice2@example.com"}' \
  -b cookies.txt
```

The orchestrator emits a verification code to the NEW email AND simultaneously emits a heads-up notification to the OLD email (clarify Q11). The email field does NOT update until the verification code is submitted:

```bash
curl -X POST "https://sacp.local/tools/account/email/verify" \
  -H "Content-Type: application/json" \
  -d '{"code": "ABCDEFGH12345678"}' \
  -b cookies.txt
```

### Change your password

```bash
curl -X POST "https://sacp.local/tools/account/password/change" \
  -H "Content-Type: application/json" \
  -d '{"current_password": "correct-horse-battery-staple", "new_password": "Tr0ub4dor&3"}' \
  -b cookies.txt
```

Successful response (HTTP 200): the new password is argon2id-hashed and stored. Every `SessionStore` sid associated with this account_id is invalidated EXCEPT the actor's current sid (clarify Q12) — other browser tabs and devices are forced to re-authenticate; the request flow continues.

### Delete your account

```bash
curl -X POST "https://sacp.local/tools/account/delete" \
  -H "Content-Type: application/json" \
  -d '{"current_password": "correct-horse-battery-staple"}' \
  -b cookies.txt
```

Successful response (HTTP 200):
- A debug-export (spec 010 format) containing every session the account joined is emitted to the registered email.
- The `email` and `password_hash` fields are zeroed (empty string).
- `status` flips to `'deleted'`.
- `deleted_at` and `email_grace_release_at` are populated.

The account row REMAINS in place to preserve participant-audit linkage (FR-012). Only the credential fields are released. Re-registration with the same email is rejected during the grace window (FR-013):

```bash
docker compose exec sacp-postgres psql -U sacp -d sacp -c \
  "SELECT id, email, status, deleted_at, email_grace_release_at FROM accounts WHERE status='deleted';"
```

After the grace window elapses (`now() > email_grace_release_at`), the email is releasable for fresh registration.

---

## Reading `admin_audit_log` for account events

```bash
docker compose exec sacp-postgres psql -U sacp -d sacp -c \
  "SELECT at, action, target_id FROM admin_audit_log WHERE action LIKE 'account_%' ORDER BY at DESC LIMIT 20;"
```

The 13 account-related action values are documented in [contracts/audit-log-events.md](./contracts/audit-log-events.md). Payloads contain hashed codes, hashed emails (for cross-account-isolation lookup), and non-secret metadata only — no plaintext passwords or codes (FR-014, SC-012).

---

## Disabling / rollback

### Disable the entire account surface

```bash
# .env
SACP_ACCOUNTS_ENABLED=0
```

Restart the orchestrator. Every account endpoint returns HTTP 404; the SPA falls back to the existing token-paste landing per FR-018. **Existing account rows are retained** in the database (no DROP) but are inaccessible via HTTP. Re-enabling via `SACP_ACCOUNTS_ENABLED=1` restores access without data loss.

### Disable a single account

There is no "suspend account" endpoint in v1. The end-user can:
- Change the password (locks out all other sessions).
- Delete the account (zeroes credentials; preserves audit linkage).

For operator-side account suspension, see the deferred FR-020 ownership-transfer surface (research.md §7).

---

## Restart recovery

The `SessionStore` is process-local in-memory (matches spec 011 H-02). On orchestrator restart, ALL sids are dropped — every authenticated session (account + token alike) is forced to re-authenticate. The SPA detects the 401 on the next request and presents the login flow.

The `accounts` and `account_participants` tables are durable Postgres state; restart preserves all account rows, all account-participant joins, and all `admin_audit_log` history. Verification codes (transient, audit-log-only) survive restart for their TTL window — a code emitted before restart is still consumable after restart up to the original 24h / 30min deadline.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Account endpoints return 404 | `SACP_ACCOUNTS_ENABLED=0` (default) | Set to `1` and restart. |
| Account creation succeeds but verification email never arrives | `SACP_EMAIL_TRANSPORT=noop` (dev default) | Read the code from `admin_audit_log`; configure a real transport (follow-up spec). |
| Login P95 well above 500ms | Argon2id parameters set above OWASP defaults | Confirm `SACP_PASSWORD_ARGON2_TIME_COST` and `_MEMORY_COST_KB`; values above the floor add latency proportionally. |
| Login returns 401 with no detail | Generic `invalid_credentials` per SC-005 | Read `admin_audit_log` for `account_login_failed` rows; the audit log has the diagnostic detail (timing leak resistance keeps it out of the response). |
| `/me/sessions` returns empty even after joining sessions | Account-participant join row not created | Verify the participant-creation flow recognized the account cookie; check `account_participants` for the participant_id. |
| Password change succeeds but other tabs aren't logged out | Reverse index `_by_account` not maintained | Bug — file an issue. The reverse index update on `SessionStore.create()` / `.delete()` is load-bearing for FR-011. |
| All seven new env vars present in `.env` but orchestrator exits at startup | One value out of range | Read the startup error message — it names the offending var. Fix and restart. |
| Test `test_023_master_switch_off.py` fails | Some account endpoint accessible despite `SACP_ACCOUNTS_ENABLED=0` | The FR-018 canary caught a leak. Find the endpoint that ignored the switch check. |
| Test `test_023_login_timing.py` fails (timing skew) | Email-miss path not running argon2id verify against dummy hash | Implementation must always run `verify()` so the timing is uniform. SC-005 ±5ms test catches this. |
