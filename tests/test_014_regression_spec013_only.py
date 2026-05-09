"""SC-004 regression canary: spec 014 controller is inactive when unconfigured.

The contract: when ALL ``SACP_DMA_*`` and ``SACP_AUTO_MODE_ENABLED`` env
vars are unset, observable session behavior MUST equal the spec-013-only
baseline. Spec 013's three mechanisms (batching cadence, convergence
threshold override, observer downgrade) keep their semantics; no
controller task spawns; no ``mode_*`` audit rows are written.

This test is the canary for FR-015. If it ever fails after Phase 2 lands,
the additive-when-unset guarantee has been broken.
"""

from __future__ import annotations

import pytest

import src.auth  # noqa: F401  -- prime auth package against loop.py circular
from src.orchestrator.high_traffic import HighTrafficSessionConfig
from src.orchestrator.loop import (
    _convergence_threshold_kwarg,
    _maybe_make_batch_scheduler,
)


def _clear_all_dma_and_high_traffic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every env var that could activate the controller or 013 mechanisms."""
    for name in (
        "SACP_DMA_TURN_RATE_THRESHOLD_TPM",
        "SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD",
        "SACP_DMA_QUEUE_DEPTH_THRESHOLD",
        "SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD",
        "SACP_DMA_DWELL_TIME_S",
        "SACP_AUTO_MODE_ENABLED",
        "SACP_HIGH_TRAFFIC_BATCH_CADENCE_S",
        "SACP_CONVERGENCE_THRESHOLD_OVERRIDE",
        "SACP_OBSERVER_DOWNGRADE_THRESHOLDS",
        "SACP_TOPOLOGY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_sc004_high_traffic_config_is_none_when_all_unset(monkeypatch) -> None:
    """Spec 013 baseline: resolved config returns None — additive guarantee."""
    _clear_all_dma_and_high_traffic_env(monkeypatch)
    assert HighTrafficSessionConfig.resolve_from_env() is None


def test_sc004_batch_scheduler_is_none_when_all_unset(monkeypatch) -> None:
    """Spec 013 baseline: no batching scheduler when env unset."""
    _clear_all_dma_and_high_traffic_env(monkeypatch)
    config = HighTrafficSessionConfig.resolve_from_env()
    assert _maybe_make_batch_scheduler(config) is None


def test_sc004_convergence_kwarg_empty_when_all_unset(monkeypatch) -> None:
    """Spec 013 baseline: no convergence-threshold override kwarg."""
    _clear_all_dma_and_high_traffic_env(monkeypatch)
    config = HighTrafficSessionConfig.resolve_from_env()
    assert _convergence_threshold_kwarg(config) == {}


def test_sc004_controller_inactive_when_no_signals_configured(monkeypatch) -> None:
    """FR-015 + SC-004: with all SACP_DMA_* unset, the controller refuses to run.

    The check is structural — ``DmaController.is_active_from_env()`` returns
    False when zero signal thresholds are configured. The controller's start
    path uses this gate so no asyncio task ever spawns in the unset case.
    """
    _clear_all_dma_and_high_traffic_env(monkeypatch)
    from src.orchestrator.dma_controller import DmaController

    assert DmaController.is_active_from_env() is False


def test_sc004_controller_inactive_in_topology_7(monkeypatch) -> None:
    """Research §7 + V12: controller is inactive in topology 7 even with thresholds set.

    Forward-proof gate: the controller refuses to spawn when SACP_TOPOLOGY=7
    is set, regardless of whether SACP_DMA_* thresholds are configured.
    """
    _clear_all_dma_and_high_traffic_env(monkeypatch)
    monkeypatch.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    monkeypatch.setenv("SACP_TOPOLOGY", "7")
    from src.orchestrator.dma_controller import DmaController

    assert DmaController.is_active_from_env() is False


def test_sc004_no_mode_audit_helpers_called_when_unset(monkeypatch) -> None:
    """FR-015: when no SACP_DMA_* env vars are set, the controller never invokes
    its audit-emission path. Structural assertion via the active-gate check.
    """
    _clear_all_dma_and_high_traffic_env(monkeypatch)
    from src.orchestrator.dma_controller import DmaController

    # The gate is the single point that prevents emission; if it returns
    # False, every audit-write path is unreachable. Asserts the contract
    # without spinning up a real session.
    assert DmaController.is_active_from_env() is False


def test_sc004_advisory_only_when_threshold_set_but_auto_unset(monkeypatch) -> None:
    """Setting only a threshold puts the controller in advisory mode (no transitions).

    FR-011: in advisory mode, the controller MUST NOT alter spec-013 env vars
    or invoke spec-013 mechanism activation paths. The active-from-env gate
    returns True (controller is active) while ``auto_mode_enabled`` is False.
    """
    _clear_all_dma_and_high_traffic_env(monkeypatch)
    monkeypatch.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    from src.orchestrator.dma_controller import DmaController, auto_mode_enabled

    assert DmaController.is_active_from_env() is True
    assert auto_mode_enabled() is False
