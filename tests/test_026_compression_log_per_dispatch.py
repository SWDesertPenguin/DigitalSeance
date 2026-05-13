# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 T034 — SC-013 log-per-dispatch invariant.

Drive multiple dispatches through ``CompressorService.compress(...)``
(all NoOp); assert exactly one ``compression_log`` row per call lands
in the telemetry accumulator. The row shape is asserted against
``contracts/compression-log-row.md``.
"""

from __future__ import annotations

import pytest

from src.compression import _telemetry_sink
from src.compression.noop import NoOpCompressor
from src.compression.service import CompressorService


@pytest.fixture(autouse=True)
def _clear_sink() -> None:
    _telemetry_sink.clear()


def _fresh_service() -> CompressorService:
    svc = CompressorService()
    svc.register("noop", NoOpCompressor)
    return svc


def test_five_dispatches_yield_five_telemetry_rows() -> None:
    """SC-013: one compression_log row per CompressorService.compress() call."""
    svc = _fresh_service()
    for i in range(5):
        svc.compress(
            f"payload {i}",
            target_budget=100,
            trust_tier="participant_supplied",
            session_id="sess-1",
            participant_id=f"pp-{i}",
            turn_id=f"turn-{i}",
        )
    records = _telemetry_sink.records()
    assert len(records) == 5


def test_per_dispatch_row_shape_matches_contract() -> None:
    """Each row carries the FR-005 column shape + Session 2026-05-11 §2 layer='noop'."""
    svc = _fresh_service()
    svc.compress(
        "hello world",
        target_budget=100,
        trust_tier="participant_supplied",
        session_id="sess-A",
        participant_id="pp-A",
        turn_id="turn-A",
    )
    record = _telemetry_sink.records()[0]
    assert record.session_id == "sess-A"
    assert record.participant_id == "pp-A"
    assert record.turn_id == "turn-A"
    assert record.compressor_id == "noop"
    assert record.compressor_version == "1"
    assert record.layer == "noop"
    assert record.trust_tier == "participant_supplied"
    assert record.output_tokens > 0
    assert record.duration_ms >= 0.0
    assert record.succeeded is True
    assert record.error_class is None


def test_noop_row_writes_layer_noop_and_zero_difference() -> None:
    """NoOp's source_tokens == output_tokens AND layer='noop' (Session 2026-05-11 §2)."""
    svc = _fresh_service()
    svc.compress(
        "x" * 40,
        target_budget=100,
        trust_tier="participant_supplied",
        session_id="s",
        participant_id="p",
        turn_id="t",
    )
    record = _telemetry_sink.records()[0]
    assert record.layer == "noop"
    assert record.output_tokens == record.source_tokens
