# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 016 -- /metrics endpoint contract tests.

Covers:
- SC-005: disabled (default) returns 404 from route absence
- SC-005: enabled returns 200 with Prometheus text content
- SC-008: /metrics is exempt from network rate limiter
- SC-007: privacy contract -- no forbidden label content in any metric
- FR-001: Content-Type is Prometheus text format
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.observability.metrics_registry import reset_registry_for_tests


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_registry_for_tests()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(*, enabled: bool) -> object:
    """Build a minimal FastAPI app with the metrics router conditionally included."""
    from fastapi import FastAPI

    from src.mcp_server.metrics_router import router as metrics_router

    app = FastAPI()
    if enabled:
        app.include_router(metrics_router)
    return app


# ---------------------------------------------------------------------------
# SC-005: disabled -- 404 from route absence
# ---------------------------------------------------------------------------


def test_sc005_metrics_disabled_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """When SACP_METRICS_ENABLED is unset, /metrics returns 404."""
    monkeypatch.delenv("SACP_METRICS_ENABLED", raising=False)
    app = _make_app(enabled=False)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/metrics")
    assert resp.status_code == 404


def test_sc005_metrics_false_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """When SACP_METRICS_ENABLED=false, /metrics returns 404."""
    monkeypatch.setenv("SACP_METRICS_ENABLED", "false")
    app = _make_app(enabled=False)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/metrics")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# FR-001: enabled -- 200 with Prometheus text
# ---------------------------------------------------------------------------


def test_fr001_metrics_enabled_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """When SACP_METRICS_ENABLED=true, /metrics returns 200."""
    monkeypatch.setenv("SACP_METRICS_ENABLED", "true")
    app = _make_app(enabled=True)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_fr001_content_type_is_prometheus_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Content-Type must be Prometheus text format."""
    monkeypatch.setenv("SACP_METRICS_ENABLED", "true")
    app = _make_app(enabled=True)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    ct = resp.headers.get("content-type", "")
    assert "text/plain" in ct


def test_fr001_body_contains_help_and_type_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Response body must contain Prometheus # HELP and # TYPE headers."""
    monkeypatch.setenv("SACP_METRICS_ENABLED", "true")
    app = _make_app(enabled=True)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/metrics")
    body = resp.text
    assert "# HELP" in body
    assert "# TYPE" in body


# ---------------------------------------------------------------------------
# SC-007: privacy contract -- no forbidden label content
# ---------------------------------------------------------------------------

# Forbidden patterns: API key material, model names, IPs, URLs, message content.
_FORBIDDEN_PATTERNS = [
    "sk-",  # OpenAI key prefix
    "anthropic-api-key",  # Anthropic header
    "api_key",  # generic key reference in labels
    "gpt-4",  # model name
    "claude-",  # model name prefix
    "gemini",  # model name
    "192.168.",  # private IP
    "10.0.",  # private IP
    "/mcp/",  # request URL
    "user-agent",  # UA header name
    "content:",  # message content marker
]


def _inject_sc007_fixture_data() -> None:
    """Inject metric data for SC-007 privacy contract scrape tests."""
    from src.observability.metrics_registry import (
        inc_participant_tokens,
        inc_provider_request,
        inc_rate_limit_rejection,
    )

    inc_rate_limit_rejection(endpoint_class="network_per_ip", exempt_match="false")
    inc_participant_tokens(
        session_id="test-session-1",
        participant_id="participant-abc-123-def-456",
        prompt_tokens=100,
        completion_tokens=50,
    )
    inc_provider_request(provider_kind="litellm", outcome="success")


def test_sc007_no_forbidden_label_content_in_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Privacy contract: no forbidden strings appear anywhere in /metrics output."""
    monkeypatch.setenv("SACP_METRICS_ENABLED", "true")
    _inject_sc007_fixture_data()
    app = _make_app(enabled=True)
    client = TestClient(app, raise_server_exceptions=True)
    body = client.get("/metrics").text
    assert "participant-abc-123-def-456" not in body
    for pattern in _FORBIDDEN_PATTERNS:
        assert pattern.lower() not in body.lower(), f"forbidden pattern {pattern!r} in /metrics"


def test_sc007_participant_id_hash_used_not_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    """participant_id_hash label must be the 8-char hash, not the raw UUID."""
    from src.observability.metrics_registry import (
        inc_participant_tokens,
        participant_id_hash,
    )

    raw_id = "my-participant-id-12345"
    expected_hash = participant_id_hash(raw_id)

    inc_participant_tokens(
        session_id="sess-x",
        participant_id=raw_id,
        prompt_tokens=10,
        completion_tokens=5,
    )

    monkeypatch.setenv("SACP_METRICS_ENABLED", "true")
    app = _make_app(enabled=True)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/metrics")
    body = resp.text

    assert raw_id not in body
    assert expected_hash in body


# ---------------------------------------------------------------------------
# SC-008: rate-limit exemption
# ---------------------------------------------------------------------------


def test_sc008_metrics_path_in_exempt_paths() -> None:
    """/metrics must appear in EXEMPT_PATHS so it bypasses the rate limiter."""
    from src.middleware.network_rate_limit import EXEMPT_PATHS

    assert (
        "GET",
        "/metrics",
    ) in EXEMPT_PATHS, "/metrics must be in EXEMPT_PATHS alongside /health (FR-002 / SC-008)"
