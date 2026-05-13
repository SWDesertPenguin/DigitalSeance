# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP session tool category. Spec 030 Phase 3, FR-069."""

from __future__ import annotations

import secrets

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.tools.registry import RegistryEntry, ToolDefinition

_CAT = "session"
_ERRORS = ("SACP_E_NOT_FOUND", "SACP_E_FORBIDDEN", "SACP_E_INTERNAL", "SACP_E_VALIDATION")

_SLUG_ADJECTIVES = (
    "amber",
    "brave",
    "clever",
    "crimson",
    "eager",
    "fancy",
    "gentle",
    "happy",
    "icy",
    "jade",
    "keen",
    "lively",
    "merry",
    "noble",
    "olive",
    "proud",
    "quiet",
    "rapid",
    "silver",
    "teal",
    "vivid",
    "witty",
)
_SLUG_ANIMALS = (
    "badger",
    "cheetah",
    "dolphin",
    "eagle",
    "falcon",
    "gazelle",
    "hawk",
    "iguana",
    "jaguar",
    "koala",
    "lynx",
    "mantis",
    "newt",
    "otter",
    "panda",
    "quail",
    "raven",
    "swan",
    "tiger",
    "urchin",
    "vixen",
    "wolf",
)


def _generate_session_slug() -> str:
    adj = secrets.choice(_SLUG_ADJECTIVES)
    noun = secrets.choice(_SLUG_ANIMALS)
    suffix = secrets.token_hex(2)
    return f"{adj}-{noun}-{suffix}"


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
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    from src.repositories.session_repo import SessionRepository

    repo = SessionRepository(ctx.db_pool)
    name = (params.get("name") or "").strip() or _generate_session_slug()
    display_name = (params.get("display_name") or "").strip() or "MCP Facilitator"
    try:
        session, facilitator, branch = await repo.create_session(
            name,
            facilitator_display_name=display_name,
            facilitator_provider=params.get("provider") or "human",
            facilitator_model=params.get("model") or "human",
            facilitator_model_tier=params.get("model_tier") or "n/a",
            facilitator_model_family=params.get("model_family") or "human",
            facilitator_context_window=int(params.get("context_window") or 0),
            facilitator_api_endpoint=params.get("api_endpoint") or None,
            review_gate_pause_scope=params.get("review_gate_pause_scope") or "session",
        )
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {
        "session_id": session.id,
        "name": session.name,
        "facilitator_id": facilitator.id,
        "branch_id": branch.id,
        "status": session.status,
    }


async def _dispatch_session_update_settings(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    session_id = params.get("session_id") or ctx.session_id
    if not session_id:
        return {"error": "SACP_E_VALIDATION", "reason": "session_id_required"}
    from src.repositories.session_repo import SessionRepository

    repo = SessionRepository(ctx.db_pool)
    try:
        if "name" in params and params["name"]:
            await repo.update_name(session_id, params["name"])
        if "review_gate_pause_scope" in params and params["review_gate_pause_scope"]:
            await repo.update_review_gate_pause_scope(session_id, params["review_gate_pause_scope"])
        session = await repo.get_session(session_id)
        if session is None:
            return {"error": "SACP_E_NOT_FOUND", "reason": "session_not_found"}
    except ValueError as exc:
        return {"error": "SACP_E_VALIDATION", "reason": str(exc)}
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"session_id": session.id, "name": session.name, "status": session.status}


async def _dispatch_session_archive(ctx: CallerContext, params: dict) -> dict:
    # archive requires the orchestrator loop state (to cancel tasks and run
    # the summarizer) which is only available on the orchestrator process.
    # A pure repo.update_status transition is the safe DB-only fallback here.
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    session_id = params.get("session_id") or ctx.session_id
    if not session_id:
        return {"error": "SACP_E_VALIDATION", "reason": "session_id_required"}
    from src.repositories.session_repo import SessionRepository

    repo = SessionRepository(ctx.db_pool)
    try:
        session = await repo.update_status(session_id, "archived")
    except ValueError as exc:
        return {"error": "SACP_E_VALIDATION", "reason": str(exc)}
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"session_id": session.id, "status": session.status}


async def _dispatch_session_delete(ctx: CallerContext, params: dict) -> dict:
    if ctx.db_pool is None:
        return {"error": "SACP_E_INTERNAL", "reason": "no_db_pool"}
    session_id = params.get("session_id") or ctx.session_id
    if not session_id:
        return {"error": "SACP_E_VALIDATION", "reason": "session_id_required"}
    from src.repositories.session_repo import SessionRepository

    repo = SessionRepository(ctx.db_pool)
    try:
        await repo.delete_session(session_id)
    except Exception as exc:
        return {"error": "SACP_E_INTERNAL", "reason": str(exc)}
    return {"session_id": session_id, "status": "deleted"}


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
