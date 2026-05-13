# SPDX-License-Identifier: AGPL-3.0-or-later
"""Idempotency key deduplication via admin_audit_log. Spec 030 Phase 3, FR-069."""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("sacp.mcp.idempotency")

_PLACEHOLDER_ACTION = "mcp_idempotency_placeholder"

_SELECT_SQL = """
    SELECT new_value
    FROM admin_audit_log
    WHERE action = $1 AND target_id = $2
    ORDER BY timestamp DESC
    LIMIT 1
"""

_INSERT_SQL = """
    INSERT INTO admin_audit_log
        (session_id, facilitator_id, action, target_id, previous_value, new_value)
    VALUES ($1, $2, $3, $4, $5, $6)
"""


def _retention_hours() -> int:
    raw = os.environ.get("SACP_MCP_TOOL_IDEMPOTENCY_RETENTION_HOURS")
    if raw and raw.strip():
        try:
            return int(raw)
        except ValueError:
            pass
    return 24


async def check_idempotency(
    pool: object,
    idempotency_key: str,
    tool_name: str,
    session_id: str,
    participant_id: str,
) -> dict | None:
    """Return stored result if the key was already used, else None."""
    action = f"mcp_idempotency_{tool_name}"
    try:
        async with pool.acquire() as conn:
            hours = _retention_hours()
            row = await conn.fetchrow(
                """
                SELECT new_value
                FROM admin_audit_log
                WHERE action = $1
                  AND target_id = $2
                  AND timestamp >= NOW() - ($3 || ' hours')::interval
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                action,
                idempotency_key,
                str(hours),
            )
        if row is not None and row["new_value"]:
            stored = json.loads(row["new_value"])
            if stored.get("_idempotency_status") == "completed":
                return stored.get("result")
    except Exception:
        log.debug("idempotency check failed silently", exc_info=True)
    return None


async def record_idempotency(
    pool: object,
    idempotency_key: str,
    tool_name: str,
    *,
    session_id: str,
    participant_id: str,
    result: dict,
) -> None:
    """Persist the tool result against the idempotency key."""
    action = f"mcp_idempotency_{tool_name}"
    payload = json.dumps({"_idempotency_status": "completed", "result": result})
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                _INSERT_SQL,
                session_id or "mcp",
                participant_id,
                action,
                idempotency_key,
                None,
                payload,
            )
    except Exception:
        log.debug("idempotency record failed silently", exc_info=True)
