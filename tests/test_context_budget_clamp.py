"""Unit tests for context_window clamping in _available_budget (spec 003 §FR-035)."""

from __future__ import annotations

import dataclasses
import logging

import pytest

from src.models.participant import Participant
from src.orchestrator.context import RESPONSE_RESERVE, _available_budget

_BASE = Participant(
    id="p1",
    session_id="s1",
    display_name="Test",
    role="participant",
    provider="openai",
    model="gpt-4o",
    model_tier="mid",
    prompt_tier="mid",
    model_family="gpt",
    context_window=128_000,
    supports_tools=True,
    supports_streaming=True,
    domain_tags="[]",
    routing_preference="always",
    observer_interval=10,
    burst_interval=20,
    review_gate_timeout=600,
    turns_since_last_burst=0,
    turn_timeout_seconds=180,
    consecutive_timeouts=0,
    status="active",
    budget_hourly=None,
    budget_daily=None,
    max_tokens_per_turn=None,
    cost_per_input_token=None,
    cost_per_output_token=None,
    system_prompt="",
    api_endpoint=None,
    api_key_encrypted=None,
    auth_token_hash=None,
    last_seen=None,
    invited_by=None,
    approved_at=None,
    token_expires_at=None,
    bound_ip=None,
)


def _make_participant(**overrides) -> Participant:
    """Build a Participant by overriding selected fields on the base instance."""
    return dataclasses.replace(_BASE, **overrides)


@pytest.fixture(autouse=True)
def _reset_clamp_warned():
    """Clear the warn-once registry so tests don't leak warnings."""
    from src.orchestrator import context as ctx

    ctx._clamp_warned.clear()
    yield
    ctx._clamp_warned.clear()


def test_budget_clamps_when_declared_exceeds_catalog():
    """The Shakedown_260503-01 regression: gpt-3.5-turbo declared at 128K."""
    p = _make_participant(model="gpt-3.5-turbo", context_window=128_000)
    budget = _available_budget(p)
    # Catalog floor is 16,385. Subtract response reserve; budget must not
    # exceed the catalog ceiling.
    assert budget <= 16_385 - RESPONSE_RESERVE
    assert budget > 0


def test_budget_unchanged_when_declared_under_catalog():
    """Declared 8K < catalog 16,385 → use the smaller declared value."""
    p = _make_participant(model="gpt-3.5-turbo", context_window=8_000)
    budget = _available_budget(p)
    assert budget == 8_000 - RESPONSE_RESERVE


def test_budget_unchanged_for_unknown_model():
    """Truly unknown models trust the operator-declared value."""
    p = _make_participant(model="custom/proprietary-model", context_window=32_000)
    budget = _available_budget(p)
    # Unknown model → no clamp → declared value used minus reserve
    assert budget == 32_000 - RESPONSE_RESERVE


def test_budget_clamps_for_anthropic_when_overdeclared():
    """Same defense applies to non-OpenAI providers."""
    p = _make_participant(model="anthropic/claude-sonnet-4-6", context_window=500_000)
    budget = _available_budget(p)
    # Clamped to the 200K catalog limit
    assert budget <= 200_000 - RESPONSE_RESERVE


def test_budget_respects_custom_response_reserve():
    """max_tokens_per_turn overrides the default RESPONSE_RESERVE."""
    p = _make_participant(
        model="gpt-3.5-turbo",
        context_window=128_000,
        max_tokens_per_turn=4_000,
    )
    budget = _available_budget(p)
    # Window clamped to 16,385; reserve = 4,000
    assert budget <= 16_385 - 4_000


def test_clamp_warning_emitted_once_per_participant(caplog):
    """First overshoot logs WARNING; subsequent calls stay silent."""
    p = _make_participant(model="gpt-3.5-turbo", context_window=128_000)
    with caplog.at_level(logging.WARNING, logger="src.orchestrator.context"):
        _available_budget(p)
        _available_budget(p)
        _available_budget(p)
    # Exactly one warning, not three
    matching = [r for r in caplog.records if "clamping" in r.getMessage()]
    assert len(matching) == 1
    assert "128000" in matching[0].getMessage()
    assert "16385" in matching[0].getMessage()
    assert "gpt-3.5-turbo" in matching[0].getMessage()


def test_clamp_warning_distinct_per_participant(caplog):
    """Different (session, participant) pairs each get their own warning."""
    p1 = _make_participant(id="p1", session_id="s1", model="gpt-3.5-turbo", context_window=128_000)
    p2 = _make_participant(id="p2", session_id="s1", model="gpt-3.5-turbo", context_window=128_000)
    with caplog.at_level(logging.WARNING, logger="src.orchestrator.context"):
        _available_budget(p1)
        _available_budget(p2)
    matching = [r for r in caplog.records if "clamping" in r.getMessage()]
    assert len(matching) == 2


def test_no_warning_when_declared_at_or_below_catalog(caplog):
    """Correctly-configured participants must not produce log noise."""
    p = _make_participant(model="gpt-3.5-turbo", context_window=16_385)
    with caplog.at_level(logging.WARNING, logger="src.orchestrator.context"):
        _available_budget(p)
    matching = [r for r in caplog.records if "clamping" in r.getMessage()]
    assert len(matching) == 0


def test_budget_floor_at_zero_when_reserve_exceeds_window():
    """Pathological config: reserve larger than clamped window → 0, not negative."""
    p = _make_participant(
        model="gpt-3.5-turbo",
        context_window=128_000,
        max_tokens_per_turn=20_000,  # exceeds 16,385 catalog
    )
    assert _available_budget(p) == 0
