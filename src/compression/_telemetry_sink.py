# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-dispatch compression_log telemetry sink — spec 026 SC-013.

The CompressorService writes one telemetry record per `compress(...)`
invocation including NoOp dispatches per Session 2026-05-11 §2 + FR-007.

This module provides an in-process accumulator that tests inspect to
assert the SC-013 "one row per dispatch" invariant. Production wires
the real DB-backed sink via `set_writer(...)` at FastAPI lifespan
startup; the writer receives the same shape and inserts into
`compression_log`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.compression.segments import CompressedSegment


@dataclass(frozen=True)
class CompressionLogRecord:
    """Per-dispatch row shape; mirrors compression_log table columns."""

    session_id: str
    turn_id: str
    participant_id: str
    source_tokens: int
    output_tokens: int
    compressor_id: str
    compressor_version: str
    trust_tier: str
    layer: str
    duration_ms: float
    succeeded: bool
    error_class: str | None = None


@dataclass
class _MemorySink:
    """Default sink — accumulates records in memory for tests."""

    records: list[CompressionLogRecord] = field(default_factory=list)

    def write(self, record: CompressionLogRecord) -> None:
        self.records.append(record)

    def clear(self) -> None:
        self.records.clear()


_memory_sink = _MemorySink()
_writer: Callable[[CompressionLogRecord], Any] | None = None


def set_writer(writer: Callable[[CompressionLogRecord], Any] | None) -> None:
    """Install a DB-backed writer. Pass None to revert to the in-memory sink."""
    global _writer
    _writer = writer


def records() -> list[CompressionLogRecord]:
    """Return the in-memory sink's accumulated records (read-only view)."""
    return list(_memory_sink.records)


def clear() -> None:
    """Reset the in-memory sink. Tests call this in fixtures."""
    _memory_sink.clear()


def record_success(
    *,
    session_id: str,
    turn_id: str,
    participant_id: str,
    source_tokens: int,
    segment: CompressedSegment,
    duration_ms: float,
) -> None:
    record = CompressionLogRecord(
        session_id=session_id,
        turn_id=turn_id,
        participant_id=participant_id,
        source_tokens=source_tokens,
        output_tokens=segment.output_tokens,
        compressor_id=segment.compressor_id,
        compressor_version=segment.compressor_version,
        trust_tier=segment.trust_tier,
        layer=segment.compressor_id,
        duration_ms=duration_ms,
        succeeded=True,
    )
    _dispatch(record)


def record_failure(
    *,
    session_id: str,
    turn_id: str,
    participant_id: str,
    compressor_id: str,
    compressor_version: str,
    trust_tier: str,
    source_tokens: int,
    duration_ms: float,
    error: BaseException,
) -> None:
    record = CompressionLogRecord(
        session_id=session_id,
        turn_id=turn_id,
        participant_id=participant_id,
        source_tokens=source_tokens,
        output_tokens=0,
        compressor_id=compressor_id,
        compressor_version=compressor_version,
        trust_tier=trust_tier,
        layer=compressor_id,
        duration_ms=duration_ms,
        succeeded=False,
        error_class=type(error).__name__,
    )
    _dispatch(record)


def _dispatch(record: CompressionLogRecord) -> None:
    _memory_sink.write(record)
    if _writer is not None:
        _writer(record)
