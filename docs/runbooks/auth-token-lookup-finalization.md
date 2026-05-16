# Auth Token Lookup Finalization Pre-Sweep (alembic 025)

> **Audience**: SACP operators preparing to apply alembic migration 025. **Purpose**: identify and resolve participants whose `auth_token_hash` is set but whose `auth_token_lookup` is NULL ("grandfathered rows") before the CHECK constraint blocks the migration. **Trigger**: ran `alembic upgrade head` and the migration aborted with the message *"alembic 025: N participants have auth_token_hash without auth_token_lookup."*

## Background

Audit C-02 v1 (PR #204, May 2026) added an HMAC-keyed `auth_token_lookup` column to `participants` and an indexed-first probe path in `_find_by_token`. To avoid breaking active sessions at deploy time, the auth service retained a fallback that bcrypt-scanned every row where `auth_token_hash IS NOT NULL AND auth_token_lookup IS NULL`. That fallback re-opens the O(N) DoS vector for any row that can be made to look "grandfathered." Migration 025 closes the door by adding `CHECK (auth_token_hash IS NULL OR auth_token_lookup IS NOT NULL)`; the auth service drops the legacy scan in the same change.

## Pre-flight

1. Schedule a brief maintenance window. The pre-sweep only takes a moment, but force-rotation requires affected participants to re-auth.
2. Confirm `SACP_AUTH_LOOKUP_KEY` is the same value that was used when those rows were last written. If the key has changed since, every row's lookup column is now wrong; use the rotation runbook (`auth-token-lookup-key-rotation.md`) instead.
3. Have a facilitator on hand to issue replacement invites.

## Identify grandfathered rows

Run the following against the production DB:

```sql
SELECT id,
       session_id,
       display_name,
       role,
       status,
       last_seen
FROM participants
WHERE auth_token_hash IS NOT NULL
  AND auth_token_lookup IS NULL
ORDER BY session_id, last_seen DESC NULLS LAST;
```

For each row, classify by `status` + `last_seen`:

- **Active** (`status='active'`, recent `last_seen`): force-rotate (next section).
- **Departed / revoked / stale** (`status` in `('departed', 'revoked')` OR no recent `last_seen` and the operator confirms the participant is gone): NULL the dangling hash (section after).

## Force-rotate active participants

For each active row identified above, a facilitator runs `revoke_token` against the participant. That sets `auth_token_hash` to a random bcrypt and NULLs the lookup column — satisfying the CHECK invariant (hash without lookup is gone; both NULL together is permitted). Then re-invite the participant via the standard flow; the new join writes both columns.

API call (or facilitator UI equivalent):

```bash
POST /admin/participants/{pid}/revoke_token
```

After this completes for every active row, re-run the SELECT above. The count should drop to zero — or only stranded / offline rows remain.

## NULL the dangling hash on stranded rows

For participants who will not re-auth (departed, offline indefinitely, or otherwise unreachable), clear the hash directly. Both columns NULL together is the legitimate post-revoke state and satisfies the CHECK:

```sql
UPDATE participants
SET auth_token_hash = NULL,
    auth_token_lookup = NULL,
    token_expires_at = NULL
WHERE auth_token_hash IS NOT NULL
  AND auth_token_lookup IS NULL;
```

Verify the count is now zero:

```sql
SELECT COUNT(*)
FROM participants
WHERE auth_token_hash IS NOT NULL
  AND auth_token_lookup IS NULL;
```

## Apply the migration

```bash
alembic upgrade head
```

The pre-sweep block in migration 025 confirms no stranded rows before it adds the CHECK. If it still aborts, the SELECT above will explain which rows slipped through.

## Verify the constraint landed

```sql
SELECT conname,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conname = 'ck_participants_lookup_when_hash';
```

Expected output: one row whose definition matches `CHECK ((auth_token_hash IS NULL) OR (auth_token_lookup IS NOT NULL))`.

## Rollback note

Migration 025 is forward-only per Constitution §6 + spec 001 §FR-017. If the application proves incompatible (it should not — the auth service is updated in the same change), the operator restores from the pre-migration backup rather than running a `downgrade`.
