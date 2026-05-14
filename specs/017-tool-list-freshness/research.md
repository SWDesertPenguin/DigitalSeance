# Research: Tool-List Freshness

## §1 — Tool-list fetch mechanism

SACP does not yet have a dedicated MCP client that calls `tools/list` on participant-registered external MCP servers. The `src/api_bridge/adapter.py` `ProviderAdapter` ABC covers provider dispatch (Anthropic, OpenAI, etc.) but has no `list_tools` method. The `src/mcp_server/` directory is a FastAPI-based SACP-native endpoint surface (misnamed per memory note); it does not implement the Model Context Protocol.

For v1, the tool-list fetch is implemented as a direct HTTP POST to the participant's registered MCP server URL (`api_endpoint` column on the participant row) using `asyncio`-friendly HTTP. The call follows the MCP JSON-RPC spec: `{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}`. The response's `result.tools` array is the tool list. If `api_endpoint` is None or empty, the participant has no registered MCP server and `register_participant` is a no-op (tool list stays empty; no audit row).

The `asyncio.wait_for` wrapper enforces `SACP_TOOL_REFRESH_TIMEOUT_S` if set. The standard library `urllib.request` is synchronous and blocks the event loop; `aiohttp` or `httpx[async]` are the two options. Since `httpx` is already used in `tests/` (via the `httpx.AsyncClient` fixture in conftest.py) and `aiohttp` is not in the existing dependency set, and since we are adding no new runtime deps, we use `asyncio.get_event_loop().run_in_executor` with `urllib.request.urlopen` for the synchronous call — or better, check if httpx is a runtime dep already.

Checking: `httpx` appears in `tests/conftest.py` as a test dependency only. For production code, `urllib.request` with `run_in_executor` avoids a new runtime dep. However, `httpx` may already be a transitive dependency via FastAPI/Starlette. Since the instruction says "no new runtime dependencies," we use the stdlib `urllib.request` via executor OR check for the existing aiohttp/httpx runtime path.

**Decision**: Use `asyncio` + `concurrent.futures.ThreadPoolExecutor` with `urllib.request.urlopen` for the MCP `tools/list` call. This is stdlib-only, no new dependencies. The call is wrapped in `asyncio.wait_for` for the timeout. If the participant's `api_endpoint` is empty/None, skip.

## §2 — Stable hash

Order-independent SHA-256 of the sorted tool list:

```python
import hashlib, json

def _compute_hash(tools: list[dict]) -> str:
    serialized = json.dumps(
        sorted(tools, key=lambda t: t.get("name", "")),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()
```

Properties: (a) order-independent — same tools in different server response order produce the same hash; (b) deterministic — `sort_keys=True` normalizes dict key order within each tool object; (c) collision-resistant for change detection purposes (SHA-256 is sufficient); (d) handles empty list (hash of `[]`).

Edge cases handled: duplicate tool names (treated as malformed — detected before hashing; logged; old list preserved). Reordered entries (same hash — no audit row emitted per spec edge case).

## §3 — §4.2 integration point in loop.py

The system prompt is assembled inside `_assemble_and_dispatch` via `assembler.assemble(...)` at line ~1067. The integration point for the freshness check is BEFORE `assembler.assemble(...)` is called, so the freshness check and any registry update complete before the system prompt is built. This ensures the assembled prompt always reflects the freshest tool set available at that turn boundary.

The call chain: `execute_turn` -> `_execute_routed_turn` -> `_dispatch_with_delay` -> `_dispatch_and_persist` -> `_assemble_and_dispatch`. The freshness check goes at the top of `_assemble_and_dispatch` before `assembler.assemble(...)`.

The `_assemble_and_dispatch` function receives `ctx` (which carries `session_id` and `pool`) and `speaker` (participant object with `.id` and `provider` field). The registry lookup key is `(ctx.session_id, speaker.id)`. The check is gated on `provider != "human"` per the feedback memory note ("exclude humans from dispatch paths").

## §4 — Push subscription attempt

At participant registration, after the participant record is persisted, `register_participant` is called. When `SACP_TOOL_REFRESH_PUSH_ENABLED=true`, it attempts to send `{"jsonrpc":"2.0","id":2,"method":"notifications/tools/list_changed","params":{}}` to the participant's MCP server. The outcome (subscribed / not_supported / failed) is audited per FR-007.

In v1, the subscription is attempted but the delivery path (receiving push notifications and calling `refresh_tool_list` on receipt) is a Phase-2 stub. The audit row records the attempt; no WebSocket or long-poll connection is opened in v1.

## §5 — V16 env var defaults

All four vars unset = pre-feature behavior (FR-014):
- `SACP_TOOL_REFRESH_POLL_INTERVAL_S` unset = None = polling disabled
- `SACP_TOOL_REFRESH_TIMEOUT_S` unset = None = inherit adapter timeout (30s fallback)
- `SACP_TOOL_LIST_MAX_BYTES` unset = None = 65536 default applied in code
- `SACP_TOOL_REFRESH_PUSH_ENABLED` unset = treated as `false` = push subscription not attempted

SC-005 regression: with all four vars unset, the loop is byte-identical to the pre-feature baseline. `maybe_refresh` returns False immediately when `SACP_TOOL_REFRESH_POLL_INTERVAL_S` is unset. `register_participant` is a no-op when `api_endpoint` is None (no MCP server registered). Tool lists stay empty; no audit events.
