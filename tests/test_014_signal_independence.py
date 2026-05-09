# SPDX-License-Identifier: AGPL-3.0-or-later

"""US3 acceptance tests: per-signal-source independence (spec 014).

Four spec acceptance scenarios:
    1. Turn-rate-only triggers ``trigger=turn_rate``.
    2. Convergence-only triggers ``trigger=convergence_derivative``.
    3. Multiple simultaneous signals -> alphabetical ``triggers[]``.
    4. Unavailable source emits one rate-limited ``signal_source_unavailable``,
       then stays silent within dwell.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.orchestrator.dma_controller import DmaController, run_decision_cycle
from src.orchestrator.high_traffic import HighTrafficRuntime

UTC = UTC


def _fixed_clock(now: datetime):
    state = {"now": now}

    def reader() -> datetime:
        return state["now"]

    return reader, state


def _bare_runtime() -> HighTrafficRuntime:
    return HighTrafficRuntime(config=None)


def _make_controller(runtime, sources, emitter, clock, *, session_id: str) -> DmaController:
    return DmaController(
        session_id=session_id,
        runtime=runtime,
        signal_sources=sources,
        emitter=emitter,
        decisions_per_minute=12,
        clock=clock,
    )


async def _run_cycle(controller) -> None:
    """Bypass the 12-dpm budget and drive a single decision cycle."""
    controller.budget._next_eligible_at = -1.0
    await run_decision_cycle(controller)


@pytest.mark.asyncio
async def test_us3_turn_rate_only_triggers(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """Only SACP_DMA_TURN_RATE_THRESHOLD_TPM set -> trigger names turn_rate only."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")

    now, _ = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = _make_controller(
        _bare_runtime(), dma_synthetic_sources, dma_recording_emitter, now, session_id="s1"
    )

    dma_signal_feeds["turn_rate"].push(42)
    # Other feeds receive values too but their adapters are not configured.
    dma_signal_feeds["convergence_derivative"].push(0.9)
    dma_signal_feeds["queue_depth"].push(99)
    dma_signal_feeds["density_anomaly"].push(50)

    controller.budget._next_eligible_at = -1.0
    await run_decision_cycle(controller)

    rec_call = next(c for c in dma_recording_emitter.calls if c[0] == "mode_recommendation")
    triggers = rec_call[1]["outcome"].triggers
    assert triggers == ["turn_rate"]
    obs_signals = [o.signal_name for o in rec_call[1]["outcome"].signal_observations]
    assert obs_signals == ["turn_rate"]


@pytest.mark.asyncio
async def test_us3_convergence_only_triggers(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """Only convergence-derivative threshold set -> trigger names that signal only."""
    dma_clear_env.setenv("SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD", "0.15")

    now, state = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = _make_controller(
        _bare_runtime(), dma_synthetic_sources, dma_recording_emitter, now, session_id="s2"
    )

    # Drive the convergence-derivative signal: window must have at least 2
    # samples differing by >= 0.15 (the adapter's evaluate rule).
    for value in (0.10, 0.30, 0.55):
        dma_signal_feeds["convergence_derivative"].push(value)
        controller.budget._next_eligible_at = -1.0
        await run_decision_cycle(controller)
        state["now"] = state["now"] + timedelta(seconds=5)

    rec_calls = [c for c in dma_recording_emitter.calls if c[0] == "mode_recommendation"]
    assert rec_calls, "expected at least one recommendation"
    triggers = rec_calls[0][1]["outcome"].triggers
    assert triggers == ["convergence_derivative"]


@pytest.mark.asyncio
async def test_us3_multiple_signals_trigger_alphabetically(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """All four configured + multiple cross simultaneously -> alphabetical triggers[]."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    dma_clear_env.setenv("SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD", "0.15")
    dma_clear_env.setenv("SACP_DMA_QUEUE_DEPTH_THRESHOLD", "10")
    dma_clear_env.setenv("SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD", "5")

    now, state = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = _make_controller(
        _bare_runtime(), dma_synthetic_sources, dma_recording_emitter, now, session_id="s3"
    )

    # Two cycles so convergence-derivative window has the [start, end] pair its check needs.
    for i in range(2):
        dma_signal_feeds["turn_rate"].push(42)
        dma_signal_feeds["convergence_derivative"].push(0.10 + i * 0.30)
        dma_signal_feeds["queue_depth"].push(99)
        dma_signal_feeds["density_anomaly"].push(20)
        await _run_cycle(controller)
        state["now"] = state["now"] + timedelta(seconds=5)

    rec_call = next(c for c in dma_recording_emitter.calls if c[0] == "mode_recommendation")
    triggers = rec_call[1]["outcome"].triggers
    obs_names = [o.signal_name for o in rec_call[1]["outcome"].signal_observations]
    # Acceptance scenario 3: alphabetical triggers[] AND matching observation order.
    assert triggers == sorted(triggers)
    assert obs_names == sorted(obs_names)


@pytest.mark.asyncio
async def test_us3_unavailable_source_emits_one_rate_limited_event(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """Permanently unavailable source -> exactly one signal_source_unavailable per dwell."""
    # Configure queue_depth but make its data feed unavailable (no scheduler).
    dma_clear_env.setenv("SACP_DMA_QUEUE_DEPTH_THRESHOLD", "10")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "120")
    # Mark the queue_depth feed unavailable; the adapter will report
    # is_available()=False because the availability lambda returns False.
    dma_signal_feeds["queue_depth"].set_available(False)

    now, state = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = _make_controller(
        _bare_runtime(), dma_synthetic_sources, dma_recording_emitter, now, session_id="s4"
    )

    # Multiple cycles — only one unavailable event per dwell window.
    for _ in range(5):
        controller.budget._next_eligible_at = -1.0
        await run_decision_cycle(controller)
        state["now"] = state["now"] + timedelta(seconds=5)

    unavailable_count = dma_recording_emitter.actions().count("signal_source_unavailable")
    assert unavailable_count == 1
    unavail_call = next(
        c for c in dma_recording_emitter.calls if c[0] == "signal_source_unavailable"
    )
    assert unavail_call[1]["signal_name"] == "queue_depth"


@pytest.mark.asyncio
async def test_us3_fr004_unset_threshold_contributes_nothing(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """FR-004 absent-not-zero: unset threshold -> signal not in audit event."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    # Explicitly leave queue_depth and others UNSET.

    now, _ = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = _make_controller(
        _bare_runtime(), dma_synthetic_sources, dma_recording_emitter, now, session_id="s5"
    )

    # Push a sample that *would* cross the unset queue_depth threshold.
    dma_signal_feeds["turn_rate"].push(42)
    dma_signal_feeds["queue_depth"].push(9999)
    controller.budget._next_eligible_at = -1.0
    await run_decision_cycle(controller)

    rec_call = next(c for c in dma_recording_emitter.calls if c[0] == "mode_recommendation")
    triggers = rec_call[1]["outcome"].triggers
    assert "queue_depth" not in triggers
    obs_names = [o.signal_name for o in rec_call[1]["outcome"].signal_observations]
    assert "queue_depth" not in obs_names
