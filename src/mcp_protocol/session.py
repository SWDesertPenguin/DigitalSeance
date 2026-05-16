# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-memory MCP session state. Spec 030 Phase 2, FR-020 + FR-027."""

from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime


class CapacityError(Exception):
    """Raised when the concurrent-session cap is reached."""


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class MCPSession:
    """Active MCP protocol session. In-memory only; not persisted."""

    mcp_session_id: str
    created_at: datetime
    last_activity_at: datetime
    bearer_token_hash: str
    negotiated_protocol_version: str
    bound_sacp_session_id: str | None = None
    bound_participant_id: str | None = None


class MCPSessionStore:
    """Thread-safe in-memory store for active MCP sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, MCPSession] = {}
        self._lock = threading.Lock()

    def create(
        self,
        bearer_token_hash: str,
        negotiated_protocol_version: str,
        bound_sacp_session_id: str | None = None,
        bound_participant_id: str | None = None,
    ) -> MCPSession:
        """Create and store a new MCP session. Raises CapacityError when at cap."""
        cap = int(os.environ.get("SACP_MCP_MAX_CONCURRENT_SESSIONS") or "100")
        with self._lock:
            if len(self._sessions) >= cap:
                raise CapacityError(f"concurrent session cap {cap} reached")
            session_id = secrets.token_bytes(32).hex()
            now = _utcnow()
            session = MCPSession(
                mcp_session_id=session_id,
                created_at=now,
                last_activity_at=now,
                bearer_token_hash=bearer_token_hash,
                negotiated_protocol_version=negotiated_protocol_version,
                bound_sacp_session_id=bound_sacp_session_id,
                bound_participant_id=bound_participant_id,
            )
            self._sessions[session_id] = session
            return session

    def get(self, mcp_session_id: str) -> MCPSession | None:
        """Return session by id or None if not present."""
        with self._lock:
            return self._sessions.get(mcp_session_id)

    def touch(self, mcp_session_id: str) -> None:
        """Update last_activity_at to now for the named session."""
        with self._lock:
            session = self._sessions.get(mcp_session_id)
            if session is not None:
                session.last_activity_at = _utcnow()

    def remove(self, mcp_session_id: str) -> None:
        """Remove a session from the store."""
        with self._lock:
            self._sessions.pop(mcp_session_id, None)

    def count(self) -> int:
        """Return the number of active sessions."""
        with self._lock:
            return len(self._sessions)

    def prune_expired(self, idle_timeout_s: int, max_lifetime_s: int) -> int:
        """Remove sessions that have exceeded the idle or lifetime cap.

        Returns the number of sessions removed.
        """
        now = _utcnow()
        to_remove: list[str] = []
        with self._lock:
            for sid, session in list(self._sessions.items()):
                idle_s = (now - session.last_activity_at).total_seconds()
                lifetime_s = (now - session.created_at).total_seconds()
                if idle_s > idle_timeout_s or lifetime_s > max_lifetime_s:
                    to_remove.append(sid)
            for sid in to_remove:
                del self._sessions[sid]
        return len(to_remove)


# Module-level singleton shared by the transport and handshake modules.
_store = MCPSessionStore()


def get_session_store() -> MCPSessionStore:
    """Return the module-level MCPSessionStore singleton."""
    return _store
