# Contract: `/.well-known/oauth-protected-resource` (OAuth Discovery)

**Phase**: 4 | **Spec FR**: FR-075 | **Date**: 2026-05-13

Discovery metadata per the MCP authorization spec (revision 2025-11-25). Returns the authorization endpoint, token endpoint, revocation endpoint, supported scopes, supported grant types, supported code challenge methods, and the CIMD submission URL.

## Request

`GET /.well-known/oauth-protected-resource` (no auth required).

## Success Response

HTTP 200, Content-Type: application/json.

```json
{
  "resource": "http://<host>:8750/mcp",
  "authorization_servers": [
    "http://<host>:8750/authorize"
  ],
  "scopes_supported": [
    "facilitator",
    "participant",
    "pending",
    "sponsor",
    "tool:session",
    "tool:participant",
    "tool:proposal",
    "tool:review_gate",
    "tool:debug_export",
    "tool:audit_log",
    "tool:detection_events",
    "tool:scratch",
    "tool:provider",
    "tool:admin"
  ],
  "bearer_methods_supported": ["header"],
  "resource_documentation": "http://<host>:8750/docs/oauth-mcp.md",
  "authorization_endpoint": "http://<host>:8750/authorize",
  "token_endpoint": "http://<host>:8750/token",
  "revocation_endpoint": "http://<host>:8750/revoke",
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "code_challenge_methods_supported": ["S256"],
  "client_registration_endpoint": "http://<host>:8750/oauth/register-cimd",
  "client_id_metadata_documents_supported": true
}
```

The `code_challenge_methods_supported` field omits `plain` per FR-071 — only `S256` is supported.

The `grant_types_supported` field omits `password` (ROPC) and `implicit` per FR-070.

The `scopes_supported` field is the union of role scopes (4) + tool-category scopes (10) = 14 distinct scopes per FR-077.

## Error Responses

| Condition | HTTP | Body |
|---|---|---|
| OAuth disabled (master switch off) | 404 | (no body; the endpoint isn't mounted when `SACP_OAUTH_ENABLED=false`) |
| Server error | 500 | (no body; logged server-side) |

When `SACP_OAUTH_ENABLED=false`, this endpoint returns HTTP 404. The MCP discovery metadata (`/.well-known/mcp-server`) omits the `oauth_metadata_url` field in that case; clients fall back to static-bearer auth.

## SACP wiring

- Endpoint mounted only when `SACP_OAUTH_ENABLED=true`
- No auth required (publicly visible metadata)
- No rate-limit (discovery should always be reachable)
- No audit log

## Budgets

- P95 latency: 50ms (plan §Technical Context)
- Cacheable response (clients SHOULD respect `Cache-Control: public, max-age=300`)
