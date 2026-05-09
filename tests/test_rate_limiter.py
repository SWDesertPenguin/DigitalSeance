# SPDX-License-Identifier: AGPL-3.0-or-later

"""Rate limiting tests — per-participant request throttling."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.mcp_server.rate_limiter import RateLimiter


def test_within_limit_passes() -> None:
    """Requests within limit succeed."""
    limiter = RateLimiter(limit=10, window=60)
    for _ in range(10):
        limiter.check("participant-a")


def test_exceeds_limit_raises_429() -> None:
    """Request over limit raises 429."""
    limiter = RateLimiter(limit=3, window=60)
    limiter.check("participant-a")
    limiter.check("participant-a")
    limiter.check("participant-a")
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("participant-a")
    assert exc_info.value.status_code == 429


def test_per_participant_isolation() -> None:
    """One participant's limit doesn't affect another."""
    limiter = RateLimiter(limit=2, window=60)
    limiter.check("participant-a")
    limiter.check("participant-a")
    # A is at limit, but B should still work
    limiter.check("participant-b")


def test_429_includes_retry_after() -> None:
    """429 response includes Retry-After header."""
    limiter = RateLimiter(limit=1, window=60)
    limiter.check("participant-a")
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("participant-a")
    assert "Retry-After" in exc_info.value.headers


def test_forget_clears_bucket() -> None:
    """forget() drops the per-participant counter so future requests start fresh."""
    limiter = RateLimiter(limit=2, window=60)
    limiter.check("participant-a")
    limiter.check("participant-a")
    limiter.forget("participant-a")
    # After forget the bucket starts empty again
    limiter.check("participant-a")
    limiter.check("participant-a")


def test_forget_unknown_id_is_noop() -> None:
    """forget() on an unknown participant does not raise."""
    limiter = RateLimiter(limit=2, window=60)
    limiter.forget("never-seen")


def test_evicts_stale_buckets_when_over_cap() -> None:
    """At cap, buckets older than 2*window are evicted to make room."""
    import time

    limiter = RateLimiter(limit=10, window=1, max_buckets=3)
    limiter.check("a")
    limiter.check("b")
    # Force bucket a's timestamp to be older than 2*window so it's eligible for eviction
    limiter._buckets["a"].timestamps = [time.monotonic() - 10]
    limiter._buckets["b"].timestamps = [time.monotonic() - 10]
    # Cap = 3, currently 2 buckets. Adding "c" hits cap on the next call.
    limiter.check("c")
    limiter.check("d")  # at cap before insert -> stale eviction kicks in
    # "a" and "b" should have been evicted (timestamps were older than 2*window)
    assert "a" not in limiter._buckets
    assert "b" not in limiter._buckets
    assert "c" in limiter._buckets
    assert "d" in limiter._buckets
