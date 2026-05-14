# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 016 -- metric counter and gauge increment tests.

Covers:
- Token counter increments on dispatch (US1)
- Cost counter increments on dispatch (US1)
- Provider request counter increments on success and failure (US2)
- Rate-limit rejection counter increments (US3 -- extends spec 019 contract)
- Routing decision counter increments (US3)
- Convergence gauge updates (US3)
- Validator coverage for the 3 new SACP_METRICS_* env vars (SC-006)
"""

from __future__ import annotations

import pytest
from prometheus_client import generate_latest

from src.observability.metrics import (
    increment_network_rate_limit_rejection,
    reset_for_tests,
    sacp_rate_limit_rejection_total,
)
from src.observability.metrics_registry import (
    get_registry,
    inc_participant_cost,
    inc_participant_tokens,
    inc_provider_request,
    inc_routing_decision,
    normalize_provider_kind,
    participant_id_hash,
    reset_registry_for_tests,
    set_convergence_similarity,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_registry_for_tests()


# ---------------------------------------------------------------------------
# US1: token + cost counters
# ---------------------------------------------------------------------------


def test_participant_tokens_prompt_increments() -> None:
    inc_participant_tokens(
        session_id="s1",
        participant_id="p1",
        prompt_tokens=500,
        completion_tokens=0,
    )
    output = generate_latest(get_registry()).decode()
    assert "sacp_participant_tokens_total" in output
    assert 'direction="prompt"' in output


def test_participant_tokens_completion_increments() -> None:
    inc_participant_tokens(
        session_id="s1",
        participant_id="p1",
        prompt_tokens=0,
        completion_tokens=200,
    )
    output = generate_latest(get_registry()).decode()
    assert 'direction="completion"' in output


def test_participant_tokens_both_directions() -> None:
    inc_participant_tokens(
        session_id="s1",
        participant_id="p1",
        prompt_tokens=100,
        completion_tokens=50,
    )
    output = generate_latest(get_registry()).decode()
    assert 'direction="prompt"' in output
    assert 'direction="completion"' in output


def test_participant_tokens_uses_hash_not_raw_id() -> None:
    raw_id = "raw-participant-uuid-here"
    inc_participant_tokens(
        session_id="s1",
        participant_id=raw_id,
        prompt_tokens=10,
        completion_tokens=5,
    )
    output = generate_latest(get_registry()).decode()
    assert raw_id not in output
    assert participant_id_hash(raw_id) in output


def test_participant_cost_increments() -> None:
    inc_participant_cost(session_id="s1", participant_id="p1", cost_usd=0.05)
    output = generate_latest(get_registry()).decode()
    assert "sacp_participant_cost_usd_total" in output


def test_participant_cost_zero_does_not_register() -> None:
    inc_participant_cost(session_id="s1", participant_id="p1", cost_usd=0.0)
    output = generate_latest(get_registry()).decode()
    # Zero cost should not create a series (cost <= 0 is skipped)
    # Counter may still show help/type headers even with no series
    assert "s1" not in output or "sacp_participant_cost_usd_total" not in output


# ---------------------------------------------------------------------------
# US2: provider request counter
# ---------------------------------------------------------------------------


def test_provider_request_success_increments() -> None:
    inc_provider_request(provider_kind="litellm", outcome="success")
    output = generate_latest(get_registry()).decode()
    assert "sacp_provider_request_total" in output
    assert 'provider_kind="litellm"' in output
    assert 'outcome="success"' in output


def test_provider_request_error_5xx_increments() -> None:
    inc_provider_request(provider_kind="litellm", outcome="error_5xx")
    output = generate_latest(get_registry()).decode()
    assert 'outcome="error_5xx"' in output


def test_provider_request_timeout_increments() -> None:
    inc_provider_request(provider_kind="mock", outcome="timeout")
    output = generate_latest(get_registry()).decode()
    assert 'provider_kind="mock"' in output
    assert 'outcome="timeout"' in output


def test_normalize_provider_kind_litellm() -> None:
    assert normalize_provider_kind("litellm") == "litellm"
    assert normalize_provider_kind("LiteLLM") == "litellm"


def test_normalize_provider_kind_mock() -> None:
    assert normalize_provider_kind("mock") == "mock"


def test_normalize_provider_kind_other() -> None:
    assert normalize_provider_kind("some-custom-provider") == "other"
    assert normalize_provider_kind(None) == "other"
    assert normalize_provider_kind("") == "other"


# ---------------------------------------------------------------------------
# US3: rate-limit rejection counter (extends spec 019 contract)
# ---------------------------------------------------------------------------


def test_rate_limit_rejection_increments() -> None:
    increment_network_rate_limit_rejection()
    val = sacp_rate_limit_rejection_total.get_sample_value(
        {"endpoint_class": "network_per_ip", "exempt_match": "false"},
    )
    assert val == 1.0


def test_rate_limit_rejection_accumulates() -> None:
    for _ in range(5):
        increment_network_rate_limit_rejection()
    val = sacp_rate_limit_rejection_total.get_sample_value(
        {"endpoint_class": "network_per_ip", "exempt_match": "false"},
    )
    assert val == 5.0


def test_rate_limit_reset_for_tests_clears_counter() -> None:
    increment_network_rate_limit_rejection()
    reset_for_tests()
    val = sacp_rate_limit_rejection_total.get_sample_value(
        {"endpoint_class": "network_per_ip", "exempt_match": "false"},
    )
    assert val is None


# ---------------------------------------------------------------------------
# US3: routing counter
# ---------------------------------------------------------------------------


def test_routing_decision_dispatched_increments() -> None:
    inc_routing_decision(session_id="s1", routing_mode="dispatched", skip_reason="")
    output = generate_latest(get_registry()).decode()
    assert "sacp_routing_decision_total" in output
    assert 'routing_mode="dispatched"' in output


def test_routing_decision_skipped_increments() -> None:
    inc_routing_decision(session_id="s1", routing_mode="skipped", skip_reason="circuit_open")
    output = generate_latest(get_registry()).decode()
    assert 'skip_reason="circuit_open"' in output


# ---------------------------------------------------------------------------
# US3: convergence gauge
# ---------------------------------------------------------------------------


def test_convergence_gauge_set() -> None:
    set_convergence_similarity(session_id="s1", similarity=0.75)
    output = generate_latest(get_registry()).decode()
    assert "sacp_session_convergence_similarity" in output
    assert "0.75" in output


def test_convergence_gauge_updates() -> None:
    set_convergence_similarity(session_id="s1", similarity=0.4)
    set_convergence_similarity(session_id="s1", similarity=0.9)
    output = generate_latest(get_registry()).decode()
    # Last value should be 0.9; 0.4 should be gone (gauge overwrite)
    assert "0.9" in output


def test_convergence_gauge_absent_before_set() -> None:
    """Cold session: gauge must not have a value before process_turn fires."""
    output = generate_latest(get_registry()).decode()
    # After reset, no session-scoped series exist
    assert "sacp_session_convergence_similarity" not in output or "s1" not in output


# ---------------------------------------------------------------------------
# SC-006: validator coverage for SACP_METRICS_* vars
# ---------------------------------------------------------------------------


def test_validator_metrics_enabled_accepts_true(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.validators import validate_metrics_enabled

    monkeypatch.setenv("SACP_METRICS_ENABLED", "true")
    assert validate_metrics_enabled() is None


def test_validator_metrics_enabled_accepts_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.validators import validate_metrics_enabled

    monkeypatch.setenv("SACP_METRICS_ENABLED", "false")
    assert validate_metrics_enabled() is None


def test_validator_metrics_enabled_accepts_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.validators import validate_metrics_enabled

    monkeypatch.delenv("SACP_METRICS_ENABLED", raising=False)
    assert validate_metrics_enabled() is None


def test_validator_metrics_enabled_rejects_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.validators import validate_metrics_enabled

    monkeypatch.setenv("SACP_METRICS_ENABLED", "yes")
    result = validate_metrics_enabled()
    assert result is not None
    assert "SACP_METRICS_ENABLED" in result.var_name


def test_validator_metrics_grace_s_accepts_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.validators import validate_metrics_session_grace_s

    monkeypatch.setenv("SACP_METRICS_SESSION_GRACE_S", "30")
    assert validate_metrics_session_grace_s() is None


def test_validator_metrics_grace_s_rejects_below_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.validators import validate_metrics_session_grace_s

    monkeypatch.setenv("SACP_METRICS_SESSION_GRACE_S", "4")
    result = validate_metrics_session_grace_s()
    assert result is not None


def test_validator_metrics_grace_s_rejects_above_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.validators import validate_metrics_session_grace_s

    monkeypatch.setenv("SACP_METRICS_SESSION_GRACE_S", "301")
    result = validate_metrics_session_grace_s()
    assert result is not None


def test_validator_metrics_bind_path_accepts_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.validators import validate_metrics_bind_path

    monkeypatch.setenv("SACP_METRICS_BIND_PATH", "/metrics")
    assert validate_metrics_bind_path() is None


def test_validator_metrics_bind_path_rejects_no_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.validators import validate_metrics_bind_path

    monkeypatch.setenv("SACP_METRICS_BIND_PATH", "metrics")
    result = validate_metrics_bind_path()
    assert result is not None


def test_validator_metrics_bind_path_rejects_health_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.config.validators import validate_metrics_bind_path

    monkeypatch.setenv("SACP_METRICS_BIND_PATH", "/health")
    result = validate_metrics_bind_path()
    assert result is not None
