# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-instance LRU cache for JWT validation results. Spec 030 Phase 4 FR-094."""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict


def _cache_ttl() -> int:
    val = os.environ.get("SACP_MCP_TOKEN_CACHE_TTL_SECONDS", "5")
    try:
        return max(1, min(30, int(val)))
    except (ValueError, TypeError):
        return 5


_MAX_ENTRIES = 4096


class _TokenCache:
    def __init__(self) -> None:
        self._valid: OrderedDict[str, float] = OrderedDict()
        self._revoked: set[str] = set()
        self._lock = threading.Lock()

    def is_revoked(self, jti: str) -> bool | None:
        with self._lock:
            if jti in self._revoked:
                return True
            if jti in self._valid:
                issued_at = self._valid[jti]
                ttl = _cache_ttl()
                if time.monotonic() - issued_at <= ttl:
                    self._valid.move_to_end(jti)
                    return False
                del self._valid[jti]
        return None

    def mark_valid(self, jti: str) -> None:
        with self._lock:
            self._valid[jti] = time.monotonic()
            self._valid.move_to_end(jti)
            while len(self._valid) > _MAX_ENTRIES:
                self._valid.popitem(last=False)

    def mark_revoked(self, jti: str) -> None:
        with self._lock:
            self._revoked.add(jti)
            self._valid.pop(jti, None)

    def invalidate(self, jti: str) -> None:
        with self._lock:
            self._valid.pop(jti, None)
            self._revoked.discard(jti)


_cache = _TokenCache()


def is_revoked(jti: str) -> bool | None:
    """None means not cached; caller must query DB."""
    return _cache.is_revoked(jti)


def mark_valid(jti: str) -> None:
    _cache.mark_valid(jti)


def mark_revoked(jti: str) -> None:
    _cache.mark_revoked(jti)


def invalidate(jti: str) -> None:
    _cache.invalidate(jti)
