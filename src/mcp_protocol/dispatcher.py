# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/call boundary. Spec 030 Phase 2, FR-039 + FR-066 + tool-registry-shape.md."""

from __future__ import annotations

import json
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

_BUILTIN_HOOKS: list[DispatchHook] = [V14TimingHook(), AuditLogHook()]

_AUDIT_LOG_SQL = """
    INSERT INTO admin_audit_log
        (session_id, facilitator_id, action, target_id,
         previous_value, new_value)
    VALUES ($1, $2, $3, $4, $5, $6)
"""


def get_registry() -> dict[str, Any]:
    """Return the live tool registry."""
    from src.mcp_protocol.tools import REGISTRY

    return REGISTRY  # type: ignore[return-value]


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
    if required_scope == "sponsor":
        if "sponsor" not in caller_context.scopes and "facilitator" not in caller_context.scopes:
            raise DispatchError(
                SACP_AUTH_FAILED,
                "Insufficient scope",
                {"sacp_error_code": SACP_E_FORBIDDEN, "required": required_scope},
            )
    elif required_scope != "any" and required_scope not in caller_context.scopes:
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


async def _emit_tool_audit_row(
    caller_context: CallerContext,
    tool_name: str,
    elapsed_ms: int,
) -> None:
    """Write per-tool action code to admin_audit_log per FR-057."""
    if caller_context.db_pool is None:
        return
    action = f"mcp_tool_{tool_name}"
    try:
        async with caller_context.db_pool.acquire() as conn:
            await conn.execute(
                _AUDIT_LOG_SQL,
                caller_context.session_id or "mcp",
                caller_context.participant_id,
                action,
                tool_name,
                None,
                json.dumps({"elapsed_ms": elapsed_ms}),
            )
    except Exception:
        log.debug("_emit_tool_audit_row failed silently", exc_info=True)


async def dispatch(
    caller_context: CallerContext,
    tool_name: str,
    arguments: dict,
    extra_hooks: list[DispatchHook] | None = None,
) -> dict:
    """Dispatch through registry + auth check + hook chain.

    Raises DispatchError on any JSON-RPC-reportable failure.
    """
    registry = get_registry()
    entry = registry.get(tool_name)
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
    await _emit_tool_audit_row(caller_context, tool_name, elapsed_ms)
    for hook in all_hooks:
        await hook.post(caller_context, tool_name, arguments, result, elapsed_ms)
    return result
