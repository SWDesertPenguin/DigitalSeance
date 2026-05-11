# SPDX-License-Identifier: AGPL-3.0-or-later

"""NoOpCompressor — Phase 1 pass-through default per spec 026 FR-007.

Returns input verbatim with `output_tokens == source_tokens`. SC-006
asserts byte-identical output vs un-compressor-mediated dispatch.

NoOp is EXEMPT from the FR-014 tier-1 refusal: it produces no
compression artefact, so the protective rationale doesn't apply.
"""

from __future__ import annotations

from src.compression.segments import CompressedSegment


def _count_tokens(text: str) -> int:
    """Approximate token count — len(text) // 4 baseline.

    NoOp doesn't need provider-accurate counts; the value lands in
    `compression_log.source_tokens` and `output_tokens` (equal for
    NoOp) for telemetry only. Real compressors use the
    TokenizerAdapter per spec 026 FR-015.
    """
    return max(len(text) // 4, 0)


class NoOpCompressor:
    """Phase 1 default. Byte-identical to un-compressor-mediated dispatch."""

    COMPRESSOR_ID: str = "noop"
    COMPRESSOR_VERSION: str = "1"

    def compress(
        self,
        payload: str,
        target_budget: int,  # noqa: ARG002  -- NoOp ignores budget by design
        trust_tier: str,
    ) -> CompressedSegment:
        token_count = _count_tokens(payload)
        return CompressedSegment(
            output_text=payload,
            output_tokens=token_count,
            trust_tier=trust_tier,
            boundary_marker=None,
            compressor_id=self.COMPRESSOR_ID,
            compressor_version=self.COMPRESSOR_VERSION,
        )
