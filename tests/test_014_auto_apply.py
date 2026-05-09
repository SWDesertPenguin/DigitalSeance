"""US2 acceptance tests: auto-apply behind feature flag (spec 014).

Four spec acceptance scenarios:
    1. ENGAGE transition with spec-013 mechanism activation.
    2. Dwell-blocked counter-direction transition emitting mode_transition_suppressed.
    3. Post-dwell DISENGAGE transition reverting mechanisms.
    4. FR-010 startup-exit case (cross-validator already in src/config/validators.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.config import validators
from src.orchestrator.dma_controller import DmaController, run_decision_cycle
from src.orchestrator.high_traffic import HighTrafficRuntime, HighTrafficSessionConfig

UTC = UTC


def _fixed_clock(now: datetime):
    state = {"now": now}

    def reader() -> datetime:
        return state["now"]

    return reader, state


def _config_runtime() -> HighTrafficRuntime:
    config = HighTrafficSessionConfig(
        batch_cadence_s=5,
        convergence_threshold_override=0.7,
        observer_downgrade=None,
    )
    return HighTrafficRuntime(config=config)


def _make_controller(runtime, sources, emitter, clock, *, session_id: str) -> DmaController:
    return DmaController(
        session_id=session_id,
        runtime=runtime,
        signal_sources=sources,
        emitter=emitter,
        decisions_per_minute=12,
        clock=clock,
    )


async def _run_one(controller, feeds, signal: str, value) -> None:
    """Push one sample, bypass the 12-dpm budget, drive a single cycle."""
    feeds[signal].push(value)
    controller.budget._next_eligible_at = -1.0
    await run_decision_cycle(controller)


@pytest.mark.asyncio
async def test_us2_acceptance_1_engage_mutates_spec013_flags(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """Auto-apply ENGAGE -> mode_transition row + spec-013 activation flips."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "60")
    dma_clear_env.setenv("SACP_AUTO_MODE_ENABLED", "true")

    runtime = _config_runtime()
    now, _ = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = _make_controller(
        runtime, dma_synthetic_sources, dma_recording_emitter, now, session_id="s1"
    )

    await _run_one(controller, dma_signal_feeds, "turn_rate", 42)

    actions = dma_recording_emitter.actions()
    assert "mode_recommendation" in actions
    assert "mode_transition" in actions

    # Find the transition emission and inspect its kwargs.
    trans_call = next(c for c in dma_recording_emitter.calls if c[0] == "mode_transition")
    kwargs = trans_call[1]
    assert kwargs["outcome"].action == "ENGAGE"
    assert "batching" in kwargs["engaged_mechanisms"]
    assert "convergence_override" in kwargs["engaged_mechanisms"]
    # observer_downgrade env unset -> skipped silently.
    assert "observer_downgrade" in kwargs["skipped_mechanisms"]


@pytest.mark.asyncio
async def test_us2_acceptance_2_dwell_blocks_counter_transition(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """Counter-direction within dwell window -> mode_transition_suppressed."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "60")
    dma_clear_env.setenv("SACP_AUTO_MODE_ENABLED", "true")

    runtime = _config_runtime()
    now, state = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = _make_controller(
        runtime, dma_synthetic_sources, dma_recording_emitter, now, session_id="s2"
    )

    # Drive ENGAGE.
    await _run_one(controller, dma_signal_feeds, "turn_rate", 42)

    # Force the controller's state to think a DISENGAGE just got picked
    # while still inside dwell. We bypass the natural dwell-detection (which
    # needs sustained-below) and craft the precondition directly.
    state["now"] = state["now"] + timedelta(seconds=10)  # still inside dwell of 60s
    controller.state.sustained_below_since = state["now"] - timedelta(seconds=120)

    await _run_one(controller, dma_signal_feeds, "turn_rate", 8)

    actions = dma_recording_emitter.actions()
    # The recommendation may emit (action change ENGAGE -> DISENGAGE), but
    # the transition itself MUST be suppressed by dwell.
    assert "mode_transition_suppressed" in actions


@pytest.mark.asyncio
async def test_us2_acceptance_3_disengage_after_dwell_reverts_mechanisms(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """Once dwell elapses, DISENGAGE fires and disengages spec-013 mechanisms."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "30")
    dma_clear_env.setenv("SACP_AUTO_MODE_ENABLED", "true")

    runtime = _config_runtime()
    now, state = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = _make_controller(
        runtime, dma_synthetic_sources, dma_recording_emitter, now, session_id="s3"
    )

    # Drive ENGAGE.
    await _run_one(controller, dma_signal_feeds, "turn_rate", 42)
    assert runtime.activation.batching is True

    # Advance past dwell and drive sustained-below.
    state["now"] = state["now"] + timedelta(seconds=120)
    controller.state.sustained_below_since = state["now"] - timedelta(seconds=120)
    # Push a low-traffic sample.
    await _run_one(controller, dma_signal_feeds, "turn_rate", 5)

    # DISENGAGE transition fired and flipped batching off.
    transitions = [c[1] for c in dma_recording_emitter.calls if c[0] == "mode_transition"]
    disengage_transitions = [t for t in transitions if t["outcome"].action == "DISENGAGE"]
    assert len(disengage_transitions) == 1
    assert runtime.activation.batching is False


def test_us2_acceptance_4_fr010_startup_exit_when_dwell_unset(
    dma_clear_env,
) -> None:
    """FR-010 cross-validator: SACP_AUTO_MODE_ENABLED=true with no dwell exits."""
    dma_clear_env.setenv("SACP_AUTO_MODE_ENABLED", "true")
    dma_clear_env.delenv("SACP_DMA_DWELL_TIME_S", raising=False)

    failure = validators.validate_auto_mode_enabled()
    assert failure is not None
    assert "SACP_DMA_DWELL_TIME_S" in failure.reason
    assert failure.var_name == "SACP_AUTO_MODE_ENABLED"


def test_us2_fr010_passes_when_both_set(dma_clear_env) -> None:
    """Both vars set together -> validator green."""
    dma_clear_env.setenv("SACP_AUTO_MODE_ENABLED", "true")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "120")
    assert validators.validate_auto_mode_enabled() is None


@pytest.mark.asyncio
async def test_us2_recommendation_pairs_with_transition_at_same_decision_at(
    dma_clear_env,
    dma_signal_feeds,
    dma_synthetic_sources,
    dma_recording_emitter,
) -> None:
    """audit-events.md pairing: mode_recommendation and mode_transition share decision_at."""
    dma_clear_env.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
    dma_clear_env.setenv("SACP_DMA_DWELL_TIME_S", "60")
    dma_clear_env.setenv("SACP_AUTO_MODE_ENABLED", "true")

    now, _ = _fixed_clock(datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    controller = _make_controller(
        _config_runtime(), dma_synthetic_sources, dma_recording_emitter, now, session_id="s4"
    )

    await _run_one(controller, dma_signal_feeds, "turn_rate", 42)

    rec_call = next(c for c in dma_recording_emitter.calls if c[0] == "mode_recommendation")
    trans_call = next(c for c in dma_recording_emitter.calls if c[0] == "mode_transition")
    assert rec_call[1]["outcome"].decision_at == trans_call[1]["outcome"].decision_at
