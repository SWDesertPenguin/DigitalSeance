# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 018 — admin_audit_log emission for partition decisions and loads.

Three audit action types reuse the existing `admin_audit_log` table:
- `tool_partition_decided` — every partition decision at session start
  and every spec-017-freshness-driven recomputation.
- `tool_loaded_on_demand` — every successful `tools.load_deferred`
  invocation that promoted a deferred tool.
- `tool_re_deferred` — every LRU eviction triggered by an on-demand
  load that exceeded budget.

The row shape follows spec 002's `admin_audit_log` schema:
`(session_id, facilitator_id, action, target_id, previous_value,
new_value)` with `target_id=participant_id` to scope by participant
(consistent with spec 014/021 patterns). The action-specific payload
lives in `new_value` as a JSON-encoded string.

When the session lacks a real facilitator (rare — system-initiated
contexts in test fixtures), the sentinel `'orchestrator'` is used
(consistent with `src.orchestrator.standby._resolve_facilitator`).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)


async def emit_partition_decided(
    *,
    pool: Any,
    session_id: str,
    participant_id: str,
    loaded_tool_names: list[str],
    deferred_tool_names: list[str],
    loaded_token_count: int,
    pathological_partition: bool,
    tokenizer_name: str,
    tokenizer_fallback_used: bool,
    selection_policy: str,
    decided_at: datetime | None,
    reason: str,
) -> None:
    """Write one `tool_partition_decided` row.

    Per US3 AS1 + SC-008: the row carries the full loaded/deferred name
    lists so operators can reconstruct partition state from the audit
    log alone, without inspecting the system prompt.
    """
    payload = {
        "loaded_count": len(loaded_tool_names),
        "deferred_count": len(deferred_tool_names),
        "loaded_token_count": loaded_token_count,
        "decided_at": _iso_or_none(decided_at),
        "selection_policy": selection_policy,
        "pathological_partition": pathological_partition,
        "tokenizer_name": tokenizer_name,
        "tokenizer_fallback_used": tokenizer_fallback_used,
        "loaded_tool_names": loaded_tool_names,
        "deferred_tool_names": deferred_tool_names,
        "reason": reason,
    }
    await _write_admin_audit_row(
        pool=pool,
        session_id=session_id,
        target_id=participant_id,
        action="tool_partition_decided",
        new_value_payload=payload,
    )


async def emit_loaded_on_demand(
    *,
    pool: Any,
    session_id: str,
    participant_id: str,
    tool_name: str,
    evicted_tool_name: str | None,
) -> None:
    """Write one `tool_loaded_on_demand` row.

    Per FR-008 + FR-009: the row records the load and sets
    `prompt_cache_invalidated=true` so cache-cost is causally
    traceable. When LRU eviction occurred, `evicted_tool_name` is
    non-null and the paired `tool_re_deferred` row records the
    eviction (emit_re_deferred is called separately).
    """
    payload = {
        "tool_name": tool_name,
        "requested_at": _iso_or_none(datetime.now(tz=UTC)),
        "prompt_cache_invalidated": True,
        "evicted_tool_name": evicted_tool_name,
    }
    await _write_admin_audit_row(
        pool=pool,
        session_id=session_id,
        target_id=participant_id,
        action="tool_loaded_on_demand",
        new_value_payload=payload,
    )


async def emit_re_deferred(
    *,
    pool: Any,
    session_id: str,
    participant_id: str,
    re_deferred_tool: str,
    evicted_for_tool: str,
) -> None:
    """Write one `tool_re_deferred` row.

    Per FR-008: the row records the LRU eviction triggered by an
    on-demand load that exceeded budget. Pair with the
    `tool_loaded_on_demand` row whose `evicted_tool_name` matches
    `re_deferred_tool` to reconstruct the full swap.
    """
    payload = {
        "tool_name": re_deferred_tool,
        "re_deferred_at": _iso_or_none(datetime.now(tz=UTC)),
        "reason": "lru_eviction_after_load",
        "evicted_for_tool_name": evicted_for_tool,
    }
    await _write_admin_audit_row(
        pool=pool,
        session_id=session_id,
        target_id=participant_id,
        action="tool_re_deferred",
        new_value_payload=payload,
    )


# ── internal ────────────────────────────────────────────────────────


async def _write_admin_audit_row(
    *,
    pool: Any,
    session_id: str,
    target_id: str,
    action: str,
    new_value_payload: dict[str, Any],
) -> None:
    """Append one row to `admin_audit_log` with a JSON-encoded payload.

    `facilitator_id` is resolved from the session's facilitator
    participant, or `'orchestrator'` when no facilitator exists
    (matches `src.orchestrator.standby._resolve_facilitator`).

    `previous_value` is NULL — the spec-018 audit rows are
    forward-only point-in-time records, not transitions between
    states. The full state lives in `new_value`.

    Best-effort: if the pool is unavailable or the write raises, the
    error is logged but the calling partition operation does NOT fail.
    The forensic audit record is desirable but not load-bearing for the
    partition behavior itself.
    """
    try:
        facilitator_id = await _resolve_facilitator(pool, session_id)
        new_value = json.dumps(new_value_payload)
        async with pool.acquire() as conn:
            await conn.execute(
                _INSERT_AUDIT_SQL,
                session_id,
                facilitator_id,
                action,
                target_id,
                None,
                new_value,
            )
    except Exception:  # noqa: BLE001 — audit emission is best-effort
        log.exception(
            "deferred_tool_audit: failed to emit %s row session=%s participant=%s",
            action,
            session_id,
            target_id,
        )


async def _resolve_facilitator(pool: Any, session_id: str) -> str:
    """Return the facilitator id or 'orchestrator' when the session lacks one."""
    sql = """
        SELECT id FROM participants
        WHERE session_id = $1 AND role = 'facilitator'
        LIMIT 1
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, session_id)
        return row["id"] if row else "orchestrator"
    except Exception:  # noqa: BLE001
        return "orchestrator"


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


_INSERT_AUDIT_SQL = """
    INSERT INTO admin_audit_log
        (session_id, facilitator_id, action,
         target_id, previous_value, new_value)
    VALUES ($1, $2, $3, $4, $5, $6)
"""
