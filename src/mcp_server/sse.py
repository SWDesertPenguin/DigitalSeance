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


class ConnectionManager:
    """Manage SSE subscriber queues per session.

    Each connected client gets its own asyncio.Queue. When a turn completes
    the loop calls broadcast() and every queue receives the event dict.
    """

    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[dict]]] = {}

    async def subscribe(self, session_id: str) -> asyncio.Queue[dict]:
        """Register a new subscriber and return its queue."""
        q: asyncio.Queue[dict] = asyncio.Queue()
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
        """Push an event to all subscribers for a session."""
        queues = self._queues.get(session_id, set())
        if not queues:
            return
        for q in list(queues):
            await q.put(event)
        log.debug("SSE broadcast to %d subscriber(s) for session %s", len(queues), session_id)


CONN_MANAGER = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Return the process-wide shared ConnectionManager instance."""
    return CONN_MANAGER
