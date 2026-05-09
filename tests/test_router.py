# SPDX-License-Identifier: AGPL-3.0-or-later

"""US4: Turn routing — 8-mode routing decision tests."""

from __future__ import annotations

from src.models.participant import Participant
from src.orchestrator.router import (
    _route_addressed_only,
    _route_always,
    _route_burst,
    _route_delegate_low,
    _route_domain_gated,
    _route_human_only,
    _route_observer,
    _route_review_gate,
)

_PARTICIPANT_DEFAULTS: dict[str, object] = {
    "id": "test-id",
    "session_id": "sess-1",
    "display_name": "Test",
    "role": "participant",
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "model_tier": "high",
    "prompt_tier": "mid",
    "model_family": "claude",
    "context_window": 200000,
    "supports_tools": True,
    "supports_streaming": True,
    "domain_tags": "[]",
    "routing_preference": "always",
    "observer_interval": 10,
    "burst_interval": 20,
    "review_gate_timeout": 600,
    "turns_since_last_burst": 0,
    "turn_timeout_seconds": 180,
    "consecutive_timeouts": 0,
    "status": "active",
    "budget_hourly": None,
    "budget_daily": None,
    "max_tokens_per_turn": None,
    "cost_per_input_token": None,
    "cost_per_output_token": None,
    "system_prompt": "",
    "api_endpoint": None,
    "api_key_encrypted": None,
    "auth_token_hash": None,
    "last_seen": None,
    "invited_by": None,
    "approved_at": None,
    "token_expires_at": None,
    "bound_ip": None,
}


def _make_participant(**overrides: object) -> Participant:
    """Create a minimal Participant for routing tests."""
    fields = {**_PARTICIPANT_DEFAULTS, **overrides}
    return Participant(**fields)


def test_always_mode_proceeds() -> None:
    """Always mode returns normal action."""
    p = _make_participant()
    d = _route_always(p, "high", False)
    assert d.action == "normal"


def test_review_gate_stages() -> None:
    """Review gate mode returns review_gated action."""
    p = _make_participant()
    d = _route_review_gate(p, "low", False)
    assert d.action == "review_gated"


def test_delegate_low_delegates_on_low() -> None:
    """Delegate_low delegates low complexity turns."""
    p = _make_participant()
    d = _route_delegate_low(p, "low", False)
    assert d.action == "delegated"


def test_delegate_low_proceeds_on_high() -> None:
    """Delegate_low proceeds normally on high complexity."""
    p = _make_participant()
    d = _route_delegate_low(p, "high", False)
    assert d.action == "normal"


def test_domain_gated_skips_low() -> None:
    """Domain_gated skips low complexity with no match."""
    p = _make_participant()
    d = _route_domain_gated(p, "low", False)
    assert d.action == "skipped"


def test_domain_gated_proceeds_on_high() -> None:
    """Domain_gated proceeds on high complexity."""
    p = _make_participant()
    d = _route_domain_gated(p, "high", False)
    assert d.action == "normal"


def test_burst_accumulates() -> None:
    """Burst accumulates when below interval."""
    p = _make_participant(turns_since_last_burst=5, burst_interval=20)
    d = _route_burst(p, "low", False)
    assert d.action == "burst_accumulating"


def test_burst_fires_at_interval() -> None:
    """Burst fires when interval reached."""
    p = _make_participant(turns_since_last_burst=20, burst_interval=20)
    d = _route_burst(p, "low", False)
    assert d.action == "burst_fired"


def test_observer_skips() -> None:
    """Observer mode skips turns."""
    p = _make_participant()
    d = _route_observer(p, "low", False)
    assert d.action == "skipped"


def test_addressed_only_skips() -> None:
    """Addressed_only skips when not mentioned."""
    p = _make_participant()
    d = _route_addressed_only(p, "low", False)
    assert d.action == "skipped"


def test_human_only_skips_without_interjection() -> None:
    """Human_only skips when no interjection pending."""
    p = _make_participant()
    d = _route_human_only(p, "low", False)
    assert d.action == "skipped"


def test_human_only_responds_with_interjection() -> None:
    """Human_only responds when interjection pending."""
    p = _make_participant()
    d = _route_human_only(p, "low", True)
    assert d.action == "human_trigger"
