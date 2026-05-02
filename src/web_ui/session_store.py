"""Server-side session-id store for the Web UI.

Audit H-02 / M-08: prior to this module the signed session cookie
carried the participant's bearer token directly. The signature blocked
forgery, but the payload was base64-readable, so anyone with cookie-jar
access (compromised endpoint, malicious browser extension, network
intercept on a downgraded link) could lift the bearer.

This store inverts the relationship: the cookie carries an opaque
session id only; the bearer (and the participant + session binding)
lives in process memory keyed by that sid. Operationally this is the
same trust boundary as the WebSocket connection manager — process-local,
lost on restart, no cross-host fan-out.

Lifecycle:
  * /login validates the bearer, calls ``create`` to mint an sid, and
    sets the cookie value to that sid (signed for integrity).
  * Every request that reads the cookie (`/me`, `/logout`, the WS
    upgrade) calls ``get`` to translate sid → entry, then re-validates
    the embedded bearer through ``AuthService.authenticate`` so
    server-side rotation/revocation still fails closed in real time.
  * /logout calls ``delete`` to drop the entry. A signed cookie that
    survives logout (e.g. preserved by a clipboard backup) cannot be
    re-used because the sid no longer maps to anything.
  * Idle entries past ``DEFAULT_TTL_SECONDS`` are purged on each access
    so a long-running process doesn't accumulate dead sessions.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass

# 8h matches COOKIE_MAX_AGE_SECONDS in auth.py. The store TTL must not
# exceed the cookie TTL; if the cookie outlived the store the user would
# get a "valid signature but unknown sid" 401 well before max-age elapsed.
DEFAULT_TTL_SECONDS = 60 * 60 * 8


@dataclass(frozen=True)
class SessionEntry:
    """One server-side session row keyed by an opaque sid."""

    sid: str
    participant_id: str
    session_id: str
    bearer: str
    created_at: float


class SessionStore:
    """In-memory sid → SessionEntry map, async-safe."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._entries: dict[str, SessionEntry] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl_seconds

    async def create(
        self,
        participant_id: str,
        session_id: str,
        bearer: str,
    ) -> str:
        """Mint a new opaque sid and store the binding. Returns the sid."""
        sid = secrets.token_urlsafe(32)
        async with self._lock:
            self._entries[sid] = SessionEntry(
                sid=sid,
                participant_id=participant_id,
                session_id=session_id,
                bearer=bearer,
                created_at=time.monotonic(),
            )
        return sid

    async def get(self, sid: str) -> SessionEntry | None:
        """Look up an sid, purging if past TTL. Missing sid returns None."""
        async with self._lock:
            entry = self._entries.get(sid)
            if entry is None:
                return None
            if time.monotonic() - entry.created_at > self._ttl:
                self._entries.pop(sid, None)
                return None
            return entry

    async def delete(self, sid: str) -> None:
        """Drop an sid; idempotent."""
        async with self._lock:
            self._entries.pop(sid, None)

    async def purge_expired(self) -> int:
        """Sweep expired entries. Returns the count purged."""
        now = time.monotonic()
        async with self._lock:
            stale = [sid for sid, e in self._entries.items() if now - e.created_at > self._ttl]
            for sid in stale:
                del self._entries[sid]
            return len(stale)

    def size(self) -> int:
        """Active entry count (test introspection)."""
        return len(self._entries)


_STORE = SessionStore()


def get_session_store() -> SessionStore:
    """Return the process-wide SessionStore singleton."""
    return _STORE
