# Contract: `tools/call` (MCP)

**Phase**: 2 (dispatch) + Phase 3 (per-tool definitions) | **Spec FR**: FR-017, FR-028, FR-029, FR-053–FR-060 | **Date**: 2026-05-13

The `tools/call` method dispatches to a registered tool. Param validation, scope enforcement, audit logging, and return validation all happen at the dispatch boundary.

## Request

`POST /mcp` with header `Mcp-Session-Id: <hex>`.

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "session.create",
    "arguments": {
      "topic": "...",
      "facilitator_id": "...",
      "_idempotency_key": "<uuid optional, write tools only>"
    }
  },
  "id": "<client-opaque>"
}
```

## Success Response

```json
{
  "jsonrpc": "2.0",
  "result": {
    "content": [
      { "type": "text", "text": "<JSON-serialized result matching the tool's returnSchema>" }
    ],
    "isError": false
  },
  "id": "<echoes request id>"
}
```

The MCP spec's `tools/call` result shape requires the `content` array; SACP serializes the result as a single text-type element holding the JSON-stringified tool return. Clients parse it as JSON against the tool's declared `returnSchema`.

## Error Responses

| Condition | HTTP | JSON-RPC code | data.sacp_error_code | Source |
|---|---|---|---|---|
| Tool not found | 200 | -32601 | `SACP_E_NOT_FOUND` | FR-019 |
| Schema validation failed | 200 | -32602 | `SACP_E_VALIDATION` (data: json_pointer) | FR-053 |
| Scope check failed | 200 | -32602 | `SACP_E_FORBIDDEN` | FR-056 |
| Idempotency-key conflict (different params, same key) | 200 | -32602 | `SACP_E_VALIDATION` | FR-058 |
| Disabled tool category | 200 | -32601 | `SACP_E_NOT_FOUND` | FR-061 |
| Dispatch raised internal | 200 | -32603 | `SACP_E_INTERNAL` | FR-054 |
| Auth failed (revoked token) | 401 | -32001 | `SACP_E_AUTH` | FR-022 |
| Rate-limit exceeded | 429 | -32002 | `SACP_E_RATE_LIMIT` (data: Retry-After) | FR-028 |
| Session expired | 404 | -32003 | `SACP_E_SESSION_EXPIRED` | research §7 |
| Step-up required (Phase 4) | 200 | -32602 | `SACP_E_STEP_UP_REQUIRED` | FR-086 |

The MCP spec calls for tool-level errors to be returned via `result.isError = true` rather than the JSON-RPC top-level error envelope. SACP uses the JSON-RPC top-level error envelope for the protocol-layer errors (above) and the `result.isError = true` shape for application-layer errors thrown by the dispatch callable itself.

## SACP wiring

1. Validate `params.name` exists in registry; -32601 if not
2. Validate `params.arguments` against tool's `paramsSchema`; -32602 if not
3. Resolve `CallerContext` from `Mcp-Session-Id` + bearer
4. Scope check: caller's scopes ⊇ tool's `scopeRequirement`; -32602/`SACP_E_FORBIDDEN` if not
5. Idempotency check (write tools): look up `_idempotency_key` in `admin_audit_log`; if hit AND args match, return original result
6. Dispatch: call `RegistryEntry.dispatch(caller_context, arguments)`
7. Validate return against tool's `returnSchema`; -32603/`SACP_E_INTERNAL` if not
8. Write audit-log row: `action='mcp_tool_<name>'`, includes caller_context, scrubbed args, dispatch result identifier
9. Marshal result into MCP envelope

## Budgets

- Dispatch overhead P95 ≤ 5ms (protocol → dispatcher → registry-lookup → scope-check)
- Per-tool `v14BudgetMs` (defined in registry; FR-060)
- Round-trip P95 ≤ 5s overall (FR-030)
