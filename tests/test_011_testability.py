# SPDX-License-Identifier: AGPL-3.0-or-later

"""011 web-ui testability suite (Phase B audit fix).

Covers items that are server-testable without a live browser:
  - Per-directive CSP coverage (SR-001)
  - Sensitive-field strip in _participant_dict (SR-011)
  - Pending-role snapshot filter (SR-010)

Browser-requiring items deferred to Phase F (fix/011-web-vitals / Playwright):
  - SR-001a frame-cap regression (WS frame > 256KB)
  - SR-009 forbidden link schemes (javascript:, data:, vbscript:)
  - SR-012 malformed-frame discard + console.warn
  - FR-014 auto-reconnect backoff (JS timer behaviour)
  - US-by-US e2e coverage matrix (US1-US12)
  - CDN-failure graceful-degradation

JS test framework decision (unblocks fix/011-testability):
  Playwright via pytest-playwright (already in [e2e] extras). CDN-loaded
  SPA with no build system -- Jest/Vitest require a module entry point that
  does not exist. Playwright drives a real browser against the running
  server, covering the shipping artifact as-is (Babel Standalone, CDN
  loading, WS behaviour). Deferred items above will land in Phase F.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.web_ui.security import _build_csp
from src.web_ui.snapshot import _participant_dict, build_state_snapshot

# ---------------------------------------------------------------------------
# Per-directive CSP coverage (SR-001)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fragment",
    [
        "default-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
        "'unsafe-eval'",
        "'unsafe-inline'",
        "https://unpkg.com",
        "https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self'",
        "font-src 'self'",
        "connect-src 'self'",
        "report-uri /csp-report",
    ],
)
def test_csp_directive_coverage(fragment: str) -> None:
    """Every required CSP directive fragment is present in the built header (SR-001)."""
    assert fragment in _build_csp(), f"Missing from CSP: {fragment!r}"


# ---------------------------------------------------------------------------
# SR-011: _participant_dict drops sensitive / encrypted fields
# ---------------------------------------------------------------------------

_SENSITIVE_FIELDS = (
    "api_key_encrypted",
    "auth_token_hash",
    "auth_token_lookup",
    "token_expires_at",
    "bound_ip",
)


def _make_participant() -> SimpleNamespace:
    """Minimal participant namespace for _participant_dict tests."""
    p = SimpleNamespace(
        id="pid",
        session_id="sid",
        display_name="X",
        role="participant",
        provider="anthropic",
        model="claude",
        model_tier="high",
        model_family="claude",
        routing_preference=None,
        status="active",
        consecutive_timeouts=0,
        budget_hourly=None,
        budget_daily=None,
        max_tokens_per_turn=None,
        context_window=200000,
        invited_by=None,
        api_key_encrypted="SECRET",
        token_expires_at=None,
        bound_ip="1.2.3.4",
    )
    p.auth_token_hash = None  # value irrelevant; presence is what we test for absence
    p.auth_token_lookup = None
    return p


def test_sr011_participant_dict_excludes_sensitive_fields() -> None:
    """_participant_dict never leaks encrypted or auth fields to the UI (SR-011)."""
    result = _participant_dict(_make_participant())
    for field in _SENSITIVE_FIELDS:
        assert field not in result, f"Sensitive field leaked: {field!r}"


def test_sr011_participant_dict_includes_public_fields() -> None:
    """_participant_dict returns the expected public fields (SR-011 complement)."""
    result = _participant_dict(_make_participant())
    for field in ("id", "display_name", "role", "provider", "model", "status"):
        assert field in result, f"Public field missing: {field!r}"


# ---------------------------------------------------------------------------
# SR-010: pending-role snapshot is filtered (humans only, empty collections)
# ---------------------------------------------------------------------------


def _fake_session_ns() -> SimpleNamespace:
    """Minimal session namespace satisfying _session_row's field access."""
    return SimpleNamespace(
        id="test-sid",
        name="Test",
        status="active",
        current_turn=0,
        last_summary_turn=0,
        cadence_preset="cruise",
        complexity_classifier_mode="pattern",
        min_model_tier="low",
        acceptance_mode="unanimous",
        review_gate_pause_scope="session",
        facilitator_id="h1",
    )


async def test_sr010_pending_snapshot_filters_to_humans_only() -> None:
    """Pending role sees only human-provider participants in state_snapshot (SR-010)."""
    mixed = [
        {"id": "h1", "provider": "human"},
        {"id": "ai1", "provider": "anthropic"},
        {"id": "ai2", "provider": "openai"},
    ]
    mock_sess_repo = AsyncMock()
    mock_sess_repo.get_session.return_value = _fake_session_ns()
    state = SimpleNamespace(session_repo=mock_sess_repo)

    with (
        patch("src.web_ui.snapshot._participants", AsyncMock(return_value=mixed)),
        patch("src.web_ui.snapshot._loop_running", return_value=False),
    ):
        event = await build_state_snapshot(state, "test-sid", {"role": "pending"})

    ids = [p["id"] for p in event["participants"]]
    assert "h1" in ids
    assert "ai1" not in ids
    assert "ai2" not in ids


async def test_sr010_pending_snapshot_has_empty_data_collections() -> None:
    """Pending snapshot has no messages, drafts, proposals, or convergence (SR-010)."""
    mock_sess_repo = AsyncMock()
    mock_sess_repo.get_session.return_value = _fake_session_ns()
    state = SimpleNamespace(session_repo=mock_sess_repo)

    with (
        patch("src.web_ui.snapshot._participants", AsyncMock(return_value=[])),
        patch("src.web_ui.snapshot._loop_running", return_value=False),
    ):
        event = await build_state_snapshot(state, "test-sid", {"role": "pending"})

    assert event["messages"] == []
    assert event["pending_drafts"] == []
    assert event["open_proposals"] == []
    assert event["convergence_scores"] == []
