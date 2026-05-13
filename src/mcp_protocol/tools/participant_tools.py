# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP participant tool category. Spec 030 Phase 3, FR-069."""

from __future__ import annotations

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.tools.registry import RegistryEntry, ToolDefinition

_CAT = "participant"
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


async def _dispatch_participant_create(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_participant_update(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_participant_remove(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_participant_rotate_token(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_participant_list(ctx: CallerContext, params: dict) -> dict:
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


async def _dispatch_participant_get(ctx: CallerContext, params: dict) -> dict:
    participant_id = params.get("participant_id") or ctx.participant_id
    if ctx.db_pool is None or not participant_id:
        return {"error": "SACP_E_NOT_FOUND", "reason": "no_db_pool"}
    try:
        async with ctx.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, display_name, role, status FROM participants WHERE id = $1",
                participant_id,
            )
        if row is None:
            return {"error": "SACP_E_NOT_FOUND", "reason": "participant_not_found"}
        return dict(row)
    except Exception:
        return {"error": "SACP_E_INTERNAL", "reason": "db_error"}


async def _dispatch_participant_inject_message(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_participant_set_routing_preference(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_participant_set_budget(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


def _register_facilitator_tools(registry: dict) -> None:
    registry["participant.create"] = RegistryEntry(
        definition=_defn("participant.create", "Add a participant to a session", idem=True),
        dispatch=_dispatch_participant_create,
    )
    registry["participant.update"] = RegistryEntry(
        definition=_defn("participant.update", "Update participant attributes", idem=True),
        dispatch=_dispatch_participant_update,
    )
    registry["participant.remove"] = RegistryEntry(
        definition=_defn("participant.remove", "Remove a participant from a session", idem=True),
        dispatch=_dispatch_participant_remove,
    )
    registry["participant.rotate_token"] = RegistryEntry(
        definition=_defn(
            "participant.rotate_token",
            "Rotate auth token (facilitator on others; participant on self)",
            idem=True,
        ),
        dispatch=_dispatch_participant_rotate_token,
    )
    registry["participant.list"] = RegistryEntry(
        definition=_defn("participant.list", "List participants in a session", page=True, v14=1000),
        dispatch=_dispatch_participant_list,
    )


def _register_read_tools(registry: dict) -> None:
    registry["participant.get"] = RegistryEntry(
        definition=_defn(
            "participant.get", "Get a single participant by ID", scope="any", ai=True, v14=200
        ),
        dispatch=_dispatch_participant_get,
    )


def _register_ai_self_service(registry: dict) -> None:
    registry["participant.inject_message"] = RegistryEntry(
        definition=_defn(
            "participant.inject_message",
            "Inject a message as the calling participant",
            scope="participant",
            ai=True,
            idem=True,
        ),
        dispatch=_dispatch_participant_inject_message,
    )
    registry["participant.set_routing_preference"] = RegistryEntry(
        definition=_defn(
            "participant.set_routing_preference",
            "Set own routing preference",
            scope="participant",
            ai=True,
            idem=True,
        ),
        dispatch=_dispatch_participant_set_routing_preference,
    )


def _register_sponsor_tools(registry: dict) -> None:
    registry["participant.set_budget"] = RegistryEntry(
        definition=_defn(
            "participant.set_budget",
            "Set spend caps on a sponsored AI participant",
            scope="sponsor",
            idem=True,
        ),
        dispatch=_dispatch_participant_set_budget,
    )


def register(registry: dict) -> None:
    _register_facilitator_tools(registry)
    _register_read_tools(registry)
    _register_ai_self_service(registry)
    _register_sponsor_tools(registry)
