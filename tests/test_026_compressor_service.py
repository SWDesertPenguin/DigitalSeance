# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 CompressorService registry + dispatch tests (T035 part of US3).

Covers research.md §5 — register / get round-trip, double-register
rejection, register-after-freeze rejection, unregistered compressor
error, topology-7 gate. The dispatch path itself is exercised in
test_026_noop_compressor.py (SC-006) and test_026_compression_log_per_dispatch.py
(SC-013).
"""

from __future__ import annotations

import pytest

from src.compression import _telemetry_sink
from src.compression.noop import NoOpCompressor
from src.compression.segments import CompressedSegment
from src.compression.service import (
    CompressionPipelineError,
    CompressorService,
    UnregisteredCompressorError,
)


@pytest.fixture(autouse=True)
def _clear_sink() -> None:
    _telemetry_sink.clear()


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SACP_COMPRESSION_DEFAULT_COMPRESSOR",
        "SACP_COMPRESSION_PHASE2_ENABLED",
        "SACP_TOPOLOGY",
    ):
        monkeypatch.delenv(var, raising=False)


def _fresh_service() -> CompressorService:
    svc = CompressorService()
    svc.register("noop", NoOpCompressor)
    return svc


def test_register_round_trip() -> None:
    svc = _fresh_service()
    assert "noop" in svc.registered_ids()


def test_double_register_raises() -> None:
    svc = _fresh_service()
    with pytest.raises(ValueError, match="already registered"):
        svc.register("noop", NoOpCompressor)


def test_register_after_freeze_raises() -> None:
    svc = _fresh_service()
    svc.freeze()
    with pytest.raises(RuntimeError, match="read-only after startup"):
        svc.register("another", NoOpCompressor)


def test_compress_dispatches_to_registered_compressor() -> None:
    svc = _fresh_service()
    segment = svc.compress(
        "hello world",
        target_budget=100,
        trust_tier="participant_supplied",
        session_id="sess-1",
        participant_id="pp-1",
        turn_id="turn-1",
    )
    assert isinstance(segment, CompressedSegment)
    assert segment.compressor_id == "noop"


def test_compress_unregistered_raises() -> None:
    svc = _fresh_service()
    with pytest.raises(UnregisteredCompressorError, match="not registered"):
        svc.compress(
            "x",
            target_budget=100,
            trust_tier="participant_supplied",
            compressor_id="never_registered",
            session_id="sess-1",
            participant_id="pp-1",
            turn_id="turn-1",
        )


def test_topology_7_gate_blocks_non_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_TOPOLOGY", "7")
    svc = _fresh_service()
    # Register a second compressor to prove the gate blocks at compress-time,
    # not at register-time.
    svc.register("llmlingua2_mbert", NoOpCompressor)
    with pytest.raises(UnregisteredCompressorError, match="topology 7"):
        svc.compress(
            "x",
            target_budget=100,
            trust_tier="participant_supplied",
            compressor_id="llmlingua2_mbert",
            session_id="s",
            participant_id="p",
            turn_id="t",
        )


def test_topology_7_gate_allows_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_TOPOLOGY", "7")
    svc = _fresh_service()
    segment = svc.compress(
        "x",
        target_budget=100,
        trust_tier="participant_supplied",
        compressor_id="noop",
        session_id="s",
        participant_id="p",
        turn_id="t",
    )
    assert segment.compressor_id == "noop"


def test_compress_resolves_default_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_DEFAULT_COMPRESSOR", "noop")
    svc = _fresh_service()
    segment = svc.compress(
        "x",
        target_budget=100,
        trust_tier="participant_supplied",
        session_id="s",
        participant_id="p",
        turn_id="t",
    )
    assert segment.compressor_id == "noop"


def test_compressor_failure_wraps_in_pipeline_error() -> None:
    class _BrokenCompressor:
        COMPRESSOR_ID = "broken"
        COMPRESSOR_VERSION = "0"

        def compress(self, payload: str, target_budget: int, trust_tier: str) -> CompressedSegment:
            raise RuntimeError("synthetic failure")

    svc = _fresh_service()
    svc.register("broken", _BrokenCompressor)
    with pytest.raises(CompressionPipelineError, match="broken"):
        svc.compress(
            "x",
            target_budget=100,
            trust_tier="participant_supplied",
            compressor_id="broken",
            session_id="s",
            participant_id="p",
            turn_id="t",
        )
    # Failure still records a telemetry row (succeeded=False) per FR-020 + SC-013.
    records = _telemetry_sink.records()
    assert len(records) == 1
    assert records[0].succeeded is False
    assert records[0].compressor_id == "broken"
    assert records[0].error_class == "RuntimeError"
