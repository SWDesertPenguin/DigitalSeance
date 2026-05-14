# SPDX-License-Identifier: AGPL-3.0-or-later

"""009 rate-limiting testability suite (Phase F, fix/009-followups).

Covers audit-plan items not addressed by ``test_rate_limiter.py``:

* FR-007 cardinality cap: 10,001st distinct participant triggers eviction
* FR-007 eviction selects only stale buckets (newest ts older than 2x window)
* FR-008 single-threaded atomicity smoke under asyncio gather
* FR-009 token rotation does not reset the bucket (participant_id keying)
* FR-010 health-check / unauthenticated endpoints bypass the limiter
* SC-004 / FR-002 429 response body shape (no internal state leaked)
* FR-012 429-counter capture (deferred trigger marker)
* FR-013 sweep rate-limit (deferred trigger marker)
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import HTTPException

from src.participant_api import rate_limiter as rate_limiter_module
from src.participant_api.rate_limiter import (
    DEFAULT_MAX_BUCKETS,
    RateLimiter,
)

# ---------------------------------------------------------------------------
# FR-007: cardinality cap + eviction
# ---------------------------------------------------------------------------


def test_fr007_eviction_triggers_at_cap_with_stale_buckets() -> None:
    """At cap, the next check() lazily evicts buckets older than 2x window."""
    cap = 50
    window = 1
    limiter = RateLimiter(limit=10, window=window, max_buckets=cap)
    # Fill to cap with timestamps that are already stale (older than 2x window).
    stale_now = time.monotonic() - 5
    for i in range(cap):
        bucket = limiter._buckets[f"stale-{i}"]
        bucket.timestamps = [stale_now]
    assert len(limiter._buckets) == cap
    # Adding the next participant trips the eviction sweep on entry.
    limiter.check("fresh-1")
    # All stale buckets must be gone; only the fresh participant's bucket remains.
    assert all(not pid.startswith("stale-") for pid in limiter._buckets)
    assert "fresh-1" in limiter._buckets


def test_fr007_eviction_skips_recent_buckets() -> None:
    """Eviction only drops stale buckets — recent buckets survive even at cap."""
    cap = 10
    window = 1
    limiter = RateLimiter(limit=10, window=window, max_buckets=cap)
    now = time.monotonic()
    # Half stale (older than 2x window), half recent.
    for i in range(5):
        limiter._buckets[f"stale-{i}"].timestamps = [now - 5]
    for i in range(5):
        limiter._buckets[f"recent-{i}"].timestamps = [now - 0.2]
    limiter.check("incoming-1")
    # All 5 stale evicted; all 5 recent survive; incoming added.
    surviving = set(limiter._buckets)
    assert {f"recent-{i}" for i in range(5)}.issubset(surviving)
    assert "incoming-1" in surviving
    assert not any(p.startswith("stale-") for p in surviving)


def test_fr007_default_max_buckets_constant() -> None:
    """The cardinality cap default is the documented 10000."""
    assert DEFAULT_MAX_BUCKETS == 10_000


# ---------------------------------------------------------------------------
# FR-008: single-threaded atomicity smoke under asyncio gather
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fr008_concurrent_check_atomicity_under_asyncio() -> None:
    """Concurrent check() calls in one event loop never exceed the limit.

    check() has no await points, so under CPython's single-threaded asyncio
    scheduler the read-prune-append sequence is atomic per call. This test
    fires 100 concurrent check() coroutines for one participant against a
    limit of 50 — exactly 50 must succeed and 50 must raise 429.
    """
    limiter = RateLimiter(limit=50, window=60)
    success = 0
    rejected = 0

    async def one_call() -> None:
        nonlocal success, rejected
        try:
            limiter.check("p-1")
            success += 1
        except HTTPException as e:
            assert e.status_code == 429
            rejected += 1

    await asyncio.gather(*(one_call() for _ in range(100)))
    assert success == 50
    assert rejected == 50


# ---------------------------------------------------------------------------
# FR-009: token rotation does NOT reset the bucket
# ---------------------------------------------------------------------------


def test_fr009_bucket_persists_across_token_rotation() -> None:
    """Bucket is keyed by participant_id, not token — rotation cannot reset.

    The rate limiter never sees the token; check() takes participant_id only.
    Simulating a rotation event is therefore a no-op against the bucket map,
    which is the property under test: a rotated token cannot circumvent the
    window because the bucket key is participant.id (FR-004 / FR-009).
    """
    limiter = RateLimiter(limit=3, window=60)
    limiter.check("p-1")
    limiter.check("p-1")
    limiter.check("p-1")
    # Simulate post-rotation request: same participant_id, fresh token.
    # The bucket survives the rotation event entirely — next check() raises.
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("p-1")
    assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# FR-010: health-check exemption (structural, exercised via middleware path)
# ---------------------------------------------------------------------------


def test_fr010_limiter_only_invoked_via_authenticated_dependency() -> None:
    """Rate limiting is gated on get_current_participant — unauth paths bypass.

    The limiter is invoked exclusively from get_current_participant in
    src/participant_api/middleware.py. Endpoints that do NOT depend on
    get_current_participant (/healthz, /docs, /openapi.json,
    /redoc, the login surface) bypass the limiter by construction.
    This test pins the integration shape: any change that calls
    limiter.check from another middleware layer would surface here.
    """
    import inspect

    from src.participant_api import middleware

    src = inspect.getsource(middleware)
    # Exactly one call site for limiter.check; it lives inside
    # get_current_participant. Adding another call site must be a deliberate
    # spec change — the test forces the conversation.
    assert src.count("limiter.check(") == 1
    # The call site is the post-auth path.
    get_current_src = inspect.getsource(middleware.get_current_participant)
    assert "limiter.check(participant.id)" in get_current_src


# ---------------------------------------------------------------------------
# SC-004 / FR-002: 429 response body shape — no internal state leaked
# ---------------------------------------------------------------------------


def test_sc004_429_body_shape_no_internal_state() -> None:
    """429 body is exactly {'detail': 'Rate limit exceeded'} — no counter leak."""
    limiter = RateLimiter(limit=1, window=60)
    limiter.check("p-1")
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("p-1")
    exc = exc_info.value
    assert exc.status_code == 429
    assert exc.detail == "Rate limit exceeded"
    # No participant id, count, or window length anywhere in the detail.
    detail_str = str(exc.detail)
    for forbidden in ("p-1", "60", "limit=", "count=", "bucket"):
        assert forbidden not in detail_str
    # Retry-After is the only timing channel.
    assert "Retry-After" in exc.headers
    # Retry-After is RFC 7231 delta-seconds (integer string, no units).
    assert exc.headers["Retry-After"].isdigit()


def test_sc004_retry_after_is_seconds_until_oldest_expires() -> None:
    """Retry-After encodes seconds-until-oldest-expires, not the full window."""
    window = 60
    limiter = RateLimiter(limit=1, window=window)
    limiter.check("p-1")
    # Backdate the oldest timestamp by 30s so half the window is gone.
    limiter._buckets["p-1"].timestamps = [time.monotonic() - 30]
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("p-1")
    retry = int(exc_info.value.headers["Retry-After"])
    # Roughly 30s left in the window — accept a generous tolerance for
    # scheduling jitter.
    assert 25 <= retry <= 35


# ---------------------------------------------------------------------------
# FR-012 / FR-013: deferred metric + sweep-throttle markers
# ---------------------------------------------------------------------------


def test_fr012_per_participant_429_counter_increments() -> None:
    """FR-012: per-participant counter increments on every 429 emit."""
    limiter = RateLimiter(limit=1, window=60)
    limiter.check("alice")  # within limit, no 429
    for _ in range(3):
        with pytest.raises(HTTPException) as exc:
            limiter.check("alice")
        assert exc.value.status_code == 429
    assert limiter.rate_limit_429_total["alice"] == 3
    assert limiter.rate_limit_429_total["bob"] == 0


def test_fr012_aggregate_429_counter_per_minute_window() -> None:
    """FR-012: aggregate counter reflects 429s within the trailing 60s."""
    limiter = RateLimiter(limit=1, window=60)
    limiter.check("alice")
    limiter.check("bob")
    for pid in ("alice", "bob", "alice"):
        with pytest.raises(HTTPException):
            limiter.check(pid)
    assert limiter.rate_limit_429_per_minute_total == 3


def test_fr012_aggregate_counter_evicts_old_entries() -> None:
    """FR-012: aggregate timestamps older than 60s are pruned on read."""
    limiter = RateLimiter(limit=1, window=60)
    # Inject an aged 429 timestamp directly so we don't sleep for 60s.
    limiter._429_aggregate_timestamps.append(time.monotonic() - 120)
    limiter._429_aggregate_timestamps.append(time.monotonic() - 0.1)
    assert limiter.rate_limit_429_per_minute_total == 1


def test_fr012_forget_clears_per_participant_counter() -> None:
    """FR-012: forget() drops the counter alongside the bucket."""
    limiter = RateLimiter(limit=1, window=60)
    limiter.check("alice")
    with pytest.raises(HTTPException):
        limiter.check("alice")
    assert limiter.rate_limit_429_total["alice"] == 1
    limiter.forget("alice")
    assert "alice" not in limiter.rate_limit_429_total


def test_fr013_sweep_throttle_short_circuits_within_one_second() -> None:
    """FR-013: rapid eviction triggers within 1s collapse to a single sweep."""
    cap = 5
    limiter = RateLimiter(limit=10, window=1, max_buckets=cap)
    stale = time.monotonic() - 5
    for i in range(cap):
        limiter._buckets[f"stale-{i}"].timestamps = [stale]

    limiter._evict_stale(time.monotonic())
    first_sweep_ts = limiter._last_sweep_ts
    assert first_sweep_ts > 0

    # Re-fill and trigger again immediately — throttle must short-circuit.
    for i in range(cap):
        limiter._buckets[f"stale2-{i}"].timestamps = [stale]
    limiter._evict_stale(time.monotonic())
    assert limiter._last_sweep_ts == first_sweep_ts, "sweep ran twice within 1s"
    # Stale buckets from the second batch must still be present (sweep skipped).
    assert any(pid.startswith("stale2-") for pid in limiter._buckets)


def test_fr013_sweep_duration_captured_in_ms() -> None:
    """FR-013: rate_limit_eviction_sweep_ms is populated after a sweep."""
    limiter = RateLimiter(limit=10, window=1, max_buckets=10)
    stale = time.monotonic() - 5
    for i in range(10):
        limiter._buckets[f"stale-{i}"].timestamps = [stale]
    assert limiter.rate_limit_eviction_sweep_ms == 0.0
    limiter._evict_stale(time.monotonic())
    assert limiter.rate_limit_eviction_sweep_ms >= 0.0
    # Sweep over 10 buckets must complete well under the 50ms operational alert threshold.
    assert limiter.rate_limit_eviction_sweep_ms < 50.0


def test_fr013_sweep_runs_again_after_throttle_window() -> None:
    """FR-013: after _SWEEP_MIN_INTERVAL elapses, the next sweep proceeds."""
    limiter = RateLimiter(limit=10, window=1, max_buckets=5)
    # Simulate the previous sweep having happened just over 1s ago.
    limiter._last_sweep_ts = time.monotonic() - rate_limiter_module._SWEEP_MIN_INTERVAL - 0.1
    stale = time.monotonic() - 5
    for i in range(5):
        limiter._buckets[f"stale-{i}"].timestamps = [stale]
    limiter._evict_stale(time.monotonic())
    assert all(not pid.startswith("stale-") for pid in limiter._buckets)
