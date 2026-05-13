# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dispatch hook protocol for pre/post tool-call instrumentation. Spec 030 FR-066."""

from __future__ import annotations

import json
import logging
from typing import Protocol, runtime_checkable

log = logging.getLogger("sacp.mcp.hooks")

_ROUTING_LOG_SQL = """
    INSERT INTO routing_log
        (session_id, turn_number, intended_participant,
         actual_participant, routing_action,
         complexity_score, domain_match, reason,
         route_ms)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
"""

_AUDIT_LOG_SQL = """
    INSERT INTO admin_audit_log
        (session_id, facilitator_id, action, target_id,
         previous_value, new_value)
    VALUES ($1, $2, $3, $4, $5, $6)
"""


@runtime_checkable
class DispatchHook(Protocol):
    async def pre(self, caller_context: object, tool_name: str, params: dict) -> None: ...

    async def post(
        self,
        caller_context: object,
        tool_name: str,
        params: dict,
        result: dict,
        elapsed_ms: int,
    ) -> None: ...


async def _get_ctx(caller_context: object) -> object | None:
    """Return caller_context if it is a CallerContext with a db_pool, else None."""
    from src.mcp_protocol.caller_context import CallerContext

    if isinstance(caller_context, CallerContext) and caller_context.db_pool is not None:
        return caller_context
    return None


class V14TimingHook:
    """Write per-stage timing to routing_log. Spec 030 FR-066 / T051."""

    async def pre(self, caller_context: object, tool_name: str, params: dict) -> None:
        pass

    async def post(
        self,
        caller_context: object,
        tool_name: str,
        params: dict,
        result: dict,
        elapsed_ms: int,
    ) -> None:
        ctx = await _get_ctx(caller_context)
        if ctx is None:
            return
        stage = f"mcp_{tool_name.replace('/', '_').replace('.', '_')}"
        try:
            async with ctx.db_pool.acquire() as conn:
                await conn.execute(
                    _ROUTING_LOG_SQL,
                    ctx.session_id or "mcp",
                    0,
                    ctx.participant_id,
                    ctx.participant_id,
                    stage,
                    "n/a",
                    False,
                    stage,
                    elapsed_ms,
                )
        except Exception:  # noqa: BLE001
            log.debug("V14TimingHook.post failed silently", exc_info=True)


class AuditLogHook:
    """Write admin_audit_log row on tool dispatch. Spec 030 FR-066."""

    async def pre(self, caller_context: object, tool_name: str, params: dict) -> None:
        pass

    async def post(
        self,
        caller_context: object,
        tool_name: str,
        params: dict,
        result: dict,
        elapsed_ms: int,
    ) -> None:
        ctx = await _get_ctx(caller_context)
        if ctx is None:
            return
        try:
            async with ctx.db_pool.acquire() as conn:
                await conn.execute(
                    _AUDIT_LOG_SQL,
                    ctx.session_id or "mcp",
                    ctx.participant_id,
                    "mcp_tool_called",
                    tool_name,
                    None,
                    json.dumps({"elapsed_ms": elapsed_ms}),
                )
        except Exception:  # noqa: BLE001
            log.debug("AuditLogHook.post failed silently", exc_info=True)
