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
