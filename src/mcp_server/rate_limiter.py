"""Per-participant rate limiting for MCP tool calls."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import HTTPException

DEFAULT_LIMIT = 60
DEFAULT_WINDOW = 60  # seconds


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
    ) -> None:
        self._limit = limit
        self._window = window
        self._buckets: dict[str, _TokenBucket] = defaultdict(_TokenBucket)

    def check(self, participant_id: str) -> None:
        """Raise HTTPException(429) if rate limit exceeded."""
        now = time.monotonic()
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
