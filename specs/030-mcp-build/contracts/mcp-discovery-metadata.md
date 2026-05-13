# Contract: `/.well-known/mcp-server` (Discovery)

**Phase**: 2 | **Spec FR**: FR-024 | **Date**: 2026-05-13

Returns server metadata for MCP clients discovering the SACP endpoint. Served on the same host:port as the MCP endpoint. Available even when `SACP_MCP_PROTOCOL_ENABLED=false` (responding with `enabled: false`).

## Request

`GET /.well-known/mcp-server` (no body, no auth required for the metadata itself).

## Success Response (master switch on)

HTTP 200, Content-Type: application/json.

```json
{
  "enabled": true,
  "protocol_version": "2025-11-25",
  "endpoint_url": "http://<host>:8750/mcp",
  "auth": {
    "scheme": "bearer",
    "oauth_metadata_url": "http://<host>:8750/.well-known/oauth-protected-resource"
  },
  "server": {
    "name": "SACP",
    "version": "<orchestrator version>"
  }
}
```

The `oauth_metadata_url` field is present only when `SACP_OAUTH_ENABLED=true` (Phase 4). In Phase 2 (OAuth-disabled), this field is omitted; clients fall back to static-bearer auth per the `auth.scheme = "bearer"` declaration.

## Success Response (master switch off)

HTTP 200, Content-Type: application/json.

```json
{
  "enabled": false,
  "server": {
    "name": "SACP",
    "version": "<orchestrator version>"
  }
}
```

The endpoint MUST respond with HTTP 200 (not 404) when `SACP_MCP_PROTOCOL_ENABLED=false`. The `enabled: false` flag is the documented signal per FR-024 + SC-023.

## Error Responses

| Condition | HTTP | Body |
|---|---|---|
| Server error | 500 | (no body; logged server-side) |

No JSON-RPC envelope on this endpoint — it is a plain JSON response, not an MCP protocol call.

## Budgets

- P95 latency: 20ms (plan §Technical Context → V14)
- No rate-limiting (discovery should always be reachable)
- No audit log (publicly visible metadata)
