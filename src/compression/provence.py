# SPDX-License-Identifier: AGPL-3.0-or-later

"""NoOpProvenceAdapter — Phase 3 Layer 5 stub per spec 026 FR-021.

Provence is a retrieval-path compressor. Layer 5 fires only when a
retrieval surface is configured, and no retrieval spec is in scope
yet. The stub registers so the registry has the slot; the real adapter
lands when retrieval enters the design per Constitution §10.
"""

from __future__ import annotations

from src.compression.segments import CompressedSegment
from src.compression.trust_tier import refuse_tier_one


class NoOpProvenceAdapter:
    """Layer 5 stub. NotImplementedError until a retrieval spec ships."""

    COMPRESSOR_ID: str = "provence"
    COMPRESSOR_VERSION: str = "0-stub"

    def compress(
        self,
        payload: str,
        target_budget: int,
        trust_tier: str,
    ) -> CompressedSegment:
        refuse_tier_one(trust_tier)
        raise NotImplementedError(
            "Layer 5 Provence requires a retrieval surface; " "not in current Phase 3 specs"
        )
