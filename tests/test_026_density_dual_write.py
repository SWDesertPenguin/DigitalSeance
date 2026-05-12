# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 T031 / FR-018 — density-anomaly dual-write to routing_log.

When the density signal fires, the existing spec 004 convergence_log
row continues to write (`tier='density_anomaly'`); spec 026 adds a
routing_log marker (`reason='density_anomaly_flagged'`) for the per-
turn-decision audit trail. Both writes co-commit in the same per-turn
transaction per Session 2026-05-11 §4.

These tests exercise the convergence-detector entry point with a mock
log_repo + session_repo and assert both write paths fire on an anomaly
fire AND neither fires on a non-anomalous turn.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.orchestrator.convergence import ConvergenceDetector


def _stub_model_with_embedding() -> MagicMock:
    """Return a mock model whose encode call yields a deterministic 384-dim vec."""
    model = MagicMock()
    encoded = MagicMock()
    encoded.tobytes = lambda: b"\x00" * 384 * 4
    model.encode.return_value = encoded
    return model


def _build_detector(*, baseline: list[float], log_repo: MagicMock) -> ConvergenceDetector:
    """Construct a detector wired to mock repos + a stub embedding model."""
    session_repo = MagicMock()
    session_repo.get_density_baseline = AsyncMock(return_value=baseline)
    session_repo.replace_density_baseline = AsyncMock()
    detector = ConvergenceDetector(log_repo=log_repo, session_repo=session_repo)
    detector._model = _stub_model_with_embedding()
    return detector


def _build_log_repo() -> MagicMock:
    """Return a mock LogRepository with the async methods the detector calls."""
    log_repo = MagicMock()
    log_repo.get_convergence_window = AsyncMock(return_value=[])
    log_repo.log_convergence = AsyncMock()
    log_repo.log_density_anomaly = AsyncMock()
    log_repo.log_routing = AsyncMock()
    log_repo._pool = MagicMock()
    return log_repo


def _force_anomaly_path() -> None:
    """Monkey-patch the module-level is_anomaly to always trip the anomaly path."""
    import src.orchestrator.convergence as convergence_mod

    convergence_mod.is_anomaly = lambda *args, **kwargs: True  # type: ignore[assignment]


def _restore_anomaly_path() -> None:
    """Restore the real is_anomaly for other tests."""
    import src.orchestrator.convergence as convergence_mod
    from src.orchestrator.density import is_anomaly as real_is_anomaly

    convergence_mod.is_anomaly = real_is_anomaly  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_density_anomaly_dual_writes_convergence_log_and_routing_log() -> None:
    """Anomalous turn writes BOTH convergence_log AND routing_log rows."""
    log_repo = _build_log_repo()
    detector = _build_detector(baseline=[0.01] * 20, log_repo=log_repo)
    _force_anomaly_path()
    try:
        await detector.process_turn(
            turn_number=21,
            session_id="s1",
            content="alpha beta gamma delta",
        )
    finally:
        _restore_anomaly_path()
    log_repo.log_density_anomaly.assert_awaited_once()
    density_call = log_repo.log_density_anomaly.await_args.kwargs
    assert density_call["turn_number"] == 21
    assert density_call["session_id"] == "s1"
    log_repo.log_routing.assert_any_call(
        session_id="s1",
        turn_number=21,
        intended="s1",
        actual="s1",
        action="quality_signal",
        complexity="n/a",
        domain_match=False,
        reason="density_anomaly_flagged",
    )


@pytest.mark.asyncio
async def test_non_anomalous_turn_does_not_emit_density_anomaly_marker() -> None:
    """Below-threshold turn writes NEITHER the convergence_log row NOR the marker."""
    log_repo = _build_log_repo()
    detector = _build_detector(baseline=[], log_repo=log_repo)
    await detector.process_turn(
        turn_number=1,
        session_id="s1",
        content="hello world",
    )
    log_repo.log_density_anomaly.assert_not_called()
    # Detector still records the convergence_log row via log_convergence,
    # but it MUST NOT emit a density_anomaly_flagged routing_log marker.
    for call in log_repo.log_routing.await_args_list:
        assert call.kwargs.get("reason") != "density_anomaly_flagged"


@pytest.mark.asyncio
async def test_density_marker_carries_speaker_id_when_present() -> None:
    """When `speaker_id` is supplied, both writes attribute to the speaker."""
    log_repo = _build_log_repo()
    detector = _build_detector(baseline=[0.01] * 20, log_repo=log_repo)
    _force_anomaly_path()
    try:
        await detector.process_turn(
            turn_number=21,
            session_id="s1",
            content="alpha beta gamma",
            speaker_id="p1",
        )
    finally:
        _restore_anomaly_path()
    routing_calls = [
        c.kwargs
        for c in log_repo.log_routing.await_args_list
        if c.kwargs.get("reason") == "density_anomaly_flagged"
    ]
    assert len(routing_calls) == 1
    assert routing_calls[0]["intended"] == "p1"
    assert routing_calls[0]["actual"] == "p1"
