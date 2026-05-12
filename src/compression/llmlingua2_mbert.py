# SPDX-License-Identifier: AGPL-3.0-or-later

"""LLMLingua2mBERTCompressor — Phase 2 scaffold per spec 026 FR-008.

v1 ships the scaffold only. Real `compress_prompt(...)` integration
lands at Phase 2 task time once `transformers` + `accelerate` are
pinned per Constitution §6.3 and the dependency landing is approved.

The Phase 2 master switch is `SACP_COMPRESSION_PHASE2_ENABLED`. When
false (default), this compressor raises NotImplementedError naming the
env var. When true, raises NotImplementedError pointing at the Phase 2
task list — the CompressorService catches the exception and falls
through to un-compressed payload per FR-020 + SC-007.
"""

from __future__ import annotations

import os

from src.compression.segments import CompressedSegment
from src.compression.trust_tier import refuse_tier_one


class LLMLingua2mBERTCompressor:
    """Phase 2 hard-compression default. Scaffold in Phase 1."""

    COMPRESSOR_ID: str = "llmlingua2_mbert"
    COMPRESSOR_VERSION: str = "0-scaffold"

    def compress(
        self,
        payload: str,
        target_budget: int,
        trust_tier: str,
    ) -> CompressedSegment:
        refuse_tier_one(trust_tier)
        if os.environ.get("SACP_COMPRESSION_PHASE2_ENABLED") != "true":
            raise NotImplementedError(
                "Phase 2 not enabled; set SACP_COMPRESSION_PHASE2_ENABLED=true to opt in"
            )
        raise NotImplementedError(
            "Phase 2 task list implements the real LLMLingua-2 mBERT body; "
            "scaffold version 0-scaffold raises until that lands"
        )
