# SPDX-License-Identifier: AGPL-3.0-or-later

"""Cross-instance WebSocket broadcast for spec 022 (research.md §1).

Routes ``detection_event_appended`` and ``detection_event_resurfaced`` to
the orchestrator process holding the facilitator's WebSocket connection,
even when that process is different from the one initiating the
broadcast. Per Clarifications §6, spec 022 must support multi-instance
deployments on day one (rather than waiting for spec 011's eventual
Redis-backed SessionStore).

Mechanism: Postgres LISTEN/NOTIFY on a per-session channel
``detection_events_{session_id}``. Each orchestrator process maintains
the existing in-process per-session subscriber map (spec 011) AND
opens an asyncpg LISTEN connection on the same channel for any session
it currently holds a facilitator subscriber for. POST/INSERT sites call
``broadcast_session_event(...)`` which:

1. Broadcasts in-process to local subscribers (same-instance fast path).
2. Emits NOTIFY so other instances holding subscribers for the same
   session receive the payload via their LISTEN handler and rebroadcast
   in-process.

Failure modes:

- NOTIFY failure: logged at WARN; the in-process broadcast still ran
  (so single-instance deployments stay correct). The cross-instance
  contract degrades to single-instance on a Postgres connection blip.
- LISTEN connection drop: each instance reconnects on its next
  facilitator-WS bind; an in-flight NOTIFY during reconnection is
  dropped (best-effort delivery, matching spec 011's existing WS
  delivery guarantee).

Channel naming keeps fan-out bounded per session; the 8000-byte
NOTIFY payload limit is respected by truncating ``trigger_snippet`` to
1000 chars server-side before emission (per ``data-model.md`` envelope
spec).

This is the scaffold — endpoint integration lands in Sweep 2 (T015-T028).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from src.web_ui.websocket import broadcast_to_session_roles

_logger = logging.getLogger(__name__)

# NOTIFY payload size cap (Postgres limit is 8000 bytes; leave headroom
# for the JSON envelope structure around the snippet field).
NOTIFY_PAYLOAD_BYTE_LIMIT = 7000
# Snippet truncation cap applied before NOTIFY emission. Client refetches
# the full snippet via REST GET on click-expand if truncated.
SNIPPET_NOTIFY_CHAR_LIMIT = 1000

FACILITATOR_ROLES = frozenset({"facilitator"})


def _channel_for_session(session_id: str) -> str:
    """Per-session NOTIFY channel name."""
    return f"detection_events_{session_id}"


def _truncate_snippet(envelope: dict[str, Any]) -> dict[str, Any]:
    """Truncate trigger_snippet if it would push the envelope over the cap."""
    event = envelope.get("event")
    if not isinstance(event, dict):
        return envelope
    snippet = event.get("trigger_snippet")
    if not isinstance(snippet, str) or len(snippet) <= SNIPPET_NOTIFY_CHAR_LIMIT:
        event["trigger_snippet_truncated"] = False
        return envelope
    event["trigger_snippet"] = snippet[:SNIPPET_NOTIFY_CHAR_LIMIT]
    event["trigger_snippet_truncated"] = True
    return envelope


async def broadcast_session_event(
    session_id: str,
    envelope: dict[str, Any],
    *,
    pool: asyncpg.Pool | None = None,
) -> None:
    """Broadcast a detection-event payload to facilitator WS subscribers.

    Same-instance subscribers receive the event via the existing
    ``broadcast_to_session_roles`` helper. Cross-instance delivery uses
    Postgres NOTIFY on the per-session channel; receiving instances'
    LISTEN handlers rebroadcast in-process (see
    ``listen_for_session_events``).

    The ``pool`` is the orchestrator's asyncpg pool. When omitted (e.g.,
    in tests without a DB), only the in-process broadcast runs and the
    cross-instance NOTIFY is skipped with a DEBUG log.
    """
    envelope = _truncate_snippet(envelope)
    await broadcast_to_session_roles(session_id, envelope, allow_roles=FACILITATOR_ROLES)
    if pool is None:
        _logger.debug(
            "cross_instance_broadcast.skip_notify_no_pool",
            extra={"session_id": session_id},
        )
        return
    await _emit_notify(pool, session_id, envelope)


async def _emit_notify(
    pool: asyncpg.Pool,
    session_id: str,
    envelope: dict[str, Any],
) -> None:
    """Emit a Postgres NOTIFY on the per-session channel."""
    payload = json.dumps(envelope, separators=(",", ":"))
    if len(payload.encode("utf-8")) > NOTIFY_PAYLOAD_BYTE_LIMIT:
        _logger.warning(
            "cross_instance_broadcast.payload_over_limit",
            extra={"session_id": session_id, "bytes": len(payload)},
        )
        return
    channel = _channel_for_session(session_id)
    try:
        async with pool.acquire() as conn:
            # asyncpg requires a literal channel name (no parameter binding)
            # but we control the channel string entirely (no user input).
            quoted_payload = payload.replace("'", "''")
            await conn.execute(f"NOTIFY {channel}, '{quoted_payload}'")
    except Exception:  # noqa: BLE001 — NOTIFY failure must not block local broadcast
        _logger.warning(
            "cross_instance_broadcast.notify_failed",
            extra={"session_id": session_id},
            exc_info=True,
        )


async def listen_for_session_events(
    pool: asyncpg.Pool,
    session_id: str,
) -> None:
    """Open a LISTEN connection for a session's detection-event channel.

    Called when a facilitator's WebSocket binds to this instance. The
    callback rebroadcasts received NOTIFY payloads to local facilitator
    subscribers via ``broadcast_to_session_roles`` so a re-surface POST
    on a different instance lands on this instance's facilitator WS.

    The caller owns the returned connection; close it on facilitator
    unbind to free the LISTEN slot. Re-entry on the same session_id
    creates a separate listener; the manager-side de-dup is the caller's
    responsibility.

    This is the scaffold — actual LISTEN-connection lifecycle management
    (open on first facilitator bind, close on last unbind) lands in
    Sweep 2's endpoint integration. The function shape lets tests
    exercise the rebroadcast contract today.
    """
    channel = _channel_for_session(session_id)

    async def _on_notify(
        _connection: asyncpg.Connection,
        _pid: int,
        _channel: str,
        payload: str,
    ) -> None:
        try:
            envelope = json.loads(payload)
        except json.JSONDecodeError:
            _logger.warning(
                "cross_instance_broadcast.malformed_notify",
                extra={"session_id": session_id, "payload_head": payload[:80]},
            )
            return
        await broadcast_to_session_roles(session_id, envelope, allow_roles=FACILITATOR_ROLES)

    conn = await pool.acquire()
    await conn.add_listener(channel, _on_notify)
    _logger.debug(
        "cross_instance_broadcast.listen_started",
        extra={"session_id": session_id, "channel": channel},
    )
