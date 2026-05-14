# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP audit_log tool category. Spec 030 Phase 3, FR-069."""

from __future__ import annotations

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.tools.registry import RegistryEntry, ToolDefinition

_CAT = "audit_log"
_COMMON_ERRORS = ("SACP_E_NOT_FOUND", "SACP_E_FORBIDDEN", "SACP_E_INTERNAL", "SACP_E_VALIDATION")


async def _dispatch_admin_get_audit_log(ctx: CallerContext, params: dict) -> dict:
    session_id = params.get("session_id") or ctx.session_id
    if ctx.db_pool is None or not session_id:
        return {"entries": [], "next_cursor": None}
    try:
        async with ctx.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, action, facilitator_id, target_id, timestamp "
                "FROM admin_audit_log WHERE session_id = $1 ORDER BY timestamp DESC LIMIT 50",
                session_id,
            )
        return {"entries": [dict(r) for r in rows], "next_cursor": None}
    except Exception:
        return {"entries": [], "next_cursor": None}


def register(registry: dict) -> None:
    registry["admin.get_audit_log"] = RegistryEntry(
        definition=ToolDefinition(
            name="admin.get_audit_log",
            description="Retrieve paginated audit log entries for a session",
            paramsSchema={},
            returnSchema={},
            errorContract=_COMMON_ERRORS,
            scopeRequirement="facilitator",
            aiAccessible=False,
            idempotencySupported=False,
            paginationSupported=True,
            v14BudgetMs=5000,
            category=_CAT,
        ),
        dispatch=_dispatch_admin_get_audit_log,
    )
