# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 NoOpCompressor tests (T033 part of US3).

Covers SC-006 byte-identical pass-through, FR-007 + SC-013 log-per-dispatch
invariant, FR-014 NoOp-exempt-from-tier-1-refusal.
"""

from __future__ import annotations

import pytest

from src.compression import _telemetry_sink
from src.compression.noop import NoOpCompressor
from src.compression.segments import CompressedSegment


@pytest.fixture(autouse=True)
def _clear_sink() -> None:
    _telemetry_sink.clear()


def test_noop_output_is_byte_identical_to_input() -> None:
    """SC-006: NoOp dispatch is byte-identical to un-compressor-mediated baseline."""
    compressor = NoOpCompressor()
    payload = "hello world, this is some content"
    segment = compressor.compress(payload, target_budget=999, trust_tier="participant_supplied")
    assert segment.output_text == payload
    assert segment.boundary_marker is None  # NoOp produces no wrapper


def test_noop_output_tokens_equals_source_tokens() -> None:
    compressor = NoOpCompressor()
    payload = "x" * 400  # 100 approx tokens at len // 4
    segment = compressor.compress(payload, target_budget=999, trust_tier="participant_supplied")
    assert segment.output_tokens == 100


def test_noop_compressor_metadata() -> None:
    compressor = NoOpCompressor()
    segment = compressor.compress("x", target_budget=1, trust_tier="participant_supplied")
    assert segment.compressor_id == "noop"
    assert segment.compressor_version == "1"
    assert NoOpCompressor.COMPRESSOR_ID == "noop"
    assert NoOpCompressor.COMPRESSOR_VERSION == "1"


def test_noop_passes_through_trust_tier_verbatim() -> None:
    compressor = NoOpCompressor()
    for tier in ("system", "facilitator", "participant_supplied"):
        segment = compressor.compress("x", target_budget=1, trust_tier=tier)
        assert segment.trust_tier == tier


def test_noop_does_not_refuse_tier_one() -> None:
    """FR-014 NoOp exemption: byte-identical output inserts no compression artefact,
    so the protective rationale doesn't apply."""
    compressor = NoOpCompressor()
    segment = compressor.compress("system prompt body", target_budget=1, trust_tier="system")
    assert segment.trust_tier == "system"
    assert segment.output_text == "system prompt body"


def test_noop_returns_compressed_segment_type() -> None:
    compressor = NoOpCompressor()
    segment = compressor.compress("x", target_budget=1, trust_tier="participant_supplied")
    assert isinstance(segment, CompressedSegment)


def test_noop_via_service_writes_one_telemetry_row() -> None:
    """SC-013: every CompressorService.compress() writes one compression_log row."""
    from src.compression.service import CompressorService

    svc = CompressorService()
    svc.register("noop", NoOpCompressor)
    svc.compress(
        "test payload",
        target_budget=100,
        trust_tier="participant_supplied",
        session_id="sess-1",
        participant_id="pp-1",
        turn_id="turn-1",
    )
    records = _telemetry_sink.records()
    assert len(records) == 1
    record = records[0]
    assert record.compressor_id == "noop"
    assert record.succeeded is True
    assert record.session_id == "sess-1"
    assert record.participant_id == "pp-1"
    assert record.turn_id == "turn-1"
    assert record.layer == "noop"
    assert record.duration_ms >= 0
