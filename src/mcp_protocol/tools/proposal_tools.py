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
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    session_id = params.get("session_id") or ctx.session_id
    proposed_by = params.get("proposed_by") or ctx.participant_id
    topic = (params.get("topic") or "").strip()
    position = (params.get("position") or "").strip()
    if not session_id or not topic or not position:
        return {"error": "SACP_E_VALIDATION", "reason": "session_id_topic_position_required"}
    from src.repositories.proposal_repo import ProposalRepository
    from src.repositories.session_repo import SessionRepository

    session_repo = SessionRepository(ctx.db_pool)
    try:
        session = await session_repo.get_session(session_id)
        if session is None:
            return {"error": "SACP_E_NOT_FOUND", "reason": "session_not_found"}
        repo = ProposalRepository(ctx.db_pool)
        proposal = await repo.create_proposal(
            session_id=session_id,
            proposed_by=proposed_by,
            topic=topic,
            position=position,
            acceptance_mode=params.get("acceptance_mode") or session.acceptance_mode,
        )
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {
        "status": "created",
        "id": proposal.id,
        "proposal_id": proposal.id,
        "topic": proposal.topic,
    }


async def _dispatch_proposal_cast_vote(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    proposal_id = params.get("proposal_id")
    participant_id = params.get("participant_id") or ctx.participant_id
    vote_value = params.get("vote")
    if not proposal_id or not vote_value:
        return {"error": "SACP_E_VALIDATION", "reason": "proposal_id_and_vote_required"}
    from src.repositories.errors import DuplicateVoteError
    from src.repositories.proposal_repo import ProposalRepository

    repo = ProposalRepository(ctx.db_pool)
    try:
        vote = await repo.cast_vote(
            proposal_id=proposal_id,
            participant_id=participant_id,
            vote=vote_value,
            comment=params.get("comment"),
        )
    except DuplicateVoteError as exc:
        return {"error": "SACP_E_VALIDATION", "reason": str(exc)}
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"status": "voted", "proposal_id": proposal_id, "vote": vote.vote}


async def _dispatch_proposal_close(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    proposal_id = params.get("proposal_id")
    resolution = params.get("status") or params.get("resolution") or "accepted"
    if not proposal_id:
        return {"error": "SACP_E_VALIDATION", "reason": "proposal_id_required"}
    from src.repositories.proposal_repo import ProposalRepository

    repo = ProposalRepository(ctx.db_pool)
    try:
        proposal = await repo.resolve_proposal(proposal_id, resolution)
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {
        "status": "resolved",
        "id": proposal.id,
        "proposal_id": proposal.id,
        "resolution": proposal.status,
    }


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
