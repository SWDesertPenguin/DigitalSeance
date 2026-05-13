# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 019 US1 — per-IP rate limiting blocks bcrypt-flood attacks.

Drives the NetworkRateLimitMiddleware directly with synthetic ASGI
scopes so we test the rate-limit decision logic without spinning up a
full HTTP server. The bcrypt-protected auth path is represented by a
counter ASGI app that records every admit; the limiter MUST keep that
counter below RPM regardless of inbound rate.

Acceptance scenarios covered:
- AS1 / SC-001: at most BURST admissions before refill (RPM bound)
- AS2 / SC-002: legitimate IP B unaffected during flood from IP A
- AS3 / FR-005: HTTP 429 carries Retry-After + fixed body, no echo
- AS4 / FR-014 / SC-006: behavior byte-identical when ENABLED=false
- IPv6 /64 keying: same /64 shares budget; different /64 does not
- FR-012: source-IP-unresolvable rejects HTTP 400 + audit row
- FR-015: WS upgrade decrements once at upgrade moment
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.audit.network_rate_limit_audit import (
    drain_unresolvable_queue,
    get_coalescer,
    reset_coalescer_for_tests,
    reset_unresolvable_queue_for_tests,
)
from src.middleware.network_rate_limit import NetworkRateLimitMiddleware
from src.observability.metrics import reset_for_tests, sacp_rate_limit_rejection_total


@pytest.fixture(autouse=True)
def _reset_global_state() -> None:
    """Each test starts with empty coalescer + unresolvable queue + counter."""
    reset_coalescer_for_tests()
    reset_unresolvable_queue_for_tests()
    reset_for_tests()


# ---------------------------------------------------------------------------
# Helpers — synthetic ASGI plumbing
# ---------------------------------------------------------------------------


class _BcryptCounter:
    """Stand-in inner ASGI app: counts admits (bcrypt invocations)."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        self.calls += 1
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"text/plain")],
            },
        )
        await send({"type": "http.response.body", "body": b"unauthenticated"})


def _make_scope(
    *,
    path: str = "/mcp/tool",
    method: str = "POST",
    client_host: str = "203.0.113.5",
    client_port: int = 50000,
    headers: list[tuple[bytes, bytes]] | None = None,
    scope_type: str = "http",
) -> dict[str, Any]:
    """Build a minimal ASGI scope dict."""
    return {
        "type": scope_type,
        "method": method,
        "path": path,
        "client": (client_host, client_port),
        "headers": headers or [],
    }


class _Recorder:
    """Capture every ASGI ``send`` event for assertion."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def __call__(self, message: dict[str, Any]) -> None:
        self.events.append(message)

    @property
    def status(self) -> int | None:
        for event in self.events:
            if event.get("type") == "http.response.start":
                return int(event["status"])
        return None

    @property
    def headers(self) -> dict[str, str]:
        for event in self.events:
            if event.get("type") == "http.response.start":
                return {
                    name.decode("latin-1").lower(): value.decode("latin-1")
                    for name, value in event["headers"]
                }
        return {}

    @property
    def body(self) -> bytes:
        chunks: list[bytes] = []
        for event in self.events:
            if event.get("type") == "http.response.body":
                chunks.append(event.get("body", b""))
        return b"".join(chunks)


async def _noop_receive() -> dict[str, Any]:
    return {"type": "http.request"}


def _build_middleware(
    *,
    rpm: int = 60,
    burst: int = 15,
    max_keys: int = 100_000,
    trust: bool = False,
) -> tuple[NetworkRateLimitMiddleware, _BcryptCounter]:
    inner = _BcryptCounter()
    mw = NetworkRateLimitMiddleware(
        inner,
        rpm=rpm,
        burst=burst,
        max_keys=max_keys,
        trust_forwarded_headers=trust,
    )
    return mw, inner


def _drive(
    mw: NetworkRateLimitMiddleware,
    *,
    count: int,
    client_host: str = "203.0.113.5",
    path: str = "/mcp/tool",
    method: str = "POST",
) -> list[_Recorder]:
    """Run ``count`` synthetic requests through the middleware."""
    recorders: list[_Recorder] = []
    for _ in range(count):
        scope = _make_scope(path=path, method=method, client_host=client_host)
        recorder = _Recorder()
        asyncio.run(mw(scope, _noop_receive, recorder))
        recorders.append(recorder)
    return recorders


# ---------------------------------------------------------------------------
# T017 — AS1 / SC-001: flood from IP A blocked before bcrypt
# ---------------------------------------------------------------------------


def test_as1_flood_capped_at_burst_before_refill() -> None:
    """200 requests in a tight burst → at most BURST admits to the inner app.

    The first BURST requests refill ~zero (timestamp deltas under a
    millisecond), so admissions stop at the burst cap. Subsequent
    requests reject with 429 BEFORE the inner app runs.
    """
    mw, inner = _build_middleware(rpm=60, burst=15)
    recorders = _drive(mw, count=200)

    admitted = [r for r in recorders if r.status == 401]
    rejected = [r for r in recorders if r.status == 429]

    assert inner.calls == len(admitted)
    assert inner.calls <= 15, f"bcrypt invoked {inner.calls} times — burst cap leaked"
    assert len(rejected) == 200 - len(admitted)


def test_as1_admit_is_unconditional_against_downstream_outcome() -> None:
    """Edge case: an admitted request decrements regardless of downstream result.

    The limiter pays its cost at the admit decision; auth-failure does
    not refund. (spec.md §"Edge Cases".)
    """
    mw, _ = _build_middleware(rpm=60, burst=2)
    _drive(mw, count=2)
    # Both burst tokens spent. A third request must reject even though
    # the prior two "failed" auth (the inner app returns 401).
    recorders = _drive(mw, count=1)
    assert recorders[0].status == 429


# ---------------------------------------------------------------------------
# T018 — AS2 / SC-002: legitimate IP B unaffected during flood from IP A
# ---------------------------------------------------------------------------


def test_as2_independent_ips_do_not_share_budget() -> None:
    """Per-IP scoping: IP B's first request admits even while IP A is rejected."""
    mw, inner = _build_middleware(rpm=60, burst=3)
    _drive(mw, count=10, client_host="203.0.113.5")  # IP A flood
    inner.calls = 0  # zero out so we can isolate IP B's effect
    recorders_b = _drive(mw, count=1, client_host="198.51.100.10")
    assert recorders_b[0].status == 401
    assert inner.calls == 1


# ---------------------------------------------------------------------------
# T019 — AS3 / FR-005: HTTP 429 carries Retry-After + fixed body
# ---------------------------------------------------------------------------


def test_as3_retry_after_header_present() -> None:
    """RFC 6585: 429 response MUST include Retry-After (integer seconds)."""
    mw, _ = _build_middleware(rpm=60, burst=1)
    _drive(mw, count=1)  # consume the burst
    recorder = _drive(mw, count=1)[0]
    assert recorder.status == 429
    retry_after = recorder.headers.get("retry-after")
    assert retry_after is not None
    assert int(retry_after) >= 1


def test_as3_body_is_fixed_string_no_echo() -> None:
    """FR-005 privacy: body equals exactly 'rate limit exceeded'; no echo."""
    mw, _ = _build_middleware(rpm=60, burst=1)
    _drive(mw, count=1)
    decoy_path = "/mcp/secret-marker-12345"
    decoy_query = "?token=NEVER_ECHOED"
    scope = _make_scope(path=decoy_path + decoy_query)
    recorder = _Recorder()
    asyncio.run(mw(scope, _noop_receive, recorder))

    assert recorder.status == 429
    assert recorder.body == b"rate limit exceeded"
    assert b"secret-marker" not in recorder.body
    assert b"NEVER_ECHOED" not in recorder.body


# ---------------------------------------------------------------------------
# T020 — AS4 / FR-014 / SC-006: ENABLED=false byte-identical
# ---------------------------------------------------------------------------


def test_as4_master_switch_off_no_middleware(monkeypatch) -> None:
    """When SACP_NETWORK_RATELIMIT_ENABLED=false, no middleware is registered.

    Pairs with the dedicated middleware-order canary in
    test_019_middleware_order.py — this test re-asserts via the app
    factory entry point so an end-to-end byte-identity regression
    surfaces here too.
    """
    from src.participant_api.app import create_app

    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "false")
    app = create_app()
    middleware_classes = [m.cls.__name__ for m in app.user_middleware]
    assert "NetworkRateLimitMiddleware" not in middleware_classes


# ---------------------------------------------------------------------------
# T021 — IPv6 /64 keying
# ---------------------------------------------------------------------------


def test_t021_ipv6_same_64_shares_budget() -> None:
    """Two distinct /128 addresses within the same /64 share one bucket (FR-004)."""
    mw, _ = _build_middleware(rpm=60, burst=2)
    # Both addresses fall under 2001:db8:1234:5678::/64 — different host bits.
    _drive(mw, count=2, client_host="2001:db8:1234:5678::1")
    recorders = _drive(mw, count=1, client_host="2001:db8:1234:5678:abcd::99")
    assert recorders[0].status == 429


def test_t021_ipv6_different_64_does_not_share() -> None:
    """A different /64 starts with a fresh bucket."""
    mw, _ = _build_middleware(rpm=60, burst=1)
    _drive(mw, count=1, client_host="2001:db8:1234:5678::1")
    recorders = _drive(mw, count=1, client_host="2001:db8:9999:0000::1")
    assert recorders[0].status == 401


# ---------------------------------------------------------------------------
# T022 — FR-012: source-IP-unresolvable → 400 + audit row
# ---------------------------------------------------------------------------


def test_t022_no_peer_yields_400_and_audit() -> None:
    """ASGI scope with no client → reject 400 + queue source_ip_unresolvable."""
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
    assert queue[0].reason == "no_peer"


def test_t022_unresolvable_increments_metric() -> None:
    """Unresolvable rejection increments with same labels as a normal one."""
    mw, _ = _build_middleware()
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/tool",
        "client": None,
        "headers": [],
    }
    asyncio.run(mw(scope, _noop_receive, _Recorder()))

    value = sacp_rate_limit_rejection_total.get_sample_value(
        {"endpoint_class": "network_per_ip", "exempt_match": "false"},
    )
    assert value == 1.0


# ---------------------------------------------------------------------------
# T022a — FR-015: WebSocket upgrade decrements once
# ---------------------------------------------------------------------------


def test_t022a_websocket_upgrade_decrements_once() -> None:
    """A WS upgrade consumes exactly one token; subsequent frames are out-of-scope."""
    mw, _ = _build_middleware(rpm=60, burst=2)
    scope = _make_scope(path="/ws", method="GET", scope_type="websocket")
    asyncio.run(mw(scope, _noop_receive, _Recorder()))

    # The middleware ran exactly once; the bucket has one token left.
    coalescer = get_coalescer()
    assert len(coalescer) == 0  # admitted → no rejection recorded
    # A second upgrade also admits.
    asyncio.run(mw(scope, _noop_receive, _Recorder()))
    # A third would reject (burst exhausted).
    recorder3 = _Recorder()
    asyncio.run(mw(scope, _noop_receive, recorder3))
    # WebSocket rejection arrives as a websocket.close, not http response.start.
    types = [e.get("type") for e in recorder3.events]
    assert "websocket.close" in types
