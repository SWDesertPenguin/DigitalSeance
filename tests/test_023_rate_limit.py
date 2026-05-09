# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 LoginRateLimiter unit tests (T030).

Covers threshold enforcement (``check`` raises when count exceeds
``SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN``), the sliding-window
eviction (entries older than 60s drop out), per-IP isolation
(separate deques per IP), the Retry-After hint, and the LRU-style
key-cap eviction. The cross-spec independence from spec 019's
limiter (clarify Q10) is asserted as "no shared module-level state"
by checking the limiter's state container is process-local to the
class.
"""

from __future__ import annotations

import pytest

from src.accounts.rate_limit import LoginRateLimiter, RateLimitExceeded


class _Clock:
    """Controllable monotonic clock for deterministic window tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ---------------------------------------------------------------------------
# Threshold enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_below_threshold_admits_quietly() -> None:
    """Calls below the threshold do not raise."""
    limiter = LoginRateLimiter(threshold=3)
    for _ in range(3):
        await limiter.check("10.0.0.1")  # all three admit


@pytest.mark.asyncio
async def test_exactly_above_threshold_raises_with_retry_after() -> None:
    """The N+1 call within the window raises RateLimitExceeded."""
    clock = _Clock()
    limiter = LoginRateLimiter(threshold=3, time_source=clock)
    for _ in range(3):
        await limiter.check("10.0.0.1")
    with pytest.raises(RateLimitExceeded) as exc:
        await limiter.check("10.0.0.1")
    # The window is 60s; oldest timestamp is at clock.now=1000;
    # retry_after rounds up to 60 (oldest drops at 1060).
    assert exc.value.retry_after_seconds == 60


@pytest.mark.asyncio
async def test_retry_after_reflects_oldest_dropping_out() -> None:
    """As the window slides, retry_after shortens to match oldest drop time."""
    clock = _Clock()
    limiter = LoginRateLimiter(threshold=2, time_source=clock)
    await limiter.check("10.0.0.1")  # t=0 (oldest)
    clock.advance(15)
    await limiter.check("10.0.0.1")  # t=15
    clock.advance(15)
    # Now t=30, window starts at t=-30 (everything still in window).
    # Threshold=2; the third call raises with retry_after = 60 - (30-0) = 30.
    with pytest.raises(RateLimitExceeded) as exc:
        await limiter.check("10.0.0.1")
    assert exc.value.retry_after_seconds == 30


# ---------------------------------------------------------------------------
# Sliding-window eviction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_old_timestamps_drop_after_window() -> None:
    """Timestamps older than 60s no longer count toward the threshold."""
    clock = _Clock()
    limiter = LoginRateLimiter(threshold=2, time_source=clock)
    await limiter.check("10.0.0.1")  # t=0
    await limiter.check("10.0.0.1")  # t=0 — at threshold
    clock.advance(61)  # window expires
    await limiter.check("10.0.0.1")  # t=61 — old entries dropped


@pytest.mark.asyncio
async def test_partial_window_eviction() -> None:
    """Only entries older than the window are dropped; recent ones survive."""
    clock = _Clock()
    limiter = LoginRateLimiter(threshold=3, time_source=clock)
    await limiter.check("10.0.0.1")  # t=0
    clock.advance(30)
    await limiter.check("10.0.0.1")  # t=30
    clock.advance(31)
    # t=61: t=0 entry is older than 60s and drops; t=30 stays.
    # Window contains [t=30, t=61].
    await limiter.check("10.0.0.1")  # t=61 (count=2 after eviction + append)
    # The fourth call within the live window raises (count would be 3 + 1 = 4 > 3? no)
    # Actually: after eviction, only [t=30] remains. After append: [t=30, t=61].
    # So we still have headroom — let's confirm the next call goes through.
    await limiter.check("10.0.0.1")  # t=61 — count=3, at threshold
    with pytest.raises(RateLimitExceeded):
        await limiter.check("10.0.0.1")  # t=61 — count=4, raises


# ---------------------------------------------------------------------------
# Per-IP isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_ip_isolation() -> None:
    """Two different IPs each get their own threshold budget."""
    limiter = LoginRateLimiter(threshold=2)
    await limiter.check("10.0.0.1")
    await limiter.check("10.0.0.1")
    # ip2 still has its full budget.
    await limiter.check("10.0.0.2")
    await limiter.check("10.0.0.2")
    # Both at threshold; both raise on next call.
    with pytest.raises(RateLimitExceeded):
        await limiter.check("10.0.0.1")
    with pytest.raises(RateLimitExceeded):
        await limiter.check("10.0.0.2")


# ---------------------------------------------------------------------------
# Env-var threshold sourcing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_threshold_sources_from_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default-constructed limiter reads SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN."""
    monkeypatch.setenv("SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN", "5")
    limiter = LoginRateLimiter()
    assert limiter.threshold == 5


@pytest.mark.asyncio
async def test_threshold_falls_back_to_default_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty env var falls back to the contracts/env-vars.md default of 10."""
    monkeypatch.delenv("SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN", raising=False)
    limiter = LoginRateLimiter()
    assert limiter.threshold == 10


# ---------------------------------------------------------------------------
# Key-cap eviction (v1-pragmatic LRU)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oldest_key_evicted_at_max_keys() -> None:
    """When the dict hits max_keys, the oldest insertion is evicted."""
    limiter = LoginRateLimiter(threshold=10, max_keys=3)
    await limiter.check("ip1")
    await limiter.check("ip2")
    await limiter.check("ip3")
    assert limiter.size() == 3
    # The 4th distinct IP triggers eviction of ip1 (oldest insertion).
    await limiter.check("ip4")
    assert limiter.size() == 3
    assert "ip1" not in limiter._state  # noqa: SLF001
    assert "ip4" in limiter._state  # noqa: SLF001


# ---------------------------------------------------------------------------
# Independence from spec 019's middleware (clarify Q10)
# ---------------------------------------------------------------------------


def test_limiter_state_is_instance_local() -> None:
    """Each LoginRateLimiter instance owns its own state — no module-level shared dict.

    Spec 019's middleware lives in src/middleware/network_rate_limit.py;
    this limiter's deque-per-IP state must NOT alias that middleware's
    counter state. Two LoginRateLimiter instances also do not share
    state with each other.
    """
    a = LoginRateLimiter(threshold=2)
    b = LoginRateLimiter(threshold=2)
    assert a._state is not b._state  # noqa: SLF001
