# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP proposal tool category. Spec 030 Phase 3, FR-069."""

from __future__ import annotations

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.tools.registry import RegistryEntry, ToolDefinition

_CAT = "proposal"
_ERRORS = ("SACP_E_NOT_FOUND", "SACP_E_FORBIDDEN", "SACP_E_INTERNAL", "SACP_E_VALIDATION")


def _defn(
    name: str,
    desc: str,
    *,
    scope: str = "participant",
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


async def _dispatch_proposal_create(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_proposal_cast_vote(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_proposal_close(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_proposal_list(ctx: CallerContext, params: dict) -> dict:
    session_id = params.get("session_id") or ctx.session_id
    if ctx.db_pool is None or not session_id:
        return {"proposals": [], "next_cursor": None}
    try:
        async with ctx.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, topic, status FROM proposals WHERE session_id = $1 LIMIT 50",
                session_id,
            )
        return {"proposals": [dict(r) for r in rows], "next_cursor": None}
    except Exception:
        return {"proposals": [], "next_cursor": None}


def _register_participant_tools(registry: dict) -> None:
    registry["proposal.create"] = RegistryEntry(
        definition=_defn(
            "proposal.create", "Create a new proposal in the session", ai=True, idem=True
        ),
        dispatch=_dispatch_proposal_create,
    )
    registry["proposal.cast_vote"] = RegistryEntry(
        definition=_defn(
            "proposal.cast_vote", "Cast a vote on an open proposal", ai=True, idem=True
        ),
        dispatch=_dispatch_proposal_cast_vote,
    )


def _register_facilitator_and_read_tools(registry: dict) -> None:
    registry["proposal.close"] = RegistryEntry(
        definition=_defn(
            "proposal.close",
            "Close / resolve a proposal (facilitator only)",
            scope="facilitator",
            idem=True,
        ),
        dispatch=_dispatch_proposal_close,
    )
    registry["proposal.list"] = RegistryEntry(
        definition=_defn(
            "proposal.list", "List proposals for a session", scope="any", page=True, v14=1000
        ),
        dispatch=_dispatch_proposal_list,
    )


def register(registry: dict) -> None:
    _register_participant_tools(registry)
    _register_facilitator_and_read_tools(registry)
