# Contract: ToolRegistry Shape

**Phase**: 2 + 3 (co-designed) | **Spec FR**: FR-039, FR-066, FR-068 | **Date**: 2026-05-13

The interface contract between Phase 2's dispatcher and Phase 3's tool definitions. This is the surface that lets the two phases be co-designed and independently mergeable.

## The boundary

Phase 2's dispatcher in `src/mcp_protocol/dispatcher.py` consumes a `ToolRegistry` populated by Phase 3 modules under `src/mcp_protocol/tools/`. The dispatcher MUST NOT depend on any Phase 3 implementation detail beyond the contract here. Phase 3 modules MUST NOT depend on any Phase 2 internal beyond importing the types declared here.

## Types (Python; canonical declarations live in `src/mcp_protocol/tools/registry.py`)

```python
from typing import Awaitable, Callable, Mapping, NamedTuple
from datetime import datetime


class ToolDefinition(NamedTuple):
    name: str                          # domain.action snake_case
    description: str                   # English-only in v1
    paramsSchema: dict                 # JSON Schema for params
    returnSchema: dict                 # JSON Schema for the result
    errorContract: tuple[str, ...]     # Beyond the universal SACP_E_*
    scopeRequirement: str              # facilitator|participant|pending|sponsor|any
    aiAccessible: bool                 # Per FR-063
    idempotencySupported: bool         # Write tools only
    paginationSupported: bool          # List-return tools only
    v14BudgetMs: int                   # P95 latency budget
    versionSuffix: str | None          # None for v1; .v2 etc later
    deprecatedAt: datetime | None      # Set during deprecation horizon


class CallerContext(NamedTuple):
    participant_id: str
    session_id: str | None
    scopes: frozenset[str]
    is_ai_caller: bool
    mcp_session_id: bytes | None
    request_id: str
    dispatch_started_at: datetime
    idempotency_key: str | None


# The dispatch callable signature
ToolDispatch = Callable[[CallerContext, dict], Awaitable[dict]]


class RegistryEntry(NamedTuple):
    definition: ToolDefinition
    dispatch: ToolDispatch
    category: str
    enabled_env_var: str


ToolRegistry = Mapping[str, RegistryEntry]
```

## Registration

Phase 3 modules populate the registry via a `register()` function called at startup. Example:

```python
# src/mcp_protocol/tools/session_tools.py
from src.mcp_protocol.tools.registry import ToolDefinition, RegistryEntry, ToolRegistry


def register(registry: dict[str, RegistryEntry]) -> None:
    registry["session.create"] = RegistryEntry(
        definition=ToolDefinition(
            name="session.create",
            description="Create a new SACP session as facilitator.",
            paramsSchema={...},
            returnSchema={...},
            errorContract=("SACP_E_SESSION_LIMIT_REACHED",),
            scopeRequirement="facilitator",
            aiAccessible=False,
            idempotencySupported=True,
            paginationSupported=False,
            v14BudgetMs=500,
            versionSuffix=None,
            deprecatedAt=None,
        ),
        dispatch=_dispatch_session_create,
        category="session",
        enabled_env_var="SACP_MCP_TOOL_SESSION_ENABLED",
    )
```

The `ToolRegistry` loader in `src/mcp_protocol/tools/__init__.py` calls each module's `register()` at startup. Categories disabled via env var per FR-061 are filtered out at registration time.

## Dispatcher contract

Phase 2's dispatcher MUST:
1. Look up the tool by name; emit `-32601` if not found
2. Validate `arguments` against `definition.paramsSchema`; emit `-32602/SACP_E_VALIDATION` on failure
3. Check caller's scopes ⊇ `definition.scopeRequirement`; emit `-32602/SACP_E_FORBIDDEN` on miss
4. If `definition.aiAccessible == False` AND `caller_context.is_ai_caller == True`: emit `-32602/SACP_E_FORBIDDEN`
5. If `definition.idempotencySupported` AND `caller_context.idempotency_key`: check `admin_audit_log` for a prior dispatch with this key
6. Invoke `dispatch(caller_context, arguments)`
7. Validate the return against `definition.returnSchema`; emit `-32603/SACP_E_INTERNAL` on failure (and log full validation error)
8. Write the audit-log row
9. Marshal into the MCP `tools/call` result envelope

## Dispatch contract

Phase 3 dispatch callables MUST:
1. Treat `CallerContext` as read-only
2. Call into the existing participant_api router function (or the equivalent service-layer function); MUST NOT duplicate the router's business logic
3. Return a dict conforming to `definition.returnSchema`
4. Raise typed exceptions for known error conditions; the dispatcher catches and maps to JSON-RPC errors
5. NOT write audit-log rows (the dispatcher writes the canonical row)
6. NOT bypass the AI security pipeline (spec 007) — call the same code path the participant_api router calls

## Pre/post hooks (FR-066)

The dispatcher exposes pre/post hook lists; Phase 2 provides built-in V14 timing + audit hooks; downstream features (future amendments) can register additional hooks at startup.

```python
# Conceptual
class DispatchHook(Protocol):
    async def pre(self, caller_context: CallerContext, tool_name: str, params: dict) -> None: ...
    async def post(self, caller_context: CallerContext, tool_name: str, params: dict, result: dict, elapsed_ms: int) -> None: ...
```

Built-in hooks (v1):
- `V14TimingHook` — emits per-stage timing to `routing_log`
- `AuditLogHook` — writes the `admin_audit_log` row

## Architectural test (FR-068, SC-036)

A CI-blocking test asserts:
- Every public route under `src/participant_api/tools/` has at least one corresponding `RegistryEntry` (or is in the documented exclusion list)
- Every `RegistryEntry`'s `dispatch` callable maps back to an existing function

CI fails if new participant_api routes ship without an MCP tool counterpart.
