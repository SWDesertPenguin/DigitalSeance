"""Polish stress tests: throttle cap + unavailability rate-limit (spec 014).

Covers:
    - SC-009: signal oscillation faster than 12 dpm caps recommendations
      at ``cap * minutes_observed`` and emits at most one
      ``decision_cycle_throttled`` per dwell window.
    - FR-013: a permanently unavailable source emits exactly one
      ``signal_source_unavailable`` per dwell window.
    - Topology-7 forward-proof gate verified end-to-end (T035): when
      ``SACP_TOPOLOGY=7`` is set the controller refuses to spawn even
      with thresholds configured.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.orchestrator.dma_controller import (
    DecisionCycleBudget,
    DmaController,
    run_decision_cycle,
)
from src.orchestrator.high_traffic import HighTrafficRuntime

UTC = UTC


def _fixed_clock(now: datetime):
    state = {"now": now}

    def reader() -> datetime:
        return state["now"]

    return reader, state


def test_decision_cycle_budget_caps_at_one_token_per_interval() -> None:
    """Capacity-1 token bucket: try_acquire returns False until refill."""
    budget = DecisionCycleBudget(cap_per_minute=12)
    # First acquire admits.
    assert budget.try_acquire() is True
    # Second acquire (immediate) is rejected — bucket is empty.
    assert budget.try_acquire() is False


@pytest.mark.asyncio
async def test_throttle_emission_rate_limited_per_dwell(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """SC-009: many throttled cycles -> at most one decision_cycle_throttled."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "120")

    now, _ = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = DmaController(
        session_id="s1",
        runtime=HighTrafficRuntime(config=None),
        signal_sources=dma_synthetic_sources,
        emitter=dma_recording_emitter,
        decisions_per_minute=12,
        clock=now,
    )

    # First cycle admits and consumes the bucket.
    dma_signal_feeds["turn_rate"].push(42)
    controller.budget._next_eligible_at = -1.0
    await run_decision_cycle(controller)

    # Now drive ten more cycles without advancing the bucket clock — they
    # all hit the throttle path. Only one audit emission should land.
    for _ in range(10):
        await run_decision_cycle(controller)

    assert dma_recording_emitter.actions().count("decision_cycle_throttled") == 1


@pytest.mark.asyncio
async def test_unavailable_source_silent_within_dwell(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """FR-013: unavailable source emits once per dwell window per signal per session."""
    dma_clear_env.setenv("SACP_DMA_QUEUE_DEPTH_THRESHOLD", "10")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "120")
    dma_signal_feeds["queue_depth"].set_available(False)

    now, state = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = DmaController(
        session_id="s2",
        runtime=HighTrafficRuntime(config=None),
        signal_sources=dma_synthetic_sources,
        emitter=dma_recording_emitter,
        decisions_per_minute=12,
        clock=now,
    )

    # Many cycles inside dwell — exactly one unavailability event.
    for _ in range(20):
        controller.budget._next_eligible_at = -1.0
        await run_decision_cycle(controller)
        state["now"] = state["now"] + timedelta(seconds=5)

    assert dma_recording_emitter.actions().count("signal_source_unavailable") == 1


def test_topology_7_disables_controller(monkeypatch) -> None:
    """Research §7 / T035: SACP_TOPOLOGY=7 disables the controller entirely."""
    monkeypatch.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    monkeypatch.setenv("SACP_TOPOLOGY", "7")
    assert DmaController.is_active_from_env() is False


def test_topology_other_values_do_not_disable(monkeypatch) -> None:
    """Topology values 1-6 do not block the controller."""
    monkeypatch.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    for topology in ("", "1", "3", "6"):
        monkeypatch.setenv("SACP_TOPOLOGY", topology)
        assert DmaController.is_active_from_env() is True


@pytest.mark.asyncio
async def test_routing_log_stage_timings_captured(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """V14 / FR-012: per-cycle and per-signal timings recorded into routing_log."""
    from src.orchestrator.timing import get_timings, start_turn

    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")

    start_turn()
    now, _ = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = DmaController(
        session_id="s3",
        runtime=HighTrafficRuntime(config=None),
        signal_sources=dma_synthetic_sources,
        emitter=dma_recording_emitter,
        decisions_per_minute=12,
        clock=now,
    )
    dma_signal_feeds["turn_rate"].push(42)
    controller.budget._next_eligible_at = -1.0
    await run_decision_cycle(controller)

    timings = get_timings()
    assert "dma_controller_eval_ms" in timings
    assert "dma_signal_turn_rate_ms" in timings
