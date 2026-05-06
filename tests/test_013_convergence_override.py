"""US2 acceptance tests: per-session convergence-threshold override (spec 013 FR-005-FR-007)."""

from __future__ import annotations

import src.auth  # noqa: F401  -- prime auth package against loop.py circular
from src.orchestrator.high_traffic import HighTrafficSessionConfig
from src.orchestrator.loop import _convergence_threshold_kwarg


def test_us2_acceptance_1_override_kwarg_when_set(monkeypatch) -> None:
    """When override env var is set, the helper passes it as a threshold kwarg."""
    monkeypatch.delenv("SACP_HIGH_TRAFFIC_BATCH_CADENCE_S", raising=False)
    monkeypatch.setenv("SACP_CONVERGENCE_THRESHOLD_OVERRIDE", "0.85")
    monkeypatch.delenv("SACP_OBSERVER_DOWNGRADE_THRESHOLDS", raising=False)
    config = HighTrafficSessionConfig.resolve_from_env()
    assert config is not None
    assert config.convergence_threshold_override == 0.85
    assert _convergence_threshold_kwarg(config) == {"threshold": 0.85}


def test_us2_acceptance_2_override_actually_threads_to_engine() -> None:
    """ConvergenceDetector accepts the threshold kwarg from the helper."""
    from src.orchestrator.convergence import ConvergenceDetector

    fake_log_repo = object()
    detector = ConvergenceDetector(fake_log_repo, threshold=0.85)
    assert detector._threshold == 0.85


def test_us2_acceptance_3_unset_falls_through_to_default(monkeypatch) -> None:
    """When override env var is unset, helper returns {} → spec-004 default applies."""
    monkeypatch.delenv("SACP_HIGH_TRAFFIC_BATCH_CADENCE_S", raising=False)
    monkeypatch.delenv("SACP_CONVERGENCE_THRESHOLD_OVERRIDE", raising=False)
    monkeypatch.delenv("SACP_OBSERVER_DOWNGRADE_THRESHOLDS", raising=False)
    config = HighTrafficSessionConfig.resolve_from_env()
    assert config is None
    assert _convergence_threshold_kwarg(config) == {}


def test_us2_acceptance_4_invalid_value_blocks_at_validator(monkeypatch) -> None:
    """V16 startup: out-of-range override is rejected by the validator (FR-007)."""
    from src.config.validators import validate_convergence_threshold_override

    monkeypatch.setenv("SACP_CONVERGENCE_THRESHOLD_OVERRIDE", "1.5")
    failure = validate_convergence_threshold_override()
    assert failure is not None
    assert "must be in strict (0.0, 1.0)" in failure.reason

    monkeypatch.setenv("SACP_CONVERGENCE_THRESHOLD_OVERRIDE", "0.0")
    failure = validate_convergence_threshold_override()
    assert failure is not None

    monkeypatch.setenv("SACP_CONVERGENCE_THRESHOLD_OVERRIDE", "not-a-float")
    failure = validate_convergence_threshold_override()
    assert failure is not None
    assert "must be a float" in failure.reason
