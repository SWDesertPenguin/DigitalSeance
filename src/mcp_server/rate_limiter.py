"""Per-participant rate limiting for MCP tool calls."""

from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field

from fastapi import HTTPException

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 60
DEFAULT_WINDOW = 60  # seconds
# Hard cap on the bucket map to prevent cardinality-attack memory exhaustion
# (009 §FR-007 / CHK003-CHK004). Above this threshold a check() call lazily
# evicts buckets whose newest timestamp is older than 2*window — those
# participants are not actively rate-limited so dropping their bucket is safe.
DEFAULT_MAX_BUCKETS = 10_000

# 009 §FR-013: eviction sweep MUST run at most once per second per process.
_SWEEP_MIN_INTERVAL = 1.0
# 009 §FR-012: aggregate 429 counter is a 60-second rolling window.
_AGG_429_WINDOW = 60.0


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
        # 009 §FR-012: per-participant 429 counter; queryable from structured logs.
        self.rate_limit_429_total: Counter[str] = Counter()
        # Aggregate 429 timestamps backing rate_limit_429_per_minute_total.
        self._429_aggregate_timestamps: deque[float] = deque()
        # 009 §FR-013: monotonic timestamp of the most recent eviction sweep.
        self._last_sweep_ts: float = 0.0
        # Duration of the most recent eviction sweep in milliseconds.
        self.rate_limit_eviction_sweep_ms: float = 0.0

    @property
    def rate_limit_429_per_minute_total(self) -> int:
        """Aggregate 429 count over the trailing 60s window (009 §FR-012)."""
        now = time.monotonic()
        cutoff = now - _AGG_429_WINDOW
        while self._429_aggregate_timestamps and self._429_aggregate_timestamps[0] < cutoff:
            self._429_aggregate_timestamps.popleft()
        return len(self._429_aggregate_timestamps)

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
            self.rate_limit_429_total[participant_id] += 1
            self._429_aggregate_timestamps.append(now)
            logger.info(
                "rate_limit_429",
                extra={
                    "participant_id": participant_id,
                    "rate_limit_429_total": self.rate_limit_429_total[participant_id],
                    "rate_limit_429_per_minute_total": len(self._429_aggregate_timestamps),
                },
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.timestamps.append(now)

    def forget(self, participant_id: str) -> None:
        """Drop a participant's bucket and 429 counter.

        Called on participant removal so the per-participant counter map
        doesn't accumulate dead entries (CHK013). The counter mirrors the
        bucket-map invariant: active participants only.
        """
        self._buckets.pop(participant_id, None)
        self.rate_limit_429_total.pop(participant_id, None)

    def _evict_stale(self, now: float) -> None:
        """Drop buckets whose newest timestamp is older than 2*window.

        Throttled to at most once per second per 009 §FR-013 — repeated
        triggers within the same second short-circuit because the most
        recent sweep already cleared the cap-eligible entries. Sweep
        duration is captured as ``rate_limit_eviction_sweep_ms``.
        """
        if now - self._last_sweep_ts < _SWEEP_MIN_INTERVAL:
            return
        sweep_start = time.monotonic()
        cutoff = now - 2 * self._window
        stale = [
            pid
            for pid, bucket in self._buckets.items()
            if not bucket.timestamps or max(bucket.timestamps) < cutoff
        ]
        for pid in stale:
            self._buckets.pop(pid, None)
        self._last_sweep_ts = now
        self.rate_limit_eviction_sweep_ms = (time.monotonic() - sweep_start) * 1000.0
        logger.debug(
            "rate_limit_eviction_sweep",
            extra={
                "rate_limit_eviction_sweep_ms": self.rate_limit_eviction_sweep_ms,
                "buckets_evicted": len(stale),
                "buckets_remaining": len(self._buckets),
            },
        )


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
