# Contract: `/token` (OAuth 2.1)

**Phase**: 4 | **Spec FR**: FR-070, FR-073, FR-078–FR-081, FR-085, FR-097 | **Date**: 2026-05-13

The token endpoint per RFC 6749. Supports `authorization_code` and `refresh_token` grants. Other grants refused.

## `authorization_code` grant

### Request

`POST /token` with `Content-Type: application/x-www-form-urlencoded`:

| Param | Required | Notes |
|---|---|---|
| `grant_type` | yes | MUST be `authorization_code` |
| `code` | yes | The opaque code from `/authorize` redirect |
| `code_verifier` | yes | PKCE verifier (SHA-256(code_verifier) must equal stored `code_challenge`) |
| `redirect_uri` | yes | Echo of original `/authorize` redirect_uri |
| `client_id` | yes | |

### Success Response (HTTP 200)

```json
{
  "access_token": "<JWT-signed access token>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "<opaque 256-bit string>",
  "scope": "facilitator tool:session tool:participant ...",
  "jti": "<access token jti claim>"
}
```

Access token JWT claims (per FR-097):
- `sub`: participant_id
- `client_id`: client_id
- `scope`: array of scopes
- `auth_time`: ISO 8601 UTC of original `/authorize` authentication
- `iat`: ISO 8601 UTC of token issuance
- `exp`: `iat + SACP_OAUTH_ACCESS_TOKEN_TTL_MINUTES`
- `jti`: unique token id

Refresh token is opaque; cleartext returned once; Fernet-encrypted form stored in `oauth_refresh_tokens.encrypted_token` with hash in `oauth_refresh_tokens.token_hash`.

## `refresh_token` grant

### Request

```
grant_type=refresh_token
&refresh_token=<cleartext from prior issuance>
&client_id=<client_id>
```

### Success Response

Same shape as `authorization_code` grant. **Atomically** (FR-079):
1. SHA-256(refresh_token) → look up in `oauth_refresh_tokens`
2. If hit + `revoked_at IS NULL` + `rotated_at IS NULL`: proceed
3. If hit + `rotated_at IS NOT NULL`: REPLAY — revoke entire token family per FR-079, emit `security_event` with `token_family_revoked_replay_attempt`, return `invalid_grant` error
4. Mark presented refresh's `rotated_at = NOW()` (effective revocation)
5. Issue new access + refresh token in same DB transaction; new refresh's `parent_token_hash` = old hash, `family_id` = old family_id
6. Audit-log: `action='token_refreshed'`

## Error Responses

Per RFC 6749 §5.2; JSON body, HTTP 400:

| `error` value | Condition |
|---|---|
| `invalid_request` | Missing/malformed param |
| `invalid_client` | client_id unknown or revoked |
| `invalid_grant` | code invalid/expired/used; refresh token invalid/replayed |
| `unauthorized_client` | grant_type not allowed for this client |
| `unsupported_grant_type` | grant_type ≠ `authorization_code` or `refresh_token` |
| `invalid_scope` | requested scope narrowing rejected |

## SACP wiring

- JWT signing: ES256, key from `SACP_OAUTH_SIGNING_KEY_PATH` (research §2)
- Refresh-token replay detection: family-based per FR-079 + data-model `oauth_token_families`
- Audit-log rows: `action='token_issued'` or `action='token_refreshed'`; FR-085
- Per-IP rate-limit per spec 019 (FR-093)

## Budgets

- P95 latency: 200ms (FR-095)
- DB transaction completes within request lifetime
