# SPDX-License-Identifier: AGPL-3.0-or-later

"""V16 startup-validator tests for spec 014 (dynamic mode assignment).

Six new SACP_DMA_* / SACP_AUTO_MODE_ENABLED env vars per spec 014 FR-014.
Each validator follows the spec-013 pattern: unset = no-op, set-but-bad =
ValidationFailure with the var name and a human-readable reason.
"""

from __future__ import annotations

from src.config import validators


def test_turn_rate_threshold_unset_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", raising=False)
    assert validators.validate_dma_turn_rate_threshold_tpm() is None


def test_turn_rate_threshold_in_range(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    assert validators.validate_dma_turn_rate_threshold_tpm() is None


def test_turn_rate_threshold_below_range(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "0")
    failure = validators.validate_dma_turn_rate_threshold_tpm()
    assert failure is not None
    assert "must be in [1, 600]" in failure.reason


def test_turn_rate_threshold_above_range(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "601")
    failure = validators.validate_dma_turn_rate_threshold_tpm()
    assert failure is not None


def test_turn_rate_threshold_non_integer(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "thirty")
    failure = validators.validate_dma_turn_rate_threshold_tpm()
    assert failure is not None
    assert "must be integer" in failure.reason


def test_convergence_derivative_threshold_unset_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD", raising=False)
    assert validators.validate_dma_convergence_derivative_threshold() is None


def test_convergence_derivative_threshold_in_range(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD", "0.15")
    assert validators.validate_dma_convergence_derivative_threshold() is None


def test_convergence_derivative_threshold_upper_inclusive(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD", "1.0")
    assert validators.validate_dma_convergence_derivative_threshold() is None


def test_convergence_derivative_threshold_lower_exclusive(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD", "0.0")
    failure = validators.validate_dma_convergence_derivative_threshold()
    assert failure is not None
    assert "must be in (0.0, 1.0]" in failure.reason


def test_convergence_derivative_threshold_above_one(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD", "1.5")
    failure = validators.validate_dma_convergence_derivative_threshold()
    assert failure is not None


def test_convergence_derivative_threshold_non_float(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD", "not-a-float")
    failure = validators.validate_dma_convergence_derivative_threshold()
    assert failure is not None
    assert "must be a float" in failure.reason


def test_queue_depth_threshold_unset_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("SACP_DMA_QUEUE_DEPTH_THRESHOLD", raising=False)
    assert validators.validate_dma_queue_depth_threshold() is None


def test_queue_depth_threshold_in_range(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_QUEUE_DEPTH_THRESHOLD", "10")
    assert validators.validate_dma_queue_depth_threshold() is None


def test_queue_depth_threshold_below_range(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_QUEUE_DEPTH_THRESHOLD", "0")
    failure = validators.validate_dma_queue_depth_threshold()
    assert failure is not None
    assert "must be in [1, 1000]" in failure.reason


def test_queue_depth_threshold_above_range(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_QUEUE_DEPTH_THRESHOLD", "1001")
    failure = validators.validate_dma_queue_depth_threshold()
    assert failure is not None


def test_density_anomaly_rate_threshold_unset_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD", raising=False)
    assert validators.validate_dma_density_anomaly_rate_threshold() is None


def test_density_anomaly_rate_threshold_in_range(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD", "5")
    assert validators.validate_dma_density_anomaly_rate_threshold() is None


def test_density_anomaly_rate_threshold_above_range(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD", "61")
    failure = validators.validate_dma_density_anomaly_rate_threshold()
    assert failure is not None
    assert "must be in [1, 60]" in failure.reason


def test_dwell_time_unset_is_noop_in_advisory(monkeypatch) -> None:
    monkeypatch.delenv("SACP_DMA_DWELL_TIME_S", raising=False)
    monkeypatch.delenv("SACP_AUTO_MODE_ENABLED", raising=False)
    assert validators.validate_dma_dwell_time_s() is None


def test_dwell_time_in_range(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_DWELL_TIME_S", "120")
    assert validators.validate_dma_dwell_time_s() is None


def test_dwell_time_below_range(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_DWELL_TIME_S", "29")
    failure = validators.validate_dma_dwell_time_s()
    assert failure is not None
    assert "must be in [30, 1800]" in failure.reason


def test_dwell_time_above_range(monkeypatch) -> None:
    monkeypatch.setenv("SACP_DMA_DWELL_TIME_S", "1801")
    failure = validators.validate_dma_dwell_time_s()
    assert failure is not None


def test_auto_mode_unset_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("SACP_AUTO_MODE_ENABLED", raising=False)
    assert validators.validate_auto_mode_enabled() is None


def test_auto_mode_false_no_dwell_required(monkeypatch) -> None:
    monkeypatch.setenv("SACP_AUTO_MODE_ENABLED", "false")
    monkeypatch.delenv("SACP_DMA_DWELL_TIME_S", raising=False)
    assert validators.validate_auto_mode_enabled() is None


def test_auto_mode_true_with_dwell_passes(monkeypatch) -> None:
    monkeypatch.setenv("SACP_AUTO_MODE_ENABLED", "true")
    monkeypatch.setenv("SACP_DMA_DWELL_TIME_S", "120")
    assert validators.validate_auto_mode_enabled() is None


def test_auto_mode_true_without_dwell_fails_fr010(monkeypatch) -> None:
    """FR-010 cross-validator: SACP_AUTO_MODE_ENABLED=true requires SACP_DMA_DWELL_TIME_S."""
    monkeypatch.setenv("SACP_AUTO_MODE_ENABLED", "true")
    monkeypatch.delenv("SACP_DMA_DWELL_TIME_S", raising=False)
    failure = validators.validate_auto_mode_enabled()
    assert failure is not None
    assert "SACP_DMA_DWELL_TIME_S" in failure.reason
    assert "auto-apply requires" in failure.reason


def test_auto_mode_invalid_value_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_AUTO_MODE_ENABLED", "True")  # case-sensitive
    failure = validators.validate_auto_mode_enabled()
    assert failure is not None
    assert "case-sensitive" in failure.reason


def test_auto_mode_yes_no_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_AUTO_MODE_ENABLED", "yes")
    failure = validators.validate_auto_mode_enabled()
    assert failure is not None


def test_all_six_validators_registered_in_tuple() -> None:
    """V16 contract: validators only fire if registered in VALIDATORS."""
    registered = {v.__name__ for v in validators.VALIDATORS}
    expected = {
        "validate_dma_turn_rate_threshold_tpm",
        "validate_dma_convergence_derivative_threshold",
        "validate_dma_queue_depth_threshold",
        "validate_dma_density_anomaly_rate_threshold",
        "validate_dma_dwell_time_s",
        "validate_auto_mode_enabled",
    }
    missing = expected - registered
    assert not missing, f"validators not registered in VALIDATORS tuple: {sorted(missing)}"
