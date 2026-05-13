# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP admin tool category (cross-session admin surfaces). Spec 030 Phase 3, FR-069."""

from __future__ import annotations

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.tools.registry import RegistryEntry, ToolDefinition

_CAT = "admin"
_ERRORS = ("SACP_E_NOT_FOUND", "SACP_E_FORBIDDEN", "SACP_E_INTERNAL", "SACP_E_VALIDATION")


def _defn(
    name: str,
    desc: str,
    *,
    ai: bool = False,
    idem: bool = False,
    page: bool = False,
    v14: int = 500,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=desc,
        paramsSchema={},
        returnSchema={},
        errorContract=_ERRORS,
        scopeRequirement="facilitator",
        aiAccessible=ai,
        idempotencySupported=idem,
        paginationSupported=page,
        v14BudgetMs=v14,
        category=_CAT,
    )


async def _dispatch_admin_list_sessions(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"sessions": [], "next_cursor": None}
    try:
        async with ctx.db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, name, status FROM sessions ORDER BY id LIMIT 50")
        return {"sessions": [dict(r) for r in rows], "next_cursor": None}
    except Exception:
        return {"sessions": [], "next_cursor": None}


async def _dispatch_admin_list_participants(ctx: CallerContext, params: dict) -> dict:
    session_id = params.get("session_id") or ctx.session_id
    if ctx.db_pool is None or not session_id:
        return {"participants": [], "next_cursor": None}
    try:
        async with ctx.db_pool.acquire() as conn:
            _sql = (
                "SELECT id, display_name, role, status FROM participants"
                " WHERE session_id = $1 LIMIT 50"
            )
            rows = await conn.fetch(_sql, session_id)
        return {"participants": [dict(r) for r in rows], "next_cursor": None}
    except Exception:
        return {"participants": [], "next_cursor": None}


async def _dispatch_admin_transfer_facilitator(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_admin_archive_session(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


def _register_list_tools(registry: dict) -> None:
    registry["admin.list_sessions"] = RegistryEntry(
        definition=_defn(
            "admin.list_sessions", "List all sessions (admin view)", page=True, v14=1000
        ),
        dispatch=_dispatch_admin_list_sessions,
    )
    registry["admin.list_participants"] = RegistryEntry(
        definition=_defn(
            "admin.list_participants",
            "List participants across a session (admin view)",
            page=True,
            v14=1000,
        ),
        dispatch=_dispatch_admin_list_participants,
    )


def _register_write_tools(registry: dict) -> None:
    registry["admin.transfer_facilitator"] = RegistryEntry(
        definition=_defn(
            "admin.transfer_facilitator",
            "Transfer facilitator role (destructive; step-up per FR-086)",
            idem=True,
        ),
        dispatch=_dispatch_admin_transfer_facilitator,
    )
    registry["admin.archive_session"] = RegistryEntry(
        definition=_defn(
            "admin.archive_session",
            "Archive a session (destructive; step-up required per FR-086)",
            idem=True,
        ),
        dispatch=_dispatch_admin_archive_session,
    )


def register(registry: dict) -> None:
    _register_list_tools(registry)
    _register_write_tools(registry)
