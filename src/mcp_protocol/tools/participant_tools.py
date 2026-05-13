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
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    session_id = params.get("session_id") or ctx.session_id
    if not session_id:
        return {"error": "SACP_E_VALIDATION", "reason": "session_id_required"}
    display_name = (params.get("display_name") or "").strip()
    if not display_name:
        return {"error": "SACP_E_VALIDATION", "reason": "display_name_required"}
    encryption_key = ctx.encryption_key
    if not encryption_key:
        # Fall back to env var when the key was not threaded through ctx
        import os

        encryption_key = os.environ.get("SACP_ENCRYPTION_KEY", "")
    if not encryption_key:
        return {"error": "SACP_E_INTERNAL", "reason": "no_encryption_key"}
    from src.repositories.participant_repo import ParticipantRepository

    repo = ParticipantRepository(ctx.db_pool, encryption_key=encryption_key)
    try:
        new_p, _ = await repo.add_participant(
            session_id=session_id,
            display_name=display_name,
            provider=params.get("provider") or "human",
            model=params.get("model") or "human",
            model_tier=params.get("model_tier") or "n/a",
            model_family=params.get("model_family") or "human",
            context_window=int(params.get("context_window") or 0),
            api_key=params.get("api_key") or None,
            api_endpoint=params.get("api_endpoint") or None,
            budget_hourly=params.get("budget_hourly"),
            budget_daily=params.get("budget_daily"),
            max_tokens_per_turn=params.get("max_tokens_per_turn"),
            auto_approve=bool(params.get("auto_approve", True)),
        )
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"participant_id": new_p.id, "role": new_p.role, "display_name": new_p.display_name}


async def _dispatch_participant_update(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    participant_id = params.get("participant_id")
    if not participant_id:
        return {"error": "SACP_E_VALIDATION", "reason": "participant_id_required"}
    # Supported update: budget fields and role changes go through repo methods.
    encryption_key = ctx.encryption_key
    if not encryption_key:
        import os

        encryption_key = os.environ.get("SACP_ENCRYPTION_KEY", "")
    if not encryption_key:
        return {"error": "SACP_E_INTERNAL", "reason": "no_encryption_key"}
    from src.repositories.participant_repo import ParticipantRepository

    repo = ParticipantRepository(ctx.db_pool, encryption_key=encryption_key)
    try:
        if "role" in params:
            await repo.update_role(participant_id, params["role"])
        if any(k in params for k in ("budget_hourly", "budget_daily", "max_tokens_per_turn")):
            await repo.update_budget(
                participant_id,
                budget_hourly=params.get("budget_hourly"),
                budget_daily=params.get("budget_daily"),
                max_tokens_per_turn=params.get("max_tokens_per_turn"),
            )
        p = await repo.get_participant(participant_id)
        if p is None:
            return {"error": "SACP_E_NOT_FOUND", "reason": "participant_not_found"}
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"participant_id": p.id, "role": p.role, "status": p.status}


async def _dispatch_participant_remove(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    participant_id = params.get("participant_id")
    if not participant_id:
        return {"error": "SACP_E_VALIDATION", "reason": "participant_id_required"}
    encryption_key = ctx.encryption_key
    if not encryption_key:
        import os

        encryption_key = os.environ.get("SACP_ENCRYPTION_KEY", "")
    if not encryption_key:
        return {"error": "SACP_E_INTERNAL", "reason": "no_encryption_key"}
    from src.repositories.participant_repo import ParticipantRepository

    repo = ParticipantRepository(ctx.db_pool, encryption_key=encryption_key)
    try:
        await repo.depart_participant(participant_id)
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"participant_id": participant_id, "status": "offline"}


async def _dispatch_participant_rotate_token(ctx: CallerContext, params: dict) -> dict:
    # Token rotation requires the AuthService (bcrypt + token reveal), which is
    # process-level state and cannot be reconstructed from the db_pool alone.
    return {"error": "SACP_E_INTERNAL", "reason": "requires_orchestrator_context"}


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
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    session_id = params.get("session_id") or ctx.session_id
    speaker_id = params.get("participant_id") or ctx.participant_id
    content = (params.get("content") or "").strip()
    if not session_id or not speaker_id or not content:
        return {
            "error": "SACP_E_VALIDATION",
            "reason": "session_id_participant_id_content_required",
        }
    from src.repositories.message_repo import MessageRepository

    msg_repo = MessageRepository(ctx.db_pool)
    # Resolve the branch_id for the session
    try:
        async with ctx.db_pool.acquire() as conn:
            branch_id = await conn.fetchval(
                "SELECT id FROM branches WHERE session_id = $1 AND name = 'main' LIMIT 1",
                session_id,
            )
        if not branch_id:
            async with ctx.db_pool.acquire() as conn:
                branch_id = await conn.fetchval(
                    "SELECT id FROM branches WHERE session_id = $1 LIMIT 1",
                    session_id,
                )
        if not branch_id:
            return {"error": "SACP_E_NOT_FOUND", "reason": "no_branch_for_session"}
        msg = await msg_repo.append_message(
            session_id=session_id,
            branch_id=branch_id,
            speaker_id=speaker_id,
            speaker_type=params.get("speaker_type") or "human",
            content=content,
            token_count=max(len(content.split()), 1),
            complexity_score="n/a",
        )
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"status": "injected", "turn_number": msg.turn_number, "id": msg.turn_number}


async def _dispatch_participant_set_routing_preference(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    participant_id = params.get("participant_id") or ctx.participant_id
    preference = params.get("preference") or params.get("routing_preference")
    if not participant_id or not preference:
        return {"error": "SACP_E_VALIDATION", "reason": "participant_id_and_preference_required"}
    try:
        async with ctx.db_pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE participants SET routing_preference = $1 WHERE id = $2",
                preference,
                participant_id,
            )
        if result == "UPDATE 0":
            return {"error": "SACP_E_NOT_FOUND", "reason": "participant_not_found"}
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"status": "updated", "participant_id": participant_id, "preference": preference}


async def _dispatch_participant_set_budget(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    participant_id = params.get("participant_id")
    if not participant_id:
        return {"error": "SACP_E_VALIDATION", "reason": "participant_id_required"}
    encryption_key = ctx.encryption_key
    if not encryption_key:
        import os

        encryption_key = os.environ.get("SACP_ENCRYPTION_KEY", "")
    if not encryption_key:
        return {"error": "SACP_E_INTERNAL", "reason": "no_encryption_key"}
    from src.repositories.participant_repo import ParticipantRepository

    repo = ParticipantRepository(ctx.db_pool, encryption_key=encryption_key)
    try:
        await repo.update_budget(
            participant_id,
            budget_hourly=params.get("budget_hourly"),
            budget_daily=params.get("budget_daily"),
            max_tokens_per_turn=params.get("max_tokens_per_turn"),
        )
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"status": "updated", "participant_id": participant_id}


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
