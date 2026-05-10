# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-IP login rate limiter for spec 023 (FR-015, clarify Q10).

Sliding-window deque per IP with a 60-second window and a threshold
sourced from ``SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN``. State is
process-local and intentionally separate from the spec 019 middleware
limiter — the two limiters apply additively per the clarify ruling.

Each ``check(ip)`` call appends the current monotonic timestamp to the
deque for that IP, evicts entries older than the window, and raises
:class:`RateLimitExceeded` (carrying ``retry_after_seconds``) when the
remaining count meets or exceeds the threshold. The window is
sliding: the retry-after hint reflects when the OLDEST timestamp in
the current window will fall out, not a fixed bucket boundary.

State eviction caps memory at a quarter of
``SACP_NETWORK_RATELIMIT_MAX_KEYS`` (a v1-pragmatic ceiling
documented in research §5; a follow-up spec can promote this to a
dedicated env var). When the dict grows past the ceiling, the
least-recently-touched IP is dropped.

See ``specs/023-user-accounts/research.md`` §5 for the algorithm
choice and additive-composition rationale.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from collections import deque
from collections.abc import Callable

log = logging.getLogger(__name__)

_WINDOW_SECONDS = 60.0
# Default per-IP threshold per contracts/env-vars.md.
_DEFAULT_THRESHOLD = 10
# Default network-rate-limit max keys ceiling (spec 019); 1/4 of that
# becomes our v1-pragmatic per-IP-key cap. Promoted to a dedicated var
# in a follow-up spec per research §5.
_DEFAULT_NETWORK_MAX_KEYS = 10000
_PER_IP_KEY_CEILING_FACTOR = 4


class RateLimitExceeded(Exception):  # noqa: N818 — name is part of the public service-layer contract
    """Raised when a per-IP login attempt count exceeds the configured threshold.

    The ``retry_after_seconds`` attribute carries the integer seconds
    the caller should send back via the HTTP ``Retry-After`` header
    on the 429 response.
    """

    def __init__(self, *, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"login rate limit exceeded; retry_after_seconds={retry_after_seconds}")


def _read_int_env(name: str, default: int) -> int:
    """Parse an int env var, falling back to ``default`` on empty / unset."""
    raw = os.environ.get(name, "")
    if raw == "":
        return default
    return int(raw)


class LoginRateLimiter:
    """Sliding-window per-IP login rate limiter.

    Construction reads the threshold and key-cap once; subsequent
    :meth:`check` calls compare against those values. Threshold can
    be overridden per-instance for tests via the constructor argument.
    """

    def __init__(
        self,
        *,
        threshold: int | None = None,
        window_seconds: float = _WINDOW_SECONDS,
        max_keys: int | None = None,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        self._threshold = (
            threshold
            if threshold is not None
            else _read_int_env(
                "SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN",
                _DEFAULT_THRESHOLD,
            )
        )
        self._window = window_seconds
        self._max_keys = (
            max_keys
            if max_keys is not None
            else _read_int_env(
                "SACP_NETWORK_RATELIMIT_MAX_KEYS",
                _DEFAULT_NETWORK_MAX_KEYS,
            )
            // _PER_IP_KEY_CEILING_FACTOR
        )
        # Monotonic clock by default; tests inject a controllable source.
        self._now = time_source if time_source is not None else _monotonic
        self._state: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    @property
    def threshold(self) -> int:
        return self._threshold

    async def check(self, ip: str) -> None:
        """Append a timestamp for ``ip`` and raise if the threshold is reached.

        The window slides — entries older than ``self._window`` are
        dropped on every call. After the append, if the resulting deque
        length is GREATER than the threshold, raise
        :class:`RateLimitExceeded` with the seconds-until-oldest-drops
        as the ``retry_after`` hint.

        Filters per memory ``feedback_exclude_humans_from_dispatch`` do
        NOT apply here — this limiter is dispatch-adjacent (gates the
        login + create-account endpoints) but does not iterate over
        participants. The IP is the sole keying axis.
        """
        now = self._now()
        async with self._lock:
            self._evict_oldest_key_if_full()
            window = self._state.setdefault(ip, deque())
            self._evict_old_timestamps(window, now)
            window.append(now)
            if len(window) > self._threshold:
                # The oldest timestamp dropping out of the window is
                # when the next attempt becomes admittable. Round up
                # so the client doesn't retry one clock-tick early.
                seconds_until_oldest_drops = self._window - (now - window[0])
                retry_after = max(1, math.ceil(seconds_until_oldest_drops))
                raise RateLimitExceeded(retry_after_seconds=retry_after)

    def _evict_old_timestamps(self, window: deque[float], now: float) -> None:
        cutoff = now - self._window
        while window and window[0] < cutoff:
            window.popleft()

    def _evict_oldest_key_if_full(self) -> None:
        """Drop the least-recently-inserted key when the dict ceiling is hit.

        ``dict`` preserves insertion order; ``next(iter(self._state))``
        is the oldest key. This is a v1-pragmatic eviction policy; a
        true LRU could land in a follow-up spec if metrics show
        eviction churn.
        """
        if len(self._state) >= self._max_keys:
            oldest = next(iter(self._state))
            del self._state[oldest]
            log.debug(
                "LoginRateLimiter evicted oldest IP key %s (max_keys=%d reached)",
                oldest,
                self._max_keys,
            )

    def size(self) -> int:
        """Active IP-key count (test introspection)."""
        return len(self._state)


def _monotonic() -> float:
    """Wrapper so tests can monkeypatch the time source via the constructor."""
    import time as _time

    return _time.monotonic()
