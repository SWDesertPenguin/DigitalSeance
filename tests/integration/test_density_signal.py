# SPDX-License-Identifier: AGPL-3.0-or-later

"""End-to-end test: density signal across a 25-turn synthetic session.

Verifies spec 004 §FR-020 wiring against a real Postgres DB:
- baseline column updates after every turn
- no anomaly logged in the first 20 turns (insufficient baseline)
- one anomalous turn beyond turn 20 produces a tier='density_anomaly' row
"""

from __future__ import annotations

from unittest.mock import MagicMock

import asyncpg
import numpy as np
import pytest

from src.orchestrator.convergence import ConvergenceDetector
from src.repositories.log_repo import LogRepository
from src.repositories.session_repo import SessionRepository


def _stub_model(monotonic_counter: list[int]) -> MagicMock:
    """Model whose embedding shape varies with turn — drives density up/down."""

    def encode(text: str, normalize_embeddings: bool = True) -> np.ndarray:
        del normalize_embeddings
        # Anomaly trigger: when the text starts with 'ANOMALOUS', emit a
        # very-low-entropy embedding so density spikes well above the 1.5×
        # baseline. Otherwise emit a uniform-ish embedding.
        if text.startswith("ANOMALOUS"):
            vec = np.full(384, 0.001, dtype=np.float32)
            vec[0] = 1.0
        else:
            vec = np.full(384, 1.0 / np.sqrt(384), dtype=np.float32)
        monotonic_counter[0] += 1
        result = MagicMock()
        result.tobytes = lambda: vec.tobytes()
        result.__class__ = np.ndarray
        return vec

    model = MagicMock()
    model.encode.side_effect = encode
    return model


async def _process_turns(
    detector: ConvergenceDetector,
    session_id: str,
    contents: list[str],
) -> None:
    for i, content in enumerate(contents, start=1):
        await detector.process_turn(
            turn_number=i,
            session_id=session_id,
            content=content,
        )


@pytest.mark.asyncio
async def test_density_baseline_updates_each_turn(
    pool: asyncpg.Pool,
    session_with_participant: tuple,
):
    session, _, _, _ = session_with_participant
    log_repo = LogRepository(pool)
    session_repo = SessionRepository(pool)
    detector = ConvergenceDetector(log_repo=log_repo, session_repo=session_repo)
    detector._model = _stub_model([0])
    contents = [f"benign turn {i} word word word" for i in range(1, 6)]
    await _process_turns(detector, session.id, contents)
    baseline = await session_repo.get_density_baseline(session.id)
    assert len(baseline) == 5
    assert all(d > 0 for d in baseline)


@pytest.mark.asyncio
async def test_no_anomaly_logged_before_baseline_is_full(
    pool: asyncpg.Pool,
    session_with_participant: tuple,
):
    session, _, _, _ = session_with_participant
    log_repo = LogRepository(pool)
    session_repo = SessionRepository(pool)
    detector = ConvergenceDetector(log_repo=log_repo, session_repo=session_repo)
    detector._model = _stub_model([0])
    # 19 turns → baseline window not yet at 20 → anomaly check disabled
    contents = [f"ANOMALOUS turn {i}" for i in range(1, 20)]
    await _process_turns(detector, session.id, contents)
    rows = await pool.fetch(
        "SELECT * FROM convergence_log WHERE session_id = $1 AND tier = 'density_anomaly'",
        session.id,
    )
    assert rows == []


@pytest.mark.asyncio
async def test_anomaly_logged_after_baseline_full(
    pool: asyncpg.Pool,
    session_with_participant: tuple,
):
    session, _, _, _ = session_with_participant
    log_repo = LogRepository(pool)
    session_repo = SessionRepository(pool)
    detector = ConvergenceDetector(log_repo=log_repo, session_repo=session_repo)
    detector._model = _stub_model([0])
    # 20 benign turns establish baseline; turn 21 is ANOMALOUS
    benign = [f"benign turn {i} word word word" for i in range(1, 21)]
    await _process_turns(detector, session.id, benign)
    await detector.process_turn(
        turn_number=21,
        session_id=session.id,
        content="ANOMALOUS dense response with many words " * 4,
    )
    rows = await pool.fetch(
        "SELECT turn_number, density_value, baseline_value FROM convergence_log "
        "WHERE session_id = $1 AND tier = 'density_anomaly' ORDER BY turn_number",
        session.id,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["turn_number"] == 21
    assert row["density_value"] > 1.5 * row["baseline_value"]


@pytest.mark.asyncio
async def test_baseline_caps_at_window_size(
    pool: asyncpg.Pool,
    session_with_participant: tuple,
):
    session, _, _, _ = session_with_participant
    log_repo = LogRepository(pool)
    session_repo = SessionRepository(pool)
    detector = ConvergenceDetector(log_repo=log_repo, session_repo=session_repo)
    detector._model = _stub_model([0])
    contents = [f"benign {i} word word word" for i in range(1, 26)]
    await _process_turns(detector, session.id, contents)
    baseline = await session_repo.get_density_baseline(session.id)
    # Baseline keeps only the most recent 20
    assert len(baseline) == 20


@pytest.mark.asyncio
async def test_convergence_log_filter_excludes_density_rows(
    pool: asyncpg.Pool,
    session_with_participant: tuple,
):
    """get_convergence_window must NOT return density-anomaly rows."""
    session, _, _, _ = session_with_participant
    log_repo = LogRepository(pool)
    # Seed one convergence row + one density-anomaly row at the same turn
    await log_repo.log_convergence(
        turn_number=1,
        session_id=session.id,
        embedding=b"\x00" * 384 * 4,
        similarity_score=0.5,
    )
    await log_repo.log_density_anomaly(
        turn_number=1,
        session_id=session.id,
        density_value=10.0,
        baseline_value=2.0,
    )
    window = await log_repo.get_convergence_window(session.id, 5)
    assert len(window) == 1
    assert window[0].turn_number == 1
