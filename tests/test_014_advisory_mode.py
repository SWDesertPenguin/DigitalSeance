# SPDX-License-Identifier: AGPL-3.0-or-later

"""US1 acceptance tests: advisory-mode recommendations (spec 014).

Three spec acceptance scenarios:
    1. Sustained over-threshold turn rate -> ENGAGE recommendation.
    2. Sustained under-threshold turn rate after engagement -> DISENGAGE.
    3. No SACP_DMA_* thresholds set -> controller inactive.

Spec FR-011 boundary: in advisory mode, the controller MUST NOT call
``engage_mechanism`` / ``disengage_mechanism`` and MUST NOT write
``mode_transition`` rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.orchestrator.dma_controller import (
    DmaController,
    auto_mode_enabled,
    run_decision_cycle,
)
from src.orchestrator.high_traffic import HighTrafficRuntime, HighTrafficSessionConfig

UTC = UTC


def _fixed_clock(now: datetime):
    """Return a callable that yields ``now`` (mutable closure for test drift)."""
    state = {"now": now}

    def reader() -> datetime:
        return state["now"]

    return reader, state


def _bare_runtime() -> HighTrafficRuntime:
    """No spec-013 config — controller advisory boundary still works."""
    return HighTrafficRuntime(config=None)


def _config_runtime() -> HighTrafficRuntime:
    """Full spec-013 config — verifies advisory mode does NOT mutate flags."""
    config = HighTrafficSessionConfig(
        batch_cadence_s=5,
        convergence_threshold_override=0.7,
        observer_downgrade=None,
    )
    return HighTrafficRuntime(config=config)


def _make_controller(runtime, sources, emitter, clock, *, session_id: str) -> DmaController:
    """Default 12-dpm controller; tests bypass the budget via _next_eligible_at."""
    return DmaController(
        session_id=session_id,
        runtime=runtime,
        signal_sources=sources,
        emitter=emitter,
        decisions_per_minute=12,
        clock=clock,
    )


async def _drive_cycles(controller, feeds, signal: str, value, state, *, count: int) -> None:
    """Push value into ``signal`` and run one decision cycle ``count`` times, advancing 5s each."""
    for _ in range(count):
        feeds[signal].push(value)
        controller.budget._next_eligible_at = -1.0
        await run_decision_cycle(controller)
        state["now"] = state["now"] + timedelta(seconds=5)


@pytest.mark.asyncio
async def test_us1_acceptance_1_engage_when_turn_rate_over_threshold(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """Sustained turn rate above threshold -> exactly one ENGAGE recommendation."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "120")

    now, state = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = _make_controller(
        _bare_runtime(), dma_synthetic_sources, dma_recording_emitter, now, session_id="s1"
    )

    # Drive turn rate above threshold across several decision cycles.
    await _drive_cycles(controller, dma_signal_feeds, "turn_rate", 42, state, count=3)

    assert dma_recording_emitter.actions().count("mode_recommendation") == 1
    rec_call = next(c for c in dma_recording_emitter.calls if c[0] == "mode_recommendation")
    kwargs = rec_call[1]
    assert kwargs["outcome"].action == "ENGAGE"
    assert "turn_rate" in kwargs["outcome"].triggers
    obs = kwargs["outcome"].signal_observations[0]
    assert obs.signal_name == "turn_rate"
    assert obs.observed_value == 42
    assert obs.configured_threshold == 30


@pytest.mark.asyncio
async def test_us1_acceptance_2_disengage_after_dwell_window(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """After ENGAGE, sustained-below-threshold for full dwell -> DISENGAGE."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "60")

    now, state = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = _make_controller(
        _bare_runtime(), dma_synthetic_sources, dma_recording_emitter, now, session_id="s2"
    )

    # Phase 1: drive ENGAGE. Phase 2: drop and advance through full dwell window (15*5 > 60).
    await _drive_cycles(controller, dma_signal_feeds, "turn_rate", 50, state, count=2)
    await _drive_cycles(controller, dma_signal_feeds, "turn_rate", 8, state, count=15)

    actions = [
        c[1]["outcome"].action for c in dma_recording_emitter.calls if c[0] == "mode_recommendation"
    ]
    assert "ENGAGE" in actions
    assert "DISENGAGE" in actions
    # ENGAGE first, DISENGAGE second; each fires exactly once on action change.
    assert actions.index("ENGAGE") < actions.index("DISENGAGE")


def test_us1_acceptance_3_inactive_when_no_thresholds_set(dma_clear_env) -> None:
    """No SACP_DMA_*_THRESHOLD env vars set -> controller declines to spawn."""
    assert DmaController.is_active_from_env() is False
    assert auto_mode_enabled() is False


@pytest.mark.asyncio
async def test_us1_fr011_advisory_does_not_mutate_spec013_flags(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """FR-011: advisory mode MUST NOT engage/disengage spec-013 mechanisms."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "120")
    # SACP_AUTO_MODE_ENABLED unset -> advisory mode.

    runtime = _config_runtime()
    now, _ = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = _make_controller(
        runtime, dma_synthetic_sources, dma_recording_emitter, now, session_id="s3"
    )

    dma_signal_feeds["turn_rate"].push(42)
    controller.budget._next_eligible_at = -1.0
    await run_decision_cycle(controller)

    # Recommendation emitted, but no transition emission and no flag mutation.
    actions = dma_recording_emitter.actions()
    assert "mode_recommendation" in actions
    assert "mode_transition" not in actions
    assert "mode_transition_suppressed" not in actions
    # Activation flags untouched (default True).
    assert runtime.activation.batching is True
    assert runtime.activation.convergence_override is True
    assert runtime.activation.observer_downgrade is True


@pytest.mark.asyncio
async def test_us1_recommendation_dedupes_within_same_action(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """Research §6: emit only on action change, not on observed-value drift."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "120")

    now, state = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = DmaController(
        session_id="s4",
        runtime=_bare_runtime(),
        signal_sources=dma_synthetic_sources,
        emitter=dma_recording_emitter,
        decisions_per_minute=12,
        clock=now,
    )

    # Five over-threshold cycles in a row — only one ENGAGE recommendation.
    for v in (42, 45, 50, 38, 60):
        dma_signal_feeds["turn_rate"].push(v)
        controller.budget._next_eligible_at = -1.0
        await run_decision_cycle(controller)
        state["now"] = state["now"] + timedelta(seconds=5)

    rec_count = dma_recording_emitter.actions().count("mode_recommendation")
    assert rec_count == 1


@pytest.mark.asyncio
async def test_us1_throttled_cycle_drops_recommendation(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """FR-002: cycle dropped when budget exceeded; no recommendation emitted."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "120")

    now, _ = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = DmaController(
        session_id="s5",
        runtime=_bare_runtime(),
        signal_sources=dma_synthetic_sources,
        emitter=dma_recording_emitter,
        decisions_per_minute=12,
        clock=now,
    )

    # First call admits; second within the same 5s window is throttled.
    dma_signal_feeds["turn_rate"].push(42)
    controller.budget._next_eligible_at = -1.0
    await run_decision_cycle(controller)

    # Second call: budget refused (not yet eligible).
    dma_signal_feeds["turn_rate"].push(50)
    # _next_eligible_at was set to ~now+5s in the previous call.
    outcome = await run_decision_cycle(controller)
    assert outcome is None
    # Throttle event emitted at most once per dwell window.
    assert dma_recording_emitter.actions().count("decision_cycle_throttled") == 1
