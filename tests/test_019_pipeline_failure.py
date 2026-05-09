# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 019 Phase 6 -- fail-closed pipeline edge cases (T049).

Covers three V15 fail-closed surfaces:

1. Validator failure at startup -- invalid env var causes process to exit
   non-zero and stderr names the offending var (SC-007).
2. Source-IP-unresolvable -> HTTP 400 (NOT 200, NOT silent drop); audit
   row queued; metric incremented (FR-012).
3. Audit-flush failure -- orchestrator stays up; metric counter retains
   per-rejection durability across the gap (V15).
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import pytest

from src.audit.network_rate_limit_audit import (
    drain_unresolvable_queue,
    flush_once,
    record_rejection,
    reset_coalescer_for_tests,
    reset_unresolvable_queue_for_tests,
)
from src.config.validators import ConfigValidationError, iter_failures
from src.middleware.network_rate_limit import NetworkRateLimitMiddleware
from src.observability.metrics import reset_for_tests, sacp_rate_limit_rejection_total


@pytest.fixture(autouse=True)
def _reset_global_state() -> None:
    reset_coalescer_for_tests()
    reset_unresolvable_queue_for_tests()
    reset_for_tests()


# Re-use US1 helpers.
from tests.test_019_us1_bcrypt_flood import (  # noqa: E402
    _build_middleware,
    _make_scope,
    _noop_receive,
    _Recorder,
)

# ---------------------------------------------------------------------------
# Fail-closed #1 -- invalid env var raises ConfigValidationError naming var
# ---------------------------------------------------------------------------


def test_invalid_rpm_raises_with_var_name(monkeypatch) -> None:
    """SC-007: invalid env var fails startup with the offending var name in the error."""
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_RPM", "99999")  # above [1, 6000]
    failures = list(iter_failures())
    rpm_failures = [f for f in failures if f.var_name == "SACP_NETWORK_RATELIMIT_RPM"]
    assert rpm_failures, "expected SACP_NETWORK_RATELIMIT_RPM to be flagged"

    # The startup harness wraps these in ConfigValidationError; assert
    # the exception text names the offending var (operator-visible signal).
    err = ConfigValidationError(rpm_failures)
    assert "SACP_NETWORK_RATELIMIT_RPM" in str(err)


def test_invalid_max_keys_emits_clear_error(monkeypatch) -> None:
    """Edge case: SACP_NETWORK_RATELIMIT_MAX_KEYS=0 (below [1024, 1_000_000])."""
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_MAX_KEYS", "0")
    failures = list(iter_failures())
    matching = [f for f in failures if f.var_name == "SACP_NETWORK_RATELIMIT_MAX_KEYS"]
    assert matching
    assert "must be in [1024, 1_000_000]" in matching[0].reason


# ---------------------------------------------------------------------------
# Fail-closed #2 -- source-IP-unresolvable -> 400 + audit + metric
# ---------------------------------------------------------------------------


def test_unresolvable_does_not_silent_drop() -> None:
    """FR-012: unresolvable request emits HTTP 400 (NOT 200, NOT silent drop)."""
    mw, _ = _build_middleware()
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/tool",
        "client": None,
        "headers": [],
    }
    recorder = _Recorder()
    asyncio.run(mw(scope, _noop_receive, recorder))
    assert recorder.status == 400
    queue = drain_unresolvable_queue()
    assert len(queue) == 1
    metric = sacp_rate_limit_rejection_total.get_sample_value(
        {"endpoint_class": "network_per_ip", "exempt_match": "false"},
    )
    assert metric == 1.0


# ---------------------------------------------------------------------------
# Fail-closed #3 -- audit-flush failure does not block request path
# ---------------------------------------------------------------------------


class _FlakyPool:
    """Synthetic pool whose ``acquire()`` connection raises on every execute."""

    def __init__(self) -> None:
        self.calls = 0

    def acquire(self) -> _FlakyPool:
        return self

    async def __aenter__(self) -> _FlakyPool:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1
        raise RuntimeError("synthetic DB outage")


def test_audit_flush_failure_does_not_propagate() -> None:
    """V15 fail-closed: flush errors log but don't propagate; counter unaffected."""
    record_rejection(
        source_ip_keyed="203.0.113.5",
        path="/mcp/tool",
        method="POST",
        remaining_s=1.0,
        now=1_700_000_000.0,
    )
    pool = _FlakyPool()
    # The flush must not raise -- the V15 contract says failure logs but does
    # not propagate. ``flush_once`` advances ``now`` past the bucket's minute.
    written = asyncio.run(flush_once(pool, now=1_700_000_120.0))
    assert written == 0  # no rows actually persisted (the synthetic pool raised)
    assert pool.calls >= 1  # but the write was attempted


def test_metric_counter_unaffected_by_flush_failure() -> None:
    """The metric counter is in-memory; a DB failure cannot touch it."""
    from src.observability.metrics import increment_network_rate_limit_rejection

    increment_network_rate_limit_rejection()
    increment_network_rate_limit_rejection()
    pool = _FlakyPool()
    asyncio.run(flush_once(pool, now=1_700_000_120.0))
    metric = sacp_rate_limit_rejection_total.get_sample_value(
        {"endpoint_class": "network_per_ip", "exempt_match": "false"},
    )
    assert metric == 2.0


# Silence unused-imports.
_ = (sys, _make_scope, NetworkRateLimitMiddleware)
