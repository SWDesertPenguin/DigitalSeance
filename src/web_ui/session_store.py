# SPDX-License-Identifier: AGPL-3.0-or-later

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
    """One server-side session row keyed by an opaque sid.

    Spec 023 extension: ``account_id`` is populated when the sid was
    minted by the account-login flow (FR-016, research §10). The
    legacy token-paste flow leaves it as ``None``. The previously-
    required ``participant_id`` / ``session_id`` / ``bearer`` fields
    are now optional so the store can represent the "account-only"
    state minted by login but not yet rebound to a per-session
    participant.
    """

    sid: str
    participant_id: str | None
    session_id: str | None
    bearer: str | None
    created_at: float
    account_id: str | None = None


class SessionStore:
    """In-memory sid → SessionEntry map, async-safe.

    Spec 023 extension: maintains a ``_by_account`` reverse index
    mapping ``account_id → set[sid]`` so the password-change flow
    (FR-011 / clarify Q12) can enumerate every sid for an account
    and invalidate all but the actor's current one. The reverse index
    is rebuilt on :meth:`create` / :meth:`delete` and stays consistent
    with the primary entries dict.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._entries: dict[str, SessionEntry] = {}
        # Spec 023 reverse index: account_id -> set of active sids.
        self._by_account: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl_seconds

    async def create(
        self,
        participant_id: str | None = None,
        session_id: str | None = None,
        bearer: str | None = None,
        *,
        account_id: str | None = None,
    ) -> str:
        """Mint a new opaque sid and store the binding. Returns the sid.

        Legacy token-paste callers pass ``participant_id`` /
        ``session_id`` / ``bearer`` positionally. Spec 023 account-login
        callers pass ``account_id`` as a keyword arg, optionally with
        ``None`` for the participant fields if the sid is in the
        account-only pre-rebind state (research §10).
        """
        sid = secrets.token_urlsafe(32)
        entry = SessionEntry(
            sid=sid,
            participant_id=participant_id,
            session_id=session_id,
            bearer=bearer,
            created_at=time.monotonic(),
            account_id=account_id,
        )
        async with self._lock:
            self._entries[sid] = entry
            if account_id is not None:
                self._by_account.setdefault(account_id, set()).add(sid)
        return sid

    async def get(self, sid: str) -> SessionEntry | None:
        """Look up an sid, purging if past TTL. Missing sid returns None."""
        async with self._lock:
            entry = self._entries.get(sid)
            if entry is None:
                return None
            if time.monotonic() - entry.created_at > self._ttl:
                self._drop_entry_locked(sid, entry)
                return None
            return entry

    async def delete(self, sid: str) -> None:
        """Drop an sid; idempotent."""
        async with self._lock:
            entry = self._entries.pop(sid, None)
            if entry is not None and entry.account_id is not None:
                self._drop_from_account_index_locked(sid, entry.account_id)

    async def purge_expired(self) -> int:
        """Sweep expired entries. Returns the count purged."""
        now = time.monotonic()
        async with self._lock:
            stale = [
                (sid, entry)
                for sid, entry in self._entries.items()
                if now - entry.created_at > self._ttl
            ]
            for sid, entry in stale:
                self._drop_entry_locked(sid, entry)
            return len(stale)

    def size(self) -> int:
        """Active entry count (test introspection)."""
        return len(self._entries)

    async def rebind_account_session(
        self,
        *,
        sid: str,
        participant_id: str,
        session_id: str,
        bearer: str | None = None,
    ) -> bool:
        """Populate participant binding fields on an existing account sid.

        Spec 023 FR-016 + research §10: the rebind endpoint resolves an
        active session entry and writes the per-session participant
        identity into the same ``SessionEntry`` so the existing cookie
        carries through. The sid is preserved (single-sid-per-cookie
        invariant from H-02). Returns False if the sid is unknown,
        True on success.
        """
        async with self._lock:
            entry = self._entries.get(sid)
            if entry is None:
                return False
            self._entries[sid] = SessionEntry(
                sid=entry.sid,
                participant_id=participant_id,
                session_id=session_id,
                bearer=bearer if bearer is not None else entry.bearer,
                created_at=entry.created_at,
                account_id=entry.account_id,
            )
            return True

    async def get_sids_for_account(self, account_id: str) -> set[str]:
        """Return all currently-active sids minted for ``account_id``.

        FR-011 / clarify Q12: the password-change handler enumerates
        these to invalidate every other sid while preserving the
        actor's current sid. Returns an empty set when no sids are
        bound (or the account is unknown).
        """
        async with self._lock:
            return set(self._by_account.get(account_id, set()))

    async def delete_all_sids_for_account(self, account_id: str) -> int:
        """Drop every sid for ``account_id`` (FR-012 account-deletion path).

        The actor is deleting themselves, so unlike the password-change
        path there is no carve-out for the actor's current sid. Returns
        the count dropped.
        """
        dropped = 0
        async with self._lock:
            bucket = self._by_account.get(account_id, set()).copy()
            for sid in bucket:
                entry = self._entries.pop(sid, None)
                if entry is not None:
                    dropped += 1
            self._by_account.pop(account_id, None)
        return dropped

    async def delete_other_sids_for_account(
        self,
        account_id: str,
        *,
        except_sid: str,
    ) -> int:
        """Drop every sid for ``account_id`` except ``except_sid``.

        Returns the count dropped. Used by the password-change handler
        per FR-011 / clarify Q12 — the actor's current sid survives so
        their browser stays logged in; every other browser is signed
        out at the next request that consults the SessionStore.
        """
        dropped = 0
        async with self._lock:
            bucket = self._by_account.get(account_id, set()).copy()
            for sid in bucket:
                if sid == except_sid:
                    continue
                entry = self._entries.pop(sid, None)
                if entry is not None:
                    dropped += 1
                self._drop_from_account_index_locked(sid, account_id)
        return dropped

    def _drop_entry_locked(self, sid: str, entry: SessionEntry) -> None:
        """Remove an entry from both the primary dict and the reverse index.

        Caller MUST hold ``self._lock``.
        """
        self._entries.pop(sid, None)
        if entry.account_id is not None:
            self._drop_from_account_index_locked(sid, entry.account_id)

    def _drop_from_account_index_locked(self, sid: str, account_id: str) -> None:
        """Remove ``sid`` from the per-account bucket, dropping empty buckets.

        Caller MUST hold ``self._lock``.
        """
        bucket = self._by_account.get(account_id)
        if bucket is None:
            return
        bucket.discard(sid)
        if not bucket:
            del self._by_account[account_id]


_STORE = SessionStore()


def get_session_store() -> SessionStore:
    """Return the process-wide SessionStore singleton."""
    return _STORE
