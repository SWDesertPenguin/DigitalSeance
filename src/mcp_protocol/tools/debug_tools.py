# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP debug_export tool category. Spec 030 Phase 3, FR-069."""

from __future__ import annotations

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.tools.registry import RegistryEntry, ToolDefinition

_CAT = "debug_export"
_COMMON_ERRORS = ("SACP_E_NOT_FOUND", "SACP_E_FORBIDDEN", "SACP_E_INTERNAL", "SACP_E_VALIDATION")


def _defn(name: str, description: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        paramsSchema={},
        returnSchema={},
        errorContract=_COMMON_ERRORS,
        scopeRequirement="facilitator",
        aiAccessible=False,
        idempotencySupported=False,
        paginationSupported=True,
        v14BudgetMs=5000,
        category=_CAT,
    )


async def _dispatch_debug_export_session(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    session_id = params.get("session_id") or ctx.session_id
    if not session_id:
        return {"error": "SACP_E_VALIDATION", "reason": "session_id_required"}
    try:
        async with ctx.db_pool.acquire() as conn:
            session_row = await conn.fetchrow(
                "SELECT id, name, status, created_at FROM sessions WHERE id = $1",
                session_id,
            )
            if session_row is None:
                return {"error": "SACP_E_NOT_FOUND", "reason": "session_not_found"}
            participants = await conn.fetch(
                "SELECT id, display_name, role, status, provider, model FROM participants"
                " WHERE session_id = $1",
                session_id,
            )
            message_count = await conn.fetchval(
                "SELECT COUNT(*) FROM messages WHERE session_id = $1",
                session_id,
            )
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {
        "session": dict(session_row),
        "participants": [dict(p) for p in participants],
        "message_count": message_count,
    }


async def _dispatch_debug_export_participant_view(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    participant_id = params.get("participant_id") or ctx.participant_id
    if not participant_id:
        return {"error": "SACP_E_VALIDATION", "reason": "participant_id_required"}
    try:
        async with ctx.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, display_name, role, status, provider, model, session_id"
                " FROM participants WHERE id = $1",
                participant_id,
            )
            if row is None:
                return {"error": "SACP_E_NOT_FOUND", "reason": "participant_not_found"}
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"participant": dict(row)}


def register(registry: dict) -> None:
    registry["debug.export_session"] = RegistryEntry(
        definition=_defn("debug.export_session", "Export full session diagnostic dump"),
        dispatch=_dispatch_debug_export_session,
    )
    registry["debug.export_participant_view"] = RegistryEntry(
        definition=_defn(
            "debug.export_participant_view", "Export participant-scoped diagnostic view"
        ),
        dispatch=_dispatch_debug_export_participant_view,
    )
