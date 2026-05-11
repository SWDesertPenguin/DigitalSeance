# SPDX-License-Identifier: AGPL-3.0-or-later

"""NoOpLayer6Adapter — Phase 3 Layer 6 stub per spec 026 FR-022 + SC-011.

Layer 6 hosts self-hosted soft-prompt / KV-cache methods (Activation
Beacon, ICAE, KV-cache compression). It applies ONLY to legs running
open-weight models the orchestrator controls (Ollama, vLLM). On
closed-API legs (Anthropic, OpenAI, Google), Layer 6 MUST be
structurally skipped without error — the dispatch path consults
`supports(provider)` before invoking `compress(...)`.

The real adapter lands in the local-model-support spec.
"""

from __future__ import annotations

from src.compression.segments import CompressedSegment
from src.compression.trust_tier import refuse_tier_one

_OPEN_WEIGHT_PROVIDERS: frozenset[str] = frozenset({"ollama", "vllm"})


class NoOpLayer6Adapter:
    """Layer 6 stub. NotImplementedError until local-model-support ships."""

    COMPRESSOR_ID: str = "layer6"
    COMPRESSOR_VERSION: str = "0-stub"

    @classmethod
    def supports(cls, provider: str) -> bool:
        """Return True iff `provider` is an open-weight leg.

        The dispatch path calls this BEFORE invoking `compress(...)`.
        Closed-API legs short-circuit to NoOp without error per SC-011.
        """
        return provider in _OPEN_WEIGHT_PROVIDERS

    def compress(
        self,
        payload: str,
        target_budget: int,
        trust_tier: str,
    ) -> CompressedSegment:
        refuse_tier_one(trust_tier)
        raise NotImplementedError(
            "Layer 6 requires local-model support (Ollama / vLLM with "
            "activation-tensor access); not in current Phase 3 specs"
        )
