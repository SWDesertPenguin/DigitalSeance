# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP detection_events tool category. Spec 030 Phase 3, FR-069."""

from __future__ import annotations

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.tools.registry import RegistryEntry, ToolDefinition

_CAT = "detection_events"
_COMMON_ERRORS = ("SACP_E_NOT_FOUND", "SACP_E_FORBIDDEN", "SACP_E_INTERNAL", "SACP_E_VALIDATION")


def _defn(
    name: str,
    description: str,
    pagination: bool = False,
    v14: int = 1000,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        paramsSchema={},
        returnSchema={},
        errorContract=_COMMON_ERRORS,
        scopeRequirement="facilitator",
        aiAccessible=True,
        idempotencySupported=False,
        paginationSupported=pagination,
        v14BudgetMs=v14,
        category=_CAT,
    )


async def _dispatch_detection_events_list(ctx: CallerContext, params: dict) -> dict:
    session_id = params.get("session_id") or ctx.session_id
    if ctx.db_pool is None or not session_id:
        return {"events": [], "next_cursor": None}
    try:
        async with ctx.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, event_class, participant_id, turn_number, disposition "
                "FROM detection_events WHERE session_id = $1 ORDER BY id DESC LIMIT 50",
                session_id,
            )
        return {"events": [dict(r) for r in rows], "next_cursor": None}
    except Exception:
        return {"events": [], "next_cursor": None}


async def _dispatch_detection_events_detail(ctx: CallerContext, params: dict) -> dict:
    event_id = params.get("event_id")
    session_id = params.get("session_id") or ctx.session_id
    if ctx.db_pool is None or not event_id or not session_id:
        return {"error": "SACP_E_NOT_FOUND", "reason": "missing_params"}
    try:
        async with ctx.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, event_class, participant_id, trigger_snippet, detector_score, "
                "turn_number, disposition, timestamp "
                "FROM detection_events WHERE id = $1 AND session_id = $2",
                int(event_id),
                session_id,
            )
        if row is None:
            return {"error": "SACP_E_NOT_FOUND", "reason": "event_not_found"}
        return dict(row)
    except Exception:
        return {"error": "SACP_E_INTERNAL", "reason": "db_error"}


def register(registry: dict) -> None:
    registry["detection_events.list"] = RegistryEntry(
        definition=_defn(
            "detection_events.list", "List detection events for a session", pagination=True
        ),
        dispatch=_dispatch_detection_events_list,
    )
    registry["detection_events.detail"] = RegistryEntry(
        definition=_defn(
            "detection_events.detail", "Get detail for a single detection event", v14=200
        ),
        dispatch=_dispatch_detection_events_detail,
    )
