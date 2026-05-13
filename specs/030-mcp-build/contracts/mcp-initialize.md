# Contract: `initialize` (MCP)

**Phase**: 2 | **Spec FR**: FR-014, FR-015, FR-020, FR-022 | **Date**: 2026-05-13

The `initialize` method opens an MCP session, negotiates protocol version, exchanges capability advertisements, and issues a fresh `Mcp-Session-Id` header. First request on every MCP session.

## Request

`POST /mcp` with header `Authorization: Bearer <static_bearer_token>` (Phase 2) or `Authorization: Bearer <jwt_access_token>` (Phase 4).

```json
{
  "jsonrpc": "2.0",
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-11-25",
    "capabilities": {
      "roots": { "listChanged": false },
      "sampling": {}
    },
    "clientInfo": {
      "name": "<client-supplied>",
      "version": "<client-supplied>"
    }
  },
  "id": "<client-opaque>"
}
```

## Success Response

HTTP 200; response carries new `Mcp-Session-Id` header (256-bit hex per FR-020).

```json
{
  "jsonrpc": "2.0",
  "result": {
    "protocolVersion": "2025-11-25",
    "capabilities": {
      "tools": { "listChanged": false },
      "logging": {}
    },
    "serverInfo": {
      "name": "SACP",
      "version": "<orchestrator version>"
    }
  },
  "id": "<echoes request id>"
}
```

The advertised server capabilities MUST NOT claim `prompts` or `resources` per FR-032 + SC-021. Only `tools` (+ `logging`) is claimed in v1.

## Error Responses

| Condition | HTTP | Code | message |
|---|---|---|---|
| Malformed JSON | 400 | -32700 | `Parse error` |
| Missing required param | 400 | -32602 | `Invalid params` (data: which field) |
| Unsupported protocolVersion | 400 | -32602 | `Unsupported protocol version; server speaks 2025-11-25` |
| Missing bearer | 401 | -32001 | `Authentication failed` |
| Invalid bearer | 401 | -32001 | `Authentication failed` |
| Concurrent-session cap reached | 503 | -32003 | `Capacity reached`; HTTP `Retry-After: <seconds>` header |
| MCP master switch off | 404 (HTTP) | n/a | `/mcp` route returns HTTP 404 with no JSON-RPC body |

## SACP wiring

- `Mcp-Session-Id` header issuance: `secrets.token_bytes(32).hex()` → 64-char hex
- MCPSession in-memory state populated per [data-model.md](../data-model.md) Phase 2 section
- Audit-log row: `action='mcp_initialize'`, includes participant_id (resolved from bearer)
- Per-stage timing label: `mcp_initialize` to `routing_log`

## Budgets

- P95 latency: 500ms (FR-030)
- Body size: response < 4 KB
- Capacity: ≤ `SACP_MCP_MAX_CONCURRENT_SESSIONS` (default 100)
