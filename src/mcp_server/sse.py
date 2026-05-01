"""SSE connection manager — per-session asyncio.Queue fan-out.

Phase 2 note: the MCP app (port 8750) and the Web UI app (port 8751)
run in the same process (src/run_apps.py) and MUST share a single
ConnectionManager instance so that a turn broadcast on the MCP side
reaches Web UI WebSocket subscribers. The module-level singleton
``CONN_MANAGER`` is that shared instance.
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)

# Per-subscriber queue depth cap (006 §FR-013 / CHK029). A slow consumer
# that stops reading has its queue overflow handled by put_nowait + drop —
# the broadcast does not block on a wedged client. 256 events is roughly
# 30 minutes of typical session turn activity at the cruise floor.
QUEUE_MAXSIZE = 256


class ConnectionManager:
    """Manage SSE subscriber queues per session.

    Each connected client gets its own bounded asyncio.Queue. When a turn
    completes the loop calls broadcast() and every queue receives the event
    dict via put_nowait — a slow consumer that fills its queue is dropped
    silently rather than blocking the broadcast loop.
    """

    def __init__(self, queue_maxsize: int = QUEUE_MAXSIZE) -> None:
        self._queues: dict[str, set[asyncio.Queue[dict]]] = {}
        self._maxsize = queue_maxsize

    def subscriber_count(self, session_id: str) -> int:
        """Current subscriber count for a session (for cap enforcement)."""
        return len(self._queues.get(session_id, set()))

    async def subscribe(self, session_id: str) -> asyncio.Queue[dict]:
        """Register a new subscriber and return its queue."""
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=self._maxsize)
        self._queues.setdefault(session_id, set()).add(q)
        count = len(self._queues[session_id])
        log.debug("SSE subscriber added for session %s (%d total)", session_id, count)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue[dict]) -> None:
        """Remove a subscriber queue."""
        queues = self._queues.get(session_id)
        if queues:
            queues.discard(q)
            if not queues:
                del self._queues[session_id]
        log.debug("SSE subscriber removed for session %s", session_id)

    async def broadcast(self, session_id: str, event: dict) -> None:
        """Push an event to all subscribers for a session.

        Uses put_nowait so a slow consumer cannot back-pressure the loop —
        a full queue means the consumer is wedged; we drop the event for
        them and continue. The dropped consumer will see stale state and
        should reconnect (the client triggers a state_snapshot resync on
        reconnect per 011 §FR-005).
        """
        queues = self._queues.get(session_id, set())
        if not queues:
            return
        dropped = 0
        for q in list(queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dropped += 1
        if dropped:
            log.warning(
                "SSE broadcast dropped event for %d wedged consumer(s) on session %s",
                dropped,
                session_id,
            )
        log.debug("SSE broadcast to %d subscriber(s) for session %s", len(queues), session_id)


CONN_MANAGER = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Return the process-wide shared ConnectionManager instance."""
    return CONN_MANAGER
