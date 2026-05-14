# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-participant MCP tool-list freshness. Spec 017."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import asyncpg
import httpx

log = logging.getLogger(__name__)

_DEFAULT_TOOL_LIST_MAX_BYTES = 65536
_DEFAULT_REFRESH_TIMEOUT_S = 30


# ---------------------------------------------------------------------------
# In-memory registry
# ---------------------------------------------------------------------------


@dataclass
class ParticipantToolRegistry:
    """Per-participant, session-local tool registry. Not persisted across restart."""

    session_id: str
    participant_id: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    tool_set_hash: str = ""
    last_refreshed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    push_subscribed: bool = False
    consecutive_failures: int = 0
    next_retry_at: datetime | None = None


# Key: (session_id, participant_id)
_REGISTRIES: dict[tuple[str, str], ParticipantToolRegistry] = {}


# ---------------------------------------------------------------------------
# Hash
# ---------------------------------------------------------------------------


def _compute_hash(tools: list[dict[str, Any]]) -> str:
    """Order-independent SHA-256 of the sorted tool list (FR-003)."""
    serialized = json.dumps(
        sorted(tools, key=lambda t: t.get("name", "")),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Env var helpers
# ---------------------------------------------------------------------------


def _poll_interval_s() -> int | None:
    """Return SACP_TOOL_REFRESH_POLL_INTERVAL_S or None if unset."""
    val = os.environ.get("SACP_TOOL_REFRESH_POLL_INTERVAL_S")
    if not val or not val.strip():
        return None
    try:
        return int(val)
    except ValueError:
        return None


def _refresh_timeout_s() -> int:
    """Return SACP_TOOL_REFRESH_TIMEOUT_S or default 30."""
    val = os.environ.get("SACP_TOOL_REFRESH_TIMEOUT_S")
    if not val or not val.strip():
        return _DEFAULT_REFRESH_TIMEOUT_S
    try:
        return int(val)
    except ValueError:
        return _DEFAULT_REFRESH_TIMEOUT_S


def _tool_list_max_bytes() -> int:
    """Return SACP_TOOL_LIST_MAX_BYTES or default 65536."""
    val = os.environ.get("SACP_TOOL_LIST_MAX_BYTES")
    if not val or not val.strip():
        return _DEFAULT_TOOL_LIST_MAX_BYTES
    try:
        return int(val)
    except ValueError:
        return _DEFAULT_TOOL_LIST_MAX_BYTES


def _push_enabled() -> bool:
    """Return True when SACP_TOOL_REFRESH_PUSH_ENABLED=true/1."""
    val = os.environ.get("SACP_TOOL_REFRESH_PUSH_ENABLED", "").strip().lower()
    return val in ("true", "1")


# ---------------------------------------------------------------------------
# MCP tools/list HTTP call
# ---------------------------------------------------------------------------


async def _fetch_tools(url: str, timeout_s: int) -> list[dict[str, Any]]:
    """Async MCP tools/list call via httpx."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.post(url, json=payload)
    response.raise_for_status()
    parsed = response.json()
    result = parsed.get("result", {})
    tools = result.get("tools", [])
    if not isinstance(tools, list):
        raise ValueError(f"tools/list result.tools is not a list: {type(tools)}")
    return tools


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------


async def _fetch_facilitator_id(pool: asyncpg.Pool, session_id: str, fallback: str) -> str:
    """Look up session facilitator_id; fall back to participant_id on error."""
    try:
        async with pool.acquire() as conn:
            fid = await conn.fetchval(
                "SELECT facilitator_id FROM sessions WHERE id = $1",
                session_id,
            )
        return fid or fallback
    except Exception:
        return fallback


@dataclass
class _AuditPayload:
    """Structured audit row payload for a tool-list change event."""

    change_kind: str
    tool_name: str | None
    old_hash: str | None
    new_hash: str | None
    trigger_source: str
    prompt_cache_invalidated: bool


def _payload_json(p: _AuditPayload) -> str:
    """Serialize audit payload to JSON string."""
    return json.dumps(
        {
            "change_kind": p.change_kind,
            "tool_name": p.tool_name,
            "old_hash": p.old_hash,
            "new_hash": p.new_hash,
            "trigger_source": p.trigger_source,
            "prompt_cache_invalidated": p.prompt_cache_invalidated,
            "observed_at": datetime.now(UTC).isoformat(),
        }
    )


async def _emit_audit_row(
    pool: asyncpg.Pool, session_id: str, participant_id: str, p: _AuditPayload
) -> None:
    """Write a tool_list_changed admin_audit_log row (FR-004). Best-effort."""
    facilitator_id = await _fetch_facilitator_id(pool, session_id, participant_id)
    new_value = _payload_json(p)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO admin_audit_log"
                " (session_id, facilitator_id, action, target_id, previous_value, new_value)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                session_id,
                facilitator_id,
                "tool_list_changed",
                participant_id,
                p.old_hash,
                new_value,
            )
    except Exception:
        log.warning(
            "tool_list_freshness: audit INSERT failed session=%s participant=%s kind=%s",
            session_id,
            participant_id,
            p.change_kind,
        )


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------


def _diff_tool_lists(
    old_tools: list[dict[str, Any]],
    new_tools: list[dict[str, Any]],
) -> list[tuple[str, str | None]]:
    """Return list of (change_kind, tool_name) pairs for each detected change."""
    old_by_name = {t.get("name", ""): t for t in old_tools}
    new_by_name = {t.get("name", ""): t for t in new_tools}

    changes: list[tuple[str, str | None]] = []
    for name, tool in new_by_name.items():
        if name not in old_by_name:
            changes.append(("added", name))
        else:
            changes.extend(_diff_single_tool(name, old_by_name[name], tool))

    for name in old_by_name:
        if name not in new_by_name:
            changes.append(("removed", name))

    return changes


def _diff_single_tool(
    name: str,
    old_tool: dict[str, Any],
    new_tool: dict[str, Any],
) -> list[tuple[str, str]]:
    """Diff a single tool that exists in both lists. Returns change tuples."""
    old_schema = old_tool.get("inputSchema", {})
    new_schema = new_tool.get("inputSchema", {})
    if json.dumps(new_schema, sort_keys=True) != json.dumps(old_schema, sort_keys=True):
        return [("schema_changed", name)]
    old_desc = old_tool.get("description", "")
    new_desc = new_tool.get("description", "")
    if old_desc != new_desc:
        return [("description_changed", name)]
    return []


# ---------------------------------------------------------------------------
# Size-cap enforcement
# ---------------------------------------------------------------------------


def _apply_size_cap(
    tools: list[dict[str, Any]],
    max_bytes: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Truncate tool list to fit within max_bytes. Returns (truncated_list, was_truncated)."""
    if len(json.dumps(tools).encode()) <= max_bytes:
        return tools, False
    kept: list[dict[str, Any]] = []
    for tool in tools:
        candidate = kept + [tool]
        if len(json.dumps(candidate).encode()) > max_bytes:
            break
        kept = candidate
    return kept, True


# ---------------------------------------------------------------------------
# Refresh internals
# ---------------------------------------------------------------------------


@dataclass
class _RefreshContext:
    """Bundled args for a single refresh operation."""

    pool: asyncpg.Pool
    session_id: str
    participant_id: str
    registry: ParticipantToolRegistry
    trigger_source: str


async def _handle_fetch_error(ctx: _RefreshContext, exc: Exception) -> bool:
    """Log and audit a failed tools/list fetch. Returns False."""
    log.warning(
        "tool_list_freshness: refresh failed session=%s participant=%s: %s",
        ctx.session_id,
        ctx.participant_id,
        exc,
    )
    ctx.registry.consecutive_failures += 1
    payload = _AuditPayload(
        change_kind="refresh_failed",
        tool_name=None,
        old_hash=ctx.registry.tool_set_hash,
        new_hash=None,
        trigger_source=ctx.trigger_source,
        prompt_cache_invalidated=False,
    )
    await _emit_audit_row(ctx.pool, ctx.session_id, ctx.participant_id, payload)
    return False


async def _emit_change_rows(
    ctx: _RefreshContext,
    changes: list[tuple[str, str | None]],
    old_hash: str,
    new_hash: str,
    prompt_cache_invalidated: bool,
) -> None:
    """Emit one audit row per detected change."""
    for change_kind, tool_name in changes:
        payload = _AuditPayload(
            change_kind=change_kind,
            tool_name=tool_name,
            old_hash=old_hash,
            new_hash=new_hash,
            trigger_source=ctx.trigger_source,
            prompt_cache_invalidated=prompt_cache_invalidated,
        )
        await _emit_audit_row(ctx.pool, ctx.session_id, ctx.participant_id, payload)


@dataclass
class _ChangeBundle:
    """Carries computed hash values and truncation flag for audit emission."""

    old_hash: str
    new_hash: str
    prompt_cache_invalidated: bool
    truncated: bool


async def _apply_and_audit_changes(
    ctx: _RefreshContext, tools: list[dict[str, Any]], bundle: _ChangeBundle
) -> None:
    """Update registry state and emit audit rows for detected changes."""
    if bundle.truncated:
        trunc_payload = _AuditPayload(
            change_kind="removed",
            tool_name=f"<truncated at {len(tools)} tools>",
            old_hash=bundle.old_hash,
            new_hash=bundle.new_hash,
            trigger_source=ctx.trigger_source,
            prompt_cache_invalidated=bundle.prompt_cache_invalidated,
        )
        await _emit_audit_row(ctx.pool, ctx.session_id, ctx.participant_id, trunc_payload)
    await _update_registry_and_emit(ctx, tools, bundle)


async def _update_registry_and_emit(
    ctx: _RefreshContext, tools: list[dict[str, Any]], bundle: _ChangeBundle
) -> None:
    """Mutate the registry and emit per-change audit rows."""
    old_tools = list(ctx.registry.tools)
    ctx.registry.tools = tools
    ctx.registry.tool_set_hash = bundle.new_hash
    changes = _diff_tool_lists(old_tools, tools) or [("schema_changed", None)]
    await _emit_change_rows(
        ctx, changes, bundle.old_hash, bundle.new_hash, bundle.prompt_cache_invalidated
    )
    log.info(
        "tool_list_freshness: tool set changed session=%s participant=%s" " old=%s new=%s n=%d",
        ctx.session_id,
        ctx.participant_id,
        bundle.old_hash[:8] if bundle.old_hash else "none",
        bundle.new_hash[:8],
        len(changes),
    )


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------


def get_tools(session_id: str, participant_id: str) -> list[dict[str, Any]]:
    """Return cached tools for the participant, or empty list if not registered."""
    registry = _REGISTRIES.get((session_id, participant_id))
    if registry is None:
        return []
    return list(registry.tools)


def _is_malformed(raw_tools: list[dict[str, Any]]) -> bool:
    """Return True when the tool list contains duplicate names."""
    names = [t.get("name", "") for t in raw_tools]
    return len(names) != len(set(names))


async def refresh_tool_list(
    session_id: str,
    participant_id: str,
    mcp_url: str,
    pool: asyncpg.Pool,
    *,
    trigger_source: str = "poll",
) -> bool:
    """Fetch tools/list, update registry, emit audit row if changed.

    Returns True if the tool set changed, False otherwise.
    Preserves cached list on failure (FR-011).
    """
    registry = _REGISTRIES.get((session_id, participant_id))
    if registry is None:
        return False
    ctx = _RefreshContext(
        pool=pool,
        session_id=session_id,
        participant_id=participant_id,
        registry=registry,
        trigger_source=trigger_source,
    )
    return await _run_refresh(ctx, mcp_url)


async def _run_refresh(ctx: _RefreshContext, mcp_url: str) -> bool:
    """Fetch and validate the tools/list response."""
    try:
        raw_tools = await _fetch_tools(mcp_url, _refresh_timeout_s())
    except Exception as exc:
        return await _handle_fetch_error(ctx, exc)

    if _is_malformed(raw_tools):
        log.warning(
            "tool_list_freshness: malformed response (duplicate tool names)"
            " session=%s participant=%s; preserving cached list",
            ctx.session_id,
            ctx.participant_id,
        )
        return await _handle_fetch_error(ctx, ValueError("duplicate tool names in response"))

    return await _process_fresh_tools(ctx, raw_tools)


async def _process_fresh_tools(ctx: _RefreshContext, raw_tools: list[dict[str, Any]]) -> bool:
    """Compare, cap, and apply a freshly fetched tool list."""
    old_hash = ctx.registry.tool_set_hash
    prompt_cache_invalidated = ctx.registry.consecutive_failures == 0
    tools, truncated = _apply_size_cap(raw_tools, _tool_list_max_bytes())
    new_hash = _compute_hash(tools)
    ctx.registry.last_refreshed_at = datetime.now(UTC)
    ctx.registry.consecutive_failures = 0
    ctx.registry.next_retry_at = None
    if new_hash == old_hash and not truncated:
        return False
    bundle = _ChangeBundle(
        old_hash=old_hash,
        new_hash=new_hash,
        prompt_cache_invalidated=prompt_cache_invalidated,
        truncated=truncated,
    )
    await _apply_and_audit_changes(ctx, tools, bundle)
    return True


async def maybe_refresh(
    session_id: str,
    participant_id: str,
    mcp_url: str | None,
    pool: asyncpg.Pool,
) -> bool:
    """Check poll interval gate; call refresh_tool_list if elapsed.

    Returns True if tool set changed. Returns False when:
    - SACP_TOOL_REFRESH_POLL_INTERVAL_S is unset (SC-005 regression gate)
    - No mcp_url (no registered MCP server for this participant)
    - No registry for this participant
    - Poll interval has not elapsed
    - Any exception (V6 graceful degradation)
    """
    interval_s = _poll_interval_s()
    if interval_s is None:
        return False
    if not mcp_url:
        return False
    registry = _REGISTRIES.get((session_id, participant_id))
    if registry is None:
        return False
    try:
        elapsed = (datetime.now(UTC) - registry.last_refreshed_at).total_seconds()
        if elapsed < interval_s:
            return False
        return await refresh_tool_list(
            session_id, participant_id, mcp_url, pool, trigger_source="poll"
        )
    except Exception:
        log.warning(
            "tool_list_freshness: maybe_refresh unexpected error session=%s participant=%s",
            session_id,
            participant_id,
            exc_info=True,
        )
        return False


async def register_participant(
    session_id: str,
    participant_id: str,
    mcp_url: str | None,
    pool: asyncpg.Pool,
) -> None:
    """Initial tool fetch at participant registration.

    Creates a registry entry and performs the first tools/list fetch.
    Attempts push subscription if SACP_TOOL_REFRESH_PUSH_ENABLED=true.
    No-op when mcp_url is None (participant has no registered MCP server).
    Fail-soft: exceptions are logged and do not abort registration.
    """
    if not mcp_url:
        return

    registry = ParticipantToolRegistry(session_id=session_id, participant_id=participant_id)
    _REGISTRIES[(session_id, participant_id)] = registry
    await _initial_fetch(session_id, participant_id, mcp_url, registry)

    if not _push_enabled():
        return
    await _attempt_push_subscription(session_id, participant_id, mcp_url, pool)


async def _initial_fetch(
    session_id: str,
    participant_id: str,
    mcp_url: str,
    registry: ParticipantToolRegistry,
) -> None:
    """Fetch the initial tool list for a newly registered participant."""
    timeout_s = _refresh_timeout_s()
    max_bytes = _tool_list_max_bytes()
    try:
        raw_tools = await _fetch_tools(mcp_url, timeout_s)
        tools, _truncated = _apply_size_cap(raw_tools, max_bytes)
        registry.tools = tools
        registry.tool_set_hash = _compute_hash(tools)
        registry.last_refreshed_at = datetime.now(UTC)
        log.info(
            "tool_list_freshness: registered participant=%s tools=%d session=%s",
            participant_id,
            len(tools),
            session_id,
        )
    except Exception as exc:
        log.warning(
            "tool_list_freshness: initial tool fetch failed participant=%s: %s",
            participant_id,
            exc,
        )


async def _attempt_push_subscription(
    session_id: str,
    participant_id: str,
    mcp_url: str,
    pool: asyncpg.Pool,
) -> None:
    """Attempt notifications/tools/list_changed subscription; audit the outcome."""
    subscribed = False
    failure_reason: str | None = None
    timeout_s = _refresh_timeout_s()
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "notifications/tools/list_changed",
            "params": {},
        }
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(mcp_url, json=payload)
        result = resp.json()
        if "error" in result:
            failure_reason = str(result["error"].get("message", "rpc_error"))
        else:
            subscribed = True
            registry = _REGISTRIES.get((session_id, participant_id))
            if registry is not None:
                registry.push_subscribed = True
    except Exception as exc:
        failure_reason = str(exc)

    await _audit_subscription_outcome(pool, session_id, participant_id, subscribed, failure_reason)


async def _audit_subscription_outcome(
    pool: asyncpg.Pool,
    session_id: str,
    participant_id: str,
    subscribed: bool,
    failure_reason: str | None,
) -> None:
    """Write tool_subscription_attempted audit row."""
    facilitator_id = await _fetch_facilitator_id(pool, session_id, participant_id)
    subscription_value = json.dumps(
        {
            "supported": subscribed,
            "subscribed_at": datetime.now(UTC).isoformat() if subscribed else None,
            "failure_reason": failure_reason,
        }
    )
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO admin_audit_log"
                " (session_id, facilitator_id, action, target_id, previous_value, new_value)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                session_id,
                facilitator_id,
                "tool_subscription_attempted",
                participant_id,
                None,
                subscription_value,
            )
    except Exception:
        log.warning(
            "tool_list_freshness: subscription audit INSERT failed session=%s participant=%s",
            session_id,
            participant_id,
        )


def evict_session(session_id: str) -> None:
    """Remove all registries for a session on session end."""
    keys_to_remove = [k for k in _REGISTRIES if k[0] == session_id]
    for k in keys_to_remove:
        del _REGISTRIES[k]
    if keys_to_remove:
        log.debug(
            "tool_list_freshness: evicted %d registries for session=%s",
            len(keys_to_remove),
            session_id,
        )
