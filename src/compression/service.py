# SPDX-License-Identifier: AGPL-3.0-or-later

"""CompressorService registry + dispatcher — spec 026 FR-006, FR-007, FR-020.

Process-scope registry of compressor implementations keyed by id.
Implementations register at module import; the orchestrator calls
`freeze()` once at FastAPI startup so the registry is read-only
during dispatch. The `compress(...)` entry point wraps each call with
per-dispatch `compression_log` telemetry (SC-013, "one row per
dispatch") and converts Compressor exceptions to
`CompressionPipelineError` + a `routing_log` marker per FR-020.

Topology gate per research.md §5: when `SACP_TOPOLOGY=7`, only the
`noop` compressor is permitted. Other registrations are still allowed
at module import (the modules import unconditionally), but
`compress(...)` refuses anything but `noop` and raises
`UnregisteredCompressorError`.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from src.compression.segments import CompressedSegment, Compressor


@dataclass(frozen=True)
class _DispatchContext:
    """Per-call identifiers for telemetry — bundle to keep arg counts sane."""

    session_id: str
    participant_id: str
    turn_id: str


class UnregisteredCompressorError(Exception):
    """Raised when `compress()` is called for an unknown compressor id."""


class CompressionPipelineError(Exception):
    """Raised when a compressor body raises any exception.

    The bridge layer catches this at the dispatch site and falls
    through to un-compressed payload per FR-020. The CompressorService
    has already emitted the `compression_pipeline_error` routing_log
    marker before raising.
    """

    def __init__(self, compressor_id: str, original: BaseException) -> None:
        self.compressor_id = compressor_id
        self.original = original
        super().__init__(
            f"compressor {compressor_id!r} failed: {type(original).__name__}: {original}"
        )


class CompressorService:
    """Process-scope compressor registry. Read-only after `freeze()`."""

    def __init__(self) -> None:
        self._registry: dict[str, type[Compressor]] = {}
        self._frozen: bool = False

    def register(self, compressor_id: str, compressor_class: type[Compressor]) -> None:
        if self._frozen:
            raise RuntimeError(
                "CompressorService is read-only after startup; register at import time"
            )
        if compressor_id in self._registry:
            raise ValueError(
                f"compressor {compressor_id!r} already registered; "
                "replacement requires process restart"
            )
        self._registry[compressor_id] = compressor_class

    def freeze(self) -> None:
        """Mark the registry read-only. Called once at FastAPI startup."""
        self._frozen = True

    def _reset_for_tests(self) -> None:
        """Flip the registry back to mutable. Test-only hook.

        Production lifespan calls `freeze()` exactly once; per-test
        FastAPI fixtures (spec 012 US7) stand the app up fresh per case
        and need to re-import the compressor modules to repopulate the
        registry. This hook is the single permitted reset path — the
        public API stays read-only after freeze.
        """
        self._frozen = False

    def registered_ids(self) -> frozenset[str]:
        return frozenset(self._registry.keys())

    def compress(
        self,
        payload: str,
        target_budget: int,
        trust_tier: str,
        *,
        compressor_id: str | None = None,
        session_id: str,
        participant_id: str,
        turn_id: str,
    ) -> CompressedSegment:
        """Dispatch to the configured compressor; emit per-dispatch telemetry.

        Selection order: explicit `compressor_id` arg > SACP env default >
        `'noop'`. Topology-7 callers MUST request `noop` explicitly
        (the env default still works on topology 7; only non-noop
        explicit selections are blocked).
        """
        selected = self._resolve_compressor_id(compressor_id)
        self._enforce_topology_gate(selected)
        compressor_class = self._lookup_class(selected)
        compressor = compressor_class()
        return self._invoke_with_telemetry(
            compressor,
            payload,
            target_budget,
            trust_tier,
            session_id=session_id,
            participant_id=participant_id,
            turn_id=turn_id,
        )

    def _resolve_compressor_id(self, explicit: str | None) -> str:
        if explicit:
            return explicit
        return os.environ.get("SACP_COMPRESSION_DEFAULT_COMPRESSOR", "noop") or "noop"

    def _enforce_topology_gate(self, compressor_id: str) -> None:
        if os.environ.get("SACP_TOPOLOGY") == "7" and compressor_id != "noop":
            raise UnregisteredCompressorError(
                f"topology 7 supports Layer 1 caching only; "
                f"compressor {compressor_id!r} is not permitted"
            )

    def _lookup_class(self, compressor_id: str) -> type[Compressor]:
        if compressor_id not in self._registry:
            raise UnregisteredCompressorError(
                f"compressor {compressor_id!r} not registered; " f"known: {sorted(self._registry)}"
            )
        return self._registry[compressor_id]

    def _invoke_with_telemetry(
        self,
        compressor: Compressor,
        payload: str,
        target_budget: int,
        trust_tier: str,
        *,
        session_id: str,
        participant_id: str,
        turn_id: str,
    ) -> CompressedSegment:
        ctx = _DispatchContext(
            session_id=session_id, participant_id=participant_id, turn_id=turn_id
        )
        start = time.perf_counter()
        try:
            segment = compressor.compress(payload, target_budget, trust_tier)
        except Exception as exc:
            self._record_failure(
                compressor,
                payload,
                trust_tier,
                duration_ms=(time.perf_counter() - start) * 1000.0,
                ctx=ctx,
                error=exc,
            )
            raise CompressionPipelineError(compressor.COMPRESSOR_ID, exc) from exc
        self._record_success(
            segment,
            len(payload),
            duration_ms=(time.perf_counter() - start) * 1000.0,
            ctx=ctx,
        )
        return segment

    def _record_success(
        self,
        segment: CompressedSegment,
        approx_source_tokens: int,
        *,
        duration_ms: float,
        ctx: _DispatchContext,
    ) -> None:
        # T018 wires the repository call site; the skeleton emits a
        # structured record via the logging surface so the
        # one-row-per-dispatch invariant (SC-013) is exercisable in
        # unit tests before the DB hook lands.
        from src.compression import _telemetry_sink

        _telemetry_sink.record_success(
            session_id=ctx.session_id,
            participant_id=ctx.participant_id,
            turn_id=ctx.turn_id,
            source_tokens=approx_source_tokens,
            segment=segment,
            duration_ms=duration_ms,
        )

    def _record_failure(
        self,
        compressor: Compressor,
        payload: str,
        trust_tier: str,
        *,
        duration_ms: float,
        ctx: _DispatchContext,
        error: BaseException,
    ) -> None:
        from src.compression import _telemetry_sink

        _telemetry_sink.record_failure(
            session_id=ctx.session_id,
            participant_id=ctx.participant_id,
            turn_id=ctx.turn_id,
            compressor_id=compressor.COMPRESSOR_ID,
            compressor_version=compressor.COMPRESSOR_VERSION,
            trust_tier=trust_tier,
            source_tokens=len(payload),
            duration_ms=duration_ms,
            error=error,
        )
