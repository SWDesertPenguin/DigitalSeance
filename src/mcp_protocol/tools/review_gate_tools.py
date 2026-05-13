# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP review_gate tool category. Spec 030 Phase 3, FR-069."""

from __future__ import annotations

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.tools.registry import RegistryEntry, ToolDefinition

_CAT = "review_gate"
_COMMON_ERRORS = ("SACP_E_NOT_FOUND", "SACP_E_FORBIDDEN", "SACP_E_INTERNAL", "SACP_E_VALIDATION")


def _defn(
    name: str,
    description: str,
    idempotency: bool = False,
    pagination: bool = False,
    v14: int = 500,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        paramsSchema={},
        returnSchema={},
        errorContract=_COMMON_ERRORS,
        scopeRequirement="facilitator",
        aiAccessible=False,
        idempotencySupported=idempotency,
        paginationSupported=pagination,
        v14BudgetMs=v14,
        category=_CAT,
    )


async def _dispatch_review_gate_list_pending(ctx: CallerContext, params: dict) -> dict:
    session_id = params.get("session_id") or ctx.session_id
    if ctx.db_pool is None or not session_id:
        return {"drafts": [], "next_cursor": None}
    try:
        async with ctx.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, participant_id, draft_content FROM review_gate_drafts "
                "WHERE session_id = $1 AND status = 'pending' LIMIT 50",
                session_id,
            )
        return {"drafts": [dict(r) for r in rows], "next_cursor": None}
    except Exception:
        return {"drafts": [], "next_cursor": None}


async def _dispatch_review_gate_approve(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    draft_id = params.get("draft_id")
    if not draft_id:
        return {"error": "SACP_E_VALIDATION", "reason": "draft_id_required"}
    from src.repositories.review_gate_repo import ReviewGateRepository

    repo = ReviewGateRepository(ctx.db_pool)
    try:
        draft = await repo.get_by_id(draft_id)
        if draft is None:
            return {"error": "SACP_E_NOT_FOUND", "reason": "draft_not_found"}
        resolved = await repo.resolve(draft_id, resolution="approved")
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"status": "approved", "id": resolved.id, "draft_id": resolved.id}


async def _dispatch_review_gate_reject(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    draft_id = params.get("draft_id")
    if not draft_id:
        return {"error": "SACP_E_VALIDATION", "reason": "draft_id_required"}
    from src.repositories.review_gate_repo import ReviewGateRepository

    repo = ReviewGateRepository(ctx.db_pool)
    try:
        draft = await repo.get_by_id(draft_id)
        if draft is None:
            return {"error": "SACP_E_NOT_FOUND", "reason": "draft_not_found"}
        resolved = await repo.resolve(draft_id, resolution="rejected")
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"status": "rejected", "id": resolved.id, "draft_id": resolved.id}


async def _dispatch_review_gate_edit_and_approve(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    draft_id = params.get("draft_id")
    edited_content = params.get("edited_content") or params.get("content")
    if not draft_id or not edited_content:
        return {"error": "SACP_E_VALIDATION", "reason": "draft_id_and_edited_content_required"}
    from src.repositories.review_gate_repo import ReviewGateRepository

    repo = ReviewGateRepository(ctx.db_pool)
    try:
        draft = await repo.get_by_id(draft_id)
        if draft is None:
            return {"error": "SACP_E_NOT_FOUND", "reason": "draft_not_found"}
        resolved = await repo.resolve(draft_id, resolution="edited", edited_content=edited_content)
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"status": "edited_and_approved", "id": resolved.id, "draft_id": resolved.id}


def register(registry: dict) -> None:
    registry["review_gate.list_pending"] = RegistryEntry(
        definition=_defn(
            "review_gate.list_pending", "List pending review-gate drafts", pagination=True, v14=1000
        ),
        dispatch=_dispatch_review_gate_list_pending,
    )
    registry["review_gate.approve"] = RegistryEntry(
        definition=_defn(
            "review_gate.approve", "Approve a pending draft verbatim", idempotency=True
        ),
        dispatch=_dispatch_review_gate_approve,
    )
    registry["review_gate.reject"] = RegistryEntry(
        definition=_defn("review_gate.reject", "Reject a pending draft", idempotency=True),
        dispatch=_dispatch_review_gate_reject,
    )
    registry["review_gate.edit_and_approve"] = RegistryEntry(
        definition=_defn(
            "review_gate.edit_and_approve",
            "Edit a draft and approve the edited content",
            idempotency=True,
            v14=1000,
        ),
        dispatch=_dispatch_review_gate_edit_and_approve,
    )
