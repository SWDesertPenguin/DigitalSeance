# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 T038 — CompressorService freeze + writer mount at FastAPI startup.

The MCP app's lifespan calls `_freeze_compressor_registry(pool)` once
the pool is built. After that point:
  - `compressor_service.freeze()` flips the registry to read-only so
    later `register(...)` calls raise.
  - `_telemetry_sink.set_writer(...)` installs a DB-backed writer
    swapping the test-only in-memory accumulator.

These tests exercise the freeze + writer hooks directly. The
asyncpg.Pool argument is a MagicMock — the writer schedules the
async DB insert as a fire-and-forget task; the test only asserts the
hook fired, not the SQL itself (insert_compression_log carries its own
schema-mirrored row-shape test).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _reset_compressor_registry_for_test() -> None:
    """Each test reimports the registry to start from an unfrozen state."""
    from src.compression import _telemetry_sink, registry

    registry.compressor_service._reset_for_tests()  # noqa: SLF001 — test hook
    _telemetry_sink.set_writer(None)
    _telemetry_sink.clear()
    yield
    registry.compressor_service._reset_for_tests()  # noqa: SLF001
    _telemetry_sink.set_writer(None)
    _telemetry_sink.clear()


def test_freeze_flips_registry_to_read_only() -> None:
    """After lifespan freeze, register() raises RuntimeError."""
    from src.compression import registry
    from src.mcp_server.app import _freeze_compressor_registry

    pool = MagicMock()
    _freeze_compressor_registry(pool)
    with pytest.raises(RuntimeError, match="read-only after startup"):
        registry.compressor_service.register("late_arrival", _build_dummy_compressor())


def test_freeze_is_idempotent_across_test_setup() -> None:
    """Calling _freeze_compressor_registry twice does not error."""
    from src.mcp_server.app import _freeze_compressor_registry

    pool = MagicMock()
    _freeze_compressor_registry(pool)
    _freeze_compressor_registry(pool)


def test_freeze_installs_telemetry_writer() -> None:
    """After freeze, _telemetry_sink._writer is non-None."""
    from src.compression import _telemetry_sink
    from src.mcp_server.app import _freeze_compressor_registry

    pool = MagicMock()
    _freeze_compressor_registry(pool)
    assert _telemetry_sink._writer is not None  # noqa: SLF001 — test inspection


def _build_dummy_compressor() -> type:
    from src.compression.segments import CompressedSegment

    class _DummyLate:
        COMPRESSOR_ID = "late_arrival"
        COMPRESSOR_VERSION = "0-dummy"

        def compress(self, payload: str, target_budget: int, trust_tier: str) -> CompressedSegment:
            return CompressedSegment(
                output_text=payload,
                output_tokens=0,
                trust_tier=trust_tier,
                boundary_marker=None,
                compressor_id=self.COMPRESSOR_ID,
                compressor_version=self.COMPRESSOR_VERSION,
            )

    return _DummyLate
