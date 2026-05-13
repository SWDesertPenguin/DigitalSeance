# Contract: `/revoke` (OAuth 2.1)

**Phase**: 4 | **Spec FR**: FR-074, FR-085, FR-092 | **Date**: 2026-05-13

Token revocation endpoint per RFC 7009. Accepts either an access token or a refresh token; revoking a refresh token revokes the entire token family.

## Request

`POST /revoke` with `Content-Type: application/x-www-form-urlencoded`:

| Param | Required | Notes |
|---|---|---|
| `token` | yes | The token to revoke (access or refresh) |
| `token_type_hint` | no | `access_token` or `refresh_token`; advisory |
| `client_id` | yes | The client revoking the token |

Authenticated via client credentials (the `Authorization: Bearer <client-credential>` for confidential clients; SACP defaults to public clients per RFC 8252 + CIMD pattern, so client_id alone authenticates the request).

## Success Response

HTTP 200, empty body (per RFC 7009).

## Server-side flow

1. Compute `token_hash = SHA-256(token)` (refresh-token path)
2. Look up in `oauth_refresh_tokens.token_hash`; if hit: set `revoked_at = NOW()` on that row AND `oauth_token_families.revoked_at = NOW()` on the family
3. If miss, treat as access token: decode JWT (without verifying claims), extract `jti`, set `oauth_access_tokens.revoked_at = NOW()` on that row
4. Emit audit-log row: `action='token_revoked'`, includes participant_id, client_id, token_type_hint, token_hash (scrubbed)
5. Per-instance cache invalidation: the per-instance JWT-validation cache (FR-094) receives the revocation via DB poll within the cache TTL window

## Connection-close behavior

Per FR-092, revocation MUST close existing MCP transport connections within `SACP_OAUTH_REVOCATION_PROPAGATION_SECONDS` (default 5).

- The dispatcher boundary check on every `tools/call` reads the JWT-validation cache (or, on miss, the DB)
- If the cache TTL is ≤ 30s (FR-094), revocations propagate within 30s worst-case
- The actual revocation-to-disconnect SLA is bounded by the cache TTL; v1 ships with `SACP_OAUTH_REVOCATION_PROPAGATION_SECONDS = 5` aspirational, and `SACP_MCP_TOKEN_CACHE_TTL_SECONDS = 5` to align

## Error Responses

Per RFC 7009; HTTP 400:

| `error` value | Condition |
|---|---|
| `invalid_request` | Missing required param |
| `invalid_client` | client_id unknown |

Notably: RFC 7009 specifies that revoking a token that doesn't exist returns HTTP 200 (not an error). SACP follows this — silent acceptance of unknown tokens prevents enumeration.

## SACP wiring

- Audit-log row per FR-085
- Per-IP rate-limit per spec 019 (FR-093)
- Family revocation cascade: revoking a refresh token revokes (a) that token, (b) the family, (c) all access tokens with the family_id

## Budgets

- P95 latency: 100ms (plan §Technical Context)
- DB transaction completes within request lifetime
