"""Spec 014 in-memory density-anomaly observer (dma_observation module).

Bridges the convergence detector's async DB write path and the DMA
controller's synchronous decision-cycle hot path. The buffer is
process-scope; tests reset between runs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.orchestrator.dma_observation import (
    count_recent_density_anomalies,
    record_density_anomaly,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _clear_buffer() -> None:
    reset_for_tests()


def test_empty_buffer_reports_zero() -> None:
    assert count_recent_density_anomalies("s1") == 0


def test_records_within_window_counted() -> None:
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)
    record_density_anomaly("s1", when=now - timedelta(seconds=30))
    record_density_anomaly("s1", when=now - timedelta(seconds=10))
    assert count_recent_density_anomalies("s1", window_seconds=60, now=now) == 2


def test_records_outside_window_excluded() -> None:
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)
    record_density_anomaly("s1", when=now - timedelta(seconds=120))
    record_density_anomaly("s1", when=now - timedelta(seconds=30))
    assert count_recent_density_anomalies("s1", window_seconds=60, now=now) == 1


def test_other_session_records_not_counted() -> None:
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)
    record_density_anomaly("s1", when=now - timedelta(seconds=10))
    record_density_anomaly("s2", when=now - timedelta(seconds=10))
    record_density_anomaly("s2", when=now - timedelta(seconds=20))
    assert count_recent_density_anomalies("s1", window_seconds=60, now=now) == 1
    assert count_recent_density_anomalies("s2", window_seconds=60, now=now) == 2


def test_default_now_uses_wall_clock() -> None:
    """Smoke: default `now=None` works against the live wall clock."""
    record_density_anomaly("s1")
    assert count_recent_density_anomalies("s1") >= 1
