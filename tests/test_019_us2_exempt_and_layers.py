"""Spec 019 US2 -- exempt paths + section7.5 isolation contract.

Drives the NetworkRateLimitMiddleware directly; covers:
- AS1 / SC-003: GET /health and GET /metrics bypass the limiter
  entirely even from a budget-exhausted IP.
- AS2 / FR-007: section7.5 application-layer per-participant limiter
  behaves independent of network-layer state.
- AS3 / FR-008 / SC-005: a network-rejected request never reaches
  application-layer state.
- AS4: app-layer limit fires independent of plentiful per-IP budget.
- T034 method-restricted: POST /health / POST /metrics are NOT exempt.
- T035 isolation probe: section7.5 limiter rejects above its own threshold;
  network-layer counter unchanged when section7.5 rejects.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import HTTPException

from src.audit.network_rate_limit_audit import (
    get_coalescer,
    reset_coalescer_for_tests,
    reset_unresolvable_queue_for_tests,
)
from src.mcp_server.rate_limiter import RateLimiter
from src.observability.metrics import reset_for_tests, sacp_rate_limit_rejection_total


@pytest.fixture(autouse=True)
def _reset_global_state() -> None:
    reset_coalescer_for_tests()
    reset_unresolvable_queue_for_tests()
    reset_for_tests()


# Re-use the synthetic-ASGI helpers in the US1 file by importing them.
from tests.test_019_us1_bcrypt_flood import (  # noqa: E402
    _BcryptCounter,
    _build_middleware,
    _drive,
    _make_scope,
    _noop_receive,
    _Recorder,
)

# ---------------------------------------------------------------------------
# T030 -- AS1 / SC-003: exempt paths bypass even from budget-exhausted IP
# ---------------------------------------------------------------------------


def test_t030_health_metrics_bypass_when_budget_exhausted() -> None:
    """GET /health + GET /metrics serve normally even when /mcp/* is rejected."""
    mw, inner = _build_middleware(rpm=10, burst=2)
    # Drain the IP's budget against a non-exempt path.
    _drive(mw, count=5, path="/mcp/tool", method="POST", client_host="203.0.113.5")
    inner.calls = 0
    # Now hit /health and /metrics from the same IP -- both must serve.
    health = _drive(mw, count=10, path="/health", method="GET", client_host="203.0.113.5")
    metrics = _drive(mw, count=10, path="/metrics", method="GET", client_host="203.0.113.5")
    for r in health + metrics:
        assert r.status == 401  # inner _BcryptCounter responds 401
    # All 20 exempt requests reached the inner app despite the IP being out of budget.
    assert inner.calls == 20


def test_t030_exempt_paths_do_not_consume_budget() -> None:
    """Exempt requests increment NO budget -- fresh IP keeps its full burst."""
    mw, _ = _build_middleware(rpm=60, burst=3)
    _drive(mw, count=100, path="/health", method="GET", client_host="198.51.100.1")
    # Budget should still be full -- three non-exempt requests must all admit.
    recorders = _drive(mw, count=3, path="/mcp/tool", method="POST", client_host="198.51.100.1")
    assert all(r.status == 401 for r in recorders)


# ---------------------------------------------------------------------------
# T032 -- FR-008 / SC-005: network-rejected request leaves app state untouched
# ---------------------------------------------------------------------------


def test_t032_rejected_request_does_not_invoke_inner() -> None:
    """A 429-rejected request never reaches the inner ASGI app."""
    mw, inner = _build_middleware(rpm=60, burst=1)
    _drive(mw, count=1, client_host="203.0.113.5")
    inner.calls = 0
    rejected = _drive(mw, count=5, client_host="203.0.113.5")
    assert all(r.status == 429 for r in rejected)
    assert inner.calls == 0  # FR-008: no application-layer touch


# ---------------------------------------------------------------------------
# T034 -- FR-006 method-restricted: POST /health is NOT exempt
# ---------------------------------------------------------------------------


def test_t034_post_health_falls_through_to_normal_limiter() -> None:
    """POST /health (and POST /metrics) are NOT exempt -- limited normally."""
    mw, _ = _build_middleware(rpm=60, burst=1)
    _drive(mw, count=1, path="/health", method="POST")  # consumes the burst
    recorders = _drive(mw, count=1, path="/health", method="POST")
    assert recorders[0].status == 429


def test_t034_post_metrics_falls_through_to_normal_limiter() -> None:
    mw, _ = _build_middleware(rpm=60, burst=1)
    _drive(mw, count=1, path="/metrics", method="POST")
    recorders = _drive(mw, count=1, path="/metrics", method="POST")
    assert recorders[0].status == 429


# ---------------------------------------------------------------------------
# T031 + T033 + T035 -- section7.5 isolation contract (FR-007 / SC-004)
# ---------------------------------------------------------------------------


def test_t031_app_layer_limiter_independent_when_network_admits() -> None:
    """section7.5 limiter rejects per-participant even when network budget is plentiful.

    The network-layer middleware admits every request below its budget;
    section7.5's per-participant counter is a SEPARATE state machine. A
    participant exceeding the section7.5 threshold gets 429'd by section7.5
    regardless of network-layer state.
    """
    network_mw, _ = _build_middleware(rpm=6000, burst=100)  # very generous network budget
    # Run a few network-admits to exercise the network layer.
    _drive(network_mw, count=5, client_host="203.0.113.5")
    # Independently drive the section7.5 limiter at limit=2 / window=60.
    app_layer = RateLimiter(limit=2, window=60)
    app_layer.check("participant-1")
    app_layer.check("participant-1")
    with pytest.raises(HTTPException) as excinfo:
        app_layer.check("participant-1")
    assert excinfo.value.status_code == 429


def test_t033_app_layer_fires_with_network_budget_remaining() -> None:
    """Symmetric of T031 -- both limiters fire on different signals (FR-007)."""
    network_mw, _ = _build_middleware(rpm=6000, burst=100)
    # Plentiful network budget -- every request admits.
    network_recorders = _drive(network_mw, count=10, client_host="203.0.113.5")
    assert all(r.status == 401 for r in network_recorders)
    # section7.5 limit at 1 -- second call rejects regardless of network budget.
    app_layer = RateLimiter(limit=1, window=60)
    app_layer.check("participant-1")
    with pytest.raises(HTTPException):
        app_layer.check("participant-1")


def test_t035_isolation_zero_shared_state() -> None:
    """SC-004: the two limiters share no in-memory state.

    Asserts (a) section7.5 RateLimiter state is a separate object than the
    network-layer middleware's bucket map, and (b) network-layer
    rejection counter is unchanged when only section7.5 fires.
    """
    network_mw, _ = _build_middleware(rpm=6000, burst=100)
    app_layer = RateLimiter(limit=1, window=60)
    # No code path connects ``network_mw._buckets`` and
    # ``app_layer._buckets`` -- assert the type of each map directly.
    network_buckets = network_mw._buckets
    app_buckets = app_layer._buckets
    assert network_buckets is not app_buckets
    assert type(network_buckets).__name__ == "_LRUBucketMap"
    assert type(app_buckets).__name__ == "defaultdict"

    # Drive section7.5 to a rejection. The network counter MUST stay at zero.
    metric_before = sacp_rate_limit_rejection_total.get_sample_value(
        {"endpoint_class": "network_per_ip", "exempt_match": "false"},
    )
    app_layer.check("participant-1")
    with pytest.raises(HTTPException):
        app_layer.check("participant-1")
    metric_after = sacp_rate_limit_rejection_total.get_sample_value(
        {"endpoint_class": "network_per_ip", "exempt_match": "false"},
    )
    assert (
        metric_before == metric_after
    ), "section7.5 rejection MUST NOT increment the network-layer counter (FR-007)"
    # And the network-layer coalescer is empty too.
    assert len(get_coalescer()) == 0


# Silence the unused-import warning while keeping the imports load-bearing.
_ = (asyncio, Any, _BcryptCounter, _Recorder, _make_scope, _noop_receive)
