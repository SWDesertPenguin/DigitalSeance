# Contract: `tools/list` (MCP)

**Phase**: 2 | **Spec FR**: FR-016 | **Date**: 2026-05-13

The `tools/list` method returns the tool registry populated by Phase 3. Each entry includes name, JSON Schema for params and returns, description, and the error contract.

## Request

`POST /mcp` with header `Mcp-Session-Id: <hex>` (from `initialize` reply).

```json
{
  "jsonrpc": "2.0",
  "method": "tools/list",
  "params": {},
  "id": "<client-opaque>"
}
```

Optional `params.cursor` for paginated listing if registry size exceeds the default page size.

## Success Response

```json
{
  "jsonrpc": "2.0",
  "result": {
    "tools": [
      {
        "name": "session.create",
        "description": "Create a new SACP session as facilitator. Returns the session id and the initial session metadata.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "topic": { "type": "string" },
            "facilitator_id": { "type": "string", "pattern": "^[0-9a-f]{12}$" }
          },
          "required": ["topic", "facilitator_id"]
        }
      }
    ],
    "nextCursor": null
  },
  "id": "<echoes request id>"
}
```

The MCP spec's `tools` array entry shape is fixed: `name`, `description`, `inputSchema`. SACP-specific metadata (`scopeRequirement`, `aiAccessible`, `errorContract`, `v14BudgetMs`) is NOT surfaced to clients in v1 — those live in the orchestrator-side `ToolDefinition` and gate dispatch behavior server-side. Surfacing them would require an MCP extension which is out of v1 scope.

## Error Responses

| Condition | HTTP | Code | message |
|---|---|---|---|
| Missing/invalid `Mcp-Session-Id` | 404 | -32003 | `Session unknown or expired` |
| Bearer revoked since `initialize` | 401 | -32001 | `Authentication failed` |
| Rate-limit exceeded | 429 | -32002 | `Rate limit exceeded`; data: Retry-After hint |

## SACP wiring

- Source: `ToolRegistry` loaded at startup; filtered by enabled-env-var per FR-061
- Disabled tool categories: MUST NOT appear in the response (per FR-061, SC-032)
- Audit-log row: `action='mcp_tools_list'`, includes participant_id, tool count returned

## Budgets

- P95 latency: 100ms (FR-030)
- Response size: < 256 KB at v1 registry size (~50 tools)
