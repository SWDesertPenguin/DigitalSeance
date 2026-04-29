"""Per-participant rate limiting for MCP tool calls."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import HTTPException

DEFAULT_LIMIT = 60
DEFAULT_WINDOW = 60  # seconds
# Hard cap on the bucket map to prevent cardinality-attack memory exhaustion
# (009 §FR-007 / CHK003-CHK004). Above this threshold a check() call lazily
# evicts buckets whose newest timestamp is older than 2*window — those
# participants are not actively rate-limited so dropping their bucket is safe.
DEFAULT_MAX_BUCKETS = 10_000


@dataclass
class _TokenBucket:
    """Sliding window counter for one participant."""

    timestamps: list[float] = field(default_factory=list)


class RateLimiter:
    """In-memory per-participant rate limiter."""

    def __init__(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        window: int = DEFAULT_WINDOW,
        max_buckets: int = DEFAULT_MAX_BUCKETS,
    ) -> None:
        self._limit = limit
        self._window = window
        self._max_buckets = max_buckets
        self._buckets: dict[str, _TokenBucket] = defaultdict(_TokenBucket)

    def check(self, participant_id: str) -> None:
        """Raise HTTPException(429) if rate limit exceeded.

        check() is synchronous and contains no await points, so under
        CPython's single-threaded event loop the read-prune-append sequence
        runs atomically per call — no inter-task interleaving is possible
        between the limit check and the timestamp append. (009 §FR-008.)
        """
        now = time.monotonic()
        if len(self._buckets) >= self._max_buckets:
            self._evict_stale(now)
        bucket = self._buckets[participant_id]
        _prune_old(bucket, now, self._window)
        if len(bucket.timestamps) >= self._limit:
            retry_after = _retry_after(bucket, now, self._window)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.timestamps.append(now)

    def forget(self, participant_id: str) -> None:
        """Drop a participant's bucket. Called on participant removal so the
        per-participant counter map doesn't accumulate dead entries (CHK013).
        """
        self._buckets.pop(participant_id, None)

    def _evict_stale(self, now: float) -> None:
        """Drop buckets whose newest timestamp is older than 2*window.

        Such participants haven't made a recent request — their bucket is
        rate-limit-irrelevant and consumes memory only.
        """
        cutoff = now - 2 * self._window
        stale = [
            pid
            for pid, bucket in self._buckets.items()
            if not bucket.timestamps or max(bucket.timestamps) < cutoff
        ]
        for pid in stale:
            self._buckets.pop(pid, None)


def _prune_old(
    bucket: _TokenBucket,
    now: float,
    window: int,
) -> None:
    """Remove timestamps older than the window."""
    cutoff = now - window
    bucket.timestamps = [t for t in bucket.timestamps if t > cutoff]


def _retry_after(
    bucket: _TokenBucket,
    now: float,
    window: int,
) -> int:
    """Compute seconds until the oldest entry expires."""
    if not bucket.timestamps:
        return 0
    oldest = min(bucket.timestamps)
    return max(1, int((oldest + window) - now))
