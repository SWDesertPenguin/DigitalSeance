# `SACP_AUTH_LOOKUP_KEY` Rotation

> **Audience**: SACP operators rotating the HMAC key used to derive `participants.auth_token_lookup`. **Purpose**: invalidate every existing lookup value, regenerate them under the new key, and bring the service back up without re-opening the O(N) bcrypt-scan vector. **Trigger**: suspected key exposure, scheduled rotation, or operator-initiated re-key.

## Background

`SACP_AUTH_LOOKUP_KEY` is the HMAC-SHA256 key that derives `auth_token_lookup` from the plaintext token (see `src/auth/token_lookup.py`). A leak of this key alone never authenticates anyone — bcrypt verification still gates every login. What a leak does do is let an attacker compute HMACs offline against captured (token, lookup) pairs, narrowing brute-force candidates.

Rotating the key requires:

1. Invalidating every active token (the bcrypt hash and the lookup are tied to the old key by construction — the old lookup will no longer match the new key's HMAC).
2. Forcing every participant to re-auth so write paths populate fresh `(auth_token_hash, auth_token_lookup)` pairs under the new key.

Migration 025's CHECK (`auth_token_hash IS NULL OR auth_token_lookup IS NOT NULL`) means the bulk-invalidate step must NULL **both** columns together, never just one.

## Pre-flight

1. Schedule a maintenance window. Every participant in every active session will be logged out.
2. Notify facilitators that they will need to re-invite every active participant after the window closes.
3. Confirm the operator has database write access (the bulk UPDATE below cannot be done via the application API).
4. Generate a fresh key:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Store it in the secret manager / env file the same way the existing key is stored. Do not commit it.

## Steps

### 1. Bring the orchestrator down

```bash
docker compose stop sacp
```

The application must not be reading or writing `auth_token_*` columns while the bulk UPDATE runs.

### 2. Bulk-invalidate every token

Connect to the database and run:

```sql
UPDATE participants
SET auth_token_hash = NULL,
    auth_token_lookup = NULL,
    token_expires_at = NULL
WHERE auth_token_hash IS NOT NULL
   OR auth_token_lookup IS NOT NULL;
```

This satisfies the CHECK constraint (both NULL together is the legitimate revoked state) and ensures no row carries a stale lookup keyed by the retired secret.

Verify:

```sql
SELECT COUNT(*) FROM participants
WHERE auth_token_hash IS NOT NULL
   OR auth_token_lookup IS NOT NULL;
```

Expected: 0.

### 3. Replace the env var

Update the deployment's environment file (or secret manager) so `SACP_AUTH_LOOKUP_KEY` references the new value generated in pre-flight.

### 4. Bring the orchestrator up

```bash
docker compose up -d sacp
```

The V16 startup validator (`validators.validate_auth_lookup_key`) confirms the new value meets the >=32-char + non-placeholder requirement before the port binds. If validation fails the process exits non-zero with a clear error.

### 5. Re-invite participants

Facilitators issue fresh invites through the normal flow. Each accepted invite writes a new `(auth_token_hash, auth_token_lookup)` pair under the new key.

## Verify post-rotation

After at least one participant has re-auth'd, sample a row:

```sql
SELECT id, auth_token_hash IS NOT NULL AS has_hash,
       auth_token_lookup IS NOT NULL AS has_lookup
FROM participants
WHERE auth_token_hash IS NOT NULL
LIMIT 5;
```

Every row in the result should show both columns populated. If any row has hash but not lookup, the auth write path is broken — open an incident; the CHECK constraint should have prevented this.

## Failure modes

- **V16 refused to bind**: the new key did not meet the length / placeholder requirement. Re-generate and retry; the old key is already invalidated in the DB so there is no rollback path other than choosing a valid new key.
- **Bulk UPDATE failed mid-run**: the CHECK constraint blocks the update only if a row would end with hash but no lookup. The UPDATE above sets both to NULL together so it cannot trip. If it does, inspect the failing row directly.
- **Participant cannot re-auth after rotation**: confirm they are accepting a fresh invite, not retrying the pre-rotation token. The old token will fail at the HMAC probe (no row matches the new-key lookup).

## Forward-only

This procedure is destructive to active sessions by design. There is no rollback to the previous key — once the bulk UPDATE NULLs the columns, the old (token, hash, lookup) tuples are gone.
