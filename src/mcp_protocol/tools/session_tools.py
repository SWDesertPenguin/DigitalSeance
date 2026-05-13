# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP session tool category. Spec 030 Phase 3, FR-069."""

from __future__ import annotations

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.tools.registry import RegistryEntry, ToolDefinition

_CAT = "session"
_ERRORS = ("SACP_E_NOT_FOUND", "SACP_E_FORBIDDEN", "SACP_E_INTERNAL", "SACP_E_VALIDATION")


def _defn(
    name: str,
    desc: str,
    *,
    scope: str = "facilitator",
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
        scopeRequirement=scope,
        aiAccessible=ai,
        idempotencySupported=idem,
        paginationSupported=page,
        v14BudgetMs=v14,
        category=_CAT,
    )


async def _dispatch_session_create(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_session_update_settings(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_session_archive(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_session_delete(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_session_list(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"sessions": [], "next_cursor": None}
    try:
        async with ctx.db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, name, status FROM sessions ORDER BY id LIMIT 50")
        return {"sessions": [dict(r) for r in rows], "next_cursor": None}
    except Exception:
        return {"sessions": [], "next_cursor": None}


async def _dispatch_session_get(ctx: CallerContext, params: dict) -> dict:
    session_id = params.get("session_id") or ctx.session_id
    if ctx.db_pool is None or not session_id:
        return {"error": "SACP_E_NOT_FOUND", "reason": "no_db_pool"}
    try:
        async with ctx.db_pool.acquire() as conn:
            _sql = "SELECT id, name, status FROM sessions WHERE id = $1"
            row = await conn.fetchrow(_sql, session_id)
        if row is None:
            return {"error": "SACP_E_NOT_FOUND", "reason": "session_not_found"}
        return dict(row)
    except Exception:
        return {"error": "SACP_E_INTERNAL", "reason": "db_error"}


def _register_write_tools(registry: dict) -> None:
    registry["session.create"] = RegistryEntry(
        definition=_defn("session.create", "Create a new SACP session", idem=True),
        dispatch=_dispatch_session_create,
    )
    registry["session.update_settings"] = RegistryEntry(
        definition=_defn("session.update_settings", "Update session settings", idem=True),
        dispatch=_dispatch_session_update_settings,
    )
    registry["session.archive"] = RegistryEntry(
        definition=_defn("session.archive", "Archive an active session", idem=True),
        dispatch=_dispatch_session_archive,
    )
    registry["session.delete"] = RegistryEntry(
        definition=_defn("session.delete", "Delete a session (step-up required)", idem=True),
        dispatch=_dispatch_session_delete,
    )


def _register_read_tools(registry: dict) -> None:
    registry["session.list"] = RegistryEntry(
        definition=_defn("session.list", "List sessions", page=True, v14=1000),
        dispatch=_dispatch_session_list,
    )
    registry["session.get"] = RegistryEntry(
        definition=_defn(
            "session.get", "Get a single session by ID", scope="any", ai=True, v14=200
        ),
        dispatch=_dispatch_session_get,
    )


def register(registry: dict) -> None:
    _register_write_tools(registry)
    _register_read_tools(registry)
