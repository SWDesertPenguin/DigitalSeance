# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 019 FR-002 startup canary: NetworkRateLimit middleware-order contract.

Two properties (per contracts/middleware-ordering.md):

1. When SACP_NETWORK_RATELIMIT_ENABLED=true, the FIRST entry in
   ``app.user_middleware`` is ``NetworkRateLimitMiddleware``. FastAPI's
   ``add_middleware()`` prepends to ``user_middleware`` (insert at index
   0), so the LAST registered middleware ends up at index 0 — that
   becomes the OUTERMOST = first to see inbound requests.
2. When SACP_NETWORK_RATELIMIT_ENABLED=false, the middleware is absent
   from ``app.user_middleware`` entirely (FR-014 / SC-006: byte-identical
   pre-feature behavior -- unconditional registration would still affect
   the request stack frame count).

Caplog assertion: with ENABLED=true, exactly one log record matching
``r"^Middleware order \\(outermost first\\): \\[NetworkRateLimitMiddleware,"``
is emitted per ``create_app()`` invocation. With ENABLED=false, NO record
matching that prefix is emitted. Pins the operator-visible introspection
contract from contracts/middleware-ordering.md.
"""

from __future__ import annotations

import logging
import re

import pytest

from src.mcp_server.app import create_app


def _set_required_env(monkeypatch) -> None:
    """Set the four downstream env vars required by the V16 cross-validator."""
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_RPM", "60")
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_BURST", "15")
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS", "false")
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_MAX_KEYS", "100000")


def test_network_ratelimit_is_outermost_when_enabled(monkeypatch) -> None:
    """FR-002: NetworkRateLimitMiddleware MUST be outermost when ENABLED=true."""
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "true")
    _set_required_env(monkeypatch)

    app = create_app()

    middleware_classes = [m.cls for m in app.user_middleware]
    assert middleware_classes, "expected at least one middleware registered"
    assert middleware_classes[0].__name__ == "NetworkRateLimitMiddleware", (
        f"FR-002 violated: NetworkRateLimitMiddleware MUST be outermost "
        f"(index 0 of user_middleware after FastAPI's prepend semantics); "
        f"got order {[c.__name__ for c in middleware_classes]}"
    )


def test_network_ratelimit_absent_when_disabled(monkeypatch) -> None:
    """FR-014, SC-006: middleware MUST NOT be registered when ENABLED=false."""
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "false")

    app = create_app()

    middleware_classes = [m.cls.__name__ for m in app.user_middleware]
    assert (
        "NetworkRateLimitMiddleware" not in middleware_classes
    ), f"SC-006 violated: middleware registered when ENABLED=false; got order {middleware_classes}"


def test_network_ratelimit_absent_when_unset(monkeypatch) -> None:
    """FR-014: master switch unset = pre-feature byte-identical (no middleware)."""
    monkeypatch.delenv("SACP_NETWORK_RATELIMIT_ENABLED", raising=False)

    app = create_app()

    middleware_classes = [m.cls.__name__ for m in app.user_middleware]
    assert "NetworkRateLimitMiddleware" not in middleware_classes


def test_introspection_log_emitted_when_enabled(monkeypatch, caplog) -> None:
    """contracts/middleware-ordering.md: emits exactly one matching log line."""
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "true")
    _set_required_env(monkeypatch)

    pattern = re.compile(r"^Middleware order \(outermost first\): \[NetworkRateLimitMiddleware,")
    with caplog.at_level(logging.INFO):
        create_app()

    matches = [r for r in caplog.records if pattern.match(r.getMessage())]
    assert len(matches) == 1, (
        f"expected exactly one introspection log line; got {len(matches)}: "
        f"{[r.getMessage() for r in matches]}"
    )


def test_introspection_log_silent_when_disabled(monkeypatch, caplog) -> None:
    """contracts/middleware-ordering.md: no introspection line when ENABLED=false."""
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "false")

    pattern = re.compile(r"^Middleware order \(outermost first\): \[")
    with caplog.at_level(logging.INFO):
        create_app()

    matches = [r for r in caplog.records if pattern.match(r.getMessage())]
    assert not matches, f"expected no introspection log line when disabled; got {len(matches)}"


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch) -> None:
    """Each test starts with the limiter master switch cleared."""
    for var in (
        "SACP_NETWORK_RATELIMIT_ENABLED",
        "SACP_NETWORK_RATELIMIT_RPM",
        "SACP_NETWORK_RATELIMIT_BURST",
        "SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS",
        "SACP_NETWORK_RATELIMIT_MAX_KEYS",
    ):
        monkeypatch.delenv(var, raising=False)
