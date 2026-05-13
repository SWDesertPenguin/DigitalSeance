# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/call boundary. Spec 030 Phase 2, FR-039 + FR-066 + tool-registry-shape.md.

Phase 4 addition (FR-099): JWT bearer validation when SACP_OAUTH_ENABLED=true.
JWT verification is ONLY performed in src/mcp_protocol/auth/; this module
calls into that package and must not import jwt directly.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.errors import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_METHOD_NOT_FOUND,
    SACP_AUTH_FAILED,
    SACP_E_FORBIDDEN,
    SACP_E_INTERNAL,
    SACP_E_NOT_FOUND,
)
from src.mcp_protocol.hooks import AuditLogHook, DispatchHook, V14TimingHook

log = logging.getLogger("sacp.mcp.dispatcher")

_BUILTIN_HOOKS: list[DispatchHook] = [V14TimingHook(), AuditLogHook()]

_AUDIT_LOG_SQL = """
    INSERT INTO admin_audit_log
        (session_id, facilitator_id, action, target_id,
         previous_value, new_value)
    VALUES ($1, $2, $3, $4, $5, $6)
"""


def get_registry() -> dict[str, Any]:
    """Return the live tool registry."""
    from src.mcp_protocol.tools import REGISTRY

    return REGISTRY  # type: ignore[return-value]


class DispatchError(Exception):
    """Raised by dispatch() when a JSON-RPC error should be returned."""

    def __init__(self, code: int, message: str, data: dict | None = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


def _check_authorization(entry: Any, caller_context: CallerContext) -> None:
    """Raise DispatchError if the caller lacks scope or AI access."""
    defn = entry.definition
    required_scope = defn.scopeRequirement
    if required_scope == "sponsor":
        if "sponsor" not in caller_context.scopes and "facilitator" not in caller_context.scopes:
            raise DispatchError(
                SACP_AUTH_FAILED,
                "Insufficient scope",
                {"sacp_error_code": SACP_E_FORBIDDEN, "required": required_scope},
            )
    elif required_scope != "any" and required_scope not in caller_context.scopes:
        raise DispatchError(
            SACP_AUTH_FAILED,
            "Insufficient scope",
            {"sacp_error_code": SACP_E_FORBIDDEN, "required": required_scope},
        )
    if not defn.aiAccessible and caller_context.is_ai_caller:
        raise DispatchError(
            SACP_AUTH_FAILED,
            "Tool not accessible to AI callers",
            {"sacp_error_code": SACP_E_FORBIDDEN},
        )


async def _invoke(entry: Any, caller_context: CallerContext, arguments: dict) -> tuple[dict, int]:
    """Invoke the tool dispatch callable; return (result, elapsed_ms)."""
    started = time.monotonic()
    try:
        result = await entry.dispatch(caller_context, arguments)
    except DispatchError:
        raise
    except Exception as exc:
        log.warning("tool dispatch raised unexpectedly: %s", exc, exc_info=True)
        raise DispatchError(
            JSONRPC_INTERNAL_ERROR,
            "Internal dispatch error",
            {"sacp_error_code": SACP_E_INTERNAL},
        ) from exc
    return result, int((time.monotonic() - started) * 1000)


async def _emit_tool_audit_row(
    caller_context: CallerContext,
    tool_name: str,
    elapsed_ms: int,
) -> None:
    """Write per-tool action code to admin_audit_log per FR-057."""
    if caller_context.db_pool is None:
        return
    action = f"mcp_tool_{tool_name}"
    try:
        async with caller_context.db_pool.acquire() as conn:
            await conn.execute(
                _AUDIT_LOG_SQL,
                caller_context.session_id or "mcp",
                caller_context.participant_id,
                action,
                tool_name,
                None,
                json.dumps({"elapsed_ms": elapsed_ms}),
            )
    except Exception:
        log.debug("_emit_tool_audit_row failed silently", exc_info=True)


_OAUTH_ENABLED_CACHE: bool | None = None

_MIGRATION_PROMPT_SQL = """
    UPDATE participants SET mcp_oauth_migration_prompted_at = $2
    WHERE id = $1 AND mcp_oauth_migration_prompted_at IS NULL
"""

_GET_MIGRATION_PROMPT_SQL = """
    SELECT mcp_oauth_migration_prompted_at FROM participants WHERE id = $1
"""


def _oauth_enabled() -> bool:
    return os.environ.get("SACP_OAUTH_ENABLED", "false").lower() == "true"


def _grace_days() -> int:
    val = os.environ.get("SACP_OAUTH_STATIC_TOKEN_GRACE_DAYS", "90")
    try:
        return max(0, min(365, int(val)))
    except (ValueError, TypeError):
        return 90


def validate_bearer_jwt(
    bearer: str,
    caller_context: CallerContext,
    tool_name: str,
) -> CallerContext | None:
    """Validate a JWT bearer when SACP_OAUTH_ENABLED=true.

    Returns an updated CallerContext on success, None on failure.
    Raises DispatchError on a definitive auth failure.
    """
    if not _oauth_enabled():
        return None
    try:
        from src.mcp_protocol.auth.jwt_signer import verify_access_token

        payload = verify_access_token(bearer)
    except Exception as exc:
        raise DispatchError(
            SACP_AUTH_FAILED,
            "Invalid or expired access token",
            {"sacp_error_code": SACP_E_FORBIDDEN, "detail": str(exc)},
        ) from exc

    session_claim = payload.get("session_id")
    if session_claim and caller_context.session_id and session_claim != caller_context.session_id:
        raise DispatchError(
            SACP_AUTH_FAILED,
            "Token session_id claim does not match target session",
            {"sacp_error_code": SACP_E_FORBIDDEN},
        )

    scopes = frozenset(payload.get("scope", []))
    return CallerContext(
        participant_id=payload.get("sub", caller_context.participant_id),
        session_id=session_claim or caller_context.session_id,
        scopes=scopes,
        is_ai_caller=False,
        mcp_session_id=caller_context.mcp_session_id,
        request_id=caller_context.request_id,
        dispatch_started_at=caller_context.dispatch_started_at,
        idempotency_key=caller_context.idempotency_key,
        db_pool=caller_context.db_pool,
        encryption_key=caller_context.encryption_key,
    )


async def check_static_bearer_migration(
    bearer: str,
    caller_context: CallerContext,
) -> dict | None:
    """When OAuth is enabled and a static bearer is presented on MCP, handle migration.

    Returns a migration_prompt error dict if the bearer is static and needs migration,
    None if the bearer should proceed normally (OAuth disabled or after grace period
    where hard rejection kicks in).

    Raises DispatchError for hard rejection post-grace-period.
    """
    if not _oauth_enabled():
        return None
    if caller_context.db_pool is None:
        return None

    participant_id = caller_context.participant_id
    now = datetime.now(tz=UTC)

    async with caller_context.db_pool.acquire() as conn:
        row = await conn.fetchrow(_GET_MIGRATION_PROMPT_SQL, participant_id)
        if row is None:
            return None
        prompted_at = row["mcp_oauth_migration_prompted_at"]
        if prompted_at is None:
            await conn.execute(_MIGRATION_PROMPT_SQL, participant_id, now)
            return {
                "migration_prompt": True,
                "message": "Static bearer tokens on the MCP endpoint will be deprecated. "
                "Please migrate to OAuth 2.1 + PKCE.",
            }

        grace = _grace_days()
        if prompted_at.tzinfo is None:
            prompted_at = prompted_at.replace(tzinfo=UTC)
        days_since = (now - prompted_at).days
        if days_since >= grace:
            raise DispatchError(
                SACP_AUTH_FAILED,
                "Static bearer token no longer accepted; OAuth migration required",
                {"sacp_error_code": "SACP_E_MIGRATION_REQUIRED"},
            )
        return {
            "migration_prompt": True,
            "days_remaining": grace - days_since,
            "message": "Static bearer tokens will be deprecated; migrate to OAuth 2.1 + PKCE.",
        }


async def dispatch(
    caller_context: CallerContext,
    tool_name: str,
    arguments: dict,
    extra_hooks: list[DispatchHook] | None = None,
) -> dict:
    """Dispatch through registry + auth check + hook chain.

    Raises DispatchError on any JSON-RPC-reportable failure.
    """
    registry = get_registry()
    entry = registry.get(tool_name)
    if entry is None:
        raise DispatchError(
            JSONRPC_METHOD_NOT_FOUND,
            f"Unknown tool: {tool_name!r}",
            {"sacp_error_code": SACP_E_NOT_FOUND},
        )
    _check_authorization(entry, caller_context)
    all_hooks: list[DispatchHook] = list(_BUILTIN_HOOKS) + (extra_hooks or [])
    for hook in all_hooks:
        await hook.pre(caller_context, tool_name, arguments)
    result, elapsed_ms = await _invoke(entry, caller_context, arguments)
    await _emit_tool_audit_row(caller_context, tool_name, elapsed_ms)
    for hook in all_hooks:
        await hook.post(caller_context, tool_name, arguments, result, elapsed_ms)
    return result
