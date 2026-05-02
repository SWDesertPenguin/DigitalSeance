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

from src.mcp_server import rate_limiter as rate_limiter_module
from src.mcp_server.rate_limiter import (
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
    src/mcp_server/middleware.py. Endpoints that do NOT depend on
    get_current_participant (/healthz, /docs, /openapi.json,
    /redoc, the login surface) bypass the limiter by construction.
    This test pins the integration shape: any change that calls
    limiter.check from another middleware layer would surface here.
    """
    import inspect

    from src.mcp_server import middleware

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


def test_fr012_429_counter_trigger_marker() -> None:
    """FR-012 per-participant + aggregate 429 counters are deferred.

    Activation: once RateLimiter exposes a metrics hook (e.g. a
    ``rate_limit_429_total`` attribute or a structured-log emitter), this
    marker test should be replaced with counter-increment assertions. Until
    then FR-012 is "untested with trigger" in the traceability table.
    """
    limiter = RateLimiter(limit=1, window=60)
    assert not hasattr(
        limiter, "rate_limit_429_total"
    ), "FR-012 metrics landed — replace marker with counter-increment tests"


def test_fr013_sweep_rate_limit_trigger_marker() -> None:
    """FR-013 sweep ≤1/sec throttle is deferred.

    Activation: once _evict_stale records a last-sweep timestamp and short-
    circuits subsequent calls within the same second, replace this marker
    with a sweep-count assertion (10 triggers in <1s -> 1 actual sweep).
    """
    limiter = RateLimiter(limit=1, window=60)
    # Module-level constant or instance attribute will appear when wired.
    has_throttle = hasattr(limiter, "_last_sweep_ts") or hasattr(
        rate_limiter_module, "_SWEEP_MIN_INTERVAL"
    )
    assert not has_throttle, "FR-013 sweep throttle landed — replace marker with sweep-count test"
