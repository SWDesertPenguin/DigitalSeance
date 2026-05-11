# SPDX-License-Identifier: AGPL-3.0-or-later

"""Process-scope CompressorService instance + module-load registration.

Importing this module instantiates the singleton CompressorService and
registers every shipped compressor against it. The FastAPI lifespan
calls `compressor_service.freeze()` once at startup so the registry
becomes read-only for the rest of the process lifetime.

Spec 026 FR-006 + FR-023: callers consume `compressor_service` (or the
module-level `compress(...)` convenience wrapper); concrete compressor
classes are NOT imported outside the compression package.
"""

from __future__ import annotations

from src.compression.layer6 import NoOpLayer6Adapter
from src.compression.llmlingua2_mbert import LLMLingua2mBERTCompressor
from src.compression.noop import NoOpCompressor
from src.compression.provence import NoOpProvenceAdapter
from src.compression.segments import CompressedSegment
from src.compression.selective_context import SelectiveContextCompressor
from src.compression.service import CompressorService

compressor_service = CompressorService()
compressor_service.register(NoOpCompressor.COMPRESSOR_ID, NoOpCompressor)
compressor_service.register(LLMLingua2mBERTCompressor.COMPRESSOR_ID, LLMLingua2mBERTCompressor)
compressor_service.register(SelectiveContextCompressor.COMPRESSOR_ID, SelectiveContextCompressor)
compressor_service.register(NoOpProvenceAdapter.COMPRESSOR_ID, NoOpProvenceAdapter)
compressor_service.register(NoOpLayer6Adapter.COMPRESSOR_ID, NoOpLayer6Adapter)


def compress(
    payload: str,
    target_budget: int,
    trust_tier: str,
    *,
    compressor_id: str | None = None,
    session_id: str,
    participant_id: str,
    turn_id: str,
) -> CompressedSegment:
    """Convenience wrapper over the process-scope CompressorService."""
    return compressor_service.compress(
        payload,
        target_budget,
        trust_tier,
        compressor_id=compressor_id,
        session_id=session_id,
        participant_id=participant_id,
        turn_id=turn_id,
    )
