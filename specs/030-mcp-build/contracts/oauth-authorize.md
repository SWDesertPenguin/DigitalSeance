# Contract: `/authorize` (OAuth 2.1)

**Phase**: 4 | **Spec FR**: FR-070–FR-072, FR-076, FR-080, FR-089 | **Date**: 2026-05-13

The authorization endpoint per RFC 6749 + RFC 7636 (PKCE). Only `S256` challenge method accepted; `plain` rejected. Implicit and ROPC grants unsupported.

## Request

`GET /authorize` with query params:

| Param | Required | Notes |
|---|---|---|
| `response_type` | yes | MUST be `code`; other values rejected |
| `client_id` | yes | Orchestrator-generated (from CIMD submission) |
| `redirect_uri` | yes | MUST match a URI from `oauth_clients.redirect_uris` |
| `scope` | yes | Space-separated scope vocabulary per FR-077 |
| `state` | yes | Client-supplied CSRF token |
| `code_challenge` | yes | PKCE challenge (32-byte SHA-256 of code_verifier) |
| `code_challenge_method` | yes | MUST be `S256`; `plain` rejected |
| `subject` | yes | The target participant_id |

## Success Flow

1. Validate all params (above table)
2. Resolve subject: confirm participant exists, participant.kind ≠ `ai` (FR-089), participant is in a sessions state that allows OAuth flows
3. Human authentication: redirect to spec 023 email+password login flow if not already authenticated; on success, the orchestrator has the email-verified subject in session
4. Authorization decision: if `scope` requests scopes not grantable to this subject, narrow to the intersection (per FR-077)
5. Generate authorization code: cryptographic 256-bit opaque value; SHA-256 hash stored in `oauth_authorization_codes` with `code_challenge`, `client_id`, `participant_id`, `scope`, TTL `SACP_OAUTH_AUTH_CODE_TTL_SECONDS` (default 60s)
6. Redirect to `<redirect_uri>?code=<code>&state=<state>`
7. Audit-log row: `action='oauth_authorize'`, includes participant_id, client_id, granted_scope

## Error Responses (per RFC 6749 §4.1.2.1)

Errors are returned via redirect to the `redirect_uri` with `error` + `error_description` + `state` params:

| `error` value | Condition |
|---|---|
| `invalid_request` | Missing/malformed required param |
| `unauthorized_client` | client_id not registered or in `revoked` status |
| `unsupported_response_type` | `response_type` ≠ `code` |
| `invalid_scope` | Requested scope not in client's allowed_scopes |
| `unsupported_challenge_method` | `code_challenge_method` ≠ `S256` |
| `access_denied` | Subject refused consent OR subject is AI participant |
| `server_error` | Internal failure |

For unredirectable errors (missing `redirect_uri`, no matching client), the orchestrator returns HTTP 400 with a plain JSON error body and emits a `security_event` row.

## SACP wiring

- AI-participant exclusion (FR-089): if resolved `participant.kind == 'ai'`, `error=access_denied` + `security_event` row
- Failed PKCE count tracked per client; beyond `SACP_OAUTH_FAILED_PKCE_THRESHOLD`, temporary client block (FR-072 § DOS mitigation)
- Per-IP rate-limit applies per spec 019 (FR-093)

## Budgets

- P95 latency: 200ms (excluding user authentication time)
- Audit-log row written within the request transaction
