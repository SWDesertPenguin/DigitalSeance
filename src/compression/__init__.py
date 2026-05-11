# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 compressor package — six-layer context compression stack.

The package owns the CompressorService registry, the CompressedSegment
dataclass, the per-layer compressor implementations (NoOp Phase 1
default + LLMLingua-2 / Selective Context Phase 2 scaffolds + Provence
/ Layer 6 Phase 3 stubs), the XML boundary marker assembly, and the
MIN-tier trust-tier inheritance per Session 2026-05-11 §3.

The dispatch path imports `from src.compression.service import
CompressorService` and never reaches concrete compressor implementations
directly per FR-023. The architectural test in
``tests/test_026_architectural.py`` enforces the boundary.

See specs/026-context-compression/ for the full design surface.
"""

from src.compression.segments import CompressedSegment, Compressor
from src.compression.service import (
    CompressionPipelineError,
    CompressorService,
    UnregisteredCompressorError,
)
from src.compression.trust_tier import TierOneRefusalError, resolve_min_tier

__all__ = [
    "CompressedSegment",
    "Compressor",
    "CompressionPipelineError",
    "CompressorService",
    "TierOneRefusalError",
    "UnregisteredCompressorError",
    "resolve_min_tier",
]
