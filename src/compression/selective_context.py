# SPDX-License-Identifier: AGPL-3.0-or-later

"""SelectiveContextCompressor — Phase 2 fallback scaffold per spec 026 FR-009.

Same Phase 2 master-switch gate as LLMLingua2mBERTCompressor. The
fallback role engages when LLMLingua-2 mBERT exceeds the latency
budget on a participant's traffic; the A/B harness lands at Phase 2
task time.
"""

from __future__ import annotations

import os

from src.compression.segments import CompressedSegment
from src.compression.trust_tier import refuse_tier_one


class SelectiveContextCompressor:
    """Phase 2 fallback. Scaffold in Phase 1."""

    COMPRESSOR_ID: str = "selective_context"
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
            "Phase 2 task list implements the real Selective Context body; "
            "scaffold version 0-scaffold raises until that lands"
        )
