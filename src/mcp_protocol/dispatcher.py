# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/call boundary. Spec 030 Phase 2, FR-039 + FR-066 + tool-registry-shape.md."""

from __future__ import annotations

import logging
import time
from typing import Any

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.errors import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_METHOD_NOT_FOUND,
    SACP_AUTH_FAILED,
    SACP_E_FORBIDDEN,
    SACP_E_INTERNAL,
    SACP_E_NOT_FOUND,
)
from src.mcp_protocol.hooks import AuditLogHook, DispatchHook, V14TimingHook

log = logging.getLogger("sacp.mcp.dispatcher")

# Phase 3 populates this registry via register() calls at startup.
# Phase 2 ships an empty registry; tools/call returns -32601 for every name.
_TOOL_REGISTRY: dict[str, Any] = {}

_BUILTIN_HOOKS: list[DispatchHook] = [V14TimingHook(), AuditLogHook()]


def get_registry() -> dict[str, Any]:
    """Return the mutable tool registry (populated by Phase 3)."""
    return _TOOL_REGISTRY


class DispatchError(Exception):
    """Raised by dispatch() when a JSON-RPC error should be returned."""

    def __init__(self, code: int, message: str, data: dict | None = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


def _check_authorization(entry: Any, caller_context: CallerContext) -> None:
    """Raise DispatchError if the caller lacks scope or AI access."""
    defn = entry.definition
    required_scope = defn.scopeRequirement
    if required_scope != "any" and required_scope not in caller_context.scopes:
        raise DispatchError(
            SACP_AUTH_FAILED,
            "Insufficient scope",
            {"sacp_error_code": SACP_E_FORBIDDEN, "required": required_scope},
        )
    if not defn.aiAccessible and caller_context.is_ai_caller:
        raise DispatchError(
            SACP_AUTH_FAILED,
            "Tool not accessible to AI callers",
            {"sacp_error_code": SACP_E_FORBIDDEN},
        )


async def _invoke(entry: Any, caller_context: CallerContext, arguments: dict) -> tuple[dict, int]:
    """Invoke the tool dispatch callable; return (result, elapsed_ms)."""
    started = time.monotonic()
    try:
        result = await entry.dispatch(caller_context, arguments)
    except DispatchError:
        raise
    except Exception as exc:
        log.warning("tool dispatch raised unexpectedly: %s", exc, exc_info=True)
        raise DispatchError(
            JSONRPC_INTERNAL_ERROR,
            "Internal dispatch error",
            {"sacp_error_code": SACP_E_INTERNAL},
        ) from exc
    return result, int((time.monotonic() - started) * 1000)


async def dispatch(
    caller_context: CallerContext,
    tool_name: str,
    arguments: dict,
    extra_hooks: list[DispatchHook] | None = None,
) -> dict:
    """Dispatch through registry + auth check + hook chain.

    Raises DispatchError on any JSON-RPC-reportable failure.
    """
    entry = _TOOL_REGISTRY.get(tool_name)
    if entry is None:
        raise DispatchError(
            JSONRPC_METHOD_NOT_FOUND,
            f"Unknown tool: {tool_name!r}",
            {"sacp_error_code": SACP_E_NOT_FOUND},
        )
    _check_authorization(entry, caller_context)
    all_hooks: list[DispatchHook] = list(_BUILTIN_HOOKS) + (extra_hooks or [])
    for hook in all_hooks:
        await hook.pre(caller_context, tool_name, arguments)
    result, elapsed_ms = await _invoke(entry, caller_context, arguments)
    for hook in all_hooks:
        await hook.post(caller_context, tool_name, arguments, result, elapsed_ms)
    return result
